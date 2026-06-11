"""Migración puntual: recalcula hash_mov de movimientos_cuenta con la nueva
fórmula (que incluye el saldo) para que la deduplicación siga funcionando con
los movimientos ya guardados. Ejecutar UNA vez tras desplegar el cambio:
    python migrar_hash_movimientos.py
"""
import hashlib
from supabase_client import supabase


def hash_movimiento(m):
    saldo = m.get('saldo')
    partes = [
        str(m.get('fecha') or ''),
        f"{float(m.get('monto') or 0):.2f}",
        (m.get('referencia') or '').strip().lower(),
    ]
    if saldo is not None:
        partes.append(f"{float(saldo):.2f}")
    else:
        partes.append((m.get('descripcion') or '').strip().lower()[:80])
    return hashlib.md5('|'.join(partes).encode('utf-8')).hexdigest()


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
