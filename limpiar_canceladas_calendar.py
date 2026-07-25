#!/usr/bin/env python3
# ------------------------------------------------------------
# Desarrollado por Marco Antonio Posligua San Martín
# ------------------------------------------------------------
"""Borra de Google Calendar los eventos de sesiones que ya están en estado 'Cancelado'
en la base de datos. Limpia también el campo evento_calendar_id en Supabase.

Uso:
    python limpiar_canceladas_calendar.py            # ejecuta los borrados
    python limpiar_canceladas_calendar.py --dry-run  # solo muestra qué borraría
"""
import sys
from supabase_client import supabase
from google_calendar import eliminar_evento_calendar


def limpiar(dry_run: bool = False):
    print("=" * 60)
    print("Limpieza de sesiones canceladas en Google Calendar")
    if dry_run:
        print("MODO DRY-RUN (no se borra nada, solo se lista)")
    print("=" * 60)

    res = (
        supabase.table('sesiones')
        .select('id, fecha, hora_inicio, hora_fin, asignatura, tema_terapia, evento_calendar_id, estudiantes(apellidos, nombres)')
        .eq('estado', 'Cancelado')
        .not_.is_('evento_calendar_id', 'null')
        .execute()
    )

    sesiones = res.data or []
    print(f"Sesiones canceladas con evento aún en Calendar: {len(sesiones)}")

    ok = 0
    errores = 0
    for s in sesiones:
        est = s.get('estudiantes') or {}
        nombre_est = f"{est.get('apellidos', '')} {est.get('nombres', '')}".strip() or '(sin estudiante)'
        asignatura = s.get('asignatura') or s.get('tema_terapia') or 'Sesión'
        ev_id = s.get('evento_calendar_id')
        print(f"\nSesión {s['id']} | {s.get('fecha')} {str(s.get('hora_inicio') or '')[:5]}-{str(s.get('hora_fin') or '')[:5]} | {nombre_est[:40]} | {asignatura[:30]}")
        print(f"   Evento Calendar: {ev_id}")

        if dry_run:
            print("   (dry-run) se borraría del calendario y se limpiaría evento_calendar_id")
            continue

        try:
            borrado = eliminar_evento_calendar(ev_id)
            supabase.table('sesiones').update({'evento_calendar_id': None}).eq('id', s['id']).execute()
            if borrado:
                print("   OK - evento borrado del calendario")
                ok += 1
            else:
                # Si Calendar devolvió error (p.ej. evento ya no existe), igualmente limpiamos el id
                print("   evento_calendar_id limpiado (Calendar no confirmó borrado, posiblemente ya no existía)")
                ok += 1
        except Exception as e:
            print(f"   ERROR: {e}")
            errores += 1

    print("\n" + "=" * 60)
    print("RESUMEN:")
    print(f"   Procesadas: {ok}")
    print(f"   Errores:    {errores}")
    print("=" * 60)


if __name__ == '__main__':
    dry = '--dry-run' in sys.argv
    limpiar(dry_run=dry)
