#!/usr/bin/env bash
# ------------------------------------------------------------
# Respaldo diario de la base de Atlas.
#
# Sirve para las dos épocas: apuntando DATABASE_URL a Supabase (hoy) o al
# Postgres auto-alojado (después de la mudanza). Es el mismo pg_dump.
#
# Por qué existe: el proyecto Supabase está en plan Free y NO tiene backups
# ("No backups" en su panel), y el Postgres del servidor tampoco se respalda
# solo. Hoy, un DROP TABLE por error o un disco muerto se lleva el historial
# completo de sesiones, pagos y marcaciones.
#
#   Uso manual:
#     DATABASE_URL="postgresql://postgres:PASS@db.PROYECTO.supabase.co:5432/postgres" \
#         deploy/backup.sh /ruta/a/backups
#
#   En cron (diario a las 03:15), con la clave en un archivo solo tuyo:
#     15 3 * * * . /root/atlas.env && /ruta/repo/deploy/backup.sh /var/backups/atlas >> /var/log/atlas-backup.log 2>&1
#
# Un backup que nadie restauró no es un backup: una vez al mes, levanta el
# último .sql.gz en una base vacía y entra a mirar que estén los datos.
# ------------------------------------------------------------
set -euo pipefail

DESTINO="${1:-${BACKUP_DIR:-/var/backups/atlas}}"
RETENCION_DIAS="${RETENCION_DIAS:-30}"
# Tamaño mínimo creíble para un dump de Atlas. Un archivo por debajo de esto
# es casi seguro un dump fallido (error de auth, base vacía): se avisa fuerte
# en vez de dejar un archivo inútil ocupando el turno del día.
MINIMO_BYTES="${MINIMO_BYTES:-51200}"

if [ -z "${DATABASE_URL:-}" ]; then
    echo "[X] Define DATABASE_URL con la cadena de conexión de la base." >&2
    exit 1
fi
command -v pg_dump >/dev/null || { echo "[X] Falta pg_dump (paquete postgresql-client)." >&2; exit 1; }

mkdir -p "$DESTINO"
FECHA="$(date +%Y%m%d_%H%M)"
ARCHIVO="$DESTINO/atlas_${FECHA}.sql.gz"
PARCIAL="$ARCHIVO.parcial"

echo "▶ $(date '+%Y-%m-%d %H:%M:%S')  volcando a $ARCHIVO"

# Se escribe a .parcial y se renombra al final: si el volcado se corta a la
# mitad (red, disco lleno, servidor reiniciado), no queda un archivo con
# nombre de backup bueno que parezca válido en la lista.
if ! pg_dump "$DATABASE_URL" --no-owner --no-privileges --schema=public | gzip -9 > "$PARCIAL"; then
    rm -f "$PARCIAL"
    echo "[X] pg_dump falló: no se generó respaldo." >&2
    exit 1
fi

TAMANO=$(wc -c < "$PARCIAL")
if [ "$TAMANO" -lt "$MINIMO_BYTES" ]; then
    rm -f "$PARCIAL"
    echo "[X] El volcado pesa $TAMANO bytes, menos del mínimo de $MINIMO_BYTES: se descarta." >&2
    exit 1
fi

mv "$PARCIAL" "$ARCHIVO"
echo "✔ Respaldo listo: $ARCHIVO ($(du -h "$ARCHIVO" | cut -f1))"

# Retención: se borran los viejos DESPUÉS de confirmar que el de hoy existe,
# nunca antes. Si el volcado falla, arriba ya se salió y no se toca nada:
# quedarse con backups viejos es infinitamente mejor que quedarse sin ninguno.
BORRADOS=$(find "$DESTINO" -maxdepth 1 -name 'atlas_*.sql.gz' -mtime "+$RETENCION_DIAS" -print -delete | wc -l)
[ "$BORRADOS" -gt 0 ] && echo "  (se borraron $BORRADOS respaldos de más de $RETENCION_DIAS días)"

echo "  quedan $(find "$DESTINO" -maxdepth 1 -name 'atlas_*.sql.gz' | wc -l) respaldos en $DESTINO"
