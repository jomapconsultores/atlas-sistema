#!/usr/bin/env python3
# ------------------------------------------------------------
# Desarrollado por Marco Antonio Posligua San Martín
# ------------------------------------------------------------
"""Script para corregir TODAS las sesiones en Google Calendar"""
from supabase_client import supabase
from google_calendar import crear_o_actualizar_evento_calendar

def fix_all_sessions():
    print("=" * 60)
    print("Corrigiendo todas las sesiones en Google Calendar...")
    print("=" * 60)
    
    sesiones = supabase.table('sesiones').select('*, estudiantes(apellidos, nombres)').execute()
    
    total = len(sesiones.data)
    print(f"Total de sesiones encontradas: {total}")
    
    ok = 0
    errores = 0
    
    for s in sesiones.data:
        try:
            est = s.get('estudiantes', {})
            nombre_est = f"{est.get('apellidos', '')} {est.get('nombres', '')}".strip()
            if not nombre_est:
                nombre_est = f"Estudiante {s.get('estudiante_id', '')}"
            
            encargado = s.get('encargado_apertura', '').strip()
            if not encargado:
                encargado = 'Por definir'
            
            evento_id_existente = s.get('evento_calendar_id')
            
            print(f"\n📅 Sesión {s['id']}: {s['fecha']} - {nombre_est[:30]}")
            print(f"   Encargado actual en sistema: {encargado}")
            
            nuevo_id = crear_o_actualizar_evento_calendar({
                'asignatura': (s.get('asignatura') or s.get('tema_terapia') or 'Sesión')[:50],
                'profesor': (s.get('profesor_terapeuta', 'Profesor'))[:50],
                'estudiantes': nombre_est[:100],
                'fecha': str(s['fecha']),
                'hora_inicio': str(s['hora_inicio'])[:5],
                'hora_fin': str(s['hora_fin'])[:5],
                'encargado_apertura': encargado
            }, evento_id_existente)
            
            if nuevo_id:
                supabase.table('sesiones').update({'evento_calendar_id': nuevo_id}).eq('id', s['id']).execute()
                print(f"   ✅ OK - Encargado: {encargado}")
                ok += 1
            else:
                print(f"   ❌ ERROR")
                errores += 1
        except Exception as e:
            print(f"   ❌ ERROR: {str(e)}")
            errores += 1
    
    print("\n" + "=" * 60)
    print(f"RESUMEN:")
    print(f"   ✅ Correctas: {ok}")
    print(f"   ❌ Errores: {errores}")
    print("=" * 60)

if __name__ == '__main__':
    fix_all_sessions()