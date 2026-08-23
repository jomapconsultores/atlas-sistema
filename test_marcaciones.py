# -*- coding: utf-8 -*-
# ------------------------------------------------------------
# Desarrollado por Marco Antonio Posligua San Martín
# ------------------------------------------------------------
"""Pruebas del modulo de asistencia: dias exigidos del mes y correccion de
marcaciones.

Cubre las dos cosas que tocan el sueldo de una persona y no se ven a simple
vista en la pantalla:

  1. Los dias exigidos salen del calendario real (lunes a viernes menos
     feriados) y no de un numero fijo. Con 22 dias fijos, agosto de 2026 —que
     solo tiene 20 trabajables— le descontaba 43.55 dolares a quien no habia
     faltado un solo dia.
  2. Una correccion de hora tiene que caber en su dia: sin solapar otro tramo
     y sin dejar dos «en curso» a la vez, o las horas dejan de cuadrar.

Uso:
    py test_marcaciones.py

No toca la base: los feriados y las marcaciones se inyectan a mano.
"""
import sys

import app

# Feriados de prueba, en lugar de la consulta a la tabla.
FERIADOS = {
    (2026, 8): {'2026-08-10'},          # Primer Grito de Independencia (lunes)
    (2026, 7): set(),
    (2026, 11): {'2026-11-02', '2026-11-03'},
}
app._feriados_mes = lambda anio, mes: FERIADOS.get((anio, mes), set())

fallos = []


def igual(etiqueta, obtenido, esperado):
    ok = abs(obtenido - esperado) < 0.01 if isinstance(esperado, float) else obtenido == esperado
    print(('  OK   ' if ok else '  FALLA ') + etiqueta + ': ' + repr(obtenido) +
          ('' if ok else ' (esperaba ' + repr(esperado) + ')'))
    if not ok:
        fallos.append(etiqueta)


def rechaza(etiqueta, obtenido, fragmento):
    """El validador tiene que devolver un error, y que hable de lo que toca."""
    ok = obtenido is not None and fragmento.lower() in obtenido.lower()
    print(('  OK   ' if ok else '  FALLA ') + etiqueta + ': ' + repr(obtenido))
    if not ok:
        fallos.append(etiqueta)


# ============================================================
# 1. Dias exigidos del mes
# ============================================================
print('== Dias trabajables del mes ==')
igual('agosto 2026 (21 de lunes a viernes, 1 feriado)', app._dias_habiles_mes(2026, 8), 20)
igual('julio 2026 (sin feriados)', app._dias_habiles_mes(2026, 7), 23)
igual('noviembre 2026 (2 feriados)', app._dias_habiles_mes(2026, 11), 19)

# Marcaciones reales de agosto de 2026: dos tramos por dia, manana y tarde.
AGOSTO = [
    ('2026-08-03', '08:59', '13:01', '15:15', '18:13'),
    ('2026-08-04', '08:59', '13:02', '13:59', '18:07'),
    ('2026-08-05', '08:59', '13:01', '13:59', '18:01'),
    ('2026-08-06', '09:00', '13:01', '13:59', '18:07'),
    ('2026-08-07', '09:00', '13:03', '14:00', '18:04'),
    ('2026-08-11', '08:58', '13:03', '14:00', '18:03'),
    ('2026-08-12', '09:00', '13:02', '14:00', '18:03'),
    ('2026-08-13', '08:57', '13:05', '14:00', '18:03'),
    ('2026-08-14', '08:50', '13:03', '13:59', '18:03'),
    ('2026-08-17', '08:56', '13:02', '14:03', '18:05'),
    ('2026-08-18', '09:36', '13:08', '14:00', '18:17'),
    ('2026-08-19', '08:57', '13:59', '15:11', '18:13'),
    ('2026-08-20', '09:06', '14:01', '15:21', '18:07'),
    ('2026-08-21', '09:00', '13:05', '13:59', '18:05'),
]
# Los dias que faltaban para cerrar el mes, a jornada limpia.
RESTO = [('2026-08-%02d' % d, '09:00', '13:00', '14:00', '18:00')
         for d in (24, 25, 26, 27, 28, 31)]


def dia(fila):
    fecha, e1, s1, e2, s2 = fila
    return {'usuario_id': 1, 'fecha': fecha, '_abierto': False,
            'usuarios': {'nombre': 'Prueba', 'rol': 'secretaria'},
            '_tramos': [{'hora_ingreso': e1 + ':00', 'hora_salida': s1 + ':00'},
                        {'hora_ingreso': e2 + ':00', 'hora_salida': s2 + ':00'}]}


HASTA_HOY = [dia(f) for f in AGOSTO]
MES_COMPLETO = HASTA_HOY + [dia(f) for f in RESTO]


def jornada(horas_dia, dias_mes, auto):
    return {1: {'usuario_id': 1, 'horas_dia': horas_dia, 'dias_mes': dias_mes,
                'horas_jornada_completa': 8, 'sueldo_tiempo_completo': 482,
                'recargo_hora_extra': 1.5, 'dias_automaticos': auto}}


def resumen(filas, horas_dia, dias_mes, auto, periodo=(2026, 8)):
    anio, mes = periodo if periodo else (None, None)
    return app._resumen_asistencia(filas, jornada(horas_dia, dias_mes, auto), None, anio, mes)[0]


print('\n== Las horas salen de los tramos, no de la primera y ultima marca ==')
r = resumen(HASTA_HOY, 4, 22, True)
igual('horas del mes', r['horas_trabajadas'], 111.0)
igual('dias trabajados', r['dias_trabajados'], 14)

print('\n== Media jornada (4 h/dia): el tope deja el sueldo completo ==')
igual('dias exigidos', r['dias_mes'], 20)
igual('de donde salen', r['dias_mes_origen'], 'calendario')
igual('horas exigidas', r['horas_esperadas_mes'], 80.0)
igual('sueldo', r['sueldo_proporcional'], 241.0)

print('\n== Mes completo a tiempo completo: el calendario frente al numero fijo ==')
auto = resumen(MES_COMPLETO, 8, 22, True)
fijo = resumen(MES_COMPLETO, 8, 22, False)
igual('horas de los 20 dias', auto['horas_trabajadas'], 159.0)
igual('calendario -> dias exigidos', auto['dias_mes'], 20)
igual('calendario -> sueldo', auto['sueldo_proporcional'], round(482 * (159 / 160.0), 2))
igual('fijo -> dias exigidos', fijo['dias_mes'], 22)
igual('fijo -> sueldo', fijo['sueldo_proporcional'], round(482 * (159 / 176.0), 2))
igual('lo que el numero fijo le quitaba',
      round(auto['sueldo_proporcional'] - fijo['sueldo_proporcional'], 2), 43.55)

print('\n== Compatibilidad ==')
igual('sin periodo manda el numero fijo', resumen(HASTA_HOY, 8, 22, True, None)['dias_mes'], 22)
sin_columna = {1: {'usuario_id': 1, 'horas_dia': 8, 'dias_mes': 22, 'horas_jornada_completa': 8,
                   'sueldo_tiempo_completo': 482, 'recargo_hora_extra': 1.5}}
igual('sin la migracion 0007 se asume automatico',
      app._resumen_asistencia(HASTA_HOY, sin_columna, None, 2026, 8)[0]['dias_mes'], 20)


# ============================================================
# 2. Correccion de marcaciones
# ============================================================
print('\n== La hora escrita a mano ==')
igual("'9:05'", app._hora_normalizada('9:05'), '09:05:00')
igual("'09:05:00'", app._hora_normalizada('09:05:00'), '09:05:00')
igual('vacio', app._hora_normalizada(''), None)
igual("'25:00' no existe", app._hora_normalizada('25:00'), None)
igual("'09:60' no existe", app._hora_normalizada('09:60'), None)
igual("'abc'", app._hora_normalizada('abc'), None)

# Un dia con la manana cerrada y la tarde todavia sin salida marcada.
ABIERTO = [{'id': 1, 'hora_ingreso': '09:00:00', 'hora_salida': '13:00:00'},
           {'id': 2, 'hora_ingreso': '14:00:00', 'hora_salida': None}]
CERRADO = [{'id': 1, 'hora_ingreso': '09:00:00', 'hora_salida': '13:00:00'},
           {'id': 2, 'hora_ingreso': '14:00:00', 'hora_salida': '18:00:00'}]
rev = app._revisar_correccion

print('\n== Correcciones que se aceptan ==')
igual('cerrar la tarde olvidada', rev(ABIERTO, 2, '14:00:00', '18:00:00'), None)
igual('dejar la tarde en curso', rev(ABIERTO, 2, '14:00:00', None), None)
igual('adelantar la entrada de la manana', rev(ABIERTO, 1, '08:30:00', '13:00:00'), None)
igual('un tramo pegado al siguiente', rev(ABIERTO, 1, '13:00:00', '14:00:00'), None)
igual('el primero de un dia vacio', rev([], None, '09:00:00', '18:00:00'), None)
igual('alargar la tarde', rev(CERRADO, 2, '14:00:00', '19:00:00'), None)

print('\n== Correcciones que se rechazan ==')
rechaza('sin entrada', rev(ABIERTO, 2, None, '18:00:00'), 'falta la hora de entrada')
rechaza('salir antes de entrar', rev(ABIERTO, 2, '14:00:00', '13:00:00'), 'posterior')
rechaza('entrar y salir a la misma hora', rev(ABIERTO, 2, '14:00:00', '14:00:00'), 'posterior')
rechaza('la manana se come la tarde', rev(ABIERTO, 1, '09:00:00', '15:00:00'), 'se cruza')
rechaza('la tarde empieza dentro de la manana', rev(ABIERTO, 2, '12:00:00', '18:00:00'), 'se cruza')
rechaza('un tramo dentro de otro', rev(ABIERTO, 2, '10:00:00', '11:00:00'), 'se cruza')
rechaza('dejar en curso un tramo que no es el ultimo',
        rev(CERRADO, 1, '09:00:00', None), 'puede quedarse sin salida')
rechaza('cruzarse con la tarde ya cerrada', rev(CERRADO, 1, '09:00:00', '14:30:00'), 'se cruza')

print('\n' + ('TODO OK' if not fallos else 'FALLAN %d: %s' % (len(fallos), ', '.join(fallos))))
sys.exit(1 if fallos else 0)
