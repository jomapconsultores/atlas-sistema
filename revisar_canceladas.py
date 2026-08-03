#!/usr/bin/env python3
# ------------------------------------------------------------
# Desarrollado por Marco Antonio Posligua San Martín
# ------------------------------------------------------------
"""Revisa las sesiones canceladas y detecta las que quedaron mal:

  (A) Sesiones en estado 'Cancelado' que siguen arrastrando dinero
      (valor_total, valor_pagar_docente o valor_atlas distintos de 0).
      La regla es $0 para todos, así que esto se corrige.

  (B) Sesiones en estado 'Cancelado-Pagado', listadas con lo que le están
      pagando al docente/psicólogo y con lo que les tocaría según la regla
      vigente. Las de terapia guardadas antes del cambio siguen con el 40.18%
      completo en vez de la mitad: --recalcular las pone al día.
      Decidir cuáles debían ser 'Cancelado' a secas sigue siendo manual.

Uso:
    python revisar_canceladas.py                    # solo informa
    python revisar_canceladas.py --corregir         # pone en $0 las del caso (A)
    python revisar_canceladas.py --recalcular       # reaplica la regla al caso (B)
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
        _, pago_ok, atlas_ok = valores_por_estado(
            'Cancelado-Pagado', s.get('tipo_sesion', 'clase'), horas,
            valor_base_sesion(s, horas))
        pago_hoy = round(float(s.get('valor_pagar_docente') or 0), 2)
        marca = ''
        if pago_hoy != pago_ok:
            desactualizadas.append((s, pago_ok, atlas_ok))
            marca = f'  ⚠ debería pagar ${pago_ok:.2f}'
        print(_linea(s) + marca)

    if desactualizadas:
        dif = round(sum(float(s.get('valor_pagar_docente') or 0) - p
                        for s, p, _ in desactualizadas), 2)
        print(f"\n    {len(desactualizadas)} no siguen la regla vigente "
              f"(se están pagando ${dif:.2f} de más).")
        if recalcular:
            ok = err = 0
            for s, pago_ok, atlas_ok in desactualizadas:
                try:
                    supabase.table('sesiones').update(
                        {'valor_pagar_docente': pago_ok, 'valor_atlas': atlas_ok}
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
    p.add_argument('--mes', type=int, help='mes a revisar (1-12)')
    p.add_argument('--anio', type=int, help='año a revisar')
    a = p.parse_args()
    if bool(a.mes) != bool(a.anio):
        p.error('--mes y --anio se usan juntos')
    revisar(corregir=a.corregir, recalcular=a.recalcular, mes=a.mes, anio=a.anio)
