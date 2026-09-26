# ------------------------------------------------------------
# Desarrollado por Marco Antonio Posligua San Martín
# ------------------------------------------------------------
"""Acceso a la base de ATLAS: PostgreSQL directo.

Reemplaza a la librería de Supabase conservando la misma forma de escribir las
consultas que usa el resto del código:

    supabase.table('gastos').select('*').eq('usuario_id', 3).order('fecha', desc=True).execute().data

Cada consulta se traduce a una petición al estilo PostgREST y `pgrest.py` la
resuelve con SQL. La conexión sale de DATABASE_URL (una cadena postgresql://).
"""
import os
from urllib.parse import urlsplit

from pgrest import BaseDirecta, ErrorConsulta

DATABASE_URL = os.environ['DATABASE_URL']
_base = BaseDirecta(DATABASE_URL, maximo=int(os.getenv('DB_POOL_MAX', '8')))

# Lo que muestra el diagnóstico de /api/passkey/diagnostico: servidor y base,
# nunca la contraseña.
_u = urlsplit(DATABASE_URL)
SUPABASE_URL = f'postgresql://{_u.hostname}{_u.path}'


class APIError(Exception):
    """Error devuelto por la base, con los mismos campos que usaba la librería anterior."""

    def __init__(self, d):
        self.code, self.message = d.get('code'), d.get('message')
        self.details, self.hint = d.get('details'), d.get('hint')
        super().__init__(str(d))

    def json(self):
        return {'code': self.code, 'message': self.message, 'details': self.details, 'hint': self.hint}


class Respuesta:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


def _valor(v):
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if v is None:
        return 'null'
    return str(v)


def _lista(valores):
    """Valores de `in.(...)`: se entrecomillan los que llevan comas, paréntesis o comillas."""
    out = []
    for v in valores:
        s = _valor(v)
        if any(ch in s for ch in ',()":\\ ') or s == '':
            s = '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'
        out.append(s)
    return '(' + ','.join(out) + ')'


class _Negacion:
    """`.not_.is_('saldo', 'null')`"""

    def __init__(self, consulta):
        self._c = consulta

    def __getattr__(self, nombre):
        metodo = getattr(self._c, nombre)

        def envoltura(col, *args, **kw):
            self._c._negar = True
            return metodo(col, *args, **kw)
        return envoltura


class Consulta:
    def __init__(self, tabla):
        self.tabla = tabla
        self.metodo = 'GET'
        self.pares = []
        self.cuerpo = None
        self.prefer = []
        self.orden = []
        self.aceptar = ''
        self._negar = False
        self._select = '*'
        self._contar = False
        self._quizas_uno = False

    # -- operación --
    def select(self, *columnas, count=None, head=False):
        self._select = ','.join(c.replace(' ', '') for c in columnas) if columnas else '*'
        if count:
            self._contar = True
            self.prefer.append(f'count={count}')
        return self

    def insert(self, datos, count=None, returning='representation', upsert=False, default_to_null=True):
        self.metodo, self.cuerpo = 'POST', datos
        self.prefer.append(f'return={returning}')
        return self

    def upsert(self, datos, on_conflict='', ignore_duplicates=False, returning='representation', count=None,
               default_to_null=True):
        self.metodo, self.cuerpo = 'POST', datos
        self.prefer.append('resolution=' + ('ignore-duplicates' if ignore_duplicates else 'merge-duplicates'))
        self.prefer.append(f'return={returning}')
        if on_conflict:
            self.pares.append(('on_conflict', on_conflict))
        return self

    def update(self, datos, count=None, returning='representation'):
        self.metodo, self.cuerpo = 'PATCH', datos
        self.prefer.append(f'return={returning}')
        return self

    def delete(self, count=None, returning='representation'):
        self.metodo = 'DELETE'
        self.prefer.append(f'return={returning}')
        return self

    # -- filtros --
    @property
    def not_(self):
        return _Negacion(self)

    def _filtro(self, col, op, valor):
        pref = 'not.' if self._negar else ''
        self._negar = False
        self.pares.append((col, f'{pref}{op}.{valor}'))
        return self

    def eq(self, col, v): return self._filtro(col, 'eq', _valor(v))
    def neq(self, col, v): return self._filtro(col, 'neq', _valor(v))
    def gt(self, col, v): return self._filtro(col, 'gt', _valor(v))
    def gte(self, col, v): return self._filtro(col, 'gte', _valor(v))
    def lt(self, col, v): return self._filtro(col, 'lt', _valor(v))
    def lte(self, col, v): return self._filtro(col, 'lte', _valor(v))
    def like(self, col, patron): return self._filtro(col, 'like', patron)
    def ilike(self, col, patron): return self._filtro(col, 'ilike', patron)
    def is_(self, col, v): return self._filtro(col, 'is', _valor(v))
    def in_(self, col, valores): return self._filtro(col, 'in', _lista(list(valores)))
    def contains(self, col, v): return self._filtro(col, 'cs', v if isinstance(v, str) else '{' + ','.join(map(_valor, v)) + '}')
    def filter(self, col, op, v): return self._filtro(col, op, v)

    def match(self, criterios):
        for k, v in criterios.items():
            self.eq(k, v)
        return self

    def or_(self, condiciones, reference_table=None):
        self.pares.append(('or', f'({condiciones})'))
        return self

    # -- forma del resultado --
    def order(self, col, desc=False, nullsfirst=None, foreign_table=None):
        # Igual que la librería anterior: sin nulls explícito, el orden de
        # PostgreSQL (en DESC los nulos van primero).
        t = f'{col}.{"desc" if desc else "asc"}'
        if nullsfirst:
            t += '.nullsfirst'
        self.orden.append(t)
        return self

    def limit(self, n, foreign_table=None):
        self.pares = [p for p in self.pares if p[0] != 'limit'] + [('limit', str(int(n)))]
        return self

    def range(self, desde, hasta, foreign_table=None):
        self.pares = [p for p in self.pares if p[0] not in ('limit', 'offset')]
        self.pares += [('offset', str(int(desde))), ('limit', str(int(hasta) - int(desde) + 1))]
        return self

    def single(self):
        self.aceptar = 'application/vnd.pgrst.object+json'
        return self

    def maybe_single(self):
        self._quizas_uno = True
        return self

    # -- ejecución --
    def execute(self):
        pares = [('select', self._select)] + list(self.pares)
        if self.orden:
            pares.append(('order', ','.join(self.orden)))
        try:
            estado, cuerpo, cab = _base.peticion(self.metodo, self.tabla, pares, self.cuerpo,
                                                 ', '.join(self.prefer), self.aceptar)
        except ErrorConsulta as e:
            raise APIError(e.cuerpo())
        conteo = None
        if self._contar:
            total = (cab.get('Content-Range') or '*/').split('/')[-1]
            conteo = int(total) if total.isdigit() else None
        if self._quizas_uno:
            if not cuerpo:
                return None
            if len(cuerpo) > 1:
                raise APIError({'code': 'PGRST116', 'message': 'JSON object requested, multiple rows returned'})
            cuerpo = cuerpo[0]
        return Respuesta(cuerpo if cuerpo is not None else [], conteo)


class Cliente:
    def table(self, nombre):
        return Consulta(nombre)

    from_ = table


supabase = Cliente()
db = supabase
