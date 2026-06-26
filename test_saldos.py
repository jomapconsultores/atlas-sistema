# -*- coding: utf-8 -*-
"""Pruebas del saldo bancario: el saldo de la cuenta de ahorros (Liquidacion)
debe coincidir con el saldo final del modulo de Movimientos.

Ambos modulos calculan el saldo a partir de la MISMA cadena de saldos del banco
(saldo previo de cada movimiento = saldo - monto). Este test verifica que esa
coincidencia se mantenga, tanto con casos sinteticos (sin BD) como contra los
datos reales (si hay conexion a Supabase).

Uso:
    py test_saldos.py            # corre todo (incluye BD si esta disponible)
    py test_saldos.py --no-db    # solo la logica pura, sin tocar la BD

No modifica nada: solo lee (SELECT).
"""
import sys
from collections import Counter
from calendar import monthrange

from app import _ordenar_por_cadena_saldos, _saldo_cierre_movimientos


# --------------------------------------------------------------------------- #
# Replica EXACTA del calculo de saldo_final/inicial del modulo movimientos_cuenta
# (app.py, ruta /movimientos-cuenta). Si esa logica cambia, actualizar aqui.
# --------------------------------------------------------------------------- #
def movimientos_saldo_inicial_final(movs):
    movs = _ordenar_por_cadena_saldos(movs)
    con_saldo = [m for m in movs if m.get('saldo') is not None]
    saldo_inicial = saldo_final = None
    if con_saldo:
        saldos = Counter(round(m.get('saldo') or 0, 2) for m in con_saldo)
        previos = Counter(round((m.get('saldo') or 0) - (m.get('monto') or 0), 2) for m in con_saldo)
        fines = list((saldos - previos).elements())
        inicios = list((previos - saldos).elements())
        if len(fines) == 1 and len(inicios) == 1:
            saldo_final, saldo_inicial = fines[0], inicios[0]
        else:
            saldo_final = con_saldo[0].get('saldo')
            viejo = con_saldo[-1]
            saldo_inicial = round((viejo.get('saldo') or 0) - (viejo.get('monto') or 0), 2)
    return saldo_inicial, saldo_final


def _mov(fecha, monto, saldo, id_=None):
    return {'fecha': fecha, 'monto': monto, 'saldo': saldo, 'id': id_}


# --------------------------------------------------------------------------- #
# Pruebas de logica pura (sin BD)
# --------------------------------------------------------------------------- #
def test_cadena_completa_coincide():
    """Cadena limpia: liquidacion y movimientos dan el MISMO cierre."""
    # Saldo abre en 1000; -100 -> 900; +50 -> 950; -50 -> 900; +190 -> 1090
    movs = [
        _mov('2026-06-01', -100, 900, 1),
        _mov('2026-06-02',   50, 950, 2),
        _mov('2026-06-03',  -50, 900, 3),
        _mov('2026-06-04',  190, 1090, 4),
    ]
    _, mov_final = movimientos_saldo_inicial_final(list(movs))
    liq_cierre, _ = _saldo_cierre_movimientos(list(movs))
    assert round(mov_final, 2) == 1090.00, mov_final
    assert round(liq_cierre, 2) == 1090.00, liq_cierre
    assert round(mov_final, 2) == round(liq_cierre, 2)


def test_orden_de_filas_no_importa():
    """El resultado no debe depender del orden en que llegan las filas
    (es el bug que se corrigio: el id ordenaba mal entre subidas distintas)."""
    movs = [
        _mov('2026-06-01', -100, 900, 1),
        _mov('2026-06-02',   50, 950, 2),
        _mov('2026-06-03',  -50, 900, 3),
        _mov('2026-06-04',  190, 1090, 4),
    ]
    import itertools
    cierres = set()
    for perm in itertools.permutations(movs):
        c, _ = _saldo_cierre_movimientos(list(perm))
        cierres.add(round(c, 2))
    assert cierres == {1090.00}, cierres  # siempre el mismo cierre


def test_saldos_repetidos_euleriano():
    """La cuenta vuelve al mismo valor (saldo repetido) y aun asi se ordena
    bien siguiendo la cadena como camino euleriano."""
    # 500 -> +100=600 -> -100=500 -> +250=750
    movs = [
        _mov('2026-06-01', 100, 600, 1),
        _mov('2026-06-02', -100, 500, 2),
        _mov('2026-06-03', 250, 750, 3),
    ]
    _, mov_final = movimientos_saldo_inicial_final(list(movs))
    liq_cierre, _ = _saldo_cierre_movimientos(list(movs))
    assert round(mov_final, 2) == 750.00
    assert round(mov_final, 2) == round(liq_cierre, 2)


def test_cadena_incompleta_fallback_coincide():
    """Con un hueco (falta un movimiento intermedio) ambos caen al mismo
    fallback: el movimiento mas reciente del listado."""
    # Dos tramos sin enlace: ...->300 (tramo viejo) y 1000->1090 (tramo nuevo)
    movs = [  # llegan en orden fecha desc / id asc, como la query real
        _mov('2026-06-10',  90, 1090, 5),
        _mov('2026-06-09', 100, 1000, 4),
        _mov('2026-05-02', -50,  300, 2),
        _mov('2026-05-01',  20,  350, 1),
    ]
    _, mov_final = movimientos_saldo_inicial_final(list(movs))
    liq_cierre, _ = _saldo_cierre_movimientos(list(movs))
    assert round(mov_final, 2) == round(liq_cierre, 2), (mov_final, liq_cierre)


def test_un_solo_movimiento():
    movs = [_mov('2026-06-01', 467.46, 467.46, 1)]
    _, mov_final = movimientos_saldo_inicial_final(list(movs))
    liq_cierre, _ = _saldo_cierre_movimientos(list(movs))
    assert round(mov_final, 2) == 467.46
    assert round(mov_final, 2) == round(liq_cierre, 2)


def test_sin_movimientos():
    assert _saldo_cierre_movimientos([]) == (None, None)
    assert movimientos_saldo_inicial_final([]) == (None, None)


# --------------------------------------------------------------------------- #
# Verificacion contra la BD real (se omite si no hay conexion)
# --------------------------------------------------------------------------- #
def test_bd_real_coincide_mes_a_mes():
    """Para cada mes con datos: el saldo_banco de Liquidacion (acumulado hasta
    fin de mes) coincide con el saldo_final de Movimientos (ese mes), y el
    periodo cuadra (inicial + creditos - debitos = final)."""
    try:
        from app import _fetch_all, supabase, FECHA_MIN_ESTADO_CUENTA
        movs_all = _fetch_all(
            supabase.table('movimientos_cuenta').select('*')
            .gte('fecha', FECHA_MIN_ESTADO_CUENTA)
            .order('fecha', desc=True).order('id', desc=False)
        )
    except Exception as e:
        print(f"  (omitido: sin conexion a la BD -> {e})")
        return 'skip'

    if not movs_all:
        print("  (omitido: no hay movimientos en la BD)")
        return 'skip'

    meses = sorted({(m.get('fecha') or '')[:7] for m in movs_all})
    for ym in meses:
        anio, mes = int(ym[:4]), int(ym[5:7])
        _, ultimo_dia = monthrange(anio, mes)
        movs_mes = [m for m in movs_all if (m.get('fecha') or '')[:7] == ym]
        ini, fin = movimientos_saldo_inicial_final(movs_mes)

        movs_hasta = _fetch_all(
            supabase.table('movimientos_cuenta').select('saldo,monto,fecha')
            .not_.is_('saldo', 'null')
            .lte('fecha', f"{anio}-{mes:02d}-{ultimo_dia}")
            .order('fecha', desc=True).order('id', desc=False)
        )
        liq_cierre, _ = _saldo_cierre_movimientos(movs_hasta)

        assert fin is not None and liq_cierre is not None, ym
        assert abs(round(fin, 2) - round(liq_cierre, 2)) < 0.005, \
            f"{ym}: movimientos={fin} != liquidacion={liq_cierre}"

        # Cuadre del periodo
        cred = sum(m.get('monto', 0) or 0 for m in movs_mes if (m.get('monto') or 0) > 0)
        deb = sum(abs(m.get('monto', 0) or 0) for m in movs_mes if (m.get('monto') or 0) < 0)
        assert abs((ini + cred - deb) - fin) < 0.02, \
            f"{ym}: no cuadra: {ini}+{cred}-{deb} != {fin}"
        print(f"  {ym}: saldo_final={fin}  liquidacion={liq_cierre}  cuadre OK")
    return 'ok'


# --------------------------------------------------------------------------- #
# Runner minimo (no requiere pytest)
# --------------------------------------------------------------------------- #
def main():
    no_db = '--no-db' in sys.argv
    pruebas = [
        test_cadena_completa_coincide,
        test_orden_de_filas_no_importa,
        test_saldos_repetidos_euleriano,
        test_cadena_incompleta_fallback_coincide,
        test_un_solo_movimiento,
        test_sin_movimientos,
    ]
    if not no_db:
        pruebas.append(test_bd_real_coincide_mes_a_mes)

    fallos = 0
    for t in pruebas:
        try:
            r = t()
            estado = 'SKIP' if r == 'skip' else 'OK'
            print(f"[{estado}] {t.__name__}")
        except AssertionError as e:
            fallos += 1
            print(f"[FALLO] {t.__name__}: {e}")
        except Exception as e:
            fallos += 1
            print(f"[ERROR] {t.__name__}: {type(e).__name__}: {e}")

    print("-" * 60)
    if fallos:
        print(f"RESULTADO: {fallos} prueba(s) fallaron")
        sys.exit(1)
    print("RESULTADO: todas las pruebas pasaron")


if __name__ == '__main__':
    main()
