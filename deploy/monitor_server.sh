#!/usr/bin/env bash
# ============================================================================
# monitor_server.sh — vigila la salud del servidor Hetzner (donde conviven
# el stack de Atlas y las apps que corren bajo Coolify) y avisa cuando algo
# se pone crítico: CPU, memoria, disco o contenedores caídos/reiniciando.
#
# Pensado para correr por cron cada 2-5 minutos. No hace nada "pesado": solo
# lee métricas del sistema y, si hace falta, manda una alerta.
#
# --- Instalación ------------------------------------------------------------
#
#   chmod +x monitor_server.sh
#   crontab -e
#
# Agregá esta línea (corre cada 5 minutos; ajustá el path real del archivo):
#
#   */5 * * * * /ruta/a/deploy/monitor_server.sh >> /ruta/a/deploy/monitor_cron.log 2>&1
#
# --- Canal de alertas --------------------------------------------------------
#
# El script SIEMPRE deja constancia en el logfile local (ver LOG_FILE abajo).
# Si además querés un aviso en el celular/Slack, definí la variable de
# entorno ALERT_WEBHOOK_URL (ej. en el crontab, o en un .env que "source"ees
# antes de llamar al script). Se manda un POST con un JSON simple que sirve
# tal cual para ntfy.sh, un webhook de Slack, o un endpoint propio.
#
# Opción A) ntfy.sh — gratis, sin registro, un solo curl para "suscribirte":
#   1. Elegí un nombre de canal difícil de adivinar, ej: atlas-alertas-x7q2
#   2. En tu celular: instalá la app ntfy y suscribite a ese canal
#      (o simplemente corré en tu PC: curl -s ntfy.sh/atlas-alertas-x7q2/json
#       para ver los mensajes en vivo).
#   3. En el servidor, antes de llamar al script (o en el crontab):
#        ALERT_WEBHOOK_URL="https://ntfy.sh/atlas-alertas-x7q2"
#
# Opción B) Bot de Telegram:
#   1. Hablá con @BotFather en Telegram, creá un bot y guardá el TOKEN.
#   2. Mandale un mensaje cualquiera a tu bot y visitá
#      https://api.telegram.org/bot<TOKEN>/getUpdates para obtener tu chat_id.
#   3. Usá como webhook:
#        ALERT_WEBHOOK_URL="https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<CHAT_ID>"
#
# Si ALERT_WEBHOOK_URL no está definida, las alertas solo quedan en el
# logfile con el prefijo "⚠️ ALERTA" — igual podés hacer
# `tail -f monitor_server.log` o meter un `grep ALERTA` en otro cron.
#
# --- Anti-spam ----------------------------------------------------------------
# Si una condición sigue mal ejecución tras ejecución, NO se re-avisa en cada
# corrida: se guarda la hora del último aviso por métrica en un STATE_FILE y
# solo se vuelve a avisar pasado el período de "enfriamiento" (COOLDOWN_MIN).
# Cuando la métrica vuelve a la normalidad, se resetea, así el próximo
# problema avisa de inmediato.
# ============================================================================

set -u

# --- Configuración (ajustable) -----------------------------------------------

# Carga: se considera "crítica" cuando el load average de 1 min supera
# núcleos_disponibles * LOAD_MULTIPLIER.
LOAD_MULTIPLIER="${LOAD_MULTIPLIER:-1.5}"

# Memoria: % de uso (sobre MemTotal, considerando MemAvailable) a partir del
# cual se avisa.
MEM_THRESHOLD_PCT="${MEM_THRESHOLD_PCT:-90}"

# Disco: % de uso del filesystem indicado en DISK_PATH a partir del cual se
# avisa. Cambiá DISK_PATH si los volúmenes de Docker viven en otro punto de
# montaje (ej: /var/lib/docker).
DISK_PATH="${DISK_PATH:-/}"
DISK_THRESHOLD_PCT="${DISK_THRESHOLD_PCT:-90}"

# Minutos de "enfriamiento" entre alertas repetidas de la misma condición.
COOLDOWN_MIN="${COOLDOWN_MIN:-15}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${LOG_FILE:-$SCRIPT_DIR/monitor_server.log}"
STATE_FILE="${STATE_FILE:-$SCRIPT_DIR/monitor_server.state}"
LOCK_FILE="${LOCK_FILE:-$SCRIPT_DIR/monitor_server.lock}"

# ALERT_WEBHOOK_URL: se toma del entorno si está definida (ver instrucciones
# arriba). No se le pone valor por defecto a propósito.
ALERT_WEBHOOK_URL="${ALERT_WEBHOOK_URL:-}"

COOLDOWN_SEG=$((COOLDOWN_MIN * 60))

# --- Utilidades ---------------------------------------------------------------

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >> "$LOG_FILE"
}

# Envía una alerta: siempre queda en el logfile; si hay webhook configurado,
# además intenta mandarlo por ahí (best-effort, no aborta el script si falla).
enviar_alerta() {
  local mensaje="$1"
  log "⚠️ ALERTA: $mensaje"

  if [ -n "$ALERT_WEBHOOK_URL" ]; then
    if command -v curl >/dev/null 2>&1; then
      local escapado
      escapado="$(printf '%s' "$mensaje" | sed 's/\\/\\\\/g; s/"/\\"/g')"
      # El body incluye "text" (Slack) y "message" (ntfy.sh); cada servicio
      # ignora la clave que no usa, así que un solo POST sirve para ambos.
      if ! curl -fsS -m 10 -X POST \
             -H "Content-Type: application/json" \
             -d "{\"text\":\"$escapado\",\"message\":\"$escapado\"}" \
             "$ALERT_WEBHOOK_URL" >/dev/null 2>>"$LOG_FILE"; then
        log "(no se pudo entregar la alerta por webhook; revisá ALERT_WEBHOOK_URL)"
      fi
    else
      log "(curl no está instalado; no se pudo enviar la alerta por webhook)"
    fi
  fi
}

# --- Estado de anti-spam (última hora de alerta por clave) -------------------

declare -A LAST_ALERT

cargar_estado() {
  [ -f "$STATE_FILE" ] || return 0
  local clave valor
  while IFS=$'\t' read -r clave valor; do
    [ -n "$clave" ] && LAST_ALERT["$clave"]="$valor"
  done < "$STATE_FILE"
}

guardar_estado() {
  # Se escribe primero a un archivo temporal y se mueve con `mv` (atómico
  # dentro del mismo filesystem) para no dejar el STATE_FILE truncado o
  # a medio escribir si el proceso se corta justo en este punto.
  local tmp clave
  tmp="$(mktemp "${STATE_FILE}.XXXXXX" 2>/dev/null)" || {
    log "Aviso: no se pudo crear archivo temporal para guardar el estado (${STATE_FILE})"
    return 0
  }
  for clave in "${!LAST_ALERT[@]}"; do
    printf '%s\t%s\n' "$clave" "${LAST_ALERT[$clave]}"
  done > "$tmp"
  mv -f "$tmp" "$STATE_FILE"
}

# evaluar_condicion CLAVE CONDICION_MALA(0/1) MENSAJE
# Si la condición es mala y ya pasó el cooldown desde la última alerta con
# esa clave, avisa y actualiza el timestamp. Si la condición se normalizó,
# limpia el estado para que el próximo problema avise de inmediato.
evaluar_condicion() {
  local clave="$1" es_mala="$2" mensaje="$3"
  local ahora
  ahora="$(date +%s)"

  if [ "$es_mala" -eq 1 ]; then
    local ultimo="${LAST_ALERT[$clave]:-0}"
    local transcurrido=$((ahora - ultimo))
    if [ "$transcurrido" -ge "$COOLDOWN_SEG" ]; then
      enviar_alerta "$mensaje"
      LAST_ALERT["$clave"]="$ahora"
    fi
  else
    unset 'LAST_ALERT[$clave]'
  fi
}

# --- Métricas -----------------------------------------------------------------

check_carga() {
  local nproc load1 umbral mala
  nproc="$(nproc 2>/dev/null || echo 1)"
  load1="$(awk '{print $1}' /proc/loadavg 2>/dev/null || echo 0)"
  umbral="$(awk -v n="$nproc" -v m="$LOAD_MULTIPLIER" 'BEGIN{printf "%.2f", n*m}')"

  if awk -v l="$load1" -v u="$umbral" 'BEGIN{exit !(l > u)}'; then
    mala=1
  else
    mala=0
  fi
  evaluar_condicion "carga" "$mala" \
    "Carga del servidor alta: load1=$load1 (umbral=$umbral, núcleos=$nproc)"
}

check_memoria() {
  [ -r /proc/meminfo ] || return 0
  local total disp usado_pct mala
  total="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"
  disp="$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)"
  if [ -z "$total" ] || [ -z "$disp" ] || [ "$total" -eq 0 ]; then
    return 0
  fi
  usado_pct="$(awk -v t="$total" -v d="$disp" 'BEGIN{printf "%.1f", (t-d)*100/t}')"

  if awk -v u="$usado_pct" -v th="$MEM_THRESHOLD_PCT" 'BEGIN{exit !(u > th)}'; then
    mala=1
  else
    mala=0
  fi
  evaluar_condicion "memoria" "$mala" \
    "Memoria alta: ${usado_pct}% en uso (umbral=${MEM_THRESHOLD_PCT}%)"
}

check_disco() {
  command -v df >/dev/null 2>&1 || return 0
  local uso_pct mala
  # Se toma el penúltimo campo (Capacity) contando desde el final, no una
  # posición fija: así no se rompe si el nombre del filesystem trae espacios.
  uso_pct="$(df -P "$DISK_PATH" 2>/dev/null | awk 'NR==2 {v=$(NF-1); gsub("%","",v); print v}')"
  [ -n "$uso_pct" ] || return 0

  if [ "$uso_pct" -gt "$DISK_THRESHOLD_PCT" ] 2>/dev/null; then
    mala=1
  else
    mala=0
  fi
  evaluar_condicion "disco" "$mala" \
    "Disco casi lleno en $DISK_PATH: ${uso_pct}% (umbral=${DISK_THRESHOLD_PCT}%)"
}

check_docker() {
  command -v docker >/dev/null 2>&1 || return 0

  local problemas=""

  # Contenedores marcados "unhealthy" por su propio healthcheck.
  local unhealthy
  unhealthy="$(docker ps -a --filter "health=unhealthy" --format '{{.Names}} ({{.Status}})' 2>/dev/null)"
  [ -n "$unhealthy" ] && problemas="${problemas}unhealthy: ${unhealthy}; "

  # Contenedores en bucle de reinicio.
  local restarting
  restarting="$(docker ps -a --filter "status=restarting" --format '{{.Names}} ({{.Status}})' 2>/dev/null)"
  [ -n "$restarting" ] && problemas="${problemas}reiniciando: ${restarting}; "

  # Contenedores que terminaron con código de salida distinto de 0
  # (se excluyen los "Exited (0)", que son salidas normales).
  local exited
  exited="$(docker ps -a --filter "status=exited" --format '{{.Names}}\t{{.Status}}' 2>/dev/null \
    | awk -F'\t' '$2 !~ /Exited \(0\)/ {print $1" ("$2")"}')"
  [ -n "$exited" ] && problemas="${problemas}salieron con error: ${exited}; "

  if [ -n "$problemas" ]; then
    evaluar_condicion "docker" 1 "Contenedores con problemas -> $problemas"
  else
    evaluar_condicion "docker" 0 ""
  fi
}

# --- Main -----------------------------------------------------------------

# Evita corridas solapadas (ej. si `docker ps` se cuelga porque el daemon
# está trabado y el cron dispara la corrida siguiente antes de que la
# anterior termine): sin esto, dos instancias leerían/escribirían el
# STATE_FILE al mismo tiempo y una pisaría los cambios de la otra.
if command -v flock >/dev/null 2>&1; then
  exec 200>"$LOCK_FILE"
  if ! flock -n 200; then
    log "Aviso: ya hay otra ejecución de monitor_server.sh en curso; se omite esta corrida."
    exit 0
  fi
fi

cargar_estado
check_carga
check_memoria
check_disco
check_docker
guardar_estado
