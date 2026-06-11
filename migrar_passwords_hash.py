"""Migración de seguridad: convierte a hash (werkzeug/pbkdf2) las contraseñas
almacenadas en texto plano en la tabla usuarios. Ejecutar UNA vez. Idempotente:
los registros que ya están hasheados no se tocan."""
from werkzeug.security import generate_password_hash
from supabase_client import supabase

PREFIJOS_HASH = ('pbkdf2:', 'scrypt:', 'argon2:')


def main():
    usuarios = supabase.table('usuarios').select('id,email,password_hash').execute().data or []
    print(f"{len(usuarios)} usuarios en la base")
    migrados = 0
    for u in usuarios:
        ph = u.get('password_hash') or ''
        if not ph or ph.startswith(PREFIJOS_HASH):
            continue
        supabase.table('usuarios').update(
            {'password_hash': generate_password_hash(ph)}).eq('id', u['id']).execute()
        print(f"  hasheado: {u.get('email')}")
        migrados += 1
    print(f"✔ {migrados} contraseñas migradas a hash; el resto ya estaba protegido.")


if __name__ == '__main__':
    main()
