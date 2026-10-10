# ── ATLAS sistema · imagen para Coolify ─────────────────────────────────────
# Sustituye a Nixpacks (10/10/2026): aquella imagen pesaba ~2 GB, la mitad en
# herramientas de Nix, y guardaba las variables de entorno —claves incluidas—
# dentro de sus capas. Aquí las variables sólo existen al ejecutar.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5000

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

# /version es pública, de sólo lectura y no toca la base.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,os; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','5000')+'/version').read()" || exit 1

# Lo mismo que el Procfile, que es lo que arrancaba Nixpacks.
CMD ["sh", "-c", "gunicorn app:app --workers=2 --timeout=120 --bind=0.0.0.0:${PORT:-5000}"]
