#!/usr/bin/env bash
# ============================================================================
# migrate_throttled.sh — corre cualquier comando "pesado" para la base de
# datos (dump, restore, migraciones grandes, VACUUM FULL, etc.) sin acaparar
# CPU/disco/red del servidor Hetzner, donde además corre Coolify con otras
# apps (procesos_CSC, marketing, etc.) que NO deben verse afectadas.
#
# Qué hace:
#   1. Revisa la carga del sistema (load average) ANTES de arrancar y se
#      niega a correr si el servidor ya está muy cargado.
#   2. Ejecuta el comando con `nice -n 19` (mínima prioridad de CPU) e
#      `ionice -c3` (clase "idle": solo usa disco cuando nadie más lo pide).
#   3. Si el comando incluye el marcador __PV__ y `pv` está instalado, lo
#      reemplaza por `pv` (con límite de banda si pediste --rate-limit) para
#      no saturar la red/disco al mover un dump grande por una tubería.
#   4. Registra hora de inicio, fin, duración y resultado en un logfile.
#
# Uso:
#   ./migrate_throttled.sh [opciones] "comando completo a ejecutar"
#
# Opciones:
#   --rate-limit TASA   Límite de transferencia para el tramo __PV__ del
#                        comando (ej: 5m = 5 MB/s, 500k = 500 KB/s).
#                        Necesita `pv` instalado (apt-get install pv).
#                        Si no está instalado, se avisa y se sigue sin límite.
#   --max-load N         Umbral de carga (load average de 1 min) a partir del
#                        cual el script se niega a arrancar. Por defecto:
#                        núcleos_disponibles * LOAD_THRESHOLD_MULTIPLIER
#                        (ver variables abajo).
#   --log ARCHIVO         Ruta del logfile (por defecto: migrate.log, junto
#                        a este script).
#   -h, --help            Muestra este mensaje.
#
# El comando se ejecuta con `bash -c`, así que podés usar pipes, comillas,
# variables de entorno, etc. tal como los escribirías en una terminal normal.
#
# ---------------------------------------------------------------------------
# EJEMPLO 1 — migración de datos completa (dump de Supabase + restore local),
# limitando la transferencia a 5 MB/s para no saturar la red del servidor
# mientras Coolify sirve otras apps:
#
#   ./migrate_throttled.sh --rate-limit 5m '
#     pg_dump "postgresql://postgres:PASS@db.naubddczohedvtywmmmy.supabase.co:5432/postgres" \
#             --no-owner --no-privileges --schema=public \
#     | __PV__ \
#     | docker compose exec -T db psql -U postgres -d atlas
#   '
#
# EJEMPLO 2 — solo el restore (ya tenés atlas_dump.sql local), sin límite de
# banda, solo con nice/ionice y chequeo de carga:
#
#   ./migrate_throttled.sh 'docker compose exec -T db psql -U postgres -d atlas < atlas_dump.sql'
#
# EJEMPLO 3 — cualquier otra tarea pesada de Postgres (ej. un VACUUM FULL o
# una migración grande con migrate.py), reusando el mismo throttling:
#
#   ./migrate_throttled.sh 'DATABASE_URL="postgres://postgres:PASS@localhost:5432/atlas" python migrate.py'
# ============================================================================

set -u

# --- Configuración (ajustable) ---------------------------------------------

# Multiplicador sobre la cantidad de núcleos para decidir cuándo la carga del
# servidor ya es "crítica" y no conviene arrancar nada nuevo encima.
# Con nproc=4 y multiplicador 1.5, el umbral por defecto es load1 > 6.0
LOAD_THRESHOLD_MULTIPLIER="${LOAD_THRESHOLD_MULTIPLIER:-1.5}"

# Prioridad de CPU (nice: -20 más prioridad ... 19 menos prioridad).
NICE_LEVEL="${NICE_LEVEL:-19}"

# Clase de I/O para ionice: 3 = "idle" (solo usa disco cuando nadie más lo
# necesita). Es la opción más segura para no competir con otros contenedores.
IONICE_CLASS="${IONICE_CLASS:-3}"

# Logfile por defecto: junto a este script.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${LOG_FILE:-$SCRIPT_DIR/migrate.log}"

# -----------------------------------------------------------------------------

RATE_LIMIT=""
MAX_LOAD_OVERRIDE=""
COMANDO=""

uso() {
  sed -n '2,60p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

while [ $# -gt 0 ]; do
  case "$1" in
    --rate-limit)
      RATE_LIMIT="${2:-}"
      shift 2
      ;;
    --max-load)
      MAX_LOAD_OVERRIDE="${2:-}"
      shift 2
      ;;
    --log)
      LOG_FILE="${2:-}"
      shift 2
      ;;
    -h|--help)
      uso
      exit 0
      ;;
    --)
      shift
      ;;
    *)
      if [ -z "$COMANDO" ]; then
        COMANDO="$1"
      else
        # Por si el usuario no puso comillas: unimos todo lo que sobre.
        COMANDO="$COMANDO $1"
      fi
      shift
      ;;
  esac
done

if [ -z "$COMANDO" ]; then
  echo "Error: falta el comando a ejecutar." >&2
  echo "Corré '$0 --help' para ver ejemplos de uso." >&2
  exit 1
fi

# --- 0. Evitar dos migraciones pesadas al mismo tiempo ----------------------
# Sin esto, dos ejecuciones simultáneas pasarían el chequeo de carga por
# separado (ninguna ve todavía el impacto de la otra) y terminarían corriendo
# dos tareas pesadas en paralelo, exactamente lo que este script busca evitar.

LOCK_FILE="${LOCK_FILE:-$SCRIPT_DIR/migrate.lock}"
if command -v flock >/dev/null 2>&1; then
  exec 200>"$LOCK_FILE"
  if ! flock -n 200; then
    echo "Error: ya hay otra ejecución de migrate_throttled.sh en curso" >&2
    echo "        (lock: $LOCK_FILE). Esperá a que termine antes de arrancar otra." >&2
    exit 3
  fi
else
  echo "Aviso: 'flock' no está disponible; no se puede garantizar que no corran" >&2
  echo "       dos migraciones al mismo tiempo. Instalalo (paquete util-linux) o" >&2
  echo "       asegurate manualmente de no lanzar ejecuciones simultáneas." >&2
fi

# --- 1. Chequeo de carga del sistema ----------------------------------------

NPROC="$(nproc 2>/dev/null || echo 1)"

if [ -n "$MAX_LOAD_OVERRIDE" ]; then
  UMBRAL_CARGA="$MAX_LOAD_OVERRIDE"
else
  UMBRAL_CARGA="$(awk -v n="$NPROC" -v m="$LOAD_THRESHOLD_MULTIPLIER" 'BEGIN{printf "%.2f", n*m}')"
fi

LOAD1="$(awk '{print $1}' /proc/loadavg 2>/dev/null || echo 0)"

if awk -v l="$LOAD1" -v u="$UMBRAL_CARGA" 'BEGIN{exit !(l > u)}'; then
  echo "Error: la carga actual del servidor (load1=$LOAD1) supera el umbral" >&2
  echo "        de seguridad ($UMBRAL_CARGA, con $NPROC núcleos detectados)." >&2
  echo "        No se arranca para no afectar otros servicios (Coolify, etc.)." >&2
  echo "        Reintentá más tarde, o forzá con --max-load <número más alto>." >&2
  exit 2
fi

# --- 2. Armar el comando con el marcador __PV__ reemplazado -----------------

if command -v pv >/dev/null 2>&1; then
  if [ -n "$RATE_LIMIT" ]; then
    PV_SUSTITUTO="pv -L $RATE_LIMIT"
  else
    PV_SUSTITUTO="pv"
  fi
else
  if [ -n "$RATE_LIMIT" ]; then
    echo "Aviso: pediste --rate-limit pero 'pv' no está instalado; se sigue" >&2
    echo "       SIN límite de banda. Instalalo con: apt-get install -y pv" >&2
  fi
  PV_SUSTITUTO="cat"
fi

CMD_FINAL="${COMANDO//__PV__/$PV_SUSTITUTO}"

# --- 3. Armar el prefijo nice/ionice (ionice es opcional) -------------------

PREFIJO=(nice -n "$NICE_LEVEL")
if command -v ionice >/dev/null 2>&1; then
  PREFIJO=(ionice -c "$IONICE_CLASS" "${PREFIJO[@]}")
else
  echo "Aviso: 'ionice' no está disponible en este sistema; se corre solo con" >&2
  echo "       nice (prioridad de CPU baja), sin prioridad de I/O reducida." >&2
fi

# --- 4. Ejecutar, cronometrar y loguear -------------------------------------

INICIO_EPOCH="$(date +%s)"
INICIO_HUMANO="$(date '+%Y-%m-%d %H:%M:%S')"

echo "[$INICIO_HUMANO] INICIO — nice=$NICE_LEVEL ionice_c=$IONICE_CLASS rate_limit=${RATE_LIMIT:-ninguno}" >> "$LOG_FILE"
echo "[$INICIO_HUMANO] comando: $COMANDO" >> "$LOG_FILE"
echo "Arrancando (load1=$LOAD1, umbral=$UMBRAL_CARGA)... log en: $LOG_FILE"

set +e
"${PREFIJO[@]}" bash -c "$CMD_FINAL"
RC=$?
set -e

FIN_EPOCH="$(date +%s)"
FIN_HUMANO="$(date '+%Y-%m-%d %H:%M:%S')"
DURACION=$((FIN_EPOCH - INICIO_EPOCH))

if [ "$RC" -eq 0 ]; then
  RESULTADO="OK"
else
  RESULTADO="ERROR (código $RC)"
fi

echo "[$FIN_HUMANO] FIN — resultado: $RESULTADO — duración: ${DURACION}s" >> "$LOG_FILE"
echo "Terminado: $RESULTADO — duración: ${DURACION}s (detalle en $LOG_FILE)"

exit "$RC"
