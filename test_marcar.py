# -*- coding: utf-8 -*-
# ------------------------------------------------------------
# Desarrollado por Marco Antonio Posligua San Martín
# ------------------------------------------------------------
"""Pruebas del acto de marcar: que el botón haga siempre lo que dice.

Lo que se reportaba desde el centro era que la marcación «a veces da error» y
«a veces no quiere marcar». No era una sola falla, eran cuatro caminos que
terminaban en la misma pantalla:

  1. El día que tenía hora de ingreso pero no tenía su tramo (una fila anterior
     a la migración 0005, o una que quedó a medias) se veía en pantalla con el
     botón «Marcar salida», y al pulsarlo el servidor contestaba «primero debes
     marcar tu ingreso». La pantalla y el servidor miraban sitios distintos.
  2. Cualquier fallo de lectura —una red intermitente desde el teléfono— se
     interpretaba como «la tabla de tramos no existe», y la respuesta era
     pedirle a la persona que aplicara una migración que ya estaba aplicada.
  3. Si el alta del día no devolvía la fila creada, se anunciaba «no se pudo
     registrar el ingreso» cuando sí se había registrado; el día quedaba con
     ingreso y sin tramo, que es el caso 1.
  4. El mismo botón pulsado dos veces (la red tarda, se vuelve a tocar) hacía
     que la segunda marcación chocara contra un índice único: la persona veía
     un error sobre algo que había funcionado.

Se prueba con una base de datos de mentira en memoria, con las mismas reglas
de unicidad que la de verdad. No toca nada real.

Uso:
    py test_marcar.py
"""
import os
import sys
import types

os.environ.setdefault('SECRET_KEY', 'prueba')
os.environ.setdefault('SUPABASE_URL', 'http://localhost')
os.environ.setdefault('SUPABASE_KEY', 'prueba')

# El cliente de Supabase se sustituye ANTES de importar app: crearlo de verdad
# exige credenciales y sale a la red, y aquí no hace falta ninguna de las dos.
_stub = types.ModuleType('supabase_client')
_stub.supabase = None
_stub.SUPABASE_URL = 'http://localhost'
sys.modules['supabase_client'] = _stub
_cal = types.ModuleType('google_calendar')
for _f in ('crear_evento_calendar', 'eliminar_evento_calendar',
           'crear_o_actualizar_evento_calendar'):
    setattr(_cal, _f, lambda *a, **k: None)
sys.modules['google_calendar'] = _cal

# Dependencias que la app importa al arrancar y que aqui no aportan nada: se
# rellenan con un modulo vacio para no obligar a instalarlas solo por correr
# las pruebas.
for _nombre in ('sentry_sdk',):
    if _nombre not in sys.modules:
        try:
            __import__(_nombre)
        except ImportError:
            _vacio = types.ModuleType(_nombre)
            _vacio.init = lambda *a, **k: None
            sys.modules[_nombre] = _vacio

import app


# ============================================================
# Base de datos de mentira
# ============================================================
class ErrorFalso(Exception):
    def __init__(self, code, mensaje):
        super().__init__(mensaje)
        self.code = code


DUPLICADO = 'duplicate key value violates unique constraint'
SIN_TABLA = "Could not find the table 'public.%s' in the schema cache"


class BaseFalsa:
    def __init__(self):
        self.filas = {'marcaciones': [], 'marcaciones_tramos': []}
        self.secuencia = {'marcaciones': 0, 'marcaciones_tramos': 0}
        self.tablas_ausentes = set()      # migración pendiente
        self.lecturas_rotas = set()       # fallo transitorio de red
        self.sin_representacion = set()   # el insert no devuelve la fila creada

    # --- utilidades de la prueba ---
    def tramos(self, uid=1, fecha=None):
        return [f for f in self.filas['marcaciones_tramos']
                if f['usuario_id'] == uid and (fecha is None or f['fecha'] == fecha)]

    def dia(self, uid=1, fecha=None):
        return next((f for f in self.filas['marcaciones']
                     if f['usuario_id'] == uid and (fecha is None or f['fecha'] == fecha)), None)

    # --- reglas de unicidad, las mismas que en migration_marcaciones.sql y en
    #     migrations/0005_marcaciones_multiples.sql ---
    def revisar_unicidad(self, tabla, fila):
        if tabla == 'marcaciones':
            if any(f['usuario_id'] == fila['usuario_id'] and f['fecha'] == fila['fecha']
                   for f in self.filas[tabla]):
                raise ErrorFalso('23505', DUPLICADO + ' "marcaciones_usuario_id_fecha_key"')
        if tabla == 'marcaciones_tramos' and fila.get('hora_salida') is None:
            if any(f['usuario_id'] == fila['usuario_id'] and f['fecha'] == fila['fecha']
                   and f.get('hora_salida') is None for f in self.filas[tabla]):
                raise ErrorFalso('23505', DUPLICADO + ' "idx_tramos_abierto_unico"')


class ConsultaFalsa:
    def __init__(self, base, tabla, operacion, datos=None):
        self.base, self.tabla, self.operacion, self.datos = base, tabla, operacion, datos
        self.filtros = []

    def _filtro(self, campo, comparacion, valor):
        self.filtros.append((campo, comparacion, valor))
        return self

    def eq(self, campo, valor):
        return self._filtro(campo, '=', valor)

    def gte(self, campo, valor):
        return self._filtro(campo, '>=', valor)

    def lte(self, campo, valor):
        return self._filtro(campo, '<=', valor)

    def in_(self, campo, valores):
        return self._filtro(campo, 'in', valores)

    def is_(self, campo, valor):
        return self._filtro(campo, '=', valor)

    def order(self, *a, **k):
        return self

    def limit(self, n):
        return self

    def range(self, desde, hasta):
        return self

    def _coincide(self, fila):
        for campo, comparacion, valor in self.filtros:
            actual = fila.get(campo)
            if comparacion == 'in':
                if str(actual) not in [str(v) for v in valor]:
                    return False
            elif comparacion == '=':
                if valor is None:
                    if actual is not None:
                        return False
                elif str(actual) != str(valor):
                    return False
            elif comparacion == '>=' and not (actual is not None and str(actual) >= str(valor)):
                return False
            elif comparacion == '<=' and not (actual is not None and str(actual) <= str(valor)):
                return False
        return True

    def execute(self):
        base = self.base
        if self.tabla in base.tablas_ausentes:
            raise ErrorFalso('PGRST205', SIN_TABLA % self.tabla)
        if self.operacion == 'select' and self.tabla in base.lecturas_rotas:
            raise ErrorFalso('', 'Server disconnected without sending a response')
        filas = base.filas[self.tabla]
        if self.operacion == 'select':
            return Respuesta([dict(f) for f in filas if self._coincide(f)])
        if self.operacion == 'insert':
            nueva = dict(self.datos)
            nueva.setdefault('hora_ingreso', None)
            nueva.setdefault('hora_salida', None)
            base.revisar_unicidad(self.tabla, nueva)
            base.secuencia[self.tabla] += 1
            nueva['id'] = base.secuencia[self.tabla]
            filas.append(nueva)
            return Respuesta([] if self.tabla in base.sin_representacion else [dict(nueva)])
        if self.operacion == 'update':
            tocadas = [f for f in filas if self._coincide(f)]
            for f in tocadas:
                f.update(self.datos)
            return Respuesta([dict(f) for f in tocadas])
        if self.operacion == 'delete':
            tocadas = [f for f in filas if self._coincide(f)]
            base.filas[self.tabla] = [f for f in filas if f not in tocadas]
            return Respuesta([dict(f) for f in tocadas])
        raise AssertionError(self.operacion)


class Respuesta:
    def __init__(self, data):
        self.data = data


class TablaFalsa:
    def __init__(self, base, nombre):
        self.base, self.nombre = base, nombre

    def select(self, *a, **k):
        return ConsultaFalsa(self.base, self.nombre, 'select')

    def insert(self, datos):
        return ConsultaFalsa(self.base, self.nombre, 'insert', datos)

    def update(self, datos):
        return ConsultaFalsa(self.base, self.nombre, 'update', datos)

    def delete(self):
        return ConsultaFalsa(self.base, self.nombre, 'delete')


class ClienteFalso:
    def __init__(self, base):
        self.base = base

    def table(self, nombre):
        return TablaFalsa(self.base, nombre)


# ============================================================
# Andamiaje
# ============================================================
fallos = []
HOY = '2026-09-11'


def nueva_base():
    base = BaseFalsa()
    app.supabase = ClienteFalso(base)
    return base


def marcar(hora, accion, uid=1, fecha=HOY):
    return app._marcar_asistencia(uid, fecha, hora, accion)


def ok(etiqueta, condicion, detalle=''):
    print(('  OK   ' if condicion else '  FALLA ') + etiqueta +
          ('' if condicion else ': ' + str(detalle)))
    if not condicion:
        fallos.append(etiqueta)


def exito(etiqueta, resultado, fragmento=''):
    mensaje, categoria = resultado
    ok(etiqueta, categoria == 'success' and fragmento.lower() in mensaje.lower(), repr(resultado))


def error(etiqueta, resultado, fragmento):
    mensaje, categoria = resultado
    ok(etiqueta, categoria == 'error' and fragmento.lower() in mensaje.lower(), repr(resultado))


# ============================================================
# 1. El día normal, con doble jornada
# ============================================================
print('== Un dia de doble jornada ==')
base = nueva_base()
exito('entra a las 08:00', marcar('08:00:00', 'ingreso'), 'Ingreso marcado a las 08:00')
ok('se creo la fila del dia', base.dia() is not None)
ok('con un tramo abierto', len(base.tramos()) == 1 and base.tramos()[0]['hora_salida'] is None)
exito('sale a las 13:00', marcar('13:00:00', 'salida'), 'Salida marcada a las 13:00')
ok('el tramo quedo cerrado', base.tramos()[0]['hora_salida'] == '13:00:00')
ok('el dia guarda la salida', base.dia()['hora_salida'] == '13:00:00')
exito('vuelve a las 14:00', marcar('14:00:00', 'ingreso'), 'Ingreso 2 del día marcado a las 14:00')
exito('sale a las 18:00', marcar('18:00:00', 'salida'), 'Salida 2 del día marcada a las 18:00')
ok('el dia tiene dos tramos', len(base.tramos()) == 2)
ok('el dia guarda la primera entrada', base.dia()['hora_ingreso'] == '08:00:00')
ok('...y la ultima salida', base.dia()['hora_salida'] == '18:00:00')

# ============================================================
# 2. El mismo botón pulsado dos veces
# ============================================================
print('\n== El boton pulsado dos veces no es un error ==')
base = nueva_base()
marcar('08:00:00', 'ingreso')
exito('el segundo toque confirma el ingreso', marcar('08:00:03', 'ingreso'), 'Ingreso marcado a las 08:00')
ok('y no abrio un tramo de mas', len(base.tramos()) == 1)
marcar('13:00:00', 'salida')
exito('el segundo toque confirma la salida', marcar('13:00:04', 'salida'), 'Salida marcada a las 13:00')
ok('la salida sigue siendo la primera', base.tramos()[0]['hora_salida'] == '13:00:00')

print('\n== Pero un olvido de verdad si se avisa ==')
base = nueva_base()
marcar('08:00:00', 'ingreso')
error('entrar dos veces, horas aparte', marcar('11:00:00', 'ingreso'), 'ingreso abierto desde las 08:00')
base = nueva_base()
error('salir sin haber entrado', marcar('08:00:00', 'salida'), 'primero debes marcar tu ingreso')
base = nueva_base()
marcar('08:00:00', 'ingreso')
marcar('13:00:00', 'salida')
error('salir dos veces, horas aparte', marcar('17:00:00', 'salida'), 'ya cerraste tu último tramo')

# ============================================================
# 3. El día con ingreso y sin tramo (el que no dejaba salir)
# ============================================================
print('\n== El dia que tenia ingreso pero no tenia tramo ==')
base = nueva_base()
base.filas['marcaciones'].append({'id': 99, 'usuario_id': 1, 'fecha': HOY,
                                  'hora_ingreso': '08:00:00', 'hora_salida': None})
base.secuencia['marcaciones'] = 99
exito('la salida se registra igual', marcar('13:00:00', 'salida'), 'Salida marcada a las 13:00')
ok('el dia quedo respaldado con su tramo', len(base.tramos()) == 1)
ok('el tramo esta cerrado', base.tramos()[0]['hora_salida'] == '13:00:00')
ok('sin perder la hora de entrada', base.tramos()[0]['hora_ingreso'] == '08:00:00')

print('\n== ...y ese hueco no deja entrar dos veces ==')
base = nueva_base()
base.filas['marcaciones'].append({'id': 99, 'usuario_id': 1, 'fecha': HOY,
                                  'hora_ingreso': '08:00:00', 'hora_salida': None})
base.secuencia['marcaciones'] = 99
error('sigue habiendo un ingreso abierto', marcar('11:00:00', 'ingreso'), 'ingreso abierto desde las 08:00')

# ============================================================
# 4. Fallos de la base: cada uno con su respuesta
# ============================================================
print('\n== Un fallo de red no es una migracion pendiente ==')
base = nueva_base()
base.lecturas_rotas.add('marcaciones_tramos')
try:
    resultado = marcar('08:00:00', 'ingreso')
    ok('el fallo se propaga, no se disfraza de migracion', False, resultado)
except ErrorFalso:
    ok('el fallo se propaga, no se disfraza de migracion', True)

print('\n== La tabla que de verdad falta si lo dice ==')
base = nueva_base()
base.tablas_ausentes.add('marcaciones_tramos')
exito('primer ingreso del dia (modo antiguo)', marcar('08:00:00', 'ingreso'), 'Ingreso marcado a las 08:00')
exito('su salida', marcar('13:00:00', 'salida'), 'Salida marcada a las 13:00')
error('el segundo ingreso pide la migracion', marcar('14:00:00', 'ingreso'),
      '0005_marcaciones_multiples.sql')

print('\n== El alta que no devuelve la fila creada ==')
base = nueva_base()
base.sin_representacion.add('marcaciones')
exito('el ingreso se confirma igual', marcar('08:00:00', 'ingreso'), 'Ingreso marcado a las 08:00')
ok('con su tramo puesto', len(base.tramos()) == 1)
ok('y un solo dia', len(base.filas['marcaciones']) == 1)

print('\n== Dos peticiones del mismo ingreso a la vez ==')
# La otra petición crea la fila del día entre la lectura y la escritura de
# esta: el UNIQUE(usuario_id, fecha) rechaza la segunda, que no falla sino que
# vuelve a leer la fila que la otra dejó puesta.
base = nueva_base()
_leer_dia = app._fila_del_dia


def _dia_que_aparece_tarde(uid, fecha):
    fila = _leer_dia(uid, fecha)
    if fila is None:
        base.filas['marcaciones'].append({'id': 1, 'usuario_id': uid, 'fecha': fecha,
                                          'hora_ingreso': '08:00:00', 'hora_salida': None})
        base.secuencia['marcaciones'] = 1
    return fila


app._fila_del_dia = _dia_que_aparece_tarde
try:
    exito('la segunda peticion confirma en vez de fallar', marcar('08:00:01', 'ingreso'),
          'Ingreso marcado')
finally:
    app._fila_del_dia = _leer_dia
ok('sin duplicar el dia', len(base.filas['marcaciones']) == 1)
ok('con un unico tramo', len(base.tramos()) == 1)

print('\n== El tramo abierto que aparece entre medias ==')
# Mismo choque, pero contra idx_tramos_abierto_unico: el día ya existía (sin
# hora de ingreso, p. ej. creado al darle permiso) y el tramo lo abrió la otra
# petición justo después de leer.
base = nueva_base()
base.filas['marcaciones'].append({'id': 1, 'usuario_id': 1, 'fecha': HOY,
                                  'hora_ingreso': None, 'hora_salida': None})
base.secuencia['marcaciones'] = 1
base.filas['marcaciones_tramos'].append({'id': 1, 'marcacion_id': 1, 'usuario_id': 1,
                                         'fecha': HOY, 'hora_ingreso': '08:00:00',
                                         'hora_salida': None})
base.secuencia['marcaciones_tramos'] = 1
_leer_tramos = app._tramos_del_dia
app._tramos_del_dia = lambda uid, fecha: []
try:
    exito('el choque se cuenta como marcado', marcar('08:00:01', 'ingreso'), 'Ingreso marcado')
finally:
    app._tramos_del_dia = _leer_tramos
ok('sin abrir un segundo tramo', len(base.tramos()) == 1)

print('\n== Un error de columna no es una tabla que falta ==')
# 42703 es «column ... does not exist». Si se contara como tabla ausente, se
# volveria al modo antiguo y al aviso de migracion pendiente, que es el fallo
# que el control vino a cerrar.
base = nueva_base()
ok('la columna ausente no se confunde con la tabla',
   not app._falta_la_tabla(ErrorFalso('42703', 'column marcaciones_tramos.foo does not exist')))
ok('la tabla ausente si se reconoce (PostgREST)',
   app._falta_la_tabla(ErrorFalso('PGRST205', SIN_TABLA % 'marcaciones_tramos')))
ok('la tabla ausente si se reconoce (Postgres)',
   app._falta_la_tabla(ErrorFalso('42P01', 'relation "marcaciones_tramos" does not exist')))
ok('un choque de unicidad no es una tabla que falta',
   not app._falta_la_tabla(ErrorFalso('23505', DUPLICADO + ' "idx_tramos_abierto_unico"')))

print('\n== El dia que existia sin hora de entrada ==')
# Lo crea el permiso, o lo deja a medias otra peticion: la primera entrada que
# llega tiene que quedar escrita tambien en la fila del dia.
base = nueva_base()
base.filas['marcaciones'].append({'id': 1, 'usuario_id': 1, 'fecha': HOY,
                                  'hora_ingreso': None, 'hora_salida': None,
                                  'con_permiso': True})
base.secuencia['marcaciones'] = 1
exito('el ingreso se registra', marcar('08:00:00', 'ingreso'), 'Ingreso marcado a las 08:00')
ok('el dia recibe la hora de entrada', base.dia()['hora_ingreso'] == '08:00:00',
   base.dia())
ok('sin crear un dia nuevo', len(base.filas['marcaciones']) == 1)
ok('con su tramo', len(base.tramos()) == 1)

# ============================================================
# 5. Tope de entradas del día
# ============================================================
print('\n== El tope de entradas del dia ==')
base = nueva_base()
for i in range(app.MAX_TRAMOS_DIA):
    marcar('%02d:00:00' % (7 + i * 2), 'ingreso')
    marcar('%02d:00:00' % (8 + i * 2), 'salida')
ok('se registraron %d tramos' % app.MAX_TRAMOS_DIA, len(base.tramos()) == app.MAX_TRAMOS_DIA,
   len(base.tramos()))
error('el siguiente ingreso se rechaza', marcar('20:00:00', 'ingreso'),
      'ya registraste %d entradas' % app.MAX_TRAMOS_DIA)

print('\n' + ('TODO OK' if not fallos else 'FALLAN %d: %s' % (len(fallos), ', '.join(fallos))))
sys.exit(1 if fallos else 0)
