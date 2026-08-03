#!/usr/bin/env python3
# ------------------------------------------------------------
# Desarrollado por Marco Antonio Posligua San Martín
# ------------------------------------------------------------
"""Revisa las sesiones canceladas y detecta las que quedaron mal:

  (A) Sesiones en estado 'Cancelado' que siguen arrastrando dinero
      (valor_total, valor_pagar_docente o valor_atlas distintos de 0).
      La regla es $0 para todos, así que esto se corrige.

  (B) Sesiones en estado 'Cancelado-Pagado', comparadas con la regla vigente:
      al estudiante no se le cobra nada y Atlas asume el pago reducido de quien
      iba a darla. Las guardadas antes del cambio siguen cobrándole al
      estudiante (y las de terapia, pagando el 40.18% en vez de la mitad):
      --recalcular las pone al día.
      Decidir cuáles debían ser 'Cancelado' a secas sigue siendo manual.

  (C) Con --estudiante NOMBRE: desglosa por qué ese estudiante aparece en el
      «Recordatorio de cobros» del panel de inicio (qué sesiones se le están
      cobrando, cuáles son 'Cancelado-Pagado' y cómo sale el saldo).

Uso:
    python revisar_canceladas.py                    # solo informa
    python revisar_canceladas.py --corregir         # pone en $0 las del caso (A)
    python revisar_canceladas.py --recalcular       # reaplica la regla al caso (B)
    python revisar_canceladas.py --estudiante ludizaca   # caso (C)
    python revisar_canceladas.py --mes 7 --anio 2026    # acota el período
"""
import argparse
from calendar import monthrange

from supabase_client import supabase
# La regla de dinero vive en un solo sitio (app.py); este script la reutiliza
# en vez de tener su propia copia que se desincronice.
from app import valor_base_sesion, valores_por_estado

CAMPOS_DINERO = ('valor_total', 'valor_pagar_docente', 'valor_atlas')


def _fetch_all(builder, page_size=1000):
    """Trae TODAS las filas paginando: PostgREST corta en 1000 por petición."""
    filas, offset = [], 0
    while True:
        lote = builder.range(offset, offset + page_size - 1).execute().data or []
        filas.extend(lote)
        if len(lote) < page_size:
            return filas
        offset += page_size


def _rango(mes, anio):
    if not (mes and anio):
        return None, None
    _, ultimo = monthrange(anio, mes)
    return f"{anio}-{mes:02d}-01", f"{anio}-{mes:02d}-{ultimo}"


def _consulta(estado, desde, hasta):
    q = supabase.table('sesiones').select(
        'id,fecha,hora_inicio,hora_fin,tipo_sesion,asignatura,tema_terapia,'
        'profesor_terapeuta,horas,precio_hora,cobro_por_sesion,'
        'valor_total,valor_pagar_docente,valor_atlas,'
        'estudiantes(apellidos,nombres)'
    ).eq('estado', estado).order('fecha', desc=True)
    if desde:
        q = q.gte('fecha', desde).lte('fecha', hasta)
    return _fetch_all(q)


def _linea(s):
    est = s.get('estudiantes') or {}
    nombre = f"{est.get('apellidos', '')} {est.get('nombres', '')}".strip() or '(sin estudiante)'
    detalle = s.get('asignatura') or s.get('tema_terapia') or s.get('tipo_sesion') or 'Sesión'
    return (f"  #{s['id']:<6} {s.get('fecha')} "
            f"{str(s.get('hora_inicio') or '')[:5]}-{str(s.get('hora_fin') or '')[:5]}  "
            f"{nombre[:28]:<28} {str(detalle)[:22]:<22} "
            f"{s.get('profesor_terapeuta') or '-':<22} "
            f"cobra ${s.get('valor_total') or 0:>8.2f}  "
            f"paga ${s.get('valor_pagar_docente') or 0:>7.2f}")


def explicar_deuda(patron):
    """Reproduce el «Recordatorio de cobros» del panel de inicio para los
    estudiantes cuyo nombre contenga `patron`, y desglosa de dónde sale el saldo.

    El panel usa la misma cuenta que el Módulo 3:
        saldo = cobrar - (pagado - devuelto)
    donde `cobrar` suma el valor de las sesiones en 'Realizado' y
    'Cancelado-Pagado'. Una sesión 'Cancelado' NO suma; una 'Cancelado-Pagado'
    SÍ se le cobra completa al estudiante, que es la causa habitual de que
    alguien siga apareciendo con deuda por una sesión que no se dio.
    """
    patron_norm = (patron or '').strip().lower()
    estudiantes = _fetch_all(supabase.table('estudiantes').select('id,nombres,apellidos,activo'))
    coinciden = [e for e in estudiantes
                 if patron_norm in f"{e.get('apellidos','')} {e.get('nombres','')}".lower()]

    print("=" * 118)
    print(f"Deuda del panel de inicio — estudiantes que coinciden con «{patron}»: {len(coinciden)}")
    print("=" * 118)
    if not coinciden:
        print("  Ningún estudiante coincide. Revisa cómo está escrito el nombre.")
        return

    for e in coinciden:
        nombre = f"{e.get('apellidos','')} {e.get('nombres','')}".strip()
        activo = 'activo' if e.get('activo') else 'INACTIVO (no sale en el panel)'
        print(f"\n── {nombre}  (id {e['id']}, {activo})")

        ses = _fetch_all(supabase.table('sesiones').select(
            'id,fecha,estado,tipo_sesion,asignatura,tema_terapia,profesor_terapeuta,valor_total'
        ).eq('estudiante_id', e['id']).order('fecha'))
        pagos = _fetch_all(supabase.table('pagos').select('id,fecha_pago,monto')
                           .eq('estudiante_id', e['id']).order('fecha_pago'))
        try:
            devs = _fetch_all(supabase.table('devoluciones').select('id,fecha,monto,sesion_id')
                              .eq('estudiante_id', e['id']).order('fecha'))
        except Exception:
            devs = []

        cuentan = [s for s in ses if s.get('estado') in ('Realizado', 'Cancelado-Pagado')]
        no_cuentan = [s for s in ses if s.get('estado') not in ('Realizado', 'Cancelado-Pagado')]
        cobrar = round(sum(float(s.get('valor_total') or 0) for s in cuentan), 2)
        pagado = round(sum(float(p.get('monto') or 0) for p in pagos), 2)
        devuelto = round(sum(float(d.get('monto') or 0) for d in devs), 2)
        saldo = round(cobrar - (pagado - devuelto), 2)

        print(f"   Sesiones que SÍ se le cobran ({len(cuentan)}):")
        for s in cuentan:
            det = s.get('asignatura') or s.get('tema_terapia') or s.get('tipo_sesion') or '-'
            aviso = '   ← cancelada, pero se le cobra igual' if s.get('estado') == 'Cancelado-Pagado' else ''
            print(f"     #{s['id']:<6} {s.get('fecha')}  {str(s.get('estado')):<17} "
                  f"{str(det)[:20]:<20} ${float(s.get('valor_total') or 0):>8.2f}{aviso}")
        if not cuentan:
            print("     (ninguna)")

        if no_cuentan:
            print(f"   Sesiones que NO se le cobran ({len(no_cuentan)}):")
            for s in no_cuentan:
                print(f"     #{s['id']:<6} {s.get('fecha')}  {str(s.get('estado')):<17} "
                      f"${float(s.get('valor_total') or 0):>8.2f}")

        print(f"   Pagos ({len(pagos)}): ${pagado:.2f}   ·   Devoluciones ({len(devs)}): ${devuelto:.2f}")
        print(f"   SALDO = {cobrar:.2f} - ({pagado:.2f} - {devuelto:.2f}) = ${saldo:.2f}"
              f"{'  → APARECE en el panel' if saldo > 0 else '  → no aparece'}")

        canc_pag = [s for s in cuentan if s.get('estado') == 'Cancelado-Pagado'
                    and float(s.get('valor_total') or 0) > 0]
        if saldo > 0 and canc_pag:
            monto = round(sum(float(s.get('valor_total') or 0) for s in canc_pag), 2)
            print(f"   ⚠ ${monto:.2f} de esa deuda vienen de {len(canc_pag)} sesión(es) "
                  f"'Cancelado-Pagado' que todavía tienen el cobro viejo.")
            print(f"     Ya no debe cobrarse: corre --recalcular y el saldo baja a "
                  f"${round(saldo - monto, 2):.2f}.")

    print("\n" + "=" * 118)


def revisar(corregir=False, recalcular=False, mes=None, anio=None):
    desde, hasta = _rango(mes, anio)
    periodo = f"{desde} a {hasta}" if desde else "todo el histórico"
    print("=" * 118)
    print(f"Revisión de sesiones canceladas — período: {periodo}")
    print("=" * 118)

    # ---- (A) Canceladas que todavía tienen dinero -------------------------
    canceladas = _consulta('Cancelado', desde, hasta)
    sucias = [s for s in canceladas
              if any(round(float(s.get(c) or 0), 2) != 0 for c in CAMPOS_DINERO)]

    print(f"\n(A) Sesiones 'Cancelado': {len(canceladas)} · con dinero pendiente de limpiar: {len(sucias)}")
    if sucias:
        print("    Deberían estar en $0 (no se cobra al estudiante ni se paga a nadie):")
        for s in sucias:
            print(_linea(s))
    if sucias and corregir:
        ok = err = 0
        for s in sucias:
            try:
                supabase.table('sesiones').update(
                    {'valor_total': 0, 'valor_pagar_docente': 0, 'valor_atlas': 0}
                ).eq('id', s['id']).execute()
                ok += 1
            except Exception as e:
                print(f"    ERROR en #{s['id']}: {e}")
                err += 1
        print(f"    → corregidas: {ok} · con error: {err}")
    elif sucias:
        print("    → vuelve a ejecutar con --corregir para ponerlas en $0")

    # ---- (B) Cancelado-Pagado: comparar con la regla vigente ---------------
    canc_pag = _consulta('Cancelado-Pagado', desde, hasta)
    total_pagado = round(sum(float(s.get('valor_pagar_docente') or 0) for s in canc_pag), 2)
    print(f"\n(B) Sesiones 'Cancelado-Pagado': {len(canc_pag)} · se pagan ${total_pagado:.2f} en total")
    print("    Revísalas: las que en realidad no debían pagarse hay que pasarlas")
    print("    a 'Cancelado' desde el Módulo 2 (así quedan en $0 automáticamente).")

    desactualizadas = []
    for s in canc_pag:
        horas = s.get('horas', 1) or 1
        tipo = s.get('tipo_sesion', 'clase')
        base = valor_base_sesion(s, horas)
        # En terapia el pago sale de la tarifa. Si no se puede reconstruir
        # (precio_hora vacío y valor_total ya en cero) recalcular la dejaría en
        # $0 sin remedio, así que se avisa y no se toca.
        if not base and tipo in ('terapia', 'ambos'):
            print(_linea(s) + '  ⚠ sin tarifa recuperable: revísala a mano')
            continue
        cobro_ok, pago_ok, atlas_ok = valores_por_estado('Cancelado-Pagado', tipo, horas, base)
        cobro_hoy = round(float(s.get('valor_total') or 0), 2)
        pago_hoy = round(float(s.get('valor_pagar_docente') or 0), 2)
        marca = ''
        if (cobro_hoy, pago_hoy) != (cobro_ok, pago_ok):
            desactualizadas.append((s, cobro_ok, pago_ok, atlas_ok))
            marca = f'  ⚠ debería cobrar ${cobro_ok:.2f} y pagar ${pago_ok:.2f}'
        print(_linea(s) + marca)

    if desactualizadas:
        de_mas_est = round(sum(float(s.get('valor_total') or 0) - c
                               for s, c, _, _ in desactualizadas), 2)
        de_mas_doc = round(sum(float(s.get('valor_pagar_docente') or 0) - p
                               for s, _, p, _ in desactualizadas), 2)
        print(f"\n    {len(desactualizadas)} no siguen la regla vigente: se están "
              f"cobrando ${de_mas_est:.2f} de más a estudiantes y pagando "
              f"${de_mas_doc:.2f} de más a docentes/psicólogos.")
        if recalcular:
            ok = err = 0
            for s, cobro_ok, pago_ok, atlas_ok in desactualizadas:
                try:
                    supabase.table('sesiones').update(
                        {'valor_total': cobro_ok, 'valor_pagar_docente': pago_ok,
                         'valor_atlas': atlas_ok}
                    ).eq('id', s['id']).execute()
                    ok += 1
                except Exception as e:
                    print(f"    ERROR en #{s['id']}: {e}")
                    err += 1
            print(f"    → recalculadas: {ok} · con error: {err}")
        else:
            print("    → vuelve a ejecutar con --recalcular para ponerlas al día")

    print("\n" + "=" * 118)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--corregir', action='store_true',
                   help="pone en $0 las sesiones 'Cancelado' que aún tienen importes")
    p.add_argument('--recalcular', action='store_true',
                   help="reaplica la regla de pago a las 'Cancelado-Pagado' desactualizadas")
    p.add_argument('--estudiante', metavar='NOMBRE',
                   help='explica por qué ese estudiante aparece con deuda en el panel de inicio')
    p.add_argument('--mes', type=int, help='mes a revisar (1-12)')
    p.add_argument('--anio', type=int, help='año a revisar')
    a = p.parse_args()
    if bool(a.mes) != bool(a.anio):
        p.error('--mes y --anio se usan juntos')
    if a.estudiante:
        explicar_deuda(a.estudiante)
    else:
        revisar(corregir=a.corregir, recalcular=a.recalcular, mes=a.mes, anio=a.anio)
