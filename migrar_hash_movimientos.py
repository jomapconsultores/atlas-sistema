"""Migración puntual: recalcula hash_mov de movimientos_cuenta con la nueva
fórmula (que incluye el saldo) para que la deduplicación siga funcionando con
los movimientos ya guardados. Ejecutar UNA vez tras desplegar el cambio:
    python migrar_hash_movimientos.py
"""
import hashlib
from supabase_client import supabase


def hash_movimiento(m):
    saldo = m.get('saldo')
    base = '|'.join([
        str(m.get('fecha') or ''),
        f"{float(m.get('monto') or 0):.2f}",
        (m.get('descripcion') or '').strip().lower()[:80],
        (m.get('referencia') or '').strip().lower(),
        f"{float(saldo):.2f}" if saldo is not None else ''
    ])
    return hashlib.md5(base.encode('utf-8')).hexdigest()


def main():
    rows = supabase.table('movimientos_cuenta').select(
        'id,fecha,monto,descripcion,referencia,saldo,hash_mov').execute().data or []
    print(f"{len(rows)} movimientos en la base")
    cambiados = 0
    for r in rows:
        nuevo = hash_movimiento(r)
        if nuevo != r.get('hash_mov'):
            try:
                supabase.table('movimientos_cuenta').update({'hash_mov': nuevo}).eq('id', r['id']).execute()
                cambiados += 1
            except Exception as e:
                print(f"  ! id {r['id']}: {e}")
    print(f"✔ {cambiados} hashes actualizados a la nueva fórmula (con saldo).")


if __name__ == '__main__':
    main()
