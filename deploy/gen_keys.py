#!/usr/bin/env python3
"""
Genera las claves JWT (anon y service_role) compatibles con Supabase/PostgREST,
firmadas con el JWT_SECRET de tu .env.

Uso:
    JWT_SECRET="...tu secreto..." python deploy/gen_keys.py
    # o, dentro de deploy/ con el .env cargado:
    python deploy/gen_keys.py

La clave 'anon' es la que va en SUPABASE_KEY de la app.
La clave 'service_role' salta RLS: úsala solo para tareas administrativas.
"""
import os
import sys
import time

try:
    import jwt  # PyJWT
except ImportError:
    sys.exit("Falta PyJWT. Instala con:  pip install PyJWT")


def _leer_secreto():
    secret = os.environ.get("JWT_SECRET")
    if secret:
        return secret
    # Intentar leer de un .env junto a este script
    aquí = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(aquí, ".env")
    if os.path.exists(env_path):
        for línea in open(env_path, encoding="utf-8"):
            línea = línea.strip()
            if línea.startswith("JWT_SECRET="):
                return línea.split("=", 1)[1].strip()
    sys.exit("Define JWT_SECRET (variable de entorno o deploy/.env)")


def generar(secret, rol, años=10):
    ahora = int(time.time())
    payload = {
        "role": rol,
        "iss": "atlas-selfhosted",
        "iat": ahora,
        "exp": ahora + años * 365 * 24 * 3600,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def main():
    secret = _leer_secreto()
    if len(secret) < 32:
        sys.exit("JWT_SECRET debe tener al menos 32 caracteres.")
    anon = generar(secret, "anon")
    service = generar(secret, "service_role")
    print("\n=== Claves generadas (válidas 10 años) ===\n")
    print("SUPABASE_KEY (anon) — esta va en la app:\n" + anon + "\n")
    print("service_role (solo administración, NO en la app):\n" + service + "\n")


if __name__ == "__main__":
    main()
