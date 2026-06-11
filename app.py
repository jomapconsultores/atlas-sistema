import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from config import Config
from models import check_password, Usuario
from supabase_client import supabase
from google_calendar import crear_evento_calendar, eliminar_evento_calendar, crear_o_actualizar_evento_calendar
from datetime import datetime, date, timedelta
from calendar import monthrange
from functools import wraps
import uuid
import io
import csv
import hashlib
import re
import unicodedata

# Lectura de estados de cuenta. Se importan de forma opcional para no romper
# el arranque si la dependencia no está instalada (el módulo avisa al usuario).
try:
    import openpyxl
except Exception:
    openpyxl = None
try:
    import pdfplumber
except Exception:
    pdfplumber = None

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return Usuario.get_by_id(int(user_id))

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if current_user.rol != 'admin':
            flash('❌ Solo administradores', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated

def socio_admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if current_user.rol not in ['admin', 'socio']:
            flash('❌ Acceso restringido', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated

# Inyecta contadores (anticipos pendientes y contactos nuevos) en TODAS las plantillas (badges del menú lateral)
@app.context_processor
def inyectar_globales():
    pendientes = 0
    contactos_nuevos = 0
    try:
        if current_user.is_authenticated and getattr(current_user, 'rol', None) in ['admin', 'socio']:
            solicitudes = supabase.table('anticipos_solicitudes').select('id').eq('estado', 'pendiente').execute()
            pendientes = len(solicitudes.data or [])
            try:
                cont = supabase.table('contactos').select('id').eq('estado', 'nuevo').execute()
                contactos_nuevos = len(cont.data or [])
            except Exception:
                contactos_nuevos = 0
    except Exception:
        pendientes = 0
    return {'solicitudes_pendientes': pendientes, 'contactos_nuevos': contactos_nuevos}

# Evita que el navegador cachee las páginas HTML (causa de "no veo los cambios" tras desplegar).
# Los recursos estáticos (logo, etc.) NO se tocan y siguen cacheando normalmente.
@app.after_request
def no_cache_html(response):
    if response.mimetype == 'text/html':
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

# ========== CONSTANTES ==========
ASIGNATURAS = [
    'Contabilidad general', 'Contabilidad de costos', 'Matemáticas', 'Geometría',
    'Cálculo diferencial', 'Cálculo integral', 'Física', 'Química', 'Biología',
    'Genética', 'Anatomía', 'Inglés', 'Lengua y Literatura', 'Matemáticas financieras',
    'Análisis financiero', 'Bioquímica', 'CCNN', 'Informática', 'Asesoría tesis',
    'Pre universitario - Matemáticas', 'Pre universitario - CCNN',
    'Pre universitario - Literatura', 'Pre universitario - Motivación'
]

ATENCION_PSICOLOGICA = [
    {'nombre': 'Evaluación psicológica (convenio)', 'precio': 63},
    {'nombre': 'Clínica en evaluación psicopedagógica (convenio)', 'precio': 28},
    {'nombre': 'Evaluación psicológica (normal)', 'precio': 90},
    {'nombre': 'Clínica en evaluación psicopedagógica (normal)', 'precio': 40},
    {'nombre': 'Paquete 4 terapias', 'precio': 160, 'sesiones': 4}
]

PRECIOS_CLASE = [10, 11, 12, 15]
PRECIOS_MATRICULA = [0, 18, 20]
PRECIOS_PENSION = [99, 100, 110]
PROFESORES = ['Carmen Reinoso', 'Rosalía Moscoso', 'Marco Antonio Posligua',
              'Edwin Rumipulla', 'Catherine Alvear', 'Alexander Nivelo',
              'Daniel Castillo', 'Johanna Nievecela']
ENCARGADOS = ['CARMEN', 'ROSALÍA', 'EDWIN', 'MAP', 'JOHANNA']
SOCIOS = ['Carmen Reinoso', 'Rosalía Moscoso', 'Marco Antonio Posligua']

INSTITUCIONES_DEFAULT = [
    'Unidad Educativa Técnico Salesiano', 'Unidad Educativa Sagrado Corazón de Jesús',
    'Colegio Benigno Malo', 'Unidad Educativa Central', 'Unidad Educativa Borja',
    'Unidad Educativa La Salle', 'Unidad Educativa Verbo', 'Unidad Educativa Santo Domingo de Guzmán',
    'Universidad de Cuenca', 'Universidad del Azuay', 'Universidad Politécnica Salesiana',
    'UCACUE', 'Universidad Católica de Cuenca',
]

NIVELES_POR_TIPO = {
    'Universidad': ['Primer nivel', 'Segundo nivel', 'Tercer nivel', 'Cuarto nivel', 'Quinto nivel',
                    'Sexto nivel', 'Séptimo nivel', 'Octavo nivel', 'Noveno nivel', 'Décimo nivel'],
    'Escuela': ['Primero de básica', 'Segundo de básica', 'Tercero de básica', 'Cuarto de básica',
                'Quinto de básica', 'Sexto de básica', 'Séptimo de básica', 'Octavo de básica',
                'Noveno de básica', 'Décimo de básica'],
    'Bachillerato': ['Primero de bachillerato', 'Segundo de bachillerato', 'Tercero de bachillerato'],
}

def cargar_asignaturas():
    """Lista de asignaturas desde la tabla `asignaturas`. Si la tabla no existe
    o está vacía, usa la lista por defecto (ASIGNATURAS)."""
    try:
        r = supabase.table('asignaturas').select('nombre').eq('activo', True).order('nombre').execute()
        nombres = [a['nombre'] for a in (r.data or []) if a.get('nombre')]
        return nombres if nombres else ASIGNATURAS
    except Exception:
        return ASIGNATURAS

def cargar_profesores():
    """Lista de nombres de docentes ('Nombres Apellidos') desde la tabla `docentes`.
    Si la tabla no existe o está vacía, usa la lista por defecto (PROFESORES)."""
    try:
        r = supabase.table('docentes').select('nombres,apellidos').eq('activo', True).execute()
        nombres = [f"{d.get('nombres','')} {d.get('apellidos','')}".strip()
                   for d in (r.data or [])]
        nombres = [n for n in nombres if n]
        return sorted(nombres) if nombres else PROFESORES
    except Exception:
        return PROFESORES

def a_oracion(texto):
    if not texto:
        return texto
    return texto.strip().lower().capitalize()

# ========== CONSTANTES DE PAGOS ==========
PAGO_DOCENCIA_POR_HORA = 7
PAGO_DOCENCIA_CANCELADO = 5   # valor FIJO al docente por clase Cancelado-Pagado (no por hora)
PORCENTAJE_PSICOLOGIA = 0.4018
COMISION_CLIENTE_EXTERNO = 0.25

def dedup_sesiones_docente(sesiones):
    """Devuelve una fila por sesión física (profesor+fecha+horario).
    Evita contar el pago al docente múltiples veces cuando varios
    estudiantes asisten a la misma clase en el mismo horario."""
    seen = set()
    result = []
    for s in sesiones:
        gid = s.get('sesion_grupo_id')
        key = str(gid) if gid else '|'.join([
            str(s.get('profesor_terapeuta', '')),
            str(s.get('fecha', '')),
            str(s.get('hora_inicio', '')),
            str(s.get('hora_fin', ''))
        ])
        if key not in seen:
            seen.add(key)
            result.append(s)
    return result

# ========== CARGAR COSTOS DESDE SUPABASE ==========
def cargar_costos():
    try:
        costos = supabase.table('costos_config').select('*').eq('activo', True).execute()
        psicologia = []
        precios_clase = []
        precios_matricula = []
        precios_pension = []
        for c in (costos.data or []):
            if c['tipo'] == 'psicologia':
                psicologia.append({'nombre': c['concepto'], 'precio': float(c['precio']), 'sesiones': 4 if 'paquete' in c['concepto'].lower() else 1})
            elif c['tipo'] == 'clase':
                precios_clase.append(float(c['precio']))
            elif c['tipo'] == 'matricula':
                precios_matricula.append(float(c['precio']))
            elif c['tipo'] == 'pension':
                precios_pension.append(float(c['precio']))
        return psicologia, precios_clase or [10], precios_matricula or [0, 18, 20], precios_pension or [99, 100, 110]
    except:
        return ATENCION_PSICOLOGICA, PRECIOS_CLASE, PRECIOS_MATRICULA, PRECIOS_PENSION

# ========== DEVOLUCIONES (helpers) ==========
def devoluciones_periodo(anio, mes):
    """Suma de devoluciones de dinero a clientes en el período indicado.
    Se usa para RESTAR de los ingresos en Reportes y Liquidación.
    Filtra por mes_periodo/anio_periodo (como gastos); si esos campos
    faltan, cae a la fecha de la devolución."""
    try:
        res = supabase.table('devoluciones').select('*').execute()
    except Exception:
        return 0.0
    total = 0.0
    for d in (res.data or []):
        mp = d.get('mes_periodo')
        ap = d.get('anio_periodo')
        if mp and ap:
            if int(mp) == int(mes) and int(ap) == int(anio):
                total += d.get('monto', 0) or 0
        else:
            f = d.get('fecha', '') or ''
            if f[:7] == f"{anio}-{mes:02d}":
                total += d.get('monto', 0) or 0
    return total

def devoluciones_por_estudiante(estudiante_id):
    """Total devuelto a un estudiante (todas las fechas). Se resta del
    'pagado' para obtener el pagado neto y el saldo real en el Módulo 3."""
    try:
        res = supabase.table('devoluciones').select('monto').eq('estudiante_id', estudiante_id).execute()
    except Exception:
        return 0.0
    return sum(d.get('monto', 0) or 0 for d in (res.data or []))

def crear_devolucion(tipo_cliente, fecha, monto, tipo_pago, motivo, pagar_docente,
                     docente_nombre, monto_docente, registrado_por,
                     estudiante_id=None, cliente_id=None, cita_id=None):
    """Registra una devolución: (1) si hay que pagar igual al docente crea un gasto
    automático vinculado, (2) inserta la devolución (resta ingresos), (3) si es cliente
    externo con cita, descuenta lo devuelto de la cita. Devuelve el id de la devolución.
    Reutilizado por el módulo de Devoluciones y por el Módulo 3 (pago de estudiantes)."""
    try:
        fecha_obj = datetime.strptime(fecha, '%Y-%m-%d')
    except Exception:
        fecha_obj = datetime.today()
    monto = float(monto or 0)
    monto_docente = float(monto_docente or 0) if pagar_docente else 0

    # 1) Gasto automático al docente
    gasto_id = None
    if pagar_docente and monto_docente > 0:
        concepto = f"Devolución - pago docente ({docente_nombre or 's/d'})"
        if motivo:
            concepto += f" · {motivo[:60]}"
        gasto_data = {
            'concepto': concepto, 'monto': monto_docente, 'fecha': fecha,
            'categoria': 'Devolución - pago docente', 'persona': docente_nombre or '',
            'reembolso': False, 'registrado_por': registrado_por,
            'mes': fecha_obj.month, 'anio': fecha_obj.year,
            'mes_periodo': fecha_obj.month, 'anio_periodo': fecha_obj.year
        }
        try:
            g = supabase.table('gastos').insert(gasto_data).execute()
            gasto_id = g.data[0]['id'] if g.data else None
        except Exception:
            gasto_data.pop('mes_periodo', None)
            gasto_data.pop('anio_periodo', None)
            g = supabase.table('gastos').insert(gasto_data).execute()
            gasto_id = g.data[0]['id'] if g.data else None

    # 2) Insertar la devolución
    res = supabase.table('devoluciones').insert({
        'fecha': fecha, 'tipo_cliente': tipo_cliente,
        'estudiante_id': estudiante_id, 'cliente_id': cliente_id, 'cita_id': cita_id,
        'monto': monto, 'tipo_pago': tipo_pago, 'motivo': motivo,
        'pagar_docente': pagar_docente, 'docente_nombre': docente_nombre,
        'monto_docente': monto_docente, 'gasto_id': gasto_id,
        'mes_periodo': fecha_obj.month, 'anio_periodo': fecha_obj.year,
        'registrado_por': registrado_por
    }).execute()

    # 3) Cliente externo con cita: restar de lo pagado
    if tipo_cliente == 'externo' and cita_id:
        cita = supabase.table('citas_psicologia').select('*').eq('id', cita_id).execute()
        if cita.data:
            c = cita.data[0]
            nuevo_pagado = max(0, (c.get('monto_pagado', 0) or 0) - monto)
            if nuevo_pagado <= 0:
                nuevo_estado = 'agendada'
            elif nuevo_pagado >= (c.get('valor', 0) or 0):
                nuevo_estado = 'pagada'
            else:
                nuevo_estado = 'parcial'
            supabase.table('citas_psicologia').update({
                'monto_pagado': nuevo_pagado, 'estado': nuevo_estado
            }).eq('id', cita_id).execute()
    return res.data[0]['id'] if res.data else None

# ========== RUTAS PRINCIPALES ==========
@app.route('/')
def inicio():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('inicio.html')

@app.route('/contacto', methods=['POST'])
def contacto():
    """Recibe el formulario de contacto de la landing pública y lo guarda.
    Genera una alerta (badge) para socios y administradores."""
    nombre = (request.form.get('nombre') or '').strip()
    telefono = (request.form.get('telefono') or '').strip()
    email = (request.form.get('email') or '').strip()
    mensaje = (request.form.get('mensaje') or '').strip()
    if not nombre or not (telefono or email):
        return redirect(url_for('inicio', error=1, _anchor='contacto'))
    try:
        supabase.table('contactos').insert({
            'nombre': nombre[:120], 'telefono': telefono[:40],
            'email': email[:120], 'mensaje': mensaje[:1000], 'estado': 'nuevo'
        }).execute()
        return redirect(url_for('inicio', enviado=1, _anchor='contacto'))
    except Exception as e:
        print(f'⚠️ Error al guardar contacto: {e}')
        return redirect(url_for('inicio', error=1, _anchor='contacto'))

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        try:
            email = request.form['email']
            nombre = request.form['nombre']
            rol = request.form['rol']
            password = request.form['password']
            existente = supabase.table('usuarios').select('*').eq('email', email).execute()
            if existente.data:
                flash('❌ Este email ya está registrado', 'error')
                return redirect(url_for('registro'))
            result = supabase.table('usuarios').insert({
                'nombre': nombre, 'email': email,
                'password_hash': password, 'rol': rol, 'activo': False
            }).execute()
            if result.data:
                flash('✅ Solicitud enviada. Espera aprobación del administrador.', 'success')
                return redirect(url_for('inicio'))
        except Exception as e:
            flash(f'❌ Error: {str(e)}', 'error')
        return redirect(url_for('registro'))
    return render_template('registro.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        result = supabase.table('usuarios').select('*').eq('email', request.form['email']).execute()
        if result.data and result.data[0].get('activo') and check_password(result.data[0]['password_hash'], request.form['password']):
            login_user(Usuario.get_by_id(result.data[0]['id']))
            return redirect(url_for('dashboard'))
        flash('❌ Credenciales incorrectas o cuenta pendiente de aprobación', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('inicio'))

@app.route('/dashboard')
@login_required
def dashboard():
    solicitudes_pendientes = 0
    if current_user.rol in ['admin', 'socio']:
        solicitudes = supabase.table('anticipos_solicitudes').select('*').eq('estado', 'pendiente').execute()
        solicitudes_pendientes = len(solicitudes.data or [])
    return render_template('dashboard.html', rol=current_user.rol, solicitudes_pendientes=solicitudes_pendientes)

# ========== MÓDULO 1: PLANIFICACIÓN ==========
@app.route('/modulo1', methods=['GET', 'POST'])
@login_required
@socio_admin_required
def modulo1():
    psicologia, precios_clase, precios_matricula, precios_pension = cargar_costos()
    
    if request.method == 'POST':
        try:
            tipo = request.form.get('tipo_sesion', 'clase')
            num_sesiones = int(request.form.get('num_sesiones', 1))
            num_estudiantes = int(request.form.get('num_estudiantes', 1))
            primera_fecha = None
            atencion = request.form.get('atencion_psicologica', '')
            es_paquete = (atencion == 'Paquete 4 terapias')
            
            es_terapia = tipo in ['terapia', 'ambos']
            if es_terapia:
                if not atencion or atencion == '':
                    flash('❌ Debe seleccionar un tipo de atención psicológica (costo)', 'error')
                    return redirect(url_for('modulo1'))
            else:
                precio_hora = request.form.get('precio_hora', '')
                if not precio_hora or precio_hora == '':
                    flash('❌ Debe seleccionar un precio por hora (costo)', 'error')
                    return redirect(url_for('modulo1'))
            
            if es_paquete:
                num_sesiones = 4
            
            # ── VALIDACIÓN ESTRICTA: ningún dato puede faltar y los horarios deben ser coherentes ──
            # 1) Al menos un estudiante seleccionado (válido)
            estudiantes_validos = [
                request.form.get(f'estudiante_id_{e}', '')
                for e in range(1, num_estudiantes + 1)
            ]
            estudiantes_validos = [e for e in estudiantes_validos if e and e != 'nuevo']
            if not estudiantes_validos:
                flash('❌ Debe seleccionar al menos un estudiante válido', 'error')
                return redirect(url_for('modulo1'))
            if len(estudiantes_validos) < num_estudiantes:
                flash('❌ Hay estudiantes sin seleccionar. Complete todos los estudiantes antes de grabar', 'error')
                return redirect(url_for('modulo1'))

            # 2) Cada sesión: datos completos y horario coherente (sin horas en retroceso ni negativas)
            for sesion_num in range(1, num_sesiones + 1):
                fecha = request.form.get(f'fecha_{sesion_num}')
                h_ini = request.form.get(f'hora_inicio_{sesion_num}')
                h_fin = request.form.get(f'hora_fin_{sesion_num}')
                encargado_v = request.form.get(f'encargado_{sesion_num}', '')
                profesor_v = request.form.get(f'profesor_{sesion_num}', '')
                nuevo_prof_v = request.form.get(f'nuevo_profesor_{sesion_num}', '')

                if not fecha or not h_ini or not h_fin:
                    flash(f'❌ Sesión {sesion_num}: faltan fecha u horario. Complete todos los campos', 'error')
                    return redirect(url_for('modulo1'))
                if not encargado_v:
                    flash(f'❌ Sesión {sesion_num}: debe seleccionar el encargado de apertura', 'error')
                    return redirect(url_for('modulo1'))
                if profesor_v == 'nuevo' and not nuevo_prof_v.strip():
                    flash(f'❌ Sesión {sesion_num}: escriba el nombre del profesor nuevo', 'error')
                    return redirect(url_for('modulo1'))

                ini_dt = datetime.strptime(f"{fecha} {h_ini}", '%Y-%m-%d %H:%M')
                fin_dt = datetime.strptime(f"{fecha} {h_fin}", '%Y-%m-%d %H:%M')
                horas_v = (fin_dt - ini_dt).total_seconds() / 3600
                if horas_v < 0:
                    flash(f'❌ Sesión {sesion_num}: horario en retroceso. La hora de fin no puede ser anterior al inicio', 'error')
                    return redirect(url_for('modulo1'))
                if horas_v == 0:
                    flash(f'❌ Sesión {sesion_num}: la duración no puede ser 0 horas', 'error')
                    return redirect(url_for('modulo1'))
                if horas_v < 0.5:
                    flash(f'❌ Sesión {sesion_num}: duración muy corta ({int(horas_v*60)} min). El mínimo es 30 minutos', 'error')
                    return redirect(url_for('modulo1'))

                # 3) El docente/psicólogo no puede tener otra sesión que se cruce en el mismo horario
                prof_efectivo = nuevo_prof_v.strip() if (profesor_v == 'nuevo' and nuevo_prof_v.strip()) else profesor_v
                if prof_efectivo and prof_efectivo != 'nuevo':
                    try:
                        ocupadas = supabase.table('sesiones').select('hora_inicio,hora_fin,estado').eq(
                            'profesor_terapeuta', prof_efectivo).eq('fecha', fecha).neq('estado', 'Cancelado').execute().data or []
                    except Exception:
                        ocupadas = []
                    ni, nf = h_ini[:5], h_fin[:5]
                    for ex in ocupadas:
                        ei = (ex.get('hora_inicio') or '')[:5]
                        ef = (ex.get('hora_fin') or '')[:5]
                        if ei and ef and ei < nf and ef > ni:  # hay cruce de horarios
                            flash(f'⛔ {prof_efectivo} ya está ocupado el {fecha} de {ei} a {ef}. '
                                  f'No se puede agendar de {ni} a {nf} (sesión {sesion_num}).', 'error')
                            return redirect(url_for('modulo1'))

            for sesion_num in range(1, num_sesiones + 1):
                fecha = request.form.get(f'fecha_{sesion_num}')
                h_ini = request.form.get(f'hora_inicio_{sesion_num}')
                h_fin = request.form.get(f'hora_fin_{sesion_num}')
                profesor = request.form.get(f'profesor_{sesion_num}', '')
                nuevo_prof = request.form.get(f'nuevo_profesor_{sesion_num}', '')
                encargado = request.form.get(f'encargado_{sesion_num}', '')
                if nuevo_prof and profesor == 'nuevo':
                    profesor = nuevo_prof
                if not fecha or not h_ini or not h_fin:
                    continue
                if not primera_fecha:
                    primera_fecha = fecha
                inicio = datetime.strptime(f"{fecha} {h_ini}", '%Y-%m-%d %H:%M')
                fin = datetime.strptime(f"{fecha} {h_fin}", '%Y-%m-%d %H:%M')
                horas = round((fin - inicio).total_seconds() / 3600, 2)
                
                if es_terapia:
                    tema = atencion
                    asignatura = request.form.get('asignatura', '') if tipo == 'ambos' else ''
                    if tema == 'Paquete 4 terapias':
                        precio = 160 / 4
                    else:
                        precio = next((item['precio'] for item in psicologia if item['nombre'] == tema), 40)
                    valor_inicial = precio
                else:
                    asignatura = request.form.get('asignatura', '')
                    tema = ''
                    precio = float(precio_hora)
                    valor_inicial = 0
                
                grupo_id = str(uuid.uuid4())
                estudiantes_nombres = []
                for est_num in range(1, num_estudiantes + 1):
                    eid = request.form.get(f'estudiante_id_{est_num}', '')
                    if eid and eid != 'nuevo':
                        # Para clases con múltiples estudiantes se puede pactar un precio distinto por estudiante
                        if not es_terapia:
                            precio_est_str = request.form.get(f'precio_hora_{est_num}', '')
                            precio_est = float(precio_est_str) if precio_est_str else precio
                        else:
                            precio_est = precio
                        datos_sesion = {
                            'tipo_sesion': tipo, 'asignatura': asignatura,
                            'tema_terapia': tema, 'profesor_terapeuta': profesor,
                            'fecha': fecha, 'hora_inicio': h_ini, 'hora_fin': h_fin,
                            'horas': horas, 'estado': 'Planificado',
                            'encargado_apertura': encargado, 'precio_hora': precio_est,
                            'valor_total': valor_inicial, 'cobro_por_sesion': es_terapia,
                            'estudiante_id': int(eid), 'usuario_id': int(current_user.id),
                            'sesion_grupo_id': grupo_id
                        }
                        try:
                            supabase.table('sesiones').insert(datos_sesion).execute()
                        except Exception:
                            datos_sesion.pop('sesion_grupo_id', None)
                            supabase.table('sesiones').insert(datos_sesion).execute()
                        est_info = supabase.table('estudiantes').select('apellidos, nombres').eq('id', int(eid)).execute()
                        if est_info.data:
                            nombre_completo = f"{est_info.data[0]['apellidos']} {est_info.data[0]['nombres']}"
                            if nombre_completo not in estudiantes_nombres:
                                estudiantes_nombres.append(nombre_completo)
                
                if crear_evento_calendar and estudiantes_nombres:
                    try:
                        evento_id = crear_evento_calendar({
                            'asignatura': asignatura or 'Sesión', 'profesor': profesor,
                            'estudiantes': ', '.join(estudiantes_nombres),
                            'fecha': fecha, 'hora_inicio': h_ini, 'hora_fin': h_fin,
                            'encargado_apertura': encargado,
                            'valor_total': valor_inicial
                        })
                        if evento_id:
                            for est_num in range(1, num_estudiantes + 1):
                                eid = request.form.get(f'estudiante_id_{est_num}', '')
                                if eid and eid != 'nuevo':
                                    supabase.table('sesiones').update({'evento_calendar_id': evento_id}).eq('estudiante_id', int(eid)).eq('fecha', fecha).eq('hora_inicio', h_ini).execute()
                    except:
                        pass
            
            flash(f'✅ {num_sesiones} sesión(es) para {num_estudiantes} estudiante(s)', 'success')
            return redirect(url_for('modulo2', fecha=primera_fecha or str(date.today())))
        except Exception as e:
            flash(f'❌ Error: {str(e)}', 'error')
        return redirect(url_for('modulo1'))
    
    estudiantes = supabase.table('estudiantes').select('*').eq('activo', True).order('apellidos').execute()
    return render_template('modulo1.html', estudiantes=estudiantes.data or [],
                         asignaturas=cargar_asignaturas(), atencion_psicologica=psicologia,
                         precios_clase=precios_clase, precios_matricula=precios_matricula,
                         precios_pension=precios_pension, profesores=cargar_profesores(),
                         encargados=ENCARGADOS, today=date.today())

# ========== EDITOR DE PLANIFICACIONES ==========
@app.route('/editar-planificaciones')
@login_required
@socio_admin_required
def editar_planificaciones():
    psicologia, precios_clase, _, _ = cargar_costos()
    estudiantes = supabase.table('estudiantes').select('*').eq('activo', True).order('apellidos').execute()
    return render_template('editar_planificaciones.html', 
                         estudiantes=estudiantes.data or [],
                         asignaturas=cargar_asignaturas(),
                         atencion_psicologica=psicologia,
                         precios_clase=precios_clase,
                         profesores=cargar_profesores(),
                         encargados=ENCARGADOS,
                         today=date.today().isoformat())

@app.route('/editar-planificacion-masiva')
@login_required
@socio_admin_required
def editar_planificacion_masiva():
    psicologia, precios_clase, _, _ = cargar_costos()
    estudiantes = supabase.table('estudiantes').select('*').eq('activo', True).order('apellidos').execute()
    return render_template('editar_planificacion_masiva.html',
                         estudiantes=estudiantes.data or [],
                         asignaturas=cargar_asignaturas(),
                         atencion_psicologica=psicologia,
                         precios_clase=precios_clase,
                         profesores=cargar_profesores(),
                         encargados=ENCARGADOS,
                         today=date.today().isoformat())

# ========== API PARA EDITAR ==========
@app.route('/api/sesiones/todas')
@login_required
def api_sesiones_todas():
    sesiones = supabase.table('sesiones').select('*, estudiantes(apellidos, nombres)').order('fecha', desc=True).execute()
    resultado = []
    for s in (sesiones.data or []):
        est = s.get('estudiantes', {})
        resultado.append({
            'id': s['id'],
            'fecha': s.get('fecha', ''),
            'hora_inicio': s.get('hora_inicio', '')[:5] if s.get('hora_inicio') else '',
            'hora_fin': s.get('hora_fin', '')[:5] if s.get('hora_fin') else '',
            'estudiante_id': s.get('estudiante_id'),
            'estudiante_nombre': f"{est.get('apellidos', '')} {est.get('nombres', '')}".strip(),
            'tipo_sesion': s.get('tipo_sesion', ''),
            'asignatura': s.get('asignatura', ''),
            'tema_terapia': s.get('tema_terapia', ''),
            'profesor_terapeuta': s.get('profesor_terapeuta', ''),
            'encargado_apertura': s.get('encargado_apertura', ''),
            'estado': s.get('estado', 'Planificado'),
            'observaciones': s.get('observaciones', ''),
            'valor_total': s.get('valor_total', 0),
            'precio_hora': s.get('precio_hora', 10)
        })
    return jsonify(resultado)

@app.route('/api/sesiones/para-sincronizar')
@login_required
def api_sesiones_para_sincronizar():
    """Devuelve las sesiones en estado 'Realizado' listas para sincronizar con Google Calendar.
    Acepta filtros opcionales ?mes=&anio= para limitar a un mes concreto."""
    mes = request.args.get('mes')
    anio = request.args.get('anio')
    query = supabase.table('sesiones').select('id, fecha, hora_inicio, hora_fin').eq('estado', 'Realizado')
    if mes and anio:
        try:
            mes_i, anio_i = int(mes), int(anio)
            ultimo_dia = monthrange(anio_i, mes_i)[1]
            query = query.gte('fecha', f"{anio_i:04d}-{mes_i:02d}-01").lte('fecha', f"{anio_i:04d}-{mes_i:02d}-{ultimo_dia:02d}")
        except (ValueError, TypeError):
            pass
    sesiones = query.order('fecha').execute()
    resultado = [
        {'id': s['id'], 'fecha': s.get('fecha', '')}
        for s in (sesiones.data or [])
        if s.get('fecha') and s.get('hora_inicio') and s.get('hora_fin')
    ]
    return jsonify(resultado)

@app.route('/api/estudiante/<int:id>/sesiones')
@login_required
def api_estudiante_sesiones(id):
    sesiones = supabase.table('sesiones').select('id, fecha, hora_inicio, hora_fin, tipo_sesion, valor_total, asignatura, tema_terapia').eq('estudiante_id', id).order('fecha', desc=True).execute()
    resultado = []
    for s in (sesiones.data or []):
        resultado.append({
            'id': s['id'],
            'fecha': s.get('fecha'),
            'hora_inicio': (s.get('hora_inicio') or '')[:5],
            'hora_fin': (s.get('hora_fin') or '')[:5],
            'tipo_sesion': s.get('tipo_sesion'),
            'valor_total': s.get('valor_total', 0),
            'asignatura': s.get('asignatura', ''),
            'tema_terapia': s.get('tema_terapia', '')
        })
    return jsonify(resultado)

@app.route('/api/sesion/<int:id>')
@login_required
def api_sesion_unica(id):
    s = supabase.table('sesiones').select('*').eq('id', id).execute()
    if not s.data:
        return jsonify({'error': 'No encontrada'}), 404
    sesion = s.data[0]
    if sesion.get('hora_inicio'):
        sesion['hora_inicio'] = sesion['hora_inicio'][:5]
    if sesion.get('hora_fin'):
        sesion['hora_fin'] = sesion['hora_fin'][:5]
    return jsonify(sesion)

@app.route('/api/sesion/<int:id>/editar', methods=['POST'])
@login_required
def api_editar_sesion(id):
    try:
        data = request.get_json()
        responsable = data.get('responsable', current_user.nombre)
        
        hora_inicio = data['hora_inicio'].split(':')[:2]
        hora_fin = data['hora_fin'].split(':')[:2]
        hora_inicio_str = f"{hora_inicio[0]}:{hora_inicio[1]}"
        hora_fin_str = f"{hora_fin[0]}:{hora_fin[1]}"
        
        inicio = datetime.strptime(f"{data['fecha']} {hora_inicio_str}", '%Y-%m-%d %H:%M')
        fin = datetime.strptime(f"{data['fecha']} {hora_fin_str}", '%Y-%m-%d %H:%M')
        horas = round((fin - inicio).total_seconds() / 3600, 2)
        
        if horas < 0:
            return jsonify({'success': False, 'error': 'Horario en retroceso: la hora de fin no puede ser anterior al inicio'})
        if horas == 0:
            return jsonify({'success': False, 'error': 'La duración de la sesión no puede ser 0 horas'})
        if horas < 0.5:
            return jsonify({'success': False, 'error': f'Duración muy corta ({int(horas*60)} min). El mínimo es 30 minutos'})
        if not data.get('estudiante_id'):
            return jsonify({'success': False, 'error': 'Debe seleccionar un estudiante'})
        if not (data.get('profesor_terapeuta') or '').strip():
            return jsonify({'success': False, 'error': 'Debe indicar el profesor/terapeuta'})
        if not (data.get('encargado_apertura') or '').strip():
            return jsonify({'success': False, 'error': 'Debe indicar el encargado de apertura'})

        valor_total = data.get('valor_total', 0)
        precio_hora = data.get('precio_hora', 10)
        es_terapia = data['tipo_sesion'] in ['terapia', 'ambos']
        
        if es_terapia:
            if not data.get('tema_terapia') or data.get('tema_terapia', '').strip() == '':
                return jsonify({'success': False, 'error': 'Debe seleccionar un tipo de atención psicológica (costo)'})
        else:
            if not precio_hora or precio_hora == 0:
                return jsonify({'success': False, 'error': 'Debe seleccionar un precio por hora (costo)'})
        
        updates = {
            'fecha': data['fecha'],
            'hora_inicio': hora_inicio_str,
            'hora_fin': hora_fin_str,
            'horas': horas,
            'tipo_sesion': data['tipo_sesion'],
            'estudiante_id': data['estudiante_id'],
            'asignatura': data.get('asignatura', ''),
            'tema_terapia': data.get('tema_terapia', ''),
            'profesor_terapeuta': data['profesor_terapeuta'],
            'encargado_apertura': data['encargado_apertura'],
            'estado': data.get('estado', 'Planificado'),
            'observaciones': data.get('observaciones', ''),
            'valor_total': valor_total,
            'precio_hora': precio_hora,
            'cobro_por_sesion': es_terapia
        }
        
        supabase.table('sesiones').update(updates).eq('id', id).execute()

        supabase.table('correcciones_pagos').insert({
            'pago_id': id,
            'monto_anterior': 0,
            'monto_nuevo': valor_total,
            'cambiado_por': responsable,
            'motivo': f'EDICION SESION #{id}'
        }).execute()

        # Auto-sincronizar el evento de Google Calendar con los datos editados
        try:
            _sincronizar_sesion_en_calendar(id)
        except Exception as e:
            print(f'⚠️ Auto-sync calendar (editar) sesión {id}: {e}')

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/sesion/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar_sesion(id):
    try:
        # Borrar primero el evento del Google Calendar (si existe) antes de eliminar la fila
        try:
            ses = supabase.table('sesiones').select('evento_calendar_id').eq('id', id).execute()
            if ses.data:
                ev_id = ses.data[0].get('evento_calendar_id')
                if ev_id:
                    eliminar_evento_calendar(ev_id)
        except Exception as e:
            print(f'⚠️ No se pudo eliminar evento de Calendar al borrar sesión {id}: {e}')
        supabase.table('sesiones').delete().eq('id', id).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

def _sincronizar_sesion_en_calendar(id):
    """Sincroniza el evento de Google Calendar de una sesión de forma GRUPAL:
    todas las filas que comparten la misma sesión física (mismo sesion_grupo_id,
    o mismo profesor+fecha+horario) comparten UN solo evento.
      - Si TODAS las filas del grupo están 'Cancelado' → elimina el evento.
      - Si hay al menos una activa → crea/actualiza el evento con los datos
        actuales (fecha, hora, profesor, estudiantes activos) y guarda el mismo
        evento_calendar_id en todas las filas del grupo.
    Devuelve (evento_id|'eliminado'|None, error|None)."""
    base = supabase.table('sesiones').select('*, estudiantes(apellidos, nombres)').eq('id', id).execute()
    if not base.data:
        return None, 'Sesión no encontrada'
    s = base.data[0]
    # Hermanos del mismo grupo físico
    gid = s.get('sesion_grupo_id')
    try:
        if gid:
            grp = supabase.table('sesiones').select('*, estudiantes(apellidos, nombres)').eq('sesion_grupo_id', gid).execute().data or [s]
        else:
            grp = supabase.table('sesiones').select('*, estudiantes(apellidos, nombres)').eq(
                'profesor_terapeuta', s.get('profesor_terapeuta')).eq('fecha', s.get('fecha')).eq(
                'hora_inicio', s.get('hora_inicio')).eq('hora_fin', s.get('hora_fin')).execute().data or [s]
    except Exception:
        grp = [s]
    sibling_ids = [g['id'] for g in grp]
    ev_id = next((g.get('evento_calendar_id') for g in grp if g.get('evento_calendar_id')), None)
    activos = [g for g in grp if (g.get('estado') or '') != 'Cancelado']

    # Toda la clase cancelada → eliminar el evento y limpiar los ids
    if not activos:
        if ev_id:
            try:
                eliminar_evento_calendar(ev_id)
            except Exception as e:
                print(f'⚠️ Error eliminando evento cancelado de Calendar (sesión {id}): {e}')
        for sid in sibling_ids:
            supabase.table('sesiones').update({'evento_calendar_id': None}).eq('id', sid).execute()
        return 'eliminado', None

    # Representante: la sesión modificada si sigue activa; si no, la primera activa
    rep = s if (s.get('estado') or '') != 'Cancelado' else activos[0]
    if not rep.get('fecha') or not rep.get('hora_inicio') or not rep.get('hora_fin'):
        return None, 'Faltan datos (fecha u horario)'
    nombres = []
    for g in activos:
        est = g.get('estudiantes') or {}
        nom = f"{est.get('apellidos', '')} {est.get('nombres', '')}".strip()
        if nom and nom not in nombres:
            nombres.append(nom)
    encargado = (rep.get('encargado_apertura') or '').strip() or 'Por definir'
    asignatura = (rep.get('asignatura') or rep.get('tema_terapia') or 'Sesión')[:50]
    evento_id = crear_o_actualizar_evento_calendar({
        'asignatura': asignatura,
        'profesor': (rep.get('profesor_terapeuta') or 'Profesor')[:50],
        'estudiantes': ', '.join(nombres)[:200],
        'fecha': str(rep['fecha']),
        'hora_inicio': (rep.get('hora_inicio') or '')[:5],
        'hora_fin': (rep.get('hora_fin') or '')[:5],
        'encargado_apertura': encargado,
        'valor_total': sum(g.get('valor_total', 0) or 0 for g in activos)
    }, ev_id)
    if evento_id:
        for g in grp:
            if g.get('evento_calendar_id') != evento_id:
                supabase.table('sesiones').update({'evento_calendar_id': evento_id}).eq('id', g['id']).execute()
        return evento_id, None
    return None, 'No se pudo crear/actualizar el evento en Google Calendar'

@app.route('/api/sesion/<int:id>/toggle', methods=['POST'])
@login_required
def toggle_sesion(id):
    data = request.get_json()
    estado = data.get('estado', 'Realizado')
    updates = {'estado': estado}
    
    if estado in ['Realizado', 'Cancelado-Pagado']:
        s = supabase.table('sesiones').select('*').eq('id', id).execute()
        if s.data:
            sd = s.data[0]
            tipo_sesion = sd.get('tipo_sesion', 'clase')
            horas = sd.get('horas', 1) or 1
            precio_hora = sd.get('precio_hora', 10) or 10

            # Valor que paga el estudiante
            if sd.get('cobro_por_sesion') or tipo_sesion in ['terapia', 'ambos']:
                valor_total_sesion = precio_hora  # tarifa por sesión
            else:
                valor_total_sesion = round(horas * precio_hora, 2)

            # Pago al docente:
            #  - Clases realizadas: $7/h
            #  - Clases Cancelado-Pagado: valor FIJO de $5 por clase (no por hora)
            #  - Terapia: 40.18% del valor (igual en realizado/cancelado-pagado)
            if tipo_sesion in ['clase', 'preuniversitario']:
                if estado == 'Cancelado-Pagado':
                    pago_docente = PAGO_DOCENCIA_CANCELADO
                else:
                    pago_docente = round(horas * PAGO_DOCENCIA_POR_HORA, 2)
            else:
                pago_docente = round(valor_total_sesion * PORCENTAJE_PSICOLOGIA, 2)

            valor_atlas = round(valor_total_sesion - pago_docente, 2)

            updates['valor_total'] = valor_total_sesion
            updates['valor_pagar_docente'] = pago_docente
            updates['valor_atlas'] = valor_atlas
    elif estado == 'Cancelado':
        updates['valor_total'] = 0
        updates['valor_pagar_docente'] = 0
        updates['valor_atlas'] = 0
    
    supabase.table('sesiones').update(updates).eq('id', id).execute()

    # Auto-sincronizar con Google Calendar: refleja el nuevo estado (realizado/cancelado) en el calendario
    try:
        _sincronizar_sesion_en_calendar(id)
    except Exception as e:
        print(f'⚠️ Auto-sync calendar (toggle) sesión {id}: {e}')

    return jsonify({'success': True})

@app.route('/api/sesion/<int:id>/sincronizar', methods=['POST'])
@login_required
def sincronizar_calendario(id):
    try:
        evento_id, error = _sincronizar_sesion_en_calendar(id)
        if evento_id:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': error or 'No se pudo sincronizar'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ========== MÓDULO 2: CALENDARIO ==========
@app.route('/modulo2')
@login_required
def modulo2():
    fecha = request.args.get('fecha', str(date.today()))
    estudiantes_lista = supabase.table('estudiantes').select('*').eq('activo', True).order('apellidos').execute().data or []
    if current_user.rol in ['admin', 'socio']:
        sesiones = supabase.table('sesiones').select('*, estudiantes(*)').eq('fecha', fecha).order('hora_inicio').execute()
        return render_template('modulo2.html', sesiones=sesiones.data or [], fecha=fecha,
                             estudiantes=estudiantes_lista, profesores=cargar_profesores())
    
    nombre_usuario = current_user.nombre.strip().lower()
    todas = supabase.table('sesiones').select('*, estudiantes(*)').eq('fecha', fecha).order('hora_inicio').execute()
    sesiones_filtradas = []
    for s in (todas.data or []):
        profesor = (s.get('profesor_terapeuta') or '').strip().lower()
        if nombre_usuario in profesor or profesor in nombre_usuario:
            sesiones_filtradas.append(s)
    return render_template('modulo2.html', sesiones=sesiones_filtradas, fecha=fecha,
                         estudiantes=estudiantes_lista, profesores=cargar_profesores())

@app.route('/api/sesion/<int:id>/modificar', methods=['POST'])
@login_required
def modificar_sesion(id):
    try:
        data = request.get_json()
        fecha = data.get('fecha')
        h_ini = data.get('hora_inicio', '')[:5]
        h_fin = data.get('hora_fin', '')[:5]
        if h_fin <= h_ini:
            return jsonify({'success': False, 'error': 'La hora de fin debe ser mayor a la hora de inicio'})
        inicio = datetime.strptime(f"{fecha} {h_ini}", '%Y-%m-%d %H:%M')
        fin = datetime.strptime(f"{fecha} {h_fin}", '%Y-%m-%d %H:%M')
        horas = round((fin - inicio).total_seconds() / 3600, 2)
        supabase.table('sesiones').update({'fecha': fecha, 'hora_inicio': h_ini, 'hora_fin': h_fin, 'horas': horas}).eq('id', id).execute()
        try:
            _sincronizar_sesion_en_calendar(id)
        except Exception as e:
            print(f'⚠️ Auto-sync calendar (modificar) sesión {id}: {e}')
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/sesion/<int:id>/cambiar-estudiante', methods=['POST'])
@login_required
def cambiar_estudiante_sesion(id):
    try:
        data = request.get_json()
        estudiante_id = data.get('estudiante_id')
        if estudiante_id == 'nuevo':
            result = supabase.table('estudiantes').insert({
                'nombres': data.get('nuevo_nombre', ''), 'apellidos': data.get('nuevo_apellido', ''),
                'nivel_curso': data.get('nuevo_nivel', ''), 'procedencia': data.get('nuevo_procedencia', ''),
                'activo': True, 'usuario_id': current_user.id
            }).execute()
            if result.data:
                estudiante_id = result.data[0]['id']
            else:
                return jsonify({'success': False, 'error': 'No se pudo crear'})
        supabase.table('sesiones').update({'estudiante_id': int(estudiante_id)}).eq('id', id).execute()
        try:
            _sincronizar_sesion_en_calendar(id)
        except Exception as e:
            print(f'⚠️ Auto-sync calendar (cambiar-estudiante) sesión {id}: {e}')
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/sesion/<int:id>/cambiar-profesor', methods=['POST'])
@login_required
def cambiar_profesor_sesion(id):
    try:
        data = request.get_json()
        nuevo_profesor = data.get('profesor', '')
        supabase.table('sesiones').update({'profesor_terapeuta': nuevo_profesor}).eq('id', id).execute()
        try:
            _sincronizar_sesion_en_calendar(id)
        except Exception as e:
            print(f'⚠️ Auto-sync calendar (cambiar-profesor) sesión {id}: {e}')
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/sesiones/pendientes')
@login_required
def api_sesiones_pendientes():
    query = supabase.table('sesiones').select('*, estudiantes(*)').eq('estado', 'Planificado')
    if current_user.rol in ['admin', 'socio']:
        sesiones = query.order('fecha').order('hora_inicio').execute()
        sesiones_data = sesiones.data or []
    else:
        todas = query.order('fecha').order('hora_inicio').execute()
        sesiones_data = []
        nombre_usuario = current_user.nombre.strip().lower()
        for s in (todas.data or []):
            profesor = (s.get('profesor_terapeuta') or '').strip().lower()
            if nombre_usuario in profesor or profesor in nombre_usuario:
                sesiones_data.append(s)
    
    resultado = []
    for s in sesiones_data:
        est = s.get('estudiantes', {})
        resultado.append({
            'id': s['id'],
            'fecha': s['fecha'],
            'hora_inicio': s['hora_inicio'],
            'hora_fin': s['hora_fin'],
            'estudiante': f"{est.get('apellidos', '')} {est.get('nombres', '')}",
            'tipo_sesion': s['tipo_sesion'],
            'asignatura': s.get('asignatura', ''),
            'profesor_terapeuta': s['profesor_terapeuta']
        })
    return jsonify(resultado)

# ========== MÓDULO 3: PAGOS ==========
@app.route('/modulo3', methods=['GET', 'POST'])
@login_required
@socio_admin_required
def modulo3():
    if request.method == 'POST':
        accion = request.form.get('accion', 'pagar')
        if accion == 'pagar':
            supabase.table('pagos').insert({
                'fecha_pago': request.form['fecha_pago'], 'monto': float(request.form['monto']),
                'tipo_pago': request.form.get('tipo_pago', 'efectivo'),
                'concepto': request.form.get('concepto', ''),
                'estudiante_id': int(request.form['estudiante_id']), 'usuario_id': int(current_user.id)
            }).execute()
            flash('✅ Pago registrado', 'success')
        elif accion == 'corregir':
            pago_id = int(request.form['pago_id'])
            nuevo_monto = float(request.form['nuevo_monto'])
            cambiado_por = request.form.get('cambiado_por', current_user.nombre)
            motivo = request.form['motivo']
            updates = {'monto': nuevo_monto}
            if request.form.get('fecha_pago'):
                updates['fecha_pago'] = request.form['fecha_pago']
            if request.form.get('tipo_pago'):
                updates['tipo_pago'] = request.form['tipo_pago']
            updates['concepto'] = request.form.get('concepto', '')
            supabase.table('pagos').update(updates).eq('id', pago_id).execute()
            supabase.table('correcciones_pagos').insert({
                'pago_id': pago_id, 'monto_anterior': 0, 'monto_nuevo': nuevo_monto,
                'cambiado_por': cambiado_por, 'motivo': motivo
            }).execute()
            flash('✅ Pago editado correctamente', 'success')
        elif accion == 'eliminar_pago':
            pago_id = int(request.form['pago_id'])
            supabase.table('pagos').delete().eq('id', pago_id).execute()
            flash('🗑️ Pago eliminado', 'info')
        elif accion == 'editar_sesion':
            sesion_id = int(request.form['sesion_id'])
            nueva_fecha = request.form['nueva_fecha']
            nueva_h_ini = request.form['nueva_hora_inicio']
            nueva_h_fin = request.form['nueva_hora_fin']
            if nueva_h_fin <= nueva_h_ini:
                flash('❌ Error: La hora de fin debe ser mayor a la hora de inicio', 'error')
                return redirect(url_for('modulo3'))
            supabase.table('sesiones').update({
                'fecha': nueva_fecha, 'hora_inicio': nueva_h_ini, 'hora_fin': nueva_h_fin
            }).eq('id', sesion_id).execute()
            try:
                _sincronizar_sesion_en_calendar(sesion_id)
            except Exception as e:
                print(f'⚠️ Auto-sync calendar (modulo3 editar_sesion) sesión {sesion_id}: {e}')
            flash('✅ Sesión actualizada', 'success')
        elif accion == 'devolucion':
            try:
                pagar_docente = request.form.get('pagar_docente') == 'true'
                crear_devolucion(
                    tipo_cliente='estudiante',
                    estudiante_id=int(request.form['estudiante_id']),
                    fecha=request.form.get('fecha') or date.today().isoformat(),
                    monto=float(request.form.get('monto', 0) or 0),
                    tipo_pago=request.form.get('tipo_pago', 'efectivo'),
                    motivo=(request.form.get('motivo', '') or '').strip(),
                    pagar_docente=pagar_docente,
                    docente_nombre=(request.form.get('docente_nombre', '') or '').strip() or None,
                    monto_docente=request.form.get('monto_docente', 0),
                    registrado_por=current_user.nombre
                )
                flash('✅ Devolución registrada (baja el ingreso del estudiante)', 'success')
            except Exception as e:
                flash(f'❌ Error al registrar la devolución: {e}', 'error')
        return redirect(url_for('modulo3'))
    
    filtro_fecha = request.args.get('filtro_fecha', str(date.today()))
    filtro_estudiante = request.args.get('filtro_estudiante', '').strip()
    filtro_docente = request.args.get('filtro_docente', '').strip()

    # Sesiones del día para registro rápido
    ses_dia_res = supabase.table('sesiones').select(
        '*, estudiantes(nombres,apellidos)'
    ).eq('fecha', filtro_fecha).order('hora_inicio').execute()
    sesiones_dia = ses_dia_res.data or []
    if filtro_docente:
        sesiones_dia = [s for s in sesiones_dia if filtro_docente.lower() in (s.get('profesor_terapeuta') or '').lower()]

    # Docentes disponibles para el filtro
    all_docs_res = supabase.table('sesiones').select('profesor_terapeuta').in_(
        'estado', ['Realizado', 'Cancelado-Pagado', 'Planificado']
    ).execute()
    all_profesores = sorted(set(s['profesor_terapeuta'] for s in (all_docs_res.data or []) if s.get('profesor_terapeuta')))

    estudiantes = supabase.table('estudiantes').select('*').eq('activo', True).order('apellidos').execute()
    datos = []
    for e in (estudiantes.data or []):
        nombre_completo = f"{e['apellidos']} {e['nombres']}"
        if filtro_estudiante and filtro_estudiante.lower() not in nombre_completo.lower():
            continue
        ses = supabase.table('sesiones').select('*').eq('estudiante_id', e['id']).in_('estado', ['Realizado', 'Cancelado-Pagado']).execute()
        pag = supabase.table('pagos').select('*').eq('estudiante_id', e['id']).order('fecha_pago', desc=True).execute()
        cobrar = sum(s.get('valor_total', 0) or 0 for s in (ses.data or []) if s.get('estado') in ['Realizado', 'Cancelado-Pagado'])
        pagado = sum(p.get('monto', 0) or 0 for p in (pag.data or []))
        devuelto = devoluciones_por_estudiante(e['id'])
        pagado_neto = pagado - devuelto
        if cobrar > 0 or pagado > 0 or devuelto > 0:
            datos.append({'id': e['id'], 'nombre': nombre_completo, 'cobrar': cobrar,
                          'pagado': pagado, 'devuelto': devuelto, 'pagado_neto': pagado_neto,
                          'saldo': cobrar - pagado_neto, 'pagos': pag.data or [], 'sesiones': ses.data or []})
    return render_template('modulo3.html', estudiantes=datos, today=date.today(),
                           sesiones_dia=sesiones_dia, filtro_fecha=filtro_fecha,
                           filtro_estudiante=filtro_estudiante, filtro_docente=filtro_docente,
                           all_profesores=all_profesores)

# ========== MÓDULO 4: CALENDARIO PÚBLICO ==========
@app.route('/modulo4')
@login_required
def modulo4():
    sesiones = supabase.table('sesiones').select('*, estudiantes(*)').gte('fecha', str(date.today())).order('fecha').execute()
    reuniones = []
    if current_user.rol in ['admin', 'socio']:
        reuniones = supabase.table('reuniones').select('*').gte('fecha', str(date.today())).order('fecha').execute()
    estudiantes_lista = supabase.table('estudiantes').select('*').eq('activo', True).order('apellidos').execute().data or []
    return render_template('modulo4.html', sesiones=sesiones.data or [], reuniones=reuniones.data if reuniones else [],
                         estudiantes=estudiantes_lista, profesores=cargar_profesores())

# ========== MÓDULO 5: PAGOS DOCENTES ==========
@app.route('/modulo5')
@login_required
def modulo5():
    if current_user.rol in ['profesor', 'psicologo']:
        return redirect(url_for('mi_reporte'))
    
    mes = request.args.get('mes', '')
    anio = request.args.get('anio', '')
    fecha_desde = request.args.get('fecha_desde', '')
    fecha_hasta = request.args.get('fecha_hasta', '')
    filtro_profesor = request.args.get('filtro_profesor', '')
    filtro_estudiante = request.args.get('filtro_estudiante', '')
    
    query = supabase.table('sesiones').select('*, estudiantes(*)').in_('estado', ['Realizado', 'Cancelado-Pagado'])
    
    if mes and mes != '':
        mes_int = int(mes)
        anio_int = int(anio) if anio else date.today().year
        fecha_inicio = f"{anio_int}-{mes_int:02d}-01"
        ultimo_dia = monthrange(anio_int, mes_int)[1]
        fecha_fin = f"{anio_int}-{mes_int:02d}-{ultimo_dia}"
        query = query.gte('fecha', fecha_inicio).lte('fecha', fecha_fin)
    
    if fecha_desde:
        query = query.gte('fecha', fecha_desde)
    if fecha_hasta:
        query = query.lte('fecha', fecha_hasta)
    
    sesiones = query.order('fecha', desc=True).execute()
    sesiones_data = sesiones.data or []
    
    if filtro_profesor and filtro_profesor != '' and current_user.rol in ['admin', 'socio']:
        sesiones_filtradas = []
        for s in sesiones_data:
            if filtro_profesor.lower() in s.get('profesor_terapeuta', '').lower():
                sesiones_filtradas.append(s)
        sesiones_data = sesiones_filtradas
    
    if filtro_estudiante and filtro_estudiante != '':
        sesiones_filtradas_est = []
        for s in sesiones_data:
            est = s.get('estudiantes', {})
            nombre_est = f"{est.get('apellidos', '')} {est.get('nombres', '')}".lower()
            if filtro_estudiante.lower() in nombre_est:
                sesiones_filtradas_est.append(s)
        sesiones_data = sesiones_filtradas_est
    
    anticipos = supabase.table('anticipos_solicitudes').select('*').eq('estado', 'aprobado').execute()
    anticipos_por_docente = {}
    for a in (anticipos.data or []):
        docente = a.get('usuario_nombre', '')
        anticipos_por_docente[docente] = anticipos_por_docente.get(docente, 0) + a.get('monto', 0)
    
    # Mapa grupo_id → lista de estudiantes (antes del dedup)
    estudiantes_por_grupo = {}
    for _s in sesiones_data:
        _gid = str(_s.get('sesion_grupo_id') or '|'.join([
            str(_s.get('profesor_terapeuta','')), str(_s.get('fecha','')),
            str(_s.get('hora_inicio','')), str(_s.get('hora_fin',''))]))
        _est = _s.get('estudiantes') or {}
        _nom = f"{_est.get('apellidos','')} {_est.get('nombres','')}".strip()
        if _nom:
            if _gid not in estudiantes_por_grupo:
                estudiantes_por_grupo[_gid] = []
            if _nom not in estudiantes_por_grupo[_gid]:
                estudiantes_por_grupo[_gid].append(_nom)

    pagos = []
    total_docencia = 0
    total_psicologia = 0
    total_adeudado = 0
    consolidado = {}
    profesores_lista = set()

    sesiones_data = dedup_sesiones_docente(sesiones_data)

    for s in sesiones_data:
        horas = s.get('horas', 0) or 0
        valor = s.get('valor_total', 0) or 0
        tipo = s.get('tipo_sesion', 'clase')
        profesor = s.get('profesor_terapeuta', 'Desconocido')
        profesores_lista.add(profesor)
        estado = s.get('estado', '')
        
        if estado == 'Cancelado-Pagado':
            valor_pagar_docente = s.get('valor_pagar_docente', 0) or 0
            valor_atlas = s.get('valor_atlas', 0) or 0
            
            if tipo in ['clase', 'preuniversitario']:
                pago_docente = valor_pagar_docente
                pago_psicologia = 0
                total_docencia += pago_docente
            else:
                pago_docente = 0
                pago_psicologia = valor_pagar_docente
                total_psicologia += pago_psicologia
            
            total_pagar = pago_docente + pago_psicologia
        else:
            if tipo in ['clase', 'preuniversitario']:
                pago_docente = horas * PAGO_DOCENCIA_POR_HORA
                pago_psicologia = 0
                total_docencia += pago_docente
            else:
                pago_docente = 0
                pago_psicologia = valor * PORCENTAJE_PSICOLOGIA
                total_psicologia += pago_psicologia
            
            total_pagar = pago_docente + pago_psicologia
        
        total_adeudado += total_pagar
        
        est = s.get('estudiantes', {})
        _gid_key = str(s.get('sesion_grupo_id') or '|'.join([
            str(s.get('profesor_terapeuta','')), str(s.get('fecha','')),
            str(s.get('hora_inicio','')), str(s.get('hora_fin',''))]))
        todos_ests = estudiantes_por_grupo.get(_gid_key, [f"{est.get('apellidos','')} {est.get('nombres','')}".strip()])
        pagos.append({
            'fecha': s['fecha'],
            'profesor': profesor,
            'estudiante': f"{est.get('apellidos', '')} {est.get('nombres', '')}".title(),
            'todos_estudiantes': [e.title() for e in todos_ests],
            'es_grupal': len(todos_ests) > 1,
            'tipo': tipo,
            'horas': horas,
            'valor_total': valor,
            'pago_docente': pago_docente,
            'pago_psicologia': pago_psicologia,
            'total_pagar': total_pagar,
            'estado': estado
        })
        
        if profesor not in consolidado:
            consolidado[profesor] = {'pago_docencia': 0, 'pago_psicologia': 0, 'total_pagar': 0, 'anticipo': 0}
        consolidado[profesor]['pago_docencia'] += pago_docente
        consolidado[profesor]['pago_psicologia'] += pago_psicologia
        consolidado[profesor]['total_pagar'] += total_pagar
        consolidado[profesor]['anticipo'] = anticipos_por_docente.get(profesor, 0)
    
    total_anticipos = sum(anticipos_por_docente.values())
    total_neto = total_adeudado - total_anticipos
    
    return render_template('modulo5.html',
                         pagos=pagos,
                         total_docencia=total_docencia,
                         total_psicologia=total_psicologia,
                         total_adeudado=total_adeudado,
                         total_anticipos=total_anticipos,
                         total_neto=total_neto,
                         consolidado=consolidado,
                         profesores_lista=sorted(list(profesores_lista)) if current_user.rol in ['admin', 'socio'] else [],
                         mes=mes, anio=anio, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
                         filtro_profesor=filtro_profesor,
                         filtro_estudiante=filtro_estudiante)

# ========== MÓDULO 6: REUNIONES ==========
@app.route('/modulo6', methods=['GET', 'POST'])
@login_required
@socio_admin_required
def modulo6():
    if request.method == 'POST':
        try:
            edit_id = request.form.get('edit_id', '')
            datos = {
                'titulo': request.form.get('titulo_otro') or request.form['titulo'],
                'fecha': request.form['fecha'],
                'hora_inicio': request.form['hora_inicio'],
                'hora_fin': request.form['hora_fin'],
                'asistentes': request.form.get('asistentes', ''),
                'tema': request.form.get('tema', ''),
                'encargado': request.form.get('encargado_otro') or request.form.get('encargado', current_user.nombre),
                'usuario_id': current_user.id
            }
            if edit_id:
                supabase.table('reuniones').update(datos).eq('id', int(edit_id)).execute()
                flash('✅ Reunión actualizada', 'success')
            else:
                supabase.table('reuniones').insert(datos).execute()
                flash('✅ Reunión programada', 'success')
        except Exception as e:
            flash(f'❌ Error: {e}', 'error')
        return redirect(url_for('modulo6'))
    reuniones = supabase.table('reuniones').select('*').gte('fecha', str(date.today())).order('fecha').execute()
    return render_template('modulo6.html', reuniones=reuniones.data or [], today=date.today())

@app.route('/api/reunion/<int:id>/eliminar', methods=['POST'])
@login_required
@socio_admin_required
def eliminar_reunion(id):
    supabase.table('reuniones').delete().eq('id', id).execute()
    return jsonify({'success': True})

@app.route('/api/reunion/<int:id>/sincronizar', methods=['POST'])
@login_required
@socio_admin_required
def sincronizar_reunion(id):
    try:
        reunion = supabase.table('reuniones').select('*').eq('id', id).execute()
        if not reunion.data:
            return jsonify({'success': False, 'error': 'Reunión no encontrada'})
        r = reunion.data[0]
        if not r.get('fecha') or not r.get('hora_inicio') or not r.get('hora_fin'):
            return jsonify({'success': False, 'error': 'Faltan datos (fecha u horario)'})
        encargado = (r.get('encargado') or '').strip()
        evento_id = crear_o_actualizar_evento_calendar({
            'asignatura': f"{r.get('titulo') or 'Reunión'} - {r.get('tema') or ''}",
            'profesor': encargado,
            'estudiantes': r.get('asistentes') or '',
            'fecha': str(r['fecha']),
            'hora_inicio': str(r['hora_inicio'])[:5],
            'hora_fin': str(r['hora_fin'])[:5],
            'encargado_apertura': encargado[:10]
        }, r.get('evento_calendar_id'))
        if evento_id:
            supabase.table('reuniones').update({'evento_calendar_id': evento_id}).eq('id', id).execute()
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'No se pudo crear/actualizar el evento en Google Calendar'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ========== API ENCARGADOS ==========
@app.route('/api/encargados')
@login_required
def api_encargados():
    encargados = supabase.table('encargados').select('*').order('nombre').execute()
    return jsonify([e['nombre'] for e in (encargados.data or [])])

@app.route('/api/encargados/crear', methods=['POST'])
@login_required
def api_crear_encargado():
    data = request.get_json()
    nombre = data.get('nombre', '').strip().upper()
    if not nombre:
        return jsonify({'success': False, 'error': 'Nombre requerido'})
    try:
        supabase.table('encargados').insert({
            'nombre': nombre,
            'creado_por': current_user.id
        }).execute()
        return jsonify({'success': True, 'nombre': nombre})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ========== ADMINISTRACIÓN DE COSTOS ==========
@app.route('/admin/costos')
@login_required
@socio_admin_required  # ← CAMBIADO
def admin_costos():
    costos = supabase.table('costos_config').select('*').order('tipo').order('concepto').execute()
    return render_template('admin_costos.html', costos=costos.data or [])

@app.route('/api/costos/crear', methods=['POST'])
@login_required
@socio_admin_required  # ← CAMBIADO
def api_crear_costo():
    data = request.get_json()
    try:
        concepto = data['concepto'].strip()
        # Formato oración: primera mayúscula, resto minúsculas
        concepto = ' '.join([w[0].upper() + w[1:].lower() if len(w) > 1 else w.upper() for w in concepto.split()])
        
        supabase.table('costos_config').insert({
            'concepto': concepto,
            'tipo': data.get('tipo', 'servicio'),
            'precio': float(data['precio']),
            'creado_por': current_user.id,
            'nombre_modificador': current_user.nombre,
            'fecha_actualizacion': date.today().isoformat()
        }).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/costos/<int:id>/editar', methods=['POST'])
@login_required
@socio_admin_required  # ← CAMBIADO
def api_editar_costo(id):
    data = request.get_json()
    try:
        concepto = data['concepto'].strip()
        # Formato oración: primera mayúscula, resto minúsculas
        concepto = ' '.join([w[0].upper() + w[1:].lower() if len(w) > 1 else w.upper() for w in concepto.split()])
        
        supabase.table('costos_config').update({
            'concepto': concepto,
            'tipo': data.get('tipo', 'servicio'),
            'precio': float(data['precio']),
            'modificado_por': current_user.id,
            'nombre_modificador': current_user.nombre,
            'fecha_actualizacion': date.today().isoformat()
        }).eq('id', id).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/costos/<int:id>/toggle', methods=['POST'])
@login_required
@socio_admin_required  # ← CAMBIADO
def api_toggle_costo(id):
    costo = supabase.table('costos_config').select('activo').eq('id', id).execute()
    if costo.data:
        nuevo_estado = not costo.data[0].get('activo', True)
        supabase.table('costos_config').update({
            'activo': nuevo_estado,
            'modificado_por': current_user.id,
            'nombre_modificador': current_user.nombre,
            'fecha_actualizacion': date.today().isoformat()
        }).eq('id', id).execute()
        return jsonify({'success': True, 'activo': nuevo_estado})
    return jsonify({'success': False, 'error': 'No encontrado'})

# ========== ANTICIPOS ==========
@app.route('/mis-anticipos')
@login_required
def mis_anticipos():
    if current_user.rol not in ['profesor', 'psicologo', 'admin', 'socio']:
        flash('❌ Acceso restringido', 'error')
        return redirect(url_for('dashboard'))
    anticipos = supabase.table('anticipos_solicitudes').select('*').eq('usuario_id', current_user.id).order('fecha_solicitud', desc=True).execute()
    mes_actual = date.today().month
    anio_actual = date.today().year
    sesiones = supabase.table('sesiones').select('*').in_('estado', ['Realizado', 'Cancelado-Pagado']).eq('profesor_terapeuta', current_user.nombre).execute()
    total_pagar_mes = 0
    for s in dedup_sesiones_docente(sesiones.data or []):
        if s.get('fecha', '')[:7] == f"{anio_actual}-{mes_actual:02d}":
            tipo = s.get('tipo_sesion', 'clase')
            if s.get('estado') == 'Cancelado-Pagado':
                total_pagar_mes += s.get('valor_pagar_docente', 0) or 0
            elif tipo in ['clase', 'preuniversitario']:
                total_pagar_mes += (s.get('horas', 0) or 0) * PAGO_DOCENCIA_POR_HORA
            else:
                total_pagar_mes += (s.get('valor_total', 0) or 0) * PORCENTAJE_PSICOLOGIA
    anticipos_aprobados = sum(a.get('monto', 0) for a in (anticipos.data or []) if a.get('estado') == 'aprobado')
    return render_template('mis_anticipos.html',
                         anticipos=anticipos.data or [],
                         total_pagar_mes=total_pagar_mes,
                         anticipos_aprobados=anticipos_aprobados,
                         disponible=total_pagar_mes - anticipos_aprobados)

@app.route('/solicitar-anticipo', methods=['POST'])
@login_required
def solicitar_anticipo():
    if current_user.rol not in ['profesor', 'psicologo']:
        flash('❌ Solo docentes y psicólogos pueden solicitar anticipos', 'error')
        return redirect(url_for('dashboard'))
    try:
        supabase.table('anticipos_solicitudes').insert({
            'usuario_id': current_user.id, 'usuario_nombre': current_user.nombre,
            'monto': float(request.form['monto']), 'motivo': request.form['motivo'],
            'estado': 'pendiente', 'fecha_solicitud': date.today().isoformat()
        }).execute()
        flash('✅ Solicitud de anticipo enviada', 'success')
    except Exception as e:
        flash(f'❌ Error: {str(e)}', 'error')
    return redirect(url_for('mis_anticipos'))

@app.route('/gestion-anticipos')
@login_required
@socio_admin_required
def gestion_anticipos():
    solicitudes = supabase.table('anticipos_solicitudes').select('*').order('fecha_solicitud', desc=True).execute()
    return render_template('gestion_anticipos.html', solicitudes=solicitudes.data or [])

@app.route('/aprobar-anticipo/<int:id>', methods=['POST'])
@login_required
@socio_admin_required
def aprobar_anticipo(id):
    supabase.table('anticipos_solicitudes').update({'estado': 'aprobado', 'fecha_aprobacion': date.today().isoformat(), 'aprobado_por': current_user.nombre}).eq('id', id).execute()
    flash('✅ Anticipo aprobado', 'success')
    return redirect(url_for('gestion_anticipos'))

@app.route('/rechazar-anticipo/<int:id>', methods=['POST'])
@login_required
@socio_admin_required
def rechazar_anticipo(id):
    supabase.table('anticipos_solicitudes').update({'estado': 'rechazado', 'motivo_rechazo': request.form.get('motivo_rechazo', 'Sin motivo')}).eq('id', id).execute()
    flash('❌ Anticipo rechazado', 'info')
    return redirect(url_for('gestion_anticipos'))

# ========== CONTACTOS (solicitudes desde la landing) ==========
@app.route('/contactos')
@login_required
@socio_admin_required
def contactos_lista():
    try:
        contactos = supabase.table('contactos').select('*').order('fecha_registro', desc=True).execute().data or []
    except Exception as e:
        contactos = []
        flash(f'⚠️ No se pudo cargar contactos (¿falta ejecutar migration_contactos.sql?): {e}', 'warning')
    return render_template('contactos.html', contactos=contactos)

@app.route('/contacto/<int:id>/atender', methods=['POST'])
@login_required
@socio_admin_required
def atender_contacto(id):
    try:
        supabase.table('contactos').update({
            'estado': 'atendido', 'atendido_por': current_user.nombre,
            'fecha_atendido': date.today().isoformat()
        }).eq('id', id).execute()
        flash('✅ Contacto marcado como atendido', 'success')
    except Exception as e:
        flash(f'❌ Error: {e}', 'error')
    return redirect(url_for('contactos_lista'))

@app.route('/contacto/<int:id>/eliminar', methods=['POST'])
@login_required
@socio_admin_required
def eliminar_contacto(id):
    try:
        supabase.table('contactos').delete().eq('id', id).execute()
        flash('🗑️ Contacto eliminado', 'info')
    except Exception as e:
        flash(f'❌ Error: {e}', 'error')
    return redirect(url_for('contactos_lista'))

# ========== PSICOLOGÍA ESPECIAL ==========
@app.route('/psicologia-especial')
@login_required
@socio_admin_required
def psicologia_especial():
    clientes = supabase.table('clientes_externos').select('*').eq('activo', True).order('nombre').execute()
    citas = supabase.table('citas_psicologia').select('*, clientes_externos(*)').order('fecha', desc=True).execute()
    psicologos = supabase.table('usuarios').select('id, nombre').eq('rol', 'psicologo').eq('activo', True).execute()
    total_citas = len(citas.data or [])
    total_pagado = sum(c.get('monto_pagado', 0) or 0 for c in (citas.data or []))
    total_comision_centro = sum(c.get('comision_centro', 0) or 0 for c in (citas.data or []))
    return render_template('psicologia_especial.html',
                         clientes=clientes.data or [], citas=citas.data or [], psicologos=psicologos.data or [],
                         total_citas=total_citas, total_pagado=total_pagado, total_comision_centro=total_comision_centro,
                         comision_porcentaje=int(COMISION_CLIENTE_EXTERNO * 100), today=date.today().isoformat())

@app.route('/api/cliente-externo', methods=['POST'])
@login_required
@socio_admin_required
def crear_cliente_externo():
    data = request.get_json()
    result = supabase.table('clientes_externos').insert({
        'nombre': data['nombre'], 'telefono': data.get('telefono', ''), 'email': data.get('email', ''),
        'activo': True, 'usuario_id': current_user.id
    }).execute()
    return jsonify({'success': True, 'id': result.data[0]['id'] if result.data else None})

@app.route('/api/cita-psicologia', methods=['POST'])
@login_required
@socio_admin_required
def crear_cita_psicologia():
    data = request.get_json()
    valor_cita = data.get('valor', 0)
    comision_centro = valor_cita * COMISION_CLIENTE_EXTERNO
    result = supabase.table('citas_psicologia').insert({
        'cliente_id': data['cliente_id'], 'psicologo_id': data['psicologo_id'],
        'psicologo_nombre': data['psicologo_nombre'], 'fecha': data['fecha'],
        'hora_inicio': data['hora_inicio'], 'hora_fin': data['hora_fin'], 'valor': valor_cita,
        'monto_pagado': 0, 'comision_centro': comision_centro, 'pago_psicologo': valor_cita - comision_centro,
        'estado': 'agendada', 'usuario_id': current_user.id
    }).execute()
    return jsonify({'success': True, 'id': result.data[0]['id'] if result.data else None})

@app.route('/api/cita/<int:id>/pagar', methods=['POST'])
@login_required
@socio_admin_required
def registrar_pago_cita(id):
    data = request.get_json()
    cita = supabase.table('citas_psicologia').select('*').eq('id', id).execute()
    if not cita.data:
        return jsonify({'success': False, 'error': 'Cita no encontrada'})
    c = cita.data[0]
    nuevo_pagado = (c.get('monto_pagado', 0) or 0) + data.get('monto', 0)
    nuevo_estado = 'pagada' if nuevo_pagado >= c.get('valor', 0) else 'parcial'
    supabase.table('citas_psicologia').update({'monto_pagado': nuevo_pagado, 'estado': nuevo_estado}).eq('id', id).execute()
    return jsonify({'success': True, 'nuevo_estado': nuevo_estado, 'pagado': nuevo_pagado})

@app.route('/api/cita/<int:id>/completar', methods=['POST'])
@login_required
@socio_admin_required
def completar_cita(id):
    supabase.table('citas_psicologia').update({'estado': 'realizada', 'fecha_realizacion': date.today().isoformat()}).eq('id', id).execute()
    return jsonify({'success': True})

# ========== MIS CLIENTES (PSICÓLOGOS) ==========
@app.route('/mis-clientes')
@login_required
def mis_clientes():
    if current_user.rol != 'psicologo':
        flash('❌ Solo psicólogos pueden acceder', 'error')
        return redirect(url_for('dashboard'))
    clientes = supabase.table('clientes_externos').select('*').eq('psicologo_id', current_user.id).eq('activo', True).order('nombre').execute()
    citas = supabase.table('citas_psicologia').select('*, clientes_externos(*)').eq('psicologo_id', current_user.id).order('fecha', desc=True).execute()
    return render_template('mis_clientes.html',
                         clientes=clientes.data or [], citas=citas.data or [],
                         today=date.today().isoformat())

@app.route('/api/mi-cliente', methods=['POST'])
@login_required
def crear_mi_cliente():
    if current_user.rol != 'psicologo':
        return jsonify({'success': False, 'error': 'Solo psicólogos pueden crear clientes'})
    data = request.get_json()
    result = supabase.table('clientes_externos').insert({
        'nombre': data['nombre'], 'telefono': data.get('telefono', ''), 'email': data.get('email', ''),
        'psicologo_id': current_user.id, 'psicologo_nombre': current_user.nombre,
        'activo': True, 'usuario_id': current_user.id
    }).execute()
    return jsonify({'success': True, 'id': result.data[0]['id'] if result.data else None})

@app.route('/api/mi-cita', methods=['POST'])
@login_required
def crear_mi_cita():
    if current_user.rol != 'psicologo':
        return jsonify({'success': False, 'error': 'Solo psicólogos pueden agendar citas'})
    data = request.get_json()
    valor_cita = data.get('valor', 0)
    comision_centro = valor_cita * COMISION_CLIENTE_EXTERNO
    result = supabase.table('citas_psicologia').insert({
        'cliente_id': data['cliente_id'], 'psicologo_id': current_user.id,
        'psicologo_nombre': current_user.nombre, 'fecha': data['fecha'],
        'hora_inicio': data['hora_inicio'], 'hora_fin': data['hora_fin'], 'valor': valor_cita,
        'monto_pagado': 0, 'comision_centro': comision_centro, 'pago_psicologo': valor_cita - comision_centro,
        'estado': 'agendada', 'usuario_id': current_user.id
    }).execute()
    return jsonify({'success': True, 'id': result.data[0]['id'] if result.data else None})

# ========== REPORTES ==========
@app.route('/reportes')
@login_required
@socio_admin_required
def reportes():
    mes = int(request.args.get('mes', date.today().month))
    anio = int(request.args.get('anio', date.today().year))
    estudiantes = supabase.table('estudiantes').select('*').eq('activo', True).order('apellidos').execute()
    
    datos_estudiantes = []
    datos_ingresos = []          # reporte de ingresos por estudiante
    counted_grupos_docente = set()  # dedup global de pagos a docente entre estudiantes
    total_horas_estudiantes = 0
    total_cobrar_estudiantes = 0
    total_pagado_estudiantes = 0
    
    planificado_clases = 0
    planificado_psicologia = 0
    total_facturado_clases = 0
    total_facturado_psicologia = 0
    total_facturado = 0
    
    asignaturas_detalle = {}
    horas_por_materia = {}
    cumplimiento = {'planificado': 0, 'realizado': 0, 'cancelado': 0, 'cancelado-pagado': 0}
    ingresos_por_tipo = {}
    pagos_por_docente = {}
    total_docencia = 0
    total_psicologia = 0
    total_pago_docentes = 0
    total_atlas = 0
    gastos_por_categoria = {}
    total_gastos = 0
    
    for e in (estudiantes.data or []):
        ses = supabase.table('sesiones').select('*').eq('estudiante_id', e['id']).in_('estado', ['Realizado', 'Cancelado-Pagado']).execute()
        pag = supabase.table('pagos').select('*').eq('estudiante_id', e['id']).order('fecha_pago', desc=True).execute()
        
        ses_data = [s for s in (ses.data or []) if s.get('fecha', '') and s['fecha'][:7] == f"{anio}-{mes:02d}"]
        pag_data = [p for p in (pag.data or []) if p.get('fecha_pago', '') and p['fecha_pago'][:7] == f"{anio}-{mes:02d}"]
        
        ses_realizadas = [s for s in ses_data if s['estado'] == 'Realizado']
        ses_cancelado_pagado = [s for s in ses_data if s['estado'] == 'Cancelado-Pagado']
        
        cobrar = sum(s.get('valor_total', 0) or 0 for s in ses_data)
        pagado = sum(p.get('monto', 0) or 0 for p in pag_data)
        
        horas_real = sum(s.get('horas', 0) or 0 for s in ses_realizadas)
        
        total_horas_estudiantes += horas_real
        total_cobrar_estudiantes += cobrar
        total_pagado_estudiantes += pagado
        
        cobrar_clases_est = 0
        cobrar_psico_est = 0
        for s in ses_data:
            tipo = s.get('tipo_sesion', 'clase')
            valor = s.get('valor_total', 0) or 0
            if tipo in ['clase', 'preuniversitario']:
                cobrar_clases_est += valor
                planificado_clases += valor
            else:
                cobrar_psico_est += valor
                planificado_psicologia += valor
        
        cobrar_total_est = cobrar_clases_est + cobrar_psico_est
        if cobrar_total_est > 0:
            proporcion_clases = cobrar_clases_est / cobrar_total_est
            proporcion_psico = cobrar_psico_est / cobrar_total_est
            ejecutado_clases_est = round(pagado * proporcion_clases, 2)
            ejecutado_psico_est = round(pagado * proporcion_psico, 2)
        else:
            ejecutado_clases_est = 0
            ejecutado_psico_est = 0
        
        total_facturado_clases += ejecutado_clases_est
        total_facturado_psicologia += ejecutado_psico_est
        total_facturado += pagado
        
        ingresos_por_tipo['clase'] = ingresos_por_tipo.get('clase', 0) + ejecutado_clases_est
        ingresos_por_tipo['terapia'] = ingresos_por_tipo.get('terapia', 0) + ejecutado_psico_est
        
        for s in ses_data:
            gid = s.get('sesion_grupo_id') or '|'.join([str(s.get('profesor_terapeuta','')), str(s.get('fecha','')), str(s.get('hora_inicio','')), str(s.get('hora_fin',''))])
            if str(gid) in counted_grupos_docente:
                continue
            counted_grupos_docente.add(str(gid))
            tipo = s.get('tipo_sesion', 'clase')
            valor = s.get('valor_total', 0) or 0
            prof = s.get('profesor_terapeuta', 'Desconocido')
            horas = s.get('horas', 0) or 0

            if s['estado'] == 'Cancelado-Pagado':
                pago_docente = s.get('valor_pagar_docente', 0) or 0
                valor_atlas = s.get('valor_atlas', 0) or 0
                total_atlas += valor_atlas
                if tipo in ['terapia', 'ambos']:
                    pago_psicologia = pago_docente
                    pago_docente = 0
                    total_psicologia += pago_psicologia
                else:
                    pago_psicologia = 0
                    total_docencia += pago_docente
            else:
                if tipo in ['clase', 'preuniversitario']:
                    pago_docente = horas * 7
                    pago_psicologia = 0
                    total_docencia += pago_docente
                else:
                    pago_docente = 0
                    pago_psicologia = valor * PORCENTAJE_PSICOLOGIA
                    total_psicologia += pago_psicologia
            
            total_pagar = pago_docente + pago_psicologia
            total_pago_docentes += total_pagar
            if prof not in pagos_por_docente:
                pagos_por_docente[prof] = {'pago_docencia': 0, 'pago_psicologia': 0, 'total_pagar': 0}
            pagos_por_docente[prof]['pago_docencia'] += pago_docente
            pagos_por_docente[prof]['pago_psicologia'] += pago_psicologia
            pagos_por_docente[prof]['total_pagar'] += total_pagar
        
        for s in ses_data:
            asig = s.get('asignatura') or s.get('tema_terapia') or 'Sin registro'
            horas_por_materia[asig] = horas_por_materia.get(asig, 0) + (s.get('horas', 0) or 0)
            if asig not in asignaturas_detalle:
                asignaturas_detalle[asig] = {'plan': 0, 'real': 0, 'canc': 0}
            if s['estado'] in ['Realizado', 'Cancelado-Pagado']:
                asignaturas_detalle[asig]['real'] += s.get('horas', 0) or 0
            cumplimiento[s.get('estado', 'Planificado').lower()] = cumplimiento.get(s.get('estado', 'Planificado').lower(), 0) + 1
        
        if cobrar > 0 or pagado > 0 or horas_real > 0:
            datos_estudiantes.append({
                'id': e['id'], 'estudiante': f"{e['apellidos']} {e['nombres']}",
                'horas_plan': 0, 'horas_real': horas_real, 'horas_canc': 0,
                'cobrar': cobrar, 'pagado': pagado, 'saldo': cobrar - pagado
            })
        if cobrar > 0 or pagado > 0:
            profe = ses_data[0].get('profesor_terapeuta','') if ses_data else ''
            tipo0 = ses_data[0].get('tipo_sesion','clase') if ses_data else 'clase'
            ph = ses_data[0].get('precio_hora', 0) or 0 if ses_data else 0
            tasa = f'${ph:.2f}/h' if tipo0 in ['clase','preuniversitario'] else f'{PORCENTAJE_PSICOLOGIA*100:.1f}%'
            datos_ingresos.append({
                'estudiante': f"{e['apellidos']} {e['nombres']}",
                'profesor': profe,
                'horas': horas_real,
                'tasa': tasa,
                'cobrar': cobrar,
                'pagado': pagado,
                'saldo': cobrar - pagado,
            })
    
    total_devoluciones = devoluciones_periodo(anio, mes)
    total_ingresos = total_facturado - total_devoluciones

    try:
        gastos_mes = supabase.table('gastos').select('*').eq('mes_periodo', mes).eq('anio_periodo', anio).execute()
    except Exception:
        gastos_mes = supabase.table('gastos').select('*').eq('mes', mes).eq('anio', anio).execute()
    total_gastos = sum(g.get('monto', 0) or 0 for g in (gastos_mes.data or []))
    for g in (gastos_mes.data or []):
        cat = g.get('categoria', 'Sin categoría')
        gastos_por_categoria[cat] = gastos_por_categoria.get(cat, 0) + (g.get('monto', 0) or 0)
    
    balance = total_ingresos - total_gastos - total_pago_docentes
    
    correcciones = supabase.table('correcciones_pagos').select('*').order('fecha_correccion', desc=True).limit(30).execute()
    observaciones = supabase.table('sesiones').select('*, estudiantes(apellidos, nombres)').not_.is_('observaciones', 'null').order('fecha', desc=True).limit(30).execute()
    _, ultimo_dia = monthrange(anio, mes)
    nuevos_usuarios = supabase.table('usuarios').select('*').gte('fecha_registro', f"{anio}-{mes:02d}-01").lte('fecha_registro', f"{anio}-{mes:02d}-{ultimo_dia}").execute()

    estudiantes_hombres = 0
    estudiantes_mujeres = 0
    horas_por_estudiante = {}
    cobrar_por_estudiante = {}
    
    for e in (estudiantes.data or []):
        genero = (e.get('genero') or '').lower()
        if genero in ['m', 'masculino', 'hombre']:
            estudiantes_hombres += 1
        elif genero in ['f', 'femenino', 'mujer']:
            estudiantes_mujeres += 1
        
        nombre_est = f"{e['apellidos']} {e['nombres']}"
        ses_est = supabase.table('sesiones').select('*').eq('estudiante_id', e['id']).in_('estado', ['Realizado', 'Cancelado-Pagado']).execute()
        ses_est_data = [s for s in (ses_est.data or []) if s.get('fecha', '') and s['fecha'][:7] == f"{anio}-{mes:02d}"]
        horas_est = sum(s.get('horas', 0) or 0 for s in ses_est_data)
        cobrar_est = sum(s.get('valor_total', 0) or 0 for s in ses_est_data)
        horas_por_estudiante[nombre_est] = horas_est
        cobrar_por_estudiante[nombre_est] = cobrar_est
    
    asignaturas_valores = {}
    asignaturas_estudiantes = {}
    for e in (estudiantes.data or []):
        nombre_est = f"{e['apellidos']} {e['nombres']}"
        ses_est = supabase.table('sesiones').select('*').eq('estudiante_id', e['id']).in_('estado', ['Realizado', 'Cancelado-Pagado']).execute()
        ses_est_data = [s for s in (ses_est.data or []) if s.get('fecha', '') and s['fecha'][:7] == f"{anio}-{mes:02d}"]
        for s in ses_est_data:
            asig = s.get('asignatura') or s.get('tema_terapia') or 'Sin registro'
            if asig not in asignaturas_valores:
                asignaturas_valores[asig] = {'horas': 0, 'valor': 0, 'estudiantes': 0}
                asignaturas_estudiantes[asig] = set()
            asignaturas_valores[asig]['horas'] += s.get('horas', 0) or 0
            asignaturas_valores[asig]['valor'] += s.get('valor_total', 0) or 0
            asignaturas_estudiantes[asig].add(nombre_est)
    
    for asig in asignaturas_valores:
        asignaturas_valores[asig]['estudiantes'] = len(asignaturas_estudiantes.get(asig, set()))
    
    total_pago_docentes_general = total_docencia + total_psicologia

    return render_template('reportes.html',
                         datos_estudiantes=datos_estudiantes, total_estudiantes=len(datos_estudiantes),
                         total_horas_estudiantes=total_horas_estudiantes,
                         total_cobrar_estudiantes=total_cobrar_estudiantes,
                         total_pagado_estudiantes=total_pagado_estudiantes,
                         total_por_pagar_estudiantes=total_cobrar_estudiantes - total_pagado_estudiantes,
                         total_ingresos=total_ingresos,
                         total_facturado_bruto=total_facturado,
                         total_devoluciones=total_devoluciones,
                         total_gastos=total_gastos, balance=balance,
                         gastos=gastos_mes.data or [], mes=mes, anio=anio,
                         ingresos_por_tipo=ingresos_por_tipo, gastos_por_categoria=gastos_por_categoria,
                         horas_por_materia=horas_por_materia, asignaturas_detalle=asignaturas_detalle,
                         cumplimiento=cumplimiento,
                         pagos_por_docente=pagos_por_docente, total_pago_docentes=total_pago_docentes,
                         total_docencia=total_docencia, total_psicologia=total_psicologia,
                         total_pago_docentes_general=total_pago_docentes_general,
                         total_atlas=total_atlas,
                         planificado_clases=planificado_clases,
                         planificado_psicologia=planificado_psicologia,
                         ejecutado_clases=total_facturado_clases,
                         ejecutado_psicologia=total_facturado_psicologia,
                         estudiantes_hombres=estudiantes_hombres,
                         estudiantes_mujeres=estudiantes_mujeres,
                         horas_por_estudiante=horas_por_estudiante,
                         cobrar_por_estudiante=cobrar_por_estudiante,
                         asignaturas_valores=asignaturas_valores,
                         asignaturas_estudiantes=asignaturas_estudiantes,
                         correcciones=correcciones.data or [], observaciones=observaciones.data or [],
                         nuevos_usuarios=nuevos_usuarios.data or [], total_planificado=0,
                         datos_ingresos=datos_ingresos)


# ========== GASTOS ==========
@app.route('/gastos', methods=['GET', 'POST'])
@login_required
def gestion_gastos():
    if request.method == 'POST':
        fecha = request.form['fecha']
        fecha_obj = datetime.strptime(fecha, '%Y-%m-%d')
        mes_periodo = int(request.form.get('mes_periodo', fecha_obj.month))
        anio_periodo = int(request.form.get('anio_periodo', fecha_obj.year))
        gasto_data = {
            'concepto': request.form['concepto'], 'monto': float(request.form['monto']),
            'fecha': fecha, 'categoria': request.form.get('categoria', ''),
            'persona': request.form.get('persona', ''), 'reembolso': request.form.get('reembolso') == 'true',
            'reembolsado_a': request.form.get('reembolsado_a', '') or None,
            'registrado_por': current_user.nombre, 'mes': fecha_obj.month, 'anio': fecha_obj.year,
            'mes_periodo': mes_periodo, 'anio_periodo': anio_periodo
        }
        try:
            supabase.table('gastos').insert(gasto_data).execute()
        except Exception:
            gasto_data.pop('mes_periodo', None)
            gasto_data.pop('anio_periodo', None)
            supabase.table('gastos').insert(gasto_data).execute()
        flash('✅ Gasto registrado', 'success')
        return redirect(url_for('gestion_gastos'))
    
    mes = int(request.args.get('mes', date.today().month))
    anio = int(request.args.get('anio', date.today().year))
    # Incluye los gastos con FECHA en el mes Y los CONSIDERADOS para el mes (mes_periodo)
    try:
        gastos = supabase.table('gastos').select('*').or_(
            f"and(mes.eq.{mes},anio.eq.{anio}),and(mes_periodo.eq.{mes},anio_periodo.eq.{anio})"
        ).order('fecha', desc=True).execute()
    except Exception:
        gastos = supabase.table('gastos').select('*').eq('mes', mes).eq('anio', anio).order('fecha', desc=True).execute()
    # Marca los que corresponden a otro mes de fecha pero fueron considerados para este período
    for g in (gastos.data or []):
        g['_de_otro_mes'] = bool(g.get('mes') and g.get('mes') != mes and g.get('mes_periodo') == mes)
    total = sum(g.get('monto', 0) or 0 for g in (gastos.data or []))
    
    # Obtener pagos a docentes del mes
    _, ultimo_dia = monthrange(anio, mes)
    sesiones_mes = supabase.table('sesiones').select('*').in_('estado', ['Realizado', 'Cancelado-Pagado']).gte('fecha', f"{anio}-{mes:02d}-01").lte('fecha', f"{anio}-{mes:02d}-{ultimo_dia}").execute()
    
    pagos_docentes_detalle = {}
    total_sesiones_docentes = 0
    total_docencia_mes = 0
    total_psicologia_mes = 0
    total_pago_docentes_mes = 0
    
    for s in dedup_sesiones_docente(sesiones_mes.data or []):
        tipo = s.get('tipo_sesion', 'clase')
        horas = s.get('horas', 0) or 0
        valor = s.get('valor_total', 0) or 0
        prof = s.get('profesor_terapeuta', 'Desconocido')
        estado = s.get('estado', '')

        if prof not in pagos_docentes_detalle:
            pagos_docentes_detalle[prof] = {'pago_docencia': 0, 'pago_psicologia': 0, 'total_pagar': 0, 'sesiones': 0, 'fecha_pago': None, 'pagado': False}
        
        pagos_docentes_detalle[prof]['sesiones'] += 1
        total_sesiones_docentes += 1
        
        if estado == 'Cancelado-Pagado':
            pago = s.get('valor_pagar_docente', 0) or 0
            if tipo in ['clase', 'preuniversitario']:
                pagos_docentes_detalle[prof]['pago_docencia'] += pago
                total_docencia_mes += pago
            else:
                pagos_docentes_detalle[prof]['pago_psicologia'] += pago
                total_psicologia_mes += pago
            pagos_docentes_detalle[prof]['total_pagar'] += pago
            total_pago_docentes_mes += pago
        else:
            if tipo in ['clase', 'preuniversitario']:
                pago = horas * PAGO_DOCENCIA_POR_HORA
                pagos_docentes_detalle[prof]['pago_docencia'] += pago
                total_docencia_mes += pago
            else:
                pago = valor * PORCENTAJE_PSICOLOGIA
                pagos_docentes_detalle[prof]['pago_psicologia'] += pago
                total_psicologia_mes += pago
            pagos_docentes_detalle[prof]['total_pagar'] += pago
            total_pago_docentes_mes += pago
    
    # Cargar fechas de pago guardadas
    fechas = supabase.table('fechas_pago_docentes').select('*').eq('mes', mes).eq('anio', anio).execute()
    for f in (fechas.data or []):
        nombre = f.get('docente_nombre')
        if nombre in pagos_docentes_detalle:
            pagos_docentes_detalle[nombre]['fecha_pago'] = f.get('fecha_pago')
            pagos_docentes_detalle[nombre]['pagado'] = f.get('pagado', False)
    
    # Reembolsos pendientes (todos los períodos, no pagados)
    try:
        reembolsos_pend = supabase.table('gastos').select('*').eq('reembolso', True).neq('reembolso_pagado', True).order('fecha', desc=True).execute()
    except Exception:
        reembolsos_pend = supabase.table('gastos').select('*').eq('reembolso', True).order('fecha', desc=True).execute()

    return render_template('gastos.html',
                         gastos=gastos.data or [], total=total, mes=mes, anio=anio, today=date.today(),
                         pagos_docentes_detalle=pagos_docentes_detalle,
                         total_pago_docentes_mes=total_pago_docentes_mes,
                         total_docencia_mes=total_docencia_mes,
                         total_psicologia_mes=total_psicologia_mes,
                         total_sesiones_docentes=total_sesiones_docentes,
                         reembolsos_pend=reembolsos_pend.data or [],
                         socios=SOCIOS)

@app.route('/api/gasto/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar_gasto(id):
    supabase.table('gastos').delete().eq('id', id).execute()
    return jsonify({'success': True})

@app.route('/api/gasto/<int:id>/reembolso', methods=['POST'])
@login_required
@socio_admin_required
def api_actualizar_reembolso(id):
    data = request.get_json()
    update = {}
    if 'reembolsado_a' in data:
        update['reembolsado_a'] = data['reembolsado_a'] or None
    if 'reembolso' in data:
        update['reembolso'] = bool(data['reembolso'])
    try:
        supabase.table('gastos').update(update).eq('id', id).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/gasto/<int:id>/marcar-reembolso-pagado', methods=['POST'])
@login_required
@socio_admin_required
def api_marcar_reembolso_pagado(id):
    data = request.get_json() or {}
    fecha = data.get('fecha', date.today().isoformat())
    try:
        supabase.table('gastos').update({
            'reembolso_pagado': True,
            'fecha_reembolso_pagado': fecha
        }).eq('id', id).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ========== LIQUIDACIÓN ==========
@app.route('/liquidacion', methods=['GET', 'POST'])
@login_required
@socio_admin_required
def liquidacion():
    mes = int(request.args.get('mes', date.today().month))
    anio = int(request.args.get('anio', date.today().year))

    # Cargar o crear registro de liquidación guardado
    try:
        liq_r = supabase.table('liquidaciones').select('*').eq('mes', mes).eq('anio', anio).execute()
        liq_record = liq_r.data[0] if liq_r.data else None
    except Exception:
        liq_record = None

    if request.method == 'POST':
        saldo_cuenta = float(request.form.get('saldo_cuenta', 0))
        try:
            if liq_record:
                supabase.table('liquidaciones').update({
                    'saldo_cuenta': saldo_cuenta
                }).eq('id', liq_record['id']).execute()
            else:
                supabase.table('liquidaciones').insert({
                    'mes': mes, 'anio': anio,
                    'saldo_cuenta': saldo_cuenta,
                    'registrado_por': current_user.nombre
                }).execute()
        except Exception:
            pass
        flash('✅ Saldo guardado', 'success')
        return redirect(url_for('liquidacion', mes=mes, anio=anio))

    saldo_cuenta = float(liq_record['saldo_cuenta']) if liq_record else 0.0
    _, ultimo_dia = monthrange(anio, mes)

    # Gastos del período
    try:
        gastos_periodo = supabase.table('gastos').select('*').eq('mes_periodo', mes).eq('anio_periodo', anio).order('fecha', desc=True).execute()
    except Exception:
        gastos_periodo = supabase.table('gastos').select('*').eq('mes', mes).eq('anio', anio).order('fecha', desc=True).execute()

    total_gastos = sum(g.get('monto', 0) or 0 for g in (gastos_periodo.data or []))
    gastos_por_cat = {}
    reembolsos_por_socio = {}
    for g in (gastos_periodo.data or []):
        cat = g.get('categoria', 'Sin categoría')
        gastos_por_cat[cat] = gastos_por_cat.get(cat, 0) + (g.get('monto', 0) or 0)
        if g.get('reembolso') and g.get('reembolsado_a'):
            benef = g['reembolsado_a']
            reembolsos_por_socio[benef] = reembolsos_por_socio.get(benef, 0) + (g.get('monto', 0) or 0)

    # Gastos pendientes de reembolso (de cualquier período anterior también)
    try:
        gastos_reembolso_pend = supabase.table('gastos').select('*').eq('reembolso', True).execute()
    except Exception:
        gastos_reembolso_pend = type('obj', (object,), {'data': []})()

    # Ingresos del período (netos de devoluciones)
    pagos_mes = supabase.table('pagos').select('*').gte('fecha_pago', f"{anio}-{mes:02d}-01").lte('fecha_pago', f"{anio}-{mes:02d}-{ultimo_dia}").execute()
    total_ingresos_bruto = sum(p.get('monto', 0) or 0 for p in (pagos_mes.data or []))
    total_devoluciones = devoluciones_periodo(anio, mes)
    total_ingresos = total_ingresos_bruto - total_devoluciones

    # Pago a docentes del período
    sesiones_mes = supabase.table('sesiones').select('*').in_('estado', ['Realizado', 'Cancelado-Pagado']).gte('fecha', f"{anio}-{mes:02d}-01").lte('fecha', f"{anio}-{mes:02d}-{ultimo_dia}").execute()

    pago_por_docente = {}
    total_pago_docentes = 0
    for s in dedup_sesiones_docente(sesiones_mes.data or []):
        prof = s.get('profesor_terapeuta', 'Desconocido')
        tipo = s.get('tipo_sesion', 'clase')
        horas = s.get('horas', 0) or 0
        valor = s.get('valor_total', 0) or 0
        estado = s.get('estado', '')
        if estado == 'Cancelado-Pagado':
            pago = s.get('valor_pagar_docente', 0) or 0
        elif tipo in ['clase', 'preuniversitario']:
            pago = horas * PAGO_DOCENCIA_POR_HORA
        else:
            pago = valor * PORCENTAJE_PSICOLOGIA
        pago_por_docente[prof] = pago_por_docente.get(prof, 0) + pago
        total_pago_docentes += pago

    balance = saldo_cuenta - total_gastos - total_pago_docentes
    parte_por_socio = balance / 3

    distribucion_socios = []
    for socio in SOCIOS:
        pago_docente_socio = pago_por_docente.get(socio, 0)
        reembolso_socio = reembolsos_por_socio.get(socio, 0)
        neto = parte_por_socio + pago_docente_socio + reembolso_socio
        distribucion_socios.append({
            'nombre': socio,
            'parte_alicuota': parte_por_socio,
            'pago_docente': pago_docente_socio,
            'reembolso': reembolso_socio,
            'neto': neto
        })

    return render_template('liquidacion.html',
        mes=mes, anio=anio, saldo_cuenta=saldo_cuenta,
        liq_guardada=liq_record is not None,
        gastos=gastos_periodo.data or [], total_gastos=total_gastos, gastos_por_cat=gastos_por_cat,
        reembolsos_por_socio=reembolsos_por_socio,
        gastos_reembolso_pend=gastos_reembolso_pend.data or [],
        total_ingresos=total_ingresos, total_ingresos_bruto=total_ingresos_bruto,
        total_devoluciones=total_devoluciones, total_pago_docentes=total_pago_docentes,
        pago_por_docente=pago_por_docente, balance=balance,
        distribucion_socios=distribucion_socios)

# ========== ESTUDIANTES ==========
@app.route('/estudiantes', methods=['GET', 'POST'])
@login_required
def gestion_estudiantes():
    estudiantes = supabase.table('estudiantes').select('*').eq('activo', True).order('apellidos').execute()
    # Instituciones dinámicas: default + las ya registradas en la BD
    procedencias_bd = list({e.get('procedencia', '') for e in (estudiantes.data or []) if e.get('procedencia')})
    instituciones = sorted(set(INSTITUCIONES_DEFAULT + procedencias_bd))
    return render_template('estudiantes.html',
        estudiantes=estudiantes.data or [], rol=current_user.rol,
        instituciones=instituciones, niveles_por_tipo=NIVELES_POR_TIPO)

@app.route('/api/crear_estudiante', methods=['POST'])
@login_required
def api_crear_estudiante():
    data = request.get_json()
    result = supabase.table('estudiantes').insert({
        'nombres': data['nombres'], 'apellidos': data['apellidos'],
        'nivel_curso': a_oracion(data.get('nivel_curso', '')),
        'procedencia': data.get('procedencia', ''),
        'padre_nombre': data.get('padre_nombre', ''),
        'madre_nombre': data.get('madre_nombre', ''),
        'tipo_institucion': data.get('tipo_institucion', ''),
        'activo': True, 'usuario_id': current_user.id
    }).execute()
    return jsonify({'success': True, 'id': result.data[0]['id'], 'nombre': f"{result.data[0]['apellidos']} {result.data[0]['nombres']}"})

@app.route('/api/crear_estudiante_form', methods=['POST'])
@login_required
def crear_estudiante_form():
    if current_user.rol not in ['admin', 'socio']:
        flash('❌ Sin permiso', 'error')
        return redirect(url_for('dashboard'))
    supabase.table('estudiantes').insert({
        'nombres': request.form['nombres'], 'apellidos': request.form['apellidos'],
        'nivel_curso': a_oracion(request.form.get('nivel_curso', '')),
        'procedencia': request.form.get('procedencia', ''),
        'padre_nombre': request.form.get('padre_nombre', ''),
        'madre_nombre': request.form.get('madre_nombre', ''),
        'tipo_institucion': request.form.get('tipo_institucion', ''),
        'activo': True, 'usuario_id': current_user.id
    }).execute()
    flash('✅ Estudiante creado', 'success')
    return redirect(url_for('gestion_estudiantes'))

@app.route('/api/estudiante/<int:id>/editar', methods=['POST'])
@login_required
def api_editar_estudiante(id):
    if current_user.rol not in ['admin', 'socio']:
        return jsonify({'success': False, 'error': 'Sin permiso'})
    data = request.get_json()
    campo = data.get('campo')
    valor = data.get('valor', '') or ''
    campos_permitidos = ['nombres', 'apellidos', 'nivel_curso', 'procedencia',
                         'padre_nombre', 'madre_nombre', 'tipo_institucion', 'genero']
    if campo not in campos_permitidos:
        return jsonify({'success': False, 'error': 'Campo no permitido'})
    if campo in ['nivel_curso']:
        valor = a_oracion(valor)
    try:
        supabase.table('estudiantes').update({campo: valor or None}).eq('id', id).execute()
        return jsonify({'success': True, 'valor': valor})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/estudiante/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar_estudiante(id):
    if current_user.rol not in ['admin', 'socio']:
        return jsonify({'success': False, 'error': 'Sin permiso'})
    supabase.table('estudiantes').update({'activo': False}).eq('id', id).execute()
    return jsonify({'success': True})

# ========== PADRES ==========
@app.route('/padres', methods=['GET', 'POST'])
@login_required
@socio_admin_required
def gestion_padres():
    if request.method == 'POST':
        supabase.table('padres_familia').insert({
            'nombres': request.form['nombres'], 'apellidos': request.form['apellidos'],
            'telefono': request.form.get('telefono', '')
        }).execute()
        flash('✅ Padre registrado', 'success')
        return redirect(url_for('gestion_padres'))
    padres = supabase.table('padres_familia').select('*').eq('activo', True).order('apellidos').execute()
    return render_template('padres.html', padres=padres.data or [])

# ========== DOCENTES ==========
@app.route('/docentes')
@login_required
@socio_admin_required
def gestion_docentes():
    try:
        docentes = supabase.table('docentes').select('*').eq('activo', True).order('apellidos').execute()
        data = docentes.data or []
    except Exception:
        data = []
    return render_template('docentes.html',
        docentes=data, rol=current_user.rol, asignaturas=cargar_asignaturas())

@app.route('/api/crear_docente_form', methods=['POST'])
@login_required
@socio_admin_required
def crear_docente_form():
    asigs = request.form.getlist('asignaturas')
    supabase.table('docentes').insert({
        'nombres': request.form['nombres'].strip(),
        'apellidos': request.form['apellidos'].strip(),
        'asignaturas': ', '.join([a.strip() for a in asigs if a.strip()]),
        'email': request.form.get('email', '').strip(),
        'telefono': request.form.get('telefono', '').strip(),
        'tipo': request.form.get('tipo', 'profesor'),
        'activo': True
    }).execute()
    flash('✅ Docente creado', 'success')
    return redirect(url_for('gestion_docentes'))

@app.route('/api/docente/<int:id>/editar', methods=['POST'])
@login_required
@socio_admin_required
def api_editar_docente(id):
    data = request.get_json()
    campo = data.get('campo')
    valor = data.get('valor', '') or ''
    campos_permitidos = ['nombres', 'apellidos', 'asignaturas', 'email', 'telefono', 'tipo']
    if campo not in campos_permitidos:
        return jsonify({'success': False, 'error': 'Campo no permitido'})
    try:
        supabase.table('docentes').update({campo: valor or None}).eq('id', id).execute()
        return jsonify({'success': True, 'valor': valor})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/docente/<int:id>/eliminar', methods=['POST'])
@login_required
@socio_admin_required
def eliminar_docente(id):
    try:
        supabase.table('docentes').update({'activo': False}).eq('id', id).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ========== ASIGNATURAS ==========
@app.route('/asignaturas')
@login_required
@socio_admin_required
def gestion_asignaturas():
    try:
        asigs = supabase.table('asignaturas').select('*').eq('activo', True).order('nombre').execute()
        data = asigs.data or []
    except Exception:
        data = []
    return render_template('asignaturas.html', asignaturas=data, rol=current_user.rol)

@app.route('/api/crear_asignatura_form', methods=['POST'])
@login_required
@socio_admin_required
def crear_asignatura_form():
    nombre = request.form['nombre'].strip()
    if nombre:
        supabase.table('asignaturas').insert({'nombre': nombre, 'activo': True}).execute()
        flash('✅ Asignatura creada', 'success')
    return redirect(url_for('gestion_asignaturas'))

@app.route('/api/asignatura/<int:id>/editar', methods=['POST'])
@login_required
@socio_admin_required
def api_editar_asignatura(id):
    data = request.get_json()
    valor = (data.get('valor', '') or '').strip()
    if not valor:
        return jsonify({'success': False, 'error': 'El nombre no puede estar vacío'})
    try:
        supabase.table('asignaturas').update({'nombre': valor}).eq('id', id).execute()
        return jsonify({'success': True, 'valor': valor})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/asignatura/<int:id>/eliminar', methods=['POST'])
@login_required
@socio_admin_required
def eliminar_asignatura(id):
    try:
        supabase.table('asignaturas').update({'activo': False}).eq('id', id).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ========== USUARIOS ==========
@app.route('/usuarios', methods=['GET', 'POST'])
@login_required
@admin_required
def gestion_usuarios():
    if request.method == 'POST':
        accion = request.form.get('accion')
        uid = int(request.form.get('usuario_id', 0))
        if accion == 'aprobar':
            supabase.table('usuarios').update({'activo': True}).eq('id', uid).execute()
            flash('✅ Usuario aprobado', 'success')
        elif accion == 'rechazar':
            supabase.table('usuarios').update({'activo': False}).eq('id', uid).execute()
            flash('❌ Usuario desactivado', 'info')
        elif accion == 'crear':
            supabase.table('usuarios').insert({
                'nombre': request.form['nombre'], 'email': request.form['email'],
                'password_hash': request.form['password'], 'rol': request.form['rol'], 'activo': True
            }).execute()
            flash('✅ Usuario creado', 'success')
        elif accion == 'editar':
            edit_id = request.form.get('edit_id')
            updates = {'nombre': request.form['nombre'], 'email': request.form['email'], 'rol': request.form['rol']}
            if request.form.get('password'):
                updates['password_hash'] = request.form['password']
            supabase.table('usuarios').update(updates).eq('id', int(edit_id)).execute()
            flash('✅ Usuario actualizado', 'success')
        return redirect(url_for('gestion_usuarios'))
    usuarios = supabase.table('usuarios').select('*').order('fecha_registro', desc=True).execute()
    return render_template('usuarios.html', usuarios=usuarios.data or [])
    
# ========== MI REPORTE ==========
@app.route('/mi-reporte')
@login_required
def mi_reporte():
    mes = int(request.args.get('mes', date.today().month))
    anio = int(request.args.get('anio', date.today().year))
    datos = []
    total_horas = 0
    total_a_pagar = 0
    anticipos_aprobados = 0
    nombre_usuario = current_user.nombre.strip().lower()
    palabras_usuario = nombre_usuario.split()
    sesiones = supabase.table('sesiones').select('*, estudiantes(*)').in_('estado', ['Realizado', 'Cancelado-Pagado']).order('fecha', desc=True).execute()

    # Mapa grupo_id → lista de estudiantes para clases grupales
    _ests_por_grupo_mr = {}
    for _s in (sesiones.data or []):
        _gid = str(_s.get('sesion_grupo_id') or '|'.join([
            str(_s.get('profesor_terapeuta','')), str(_s.get('fecha','')),
            str(_s.get('hora_inicio','')), str(_s.get('hora_fin',''))]))
        _est2 = _s.get('estudiantes') or {}
        _nom2 = f"{_est2.get('apellidos','')} {_est2.get('nombres','')}".strip()
        if _nom2:
            if _gid not in _ests_por_grupo_mr:
                _ests_por_grupo_mr[_gid] = []
            if _nom2 not in _ests_por_grupo_mr[_gid]:
                _ests_por_grupo_mr[_gid].append(_nom2)

    anticipos = supabase.table('anticipos_solicitudes').select('*').eq('usuario_id', current_user.id).eq('estado', 'aprobado').execute()
    for a in (anticipos.data or []):
        anticipos_aprobados += a.get('monto', 0)

    for s in dedup_sesiones_docente(sesiones.data or []):
        if mes != 0 and s.get('fecha', '') and s['fecha'][:7] != f"{anio}-{mes:02d}":
            continue
        profesor = (s.get('profesor_terapeuta') or '').strip().lower()
        est = s.get('estudiantes', {})
        nombre_est = f"{est.get('apellidos', '')} {est.get('nombres', '')}".strip().lower()
        incluir = False
        
        if current_user.rol in ['profesor', 'psicologo']:
            if nombre_usuario in profesor or profesor in nombre_usuario:
                incluir = True
            else:
                for p in palabras_usuario:
                    if len(p) >= 3 and p in profesor:
                        incluir = True
                        break
        elif current_user.rol in ['estudiante', 'padre']:
            apellidos_est = (est.get('apellidos', '') or '').strip().lower()
            nombres_est = (est.get('nombres', '') or '').strip().lower()
            if nombre_usuario in nombre_est or nombre_est in nombre_usuario:
                incluir = True
            else:
                for p in palabras_usuario:
                    if len(p) >= 3 and (p in apellidos_est or p in nombres_est):
                        incluir = True
                        break
        
        if incluir:
            horas = s.get('horas', 0) or 0
            valor = s.get('valor_total', 0) or 0
            tipo = s.get('tipo_sesion', 'clase')
            
            if s.get('estado') == 'Cancelado-Pagado':
                mi_pago = s.get('valor_pagar_docente', 0) or 0
            elif tipo in ['clase', 'preuniversitario']:
                mi_pago = horas * 7
            else:
                mi_pago = valor * PORCENTAJE_PSICOLOGIA
                
            total_a_pagar += mi_pago
            total_horas += horas
            _gid_mr = str(s.get('sesion_grupo_id') or '|'.join([
                str(s.get('profesor_terapeuta','')), str(s.get('fecha','')),
                str(s.get('hora_inicio','')), str(s.get('hora_fin',''))]))
            todos_ests_mr = _ests_por_grupo_mr.get(_gid_mr, [nombre_est])
            datos.append({
                'fecha': s['fecha'],
                'estudiante': nombre_est,
                'todos_estudiantes': [e.title() for e in todos_ests_mr],
                'es_grupal': len(todos_ests_mr) > 1,
                'tipo': tipo,
                'asignatura': s.get('asignatura') or s.get('tema_terapia') or '-',
                'horas': horas,
                'valor': valor,
                'mi_pago': mi_pago,
                'estado': s['estado']
            })
    
    neto_a_recibir = total_a_pagar - anticipos_aprobados
    return render_template('mi_reporte.html',
                         datos=datos, total_horas=total_horas,
                         total_a_pagar=total_a_pagar,
                         anticipos_aprobados=anticipos_aprobados,
                         neto_a_recibir=neto_a_recibir,
                         mes=mes, anio=anio)

# ========== EDITAR PERFIL ==========
@app.route('/editar-perfil', methods=['GET', 'POST'])
@login_required
def editar_perfil():
    if request.method == 'POST':
        updates = {'nombre': request.form['nombre'], 'email': request.form['email']}
        if request.form.get('password'):
            updates['password_hash'] = request.form['password']
        supabase.table('usuarios').update(updates).eq('id', current_user.id).execute()
        if current_user.rol in ['profesor', 'psicologo']:
            supabase.table('sesiones').update({'profesor_terapeuta': request.form['nombre']}).eq('profesor_terapeuta', current_user.nombre).execute()
        flash('✅ Perfil actualizado', 'success')
        return redirect(url_for('dashboard'))
    return render_template('editar_perfil.html')

# ========== API GENERAL ==========
@app.route('/api/estudiante/<int:id>')
@login_required
def api_estudiante(id):
    ses = supabase.table('sesiones').select('*').eq('estudiante_id', id).eq('estado', 'Realizado').execute()
    pag = supabase.table('pagos').select('*').eq('estudiante_id', id).order('fecha_pago', desc=True).execute()
    return jsonify({
        'cobrar': sum(s.get('valor_total', 0) or 0 for s in (ses.data or [])),
        'pagado': sum(p.get('monto', 0) or 0 for p in (pag.data or [])),
        'sesiones': [{'id': s['id'], 'fecha': s['fecha'], 'tipo': s['tipo_sesion'], 'asignatura': s.get('asignatura', ''), 'valor': s.get('valor_total', 0)} for s in (ses.data or [])],
        'pagos': [{'id': p['id'], 'fecha': p['fecha_pago'], 'monto': p['monto'], 'tipo': p.get('tipo_pago', '')} for p in (pag.data or [])]
    })

@app.route('/api/estudiantes')
@login_required
def api_estudiantes():
    est = supabase.table('estudiantes').select('*').eq('activo', True).order('apellidos').execute()
    return jsonify([{'id': e['id'], 'nombre': f"{e['apellidos']} {e['nombres']}"} for e in (est.data or [])])

@app.route('/api/sesion/<int:id>/observacion', methods=['POST'])
@login_required
def agregar_observacion(id):
    if current_user.rol not in ['admin', 'socio']:
        return jsonify({'success': False, 'error': 'Sin permiso'})
    data = request.get_json()
    supabase.table('sesiones').update({'observaciones': data.get('observaciones', '')}).eq('id', id).execute()
    return jsonify({'success': True})

# ========== API EDICIÓN RÁPIDA DE GASTOS ==========
@app.route('/api/gasto/<int:id>/editar', methods=['POST'])
@login_required
def api_editar_gasto(id):
    data = request.get_json()
    campo = data.get('campo')
    valor = data.get('valor')
    try:
        if campo == 'monto':
            valor = float(valor)
        supabase.table('gastos').update({campo: valor}).eq('id', id).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ========== API FECHA PAGO DOCENTES ==========
@app.route('/api/pago-docente/fecha', methods=['POST'])
@login_required
def api_fecha_pago_docente():
    data = request.get_json()
    docente = data.get('docente')
    fecha = data.get('fecha')
    # Mes/año del período que se está viendo (no el de hoy) para que filtre bien
    mes = int(data.get('mes') or date.today().month)
    anio = int(data.get('anio') or date.today().year)
    try:
        existente = supabase.table('fechas_pago_docentes').select('*').eq('docente_nombre', docente).eq('mes', mes).eq('anio', anio).execute()
        if existente.data:
            supabase.table('fechas_pago_docentes').update({'fecha_pago': fecha}).eq('id', existente.data[0]['id']).execute()
        else:
            supabase.table('fechas_pago_docentes').insert({
                'docente_nombre': docente, 'fecha_pago': fecha,
                'mes': mes, 'anio': anio, 'registrado_por': current_user.nombre
            }).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/pago-docente/toggle', methods=['POST'])
@login_required
def api_toggle_pago_docente():
    data = request.get_json()
    docente = data.get('docente')
    mes = int(data.get('mes') or date.today().month)
    anio = int(data.get('anio') or date.today().year)
    try:
        existente = supabase.table('fechas_pago_docentes').select('*').eq('docente_nombre', docente).eq('mes', mes).eq('anio', anio).execute()
        if existente.data and existente.data[0].get('pagado'):
            supabase.table('fechas_pago_docentes').update({'pagado': False}).eq('id', existente.data[0]['id']).execute()
        elif existente.data:
            supabase.table('fechas_pago_docentes').update({'pagado': True}).eq('id', existente.data[0]['id']).execute()
        else:
            supabase.table('fechas_pago_docentes').insert({
                'docente_nombre': docente, 'pagado': True,
                'mes': mes, 'anio': anio, 'registrado_por': current_user.nombre
            }).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ========== REPORTE DE CLASES GRUPALES / DUPLICADOS ==========
@app.route('/reporte-duplicados')
@login_required
def reporte_duplicados():
    if current_user.rol not in ['admin', 'socio']:
        flash('❌ Acceso restringido', 'error')
        return redirect(url_for('dashboard'))

    try:
        sesiones = supabase.table('sesiones').select(
            'id,fecha,hora_inicio,hora_fin,profesor_terapeuta,estudiante_id,horas,tipo_sesion,estado,valor_total,asignatura,tema_terapia,sesion_grupo_id,estudiantes(nombres,apellidos)'
        ).in_('estado', ['Realizado', 'Cancelado-Pagado']).order('fecha', desc=True).execute()
    except Exception:
        sesiones = supabase.table('sesiones').select(
            'id,fecha,hora_inicio,hora_fin,profesor_terapeuta,estudiante_id,horas,tipo_sesion,estado,valor_total,asignatura,tema_terapia,estudiantes(nombres,apellidos)'
        ).in_('estado', ['Realizado', 'Cancelado-Pagado']).order('fecha', desc=True).execute()

    from collections import defaultdict
    grupos = defaultdict(list)
    for s in (sesiones.data or []):
        gid = s.get('sesion_grupo_id')
        key = str(gid) if gid else '|'.join([
            str(s.get('profesor_terapeuta', '')),
            str(s.get('fecha', '')),
            str(s.get('hora_inicio', '')),
            str(s.get('hora_fin', ''))
        ])
        grupos[key].append(s)

    duplicados = []
    total_sobrepago = 0.0
    for key, rows in sorted(grupos.items(), key=lambda x: x[1][0].get('fecha',''), reverse=True):
        if len(rows) < 2:
            continue
        rep = rows[0]
        horas = rep.get('horas', 0) or 0
        tipo = rep.get('tipo_sesion', 'clase')
        if tipo in ['clase', 'preuniversitario']:
            pago_correcto = horas * PAGO_DOCENCIA_POR_HORA
            pago_actual   = pago_correcto * len(rows)
        else:
            valor = rep.get('valor_total', 0) or 0
            pago_correcto = round(valor * PORCENTAJE_PSICOLOGIA, 2)
            pago_actual   = round(pago_correcto * len(rows), 2)
        sobrepago = round(pago_actual - pago_correcto, 2)
        total_sobrepago += sobrepago

        estudiantes_lista = []
        for r in rows:
            est = r.get('estudiantes') or {}
            nombre = f"{est.get('apellidos','')} {est.get('nombres','')}".strip() or f"ID {r.get('estudiante_id','?')}"
            estudiantes_lista.append(nombre)

        duplicados.append({
            'fecha': rep.get('fecha'),
            'hora_inicio': (rep.get('hora_inicio') or '')[:5],
            'hora_fin': (rep.get('hora_fin') or '')[:5],
            'profesor': rep.get('profesor_terapeuta'),
            'asignatura': rep.get('asignatura') or rep.get('tema_terapia') or '-',
            'tipo': tipo,
            'horas': horas,
            'num_estudiantes': len(rows),
            'estudiantes': estudiantes_lista,
            'pago_correcto': pago_correcto,
            'pago_anterior': pago_actual,
            'sobrepago': sobrepago,
            'ids': [r['id'] for r in rows],
        })

    return render_template('reporte_duplicados.html',
                           duplicados=duplicados,
                           total_sobrepago=round(total_sobrepago, 2))


# ========== DEVOLUCIONES DE DINERO ==========
@app.route('/devoluciones', methods=['GET', 'POST'])
@login_required
@socio_admin_required
def devoluciones():
    if request.method == 'POST':
        accion = request.form.get('accion', 'registrar')
        if accion == 'registrar':
            tipo_cliente = request.form.get('tipo_cliente', 'estudiante')
            fecha = request.form.get('fecha') or date.today().isoformat()
            try:
                fecha_obj = datetime.strptime(fecha, '%Y-%m-%d')
            except Exception:
                fecha_obj = datetime.today()
            monto = float(request.form.get('monto', 0) or 0)
            tipo_pago = request.form.get('tipo_pago', 'efectivo')
            motivo = (request.form.get('motivo', '') or '').strip()
            pagar_docente = request.form.get('pagar_docente') == 'true'
            docente_nombre = (request.form.get('docente_nombre', '') or '').strip() or None
            monto_docente = float(request.form.get('monto_docente', 0) or 0) if pagar_docente else 0

            if monto <= 0:
                flash('❌ El monto a devolver debe ser mayor a 0', 'error')
                return redirect(url_for('devoluciones'))

            estudiante_id = None
            cliente_id = None
            cita_id = None
            nombre_cliente = ''
            if tipo_cliente == 'estudiante':
                estudiante_id = int(request.form['estudiante_id']) if request.form.get('estudiante_id') else None
                if not estudiante_id:
                    flash('❌ Selecciona un estudiante', 'error')
                    return redirect(url_for('devoluciones'))
            else:
                cliente_id = int(request.form['cliente_id']) if request.form.get('cliente_id') else None
                cita_id = int(request.form['cita_id']) if request.form.get('cita_id') else None

            # 1) Gasto automático vinculado si hay que pagar al docente igual
            gasto_id = None
            if pagar_docente and monto_docente > 0:
                concepto = f"Devolución - pago docente ({docente_nombre or 's/d'})"
                if motivo:
                    concepto += f" · {motivo[:60]}"
                gasto_data = {
                    'concepto': concepto, 'monto': monto_docente, 'fecha': fecha,
                    'categoria': 'Devolución - pago docente', 'persona': docente_nombre or '',
                    'reembolso': False, 'registrado_por': current_user.nombre,
                    'mes': fecha_obj.month, 'anio': fecha_obj.year,
                    'mes_periodo': fecha_obj.month, 'anio_periodo': fecha_obj.year
                }
                try:
                    g = supabase.table('gastos').insert(gasto_data).execute()
                    gasto_id = g.data[0]['id'] if g.data else None
                except Exception:
                    gasto_data.pop('mes_periodo', None)
                    gasto_data.pop('anio_periodo', None)
                    g = supabase.table('gastos').insert(gasto_data).execute()
                    gasto_id = g.data[0]['id'] if g.data else None

            # 2) Registrar la devolución
            supabase.table('devoluciones').insert({
                'fecha': fecha, 'tipo_cliente': tipo_cliente,
                'estudiante_id': estudiante_id, 'cliente_id': cliente_id, 'cita_id': cita_id,
                'monto': monto, 'tipo_pago': tipo_pago, 'motivo': motivo,
                'pagar_docente': pagar_docente, 'docente_nombre': docente_nombre,
                'monto_docente': monto_docente, 'gasto_id': gasto_id,
                'mes_periodo': fecha_obj.month, 'anio_periodo': fecha_obj.year,
                'registrado_por': current_user.nombre
            }).execute()

            # 3) Si es cliente externo con cita, restar de lo pagado de la cita
            if tipo_cliente == 'externo' and cita_id:
                cita = supabase.table('citas_psicologia').select('*').eq('id', cita_id).execute()
                if cita.data:
                    c = cita.data[0]
                    nuevo_pagado = max(0, (c.get('monto_pagado', 0) or 0) - monto)
                    if nuevo_pagado <= 0:
                        nuevo_estado = 'agendada'
                    elif nuevo_pagado >= (c.get('valor', 0) or 0):
                        nuevo_estado = 'pagada'
                    else:
                        nuevo_estado = 'parcial'
                    supabase.table('citas_psicologia').update({
                        'monto_pagado': nuevo_pagado, 'estado': nuevo_estado
                    }).eq('id', cita_id).execute()

            flash('✅ Devolución registrada', 'success')
        return redirect(url_for('devoluciones'))

    # GET
    mes = int(request.args.get('mes', date.today().month))
    anio = int(request.args.get('anio', date.today().year))

    estudiantes = supabase.table('estudiantes').select('id,nombres,apellidos').eq('activo', True).order('apellidos').execute()
    estudiantes_lista = [{'id': e['id'], 'nombre': f"{e['apellidos']} {e['nombres']}"} for e in (estudiantes.data or [])]

    try:
        clientes_ext = supabase.table('clientes_externos').select('id,nombre').eq('activo', True).order('nombre').execute().data or []
    except Exception:
        clientes_ext = []
    try:
        citas = supabase.table('citas_psicologia').select('id,cliente_id,fecha,valor,monto_pagado,psicologo_nombre').gt('monto_pagado', 0).order('fecha', desc=True).execute().data or []
    except Exception:
        citas = []

    # Devoluciones del período + enriquecer con nombre del cliente
    try:
        devs = supabase.table('devoluciones').select('*').order('fecha', desc=True).execute().data or []
    except Exception:
        devs = []
    est_map = {e['id']: e['nombre'] for e in estudiantes_lista}
    cli_map = {c['id']: c['nombre'] for c in clientes_ext}
    devs_periodo = []
    total_devuelto = 0.0
    total_docente = 0.0
    for d in devs:
        mp, ap = d.get('mes_periodo'), d.get('anio_periodo')
        en_periodo = (int(mp) == mes and int(ap) == anio) if (mp and ap) else ((d.get('fecha','') or '')[:7] == f"{anio}-{mes:02d}")
        if d.get('tipo_cliente') == 'estudiante':
            d['cliente_nombre'] = est_map.get(d.get('estudiante_id'), 'Estudiante')
        else:
            d['cliente_nombre'] = cli_map.get(d.get('cliente_id'), 'Cliente externo')
        if en_periodo:
            devs_periodo.append(d)
            total_devuelto += d.get('monto', 0) or 0
            total_docente += d.get('monto_docente', 0) or 0

    return render_template('devoluciones.html',
                           estudiantes=estudiantes_lista, clientes_externos=clientes_ext, citas=citas,
                           devoluciones=devs_periodo, total_devuelto=total_devuelto, total_docente=total_docente,
                           profesores=cargar_profesores(), mes=mes, anio=anio, today=date.today().isoformat())

@app.route('/api/devolucion/<int:id>/eliminar', methods=['POST'])
@login_required
@socio_admin_required
def eliminar_devolucion(id):
    dev = supabase.table('devoluciones').select('*').eq('id', id).execute()
    if not dev.data:
        return jsonify({'success': False, 'error': 'No encontrada'})
    d = dev.data[0]
    # Revertir el gasto vinculado
    if d.get('gasto_id'):
        try:
            supabase.table('gastos').delete().eq('id', d['gasto_id']).execute()
        except Exception:
            pass
    # Revertir el pago de la cita externa (volver a sumar lo devuelto)
    if d.get('tipo_cliente') == 'externo' and d.get('cita_id'):
        cita = supabase.table('citas_psicologia').select('*').eq('id', d['cita_id']).execute()
        if cita.data:
            c = cita.data[0]
            nuevo_pagado = (c.get('monto_pagado', 0) or 0) + (d.get('monto', 0) or 0)
            nuevo_estado = 'pagada' if nuevo_pagado >= (c.get('valor', 0) or 0) else 'parcial'
            supabase.table('citas_psicologia').update({
                'monto_pagado': nuevo_pagado, 'estado': nuevo_estado
            }).eq('id', d['cita_id']).execute()
    supabase.table('devoluciones').delete().eq('id', id).execute()
    return jsonify({'success': True})


# ========== MOVIMIENTOS EN CUENTA (conciliación bancaria) — SOLO ADMIN ==========
def _norm_num(v):
    """Convierte un valor de celda a float. Maneja $, separadores de miles,
    coma decimal y paréntesis (negativos). Devuelve 0.0 si no es numérico."""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return 0.0
    neg = s.startswith('(') and s.endswith(')')
    s = s.replace('$', '').replace('USD', '').replace('(', '').replace(')', '').replace(' ', '')
    if ',' in s and '.' in s:
        # 1.234,56 -> miles '.', decimal ','
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        n = float(s)
    except ValueError:
        return 0.0
    return -n if neg else n

def _norm_fecha(v):
    """Devuelve 'YYYY-MM-DD' a partir de varios formatos comunes o None."""
    if v is None or v == '':
        return None
    if isinstance(v, (datetime, date)):
        return v.strftime('%Y-%m-%d')
    s = str(v).strip()
    # quita parte de hora si viene 'YYYY-MM-DD HH:MM:SS' o '2026-6-10, 2:23 PM'
    s = s.split(' ')[0].rstrip(',;')
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y', '%d-%m-%y', '%m/%d/%Y'):
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None

def hash_movimiento(m):
    """md5 estable de los campos clave para deduplicar el estado de cuenta.
    Incluye el SALDO: dos movimientos del mismo día con igual monto y
    descripción (p.ej. dos transferencias idénticas) tienen saldo distinto,
    así que ambos se registran en lugar de descartar el segundo como repetido."""
    saldo = m.get('saldo')
    base = '|'.join([
        str(m.get('fecha') or ''),
        f"{float(m.get('monto') or 0):.2f}",
        (m.get('descripcion') or '').strip().lower()[:80],
        (m.get('referencia') or '').strip().lower(),
        f"{float(saldo):.2f}" if saldo is not None else ''
    ])
    return hashlib.md5(base.encode('utf-8')).hexdigest()

# Palabras clave para mapear columnas del estado de cuenta
_COL_KEYS = {
    'fecha': ['fecha', 'date'],
    'descripcion': ['descrip', 'concepto', 'detalle', 'transacc', 'glosa'],
    'debito': ['debito', 'débito', 'retiro', 'cargo', 'egreso', 'debe'],
    'credito': ['credito', 'crédito', 'deposito', 'depósito', 'abono', 'ingreso', 'haber'],
    'monto': ['monto', 'valor', 'importe'],
    'saldo': ['saldo', 'balance'],
    'referencia': ['referencia', 'documento', 'comprobante', 'num', 'nº', 'no.', 'doc'],
}

def _mapear_columnas(headers):
    """headers: lista de strings de la fila de cabecera. Devuelve dict col->idx."""
    mapa = {}
    for idx, h in enumerate(headers):
        hl = (str(h) if h is not None else '').strip().lower()
        if not hl:
            continue
        for campo, claves in _COL_KEYS.items():
            if campo in mapa:
                continue
            if any(k in hl for k in claves):
                mapa[campo] = idx
                break
    return mapa

def _fila_a_movimiento(row, mapa):
    """Convierte una fila (lista) en un movimiento normalizado o None."""
    def cell(campo):
        i = mapa.get(campo)
        return row[i] if (i is not None and i < len(row)) else None
    fecha = _norm_fecha(cell('fecha'))
    if not fecha:
        return None
    descripcion = str(cell('descripcion') or '').strip()
    referencia = str(cell('referencia') or '').strip()
    saldo = _norm_num(cell('saldo')) if mapa.get('saldo') is not None else None
    # Monto: prioriza débito/crédito separados; si no, columna única
    monto = 0.0
    if mapa.get('credito') is not None or mapa.get('debito') is not None:
        cr = _norm_num(cell('credito'))
        de = _norm_num(cell('debito'))
        monto = abs(cr) - abs(de)
    elif mapa.get('monto') is not None:
        monto = _norm_num(cell('monto'))
    if monto == 0:
        return None
    return {
        'fecha': fecha, 'descripcion': descripcion, 'referencia': referencia,
        'monto': round(monto, 2), 'tipo': 'credito' if monto > 0 else 'debito',
        'saldo': round(saldo, 2) if saldo is not None else None
    }

def parsear_estado_cuenta(file_bytes, filename):
    """Devuelve (lista_movimientos, error_msg). error_msg None si todo ok."""
    nombre = (filename or '').lower()
    if nombre.endswith(('.xlsx', '.xlsm', '.xls')):
        if openpyxl is None:
            return [], 'Falta la librería openpyxl en el servidor (pip install openpyxl).'
        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
        except Exception as e:
            return [], f'No se pudo abrir el Excel: {e}'
        ws = wb.active
        # Algunos bancos exportan el XLSX con la dimensión mal declarada (A1:A1);
        # en modo read_only openpyxl la cree y lee una sola celda vacía.
        try:
            ws.reset_dimensions()
        except AttributeError:
            pass
        filas = [[c for c in row] for row in ws.iter_rows(values_only=True)]
        # Buscar fila de cabecera en las primeras 20 filas
        mapa, header_idx = {}, None
        for i, fila in enumerate(filas[:20]):
            m = _mapear_columnas([str(c) if c is not None else '' for c in fila])
            if 'fecha' in m and (('credito' in m or 'debito' in m) or 'monto' in m):
                mapa, header_idx = m, i
                break
        if header_idx is None:
            return [], 'No se reconocieron las columnas (fecha y débito/crédito o monto) en el Excel.'
        movs = []
        for fila in filas[header_idx + 1:]:
            mv = _fila_a_movimiento(list(fila), mapa)
            if mv:
                movs.append(mv)
        return movs, None
    elif nombre.endswith('.pdf'):
        if pdfplumber is None:
            return [], 'Falta la librería pdfplumber en el servidor (pip install pdfplumber).'
        movs = []
        try:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                texto = '\n'.join((p.extract_text() or '') for p in pdf.pages)
        except Exception as e:
            return [], f'No se pudo leer el PDF: {e}'
        # Best-effort: líneas que empiezan con fecha y traen al menos un monto
        patron_fecha = re.compile(r'^(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s+(.*)')
        patron_monto = re.compile(r'-?\$?\(?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})\)?')
        for linea in texto.splitlines():
            linea = linea.strip()
            mf = patron_fecha.match(linea)
            if not mf:
                continue
            fecha = _norm_fecha(mf.group(1))
            if not fecha:
                continue
            resto = mf.group(2)
            montos = patron_monto.findall(resto)
            if not montos:
                continue
            # El último número suele ser el saldo; el penúltimo (si hay) el movimiento
            valores = [_norm_num(x) for x in montos]
            if len(valores) >= 2:
                monto, saldo = valores[-2], valores[-1]
            else:
                monto, saldo = valores[-1], None
            descripcion = patron_monto.sub('', resto).strip()
            if monto == 0:
                continue
            movs.append({
                'fecha': fecha, 'descripcion': descripcion, 'referencia': '',
                'monto': round(monto, 2), 'tipo': 'credito' if monto > 0 else 'debito',
                'saldo': round(saldo, 2) if saldo is not None else None
            })
        if not movs:
            return [], 'No se pudieron extraer movimientos del PDF (formato no reconocido). Sube el Excel del estado de cuenta.'
        return movs, None
    return [], 'Formato no soportado. Sube un archivo .xlsx o .pdf.'

# Los estados de cuenta solo se contemplan a partir de mayo 2026
FECHA_MIN_ESTADO_CUENTA = '2026-05-01'
DIAS_TOLERANCIA_CONCILIACION = 5

def _norm_texto(s):
    """minúsculas, sin tildes, solo letras/números — para comparar nombres con descripciones bancarias."""
    s = (s or '').lower()
    s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z0-9 ]+', ' ', s)

def _nombre_coincide(nombre, descripcion_norm):
    """True si alguna palabra significativa (≥4 letras) del nombre aparece en la descripción del banco."""
    if not nombre or not descripcion_norm:
        return False
    palabras = [w for w in _norm_texto(nombre).split() if len(w) >= 4]
    return any(w in descripcion_norm for w in palabras)

def _dias_entre(fecha_a, fecha_b):
    try:
        return abs((datetime.strptime(str(fecha_a)[:10], '%Y-%m-%d') - datetime.strptime(str(fecha_b)[:10], '%Y-%m-%d')).days)
    except Exception:
        return None

def _pagos_ya_conciliados():
    """IDs de pagos ya enlazados a algún movimiento (no se enlazan dos veces)."""
    r = supabase.table('movimientos_cuenta').select('conciliado_id').eq('conciliado_tipo', 'pago').eq('estado_conciliacion', 'conciliado').execute()
    return {x['conciliado_id'] for x in (r.data or []) if x.get('conciliado_id')}

def _cargar_pagos_rango(fmin, fmax):
    """Pagos del rango con el nombre del estudiante y de sus padres (para cruzar con la descripción)."""
    pagos = supabase.table('pagos').select('id,monto,fecha_pago,tipo_pago,concepto,estudiante_id').gte('fecha_pago', fmin).lte('fecha_pago', fmax).execute().data or []
    est_ids = list({p['estudiante_id'] for p in pagos if p.get('estudiante_id')})
    est_map = {}
    for i in range(0, len(est_ids), 100):
        r = supabase.table('estudiantes').select('id,nombres,apellidos,padre_nombre,madre_nombre').in_('id', est_ids[i:i + 100]).execute()
        for e in (r.data or []):
            est_map[e['id']] = e
    for p in pagos:
        e = est_map.get(p.get('estudiante_id')) or {}
        p['estudiante'] = f"{e.get('apellidos') or ''} {e.get('nombres') or ''}".strip()
        p['padre_nombre'] = e.get('padre_nombre') or ''
        p['madre_nombre'] = e.get('madre_nombre') or ''
        p['nombres_busqueda'] = [n for n in (p['estudiante'], p['padre_nombre'], p['madre_nombre']) if n]
    return pagos

def _score_pago(mov, pago):
    """Puntaje de cruce movimiento↔pago o None si no cumple monto+fecha.
    Mayor puntaje = mejor candidato (fecha exacta y nombre del padre/madre suman)."""
    if abs((pago.get('monto') or 0) - abs(mov.get('monto') or 0)) >= 0.01:
        return None
    dias = _dias_entre(pago.get('fecha_pago'), mov.get('fecha'))
    if dias is None or dias > DIAS_TOLERANCIA_CONCILIACION:
        return None
    desc_norm = _norm_texto(mov.get('descripcion'))
    nombre_ok = any(_nombre_coincide(n, desc_norm) for n in pago.get('nombres_busqueda', []))
    return (3 if nombre_ok else 0) + (2 if dias == 0 else 1), dias, nombre_ok

def conciliar_nuevos(movs):
    """Cruza movimientos (dicts con id) con pagos y gastos confirmando monto y fecha;
    el nombre del padre/madre/estudiante en la descripción desempata y refuerza el cruce.
    Crédito ↔ pago, débito ↔ gasto. Lo que no cruza queda 'pendiente' (por cuadrar).
    Devuelve cuántos quedaron conciliados."""
    movs = [m for m in movs if m.get('fecha') and m['fecha'] >= FECHA_MIN_ESTADO_CUENTA]
    if not movs:
        return 0
    fechas = [m['fecha'] for m in movs]
    fmin = (datetime.strptime(min(fechas), '%Y-%m-%d') - timedelta(days=DIAS_TOLERANCIA_CONCILIACION)).strftime('%Y-%m-%d')
    fmax = (datetime.strptime(max(fechas), '%Y-%m-%d') + timedelta(days=DIAS_TOLERANCIA_CONCILIACION)).strftime('%Y-%m-%d')
    pagos = _cargar_pagos_rango(fmin, fmax)
    usados_pago = _pagos_ya_conciliados()
    pagos = [p for p in pagos if p['id'] not in usados_pago]
    gastos = supabase.table('gastos').select('id,monto,fecha').gte('fecha', fmin).lte('fecha', fmax).execute().data or []
    usados_gasto = set()
    conciliados = 0
    for m in movs:
        tipo, ref_id = None, None
        if (m.get('monto') or 0) > 0:  # crédito ↔ pago de estudiante
            candidatos = []
            for p in pagos:
                if p['id'] in usados_pago:
                    continue
                score = _score_pago(m, p)
                if score:
                    candidatos.append((score[0], -score[1], p))
            if candidatos:
                candidatos.sort(key=lambda c: (c[0], c[1]), reverse=True)
                mejor = candidatos[0][2]
                tipo, ref_id = 'pago', mejor['id']
                usados_pago.add(mejor['id'])
        else:  # débito ↔ gasto
            for g in gastos:
                if g['id'] in usados_gasto:
                    continue
                if abs((g.get('monto') or 0) - abs(m['monto'])) < 0.01:
                    dias = _dias_entre(g.get('fecha'), m['fecha'])
                    if dias is not None and dias <= DIAS_TOLERANCIA_CONCILIACION:
                        tipo, ref_id = 'gasto', g['id']
                        usados_gasto.add(g['id'])
                        break
        if tipo:
            supabase.table('movimientos_cuenta').update({
                'estado_conciliacion': 'conciliado', 'conciliado_tipo': tipo, 'conciliado_id': ref_id
            }).eq('id', m['id']).execute()
            conciliados += 1
    return conciliados

@app.route('/movimientos-cuenta')
@login_required
@socio_admin_required
def movimientos_cuenta():
    mes = request.args.get('mes', '')
    anio = request.args.get('anio', '')
    fecha_desde = request.args.get('fecha_desde', '')
    fecha_hasta = request.args.get('fecha_hasta', '')
    # Orden: fecha desc; dentro de la misma fecha, id asc (el banco lista de lo
    # más reciente a lo más antiguo, así que el id menor es el más nuevo)
    q = supabase.table('movimientos_cuenta').select('*').gte('fecha', FECHA_MIN_ESTADO_CUENTA) \
        .order('fecha', desc=True).order('id', desc=False)
    movs_all = q.execute().data or []
    movs = movs_all
    # Período: por fechas específicas (prioridad) o por mes/año
    _MESES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio',
              'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
    if fecha_desde or fecha_hasta:
        movs = [m for m in movs
                if (not fecha_desde or (m.get('fecha', '') or '') >= fecha_desde)
                and (not fecha_hasta or (m.get('fecha', '') or '') <= fecha_hasta)]
        periodo_label = f"{fecha_desde or 'inicio'} → {fecha_hasta or 'última fecha'}"
    elif mes and anio:
        movs = [m for m in movs if (m.get('fecha', '') or '')[:7] == f"{int(anio)}-{int(mes):02d}"]
        periodo_label = f"{_MESES[int(mes) - 1]} {anio}"
    else:
        periodo_label = 'Todo el período cargado'
    total_conc = sum(m.get('monto', 0) or 0 for m in movs if m.get('estado_conciliacion') == 'conciliado')
    total_pend = sum(m.get('monto', 0) or 0 for m in movs if m.get('estado_conciliacion') == 'pendiente')
    n_pend = sum(1 for m in movs if m.get('estado_conciliacion') == 'pendiente')
    total_cred = sum(m.get('monto', 0) or 0 for m in movs if (m.get('monto') or 0) > 0)
    total_deb = sum(abs(m.get('monto', 0) or 0) for m in movs if (m.get('monto') or 0) < 0)

    # Saldo inicial y final del período mostrado (saldo que reporta el banco):
    # final = saldo del movimiento más reciente; inicial = saldo del más
    # antiguo menos su monto (saldo antes de ese movimiento)
    con_saldo = [m for m in movs if m.get('saldo') is not None]
    saldo_final = con_saldo[0].get('saldo') if con_saldo else None
    saldo_inicial = None
    if con_saldo:
        viejo = con_saldo[-1]
        saldo_inicial = round((viejo.get('saldo') or 0) - (viejo.get('monto') or 0), 2)

    # Lotes subidos (estados de cuenta) — gestión solo para el administrador
    lotes_map = {}
    for m in movs_all:
        lid = m.get('lote_id')
        if not lid:
            continue
        l = lotes_map.setdefault(lid, {'lote_id': lid, 'banco': m.get('banco') or '—', 'n': 0,
                                       'fmin': m['fecha'], 'fmax': m['fecha'],
                                       'cargado_por': m.get('cargado_por') or ''})
        l['n'] += 1
        l['fmin'] = min(l['fmin'], m['fecha'])
        l['fmax'] = max(l['fmax'], m['fecha'])
    lotes = sorted(lotes_map.values(), key=lambda x: x['fmax'], reverse=True)
    # Detalle de los pagos enlazados (para mostrar estudiante y fecha en lugar de solo el ID)
    pago_ids = list({m['conciliado_id'] for m in movs if m.get('conciliado_tipo') == 'pago' and m.get('conciliado_id')})
    pagos_det = {}
    for i in range(0, len(pago_ids), 100):
        try:
            r = supabase.table('pagos').select('id,monto,fecha_pago,estudiante_id').in_('id', pago_ids[i:i + 100]).execute()
            for p in (r.data or []):
                pagos_det[p['id']] = p
        except Exception:
            pass
    est_ids = list({p['estudiante_id'] for p in pagos_det.values() if p.get('estudiante_id')})
    est_nombres = {}
    for i in range(0, len(est_ids), 100):
        try:
            r = supabase.table('estudiantes').select('id,nombres,apellidos').in_('id', est_ids[i:i + 100]).execute()
            for e in (r.data or []):
                est_nombres[e['id']] = f"{e.get('apellidos') or ''} {e.get('nombres') or ''}".strip()
        except Exception:
            pass
    for m in movs:
        p = pagos_det.get(m.get('conciliado_id')) if m.get('conciliado_tipo') == 'pago' else None
        if p:
            m['conciliado_detalle'] = f"{est_nombres.get(p.get('estudiante_id'), 'Estudiante')} · {str(p.get('fecha_pago') or '')[:10]}"
    return render_template('movimientos_cuenta.html',
                           movimientos=movs, total_conciliado=total_conc, total_pendiente=total_pend,
                           n_pendientes=n_pend, mes=mes, anio=anio,
                           fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, periodo_label=periodo_label,
                           total_creditos=total_cred, total_debitos=total_deb,
                           saldo_inicial=saldo_inicial, saldo_final=saldo_final, lotes=lotes,
                           openpyxl_ok=openpyxl is not None, pdf_ok=pdfplumber is not None,
                           today=date.today().isoformat())

@app.route('/movimientos-cuenta/subir', methods=['POST'])
@login_required
@socio_admin_required
def subir_estado_cuenta():
    archivo = request.files.get('archivo')
    if not archivo or not archivo.filename:
        flash('❌ Selecciona un archivo (.xlsx o .pdf)', 'error')
        return redirect(url_for('movimientos_cuenta'))
    banco = (request.form.get('banco', '') or '').strip()
    movs, error = parsear_estado_cuenta(archivo.read(), archivo.filename)
    if error:
        flash(f'❌ {error}', 'error')
        return redirect(url_for('movimientos_cuenta'))
    if not movs:
        flash('⚠️ No se encontraron movimientos en el archivo', 'warning')
        return redirect(url_for('movimientos_cuenta'))

    # Solo se contemplan movimientos desde mayo
    antes_de_mayo = [m for m in movs if m['fecha'] < FECHA_MIN_ESTADO_CUENTA]
    movs = [m for m in movs if m['fecha'] >= FECHA_MIN_ESTADO_CUENTA]
    if not movs:
        flash(f'⚠️ Todos los movimientos del archivo son anteriores a mayo ({len(antes_de_mayo)} descartados). Solo se contemplan estados de cuenta desde mayo.', 'warning')
        return redirect(url_for('movimientos_cuenta'))

    # Calcular hash y deduplicar contra lo ya guardado
    for m in movs:
        m['hash_mov'] = hash_movimiento(m)
    hashes = list({m['hash_mov'] for m in movs})
    existentes = set()
    for i in range(0, len(hashes), 100):
        chunk = hashes[i:i + 100]
        try:
            r = supabase.table('movimientos_cuenta').select('hash_mov').in_('hash_mov', chunk).execute()
            existentes.update(x['hash_mov'] for x in (r.data or []))
        except Exception:
            pass

    nuevos = [m for m in movs if m['hash_mov'] not in existentes]
    # Evita duplicados dentro del mismo archivo
    vistos, nuevos_unicos = set(), []
    for m in nuevos:
        if m['hash_mov'] in vistos:
            continue
        vistos.add(m['hash_mov'])
        nuevos_unicos.append(m)
    nuevos = nuevos_unicos

    ya_existian = len(movs) - len(nuevos)
    if not nuevos:
        flash(f'ℹ️ Este estado de cuenta ya está subido completamente ({ya_existian} movimientos ya registrados).', 'info')
        return redirect(url_for('movimientos_cuenta'))

    lote_id = str(uuid.uuid4())
    insertados = []
    for m in nuevos:
        fila = {
            'lote_id': lote_id, 'banco': banco or None, 'fecha': m['fecha'],
            'descripcion': m['descripcion'], 'referencia': m['referencia'] or None,
            'monto': m['monto'], 'tipo': m['tipo'], 'saldo': m['saldo'],
            'hash_mov': m['hash_mov'], 'estado_conciliacion': 'pendiente',
            'cargado_por': current_user.nombre
        }
        try:
            res = supabase.table('movimientos_cuenta').insert(fila).execute()
            if res.data:
                m['id'] = res.data[0]['id']
                insertados.append(m)
        except Exception:
            pass  # hash duplicado por carrera u otro error: se ignora

    n_conciliados = conciliar_nuevos(insertados)

    partes = [f'✅ {len(insertados)} movimientos agregados', f'{n_conciliados} cruzados automáticamente con pagos/gastos']
    if ya_existian:
        partes.append(f'{ya_existian} repetidos ignorados')
    if antes_de_mayo:
        partes.append(f'{len(antes_de_mayo)} anteriores a mayo descartados')
    flash(' · '.join(partes) + '.', 'success')
    return redirect(url_for('movimientos_cuenta'))

@app.route('/movimientos-cuenta/conciliar-todo', methods=['POST'])
@login_required
@socio_admin_required
def conciliar_pendientes():
    """Re-cruza todos los movimientos pendientes con los pagos y gastos registrados."""
    movs = supabase.table('movimientos_cuenta').select('id,fecha,monto,descripcion') \
        .eq('estado_conciliacion', 'pendiente').gte('fecha', FECHA_MIN_ESTADO_CUENTA).execute().data or []
    n = conciliar_nuevos(movs)
    if n:
        flash(f'✅ {n} movimientos cruzados con pagos/gastos. Quedan {len(movs) - n} por cuadrar.', 'success')
    else:
        flash(f'ℹ️ No se encontraron cruces nuevos. {len(movs)} movimientos siguen por cuadrar.', 'info')
    return redirect(url_for('movimientos_cuenta'))

@app.route('/api/movimiento/<int:id>/candidatos')
@login_required
@socio_admin_required
def candidatos_movimiento(id):
    """Pagos (créditos) o gastos (débitos) candidatos para enlazar manualmente un movimiento.
    Marca coincidencia de monto, cercanía de fecha y nombre del padre/madre/estudiante."""
    r = supabase.table('movimientos_cuenta').select('*').eq('id', id).execute()
    if not r.data:
        return jsonify({'success': False, 'error': 'Movimiento no encontrado'})
    mov = r.data[0]
    objetivo = abs(mov.get('monto') or 0)
    desc_norm = _norm_texto(mov.get('descripcion'))
    ventana = 30  # días alrededor del movimiento para ofrecer candidatos
    fmin = (datetime.strptime(mov['fecha'], '%Y-%m-%d') - timedelta(days=ventana)).strftime('%Y-%m-%d')
    fmax = (datetime.strptime(mov['fecha'], '%Y-%m-%d') + timedelta(days=ventana)).strftime('%Y-%m-%d')
    candidatos = []
    if (mov.get('monto') or 0) > 0:
        pagos = _cargar_pagos_rango(fmin, fmax)
        usados = _pagos_ya_conciliados()
        for p in pagos:
            dias = _dias_entre(p.get('fecha_pago'), mov['fecha'])
            monto_igual = abs((p.get('monto') or 0) - objetivo) < 0.01
            nombre_ok = any(_nombre_coincide(n, desc_norm) for n in p.get('nombres_busqueda', []))
            candidatos.append({
                'tipo': 'pago', 'id': p['id'], 'fecha': str(p.get('fecha_pago') or '')[:10],
                'monto': p.get('monto'), 'detalle': p['estudiante'] or 'Sin estudiante',
                'extra': ' / '.join(x for x in (p['padre_nombre'], p['madre_nombre']) if x),
                'monto_igual': monto_igual, 'dias': dias, 'nombre_coincide': nombre_ok,
                'ya_usado': p['id'] in usados
            })
    else:
        gastos = supabase.table('gastos').select('*').gte('fecha', fmin).lte('fecha', fmax).execute().data or []
        for g in gastos:
            dias = _dias_entre(g.get('fecha'), mov['fecha'])
            candidatos.append({
                'tipo': 'gasto', 'id': g['id'], 'fecha': str(g.get('fecha') or '')[:10],
                'monto': g.get('monto'), 'detalle': g.get('concepto') or 'Gasto',
                'extra': g.get('persona') or g.get('categoria') or '',
                'monto_igual': abs((g.get('monto') or 0) - objetivo) < 0.01,
                'dias': dias, 'nombre_coincide': False, 'ya_usado': False
            })
    # Mejores primero: monto igual, luego nombre, luego cercanía de fecha
    candidatos.sort(key=lambda c: (not c['monto_igual'], not c['nombre_coincide'], c['dias'] if c['dias'] is not None else 999))
    return jsonify({'success': True, 'movimiento': {
        'id': mov['id'], 'fecha': mov['fecha'], 'monto': mov['monto'], 'descripcion': mov.get('descripcion') or ''
    }, 'candidatos': candidatos[:40]})

@app.route('/api/estudiantes/lista')
@login_required
@socio_admin_required
def estudiantes_lista_conciliacion():
    """Estudiantes (apellidos + nombres) para el selector del enlace manual."""
    r = supabase.table('estudiantes').select('id,nombres,apellidos').order('apellidos').execute()
    data = [{'id': e['id'], 'nombre': f"{e.get('apellidos') or ''} {e.get('nombres') or ''}".strip()}
            for e in (r.data or [])]
    return jsonify({'success': True, 'estudiantes': data})


@app.route('/api/estudiante/<int:id>/historial-pagos')
@login_required
@socio_admin_required
def historial_pagos_estudiante(id):
    """Historial para el enlace manual: pagos del estudiante (fecha, monto, tipo,
    concepto) con las asignaturas de sus sesiones cercanas a cada pago (±30 días;
    si no hay sesiones cerca, se muestran todas las asignaturas del estudiante)."""
    est = supabase.table('estudiantes').select('id,nombres,apellidos,padre_nombre,madre_nombre').eq('id', id).execute()
    if not est.data:
        return jsonify({'success': False, 'error': 'Estudiante no encontrado'})
    e = est.data[0]
    pagos = supabase.table('pagos').select('id,monto,fecha_pago,tipo_pago,concepto') \
        .eq('estudiante_id', id).order('fecha_pago', desc=True).execute().data or []
    sesiones = supabase.table('sesiones').select('fecha,asignatura,tema_terapia') \
        .eq('estudiante_id', id).execute().data or []
    usados = _pagos_ya_conciliados()
    asignaturas_todas = sorted({(s.get('asignatura') or s.get('tema_terapia') or '').strip()
                                for s in sesiones} - {''})
    out = []
    for p in pagos:
        cerca = set()
        for s in sesiones:
            d = _dias_entre(s.get('fecha'), p.get('fecha_pago'))
            if d is not None and d <= 30:
                a = (s.get('asignatura') or s.get('tema_terapia') or '').strip()
                if a:
                    cerca.add(a)
        out.append({
            'id': p['id'], 'fecha': str(p.get('fecha_pago') or '')[:10],
            'monto': p.get('monto'), 'tipo_pago': p.get('tipo_pago') or '',
            'concepto': p.get('concepto') or '',
            'asignaturas': sorted(cerca) or asignaturas_todas,
            'ya_usado': p['id'] in usados,
        })
    return jsonify({'success': True,
                    'estudiante': {'id': e['id'],
                                   'nombre': f"{e.get('apellidos') or ''} {e.get('nombres') or ''}".strip(),
                                   'padres': ' / '.join(x for x in (e.get('padre_nombre'), e.get('madre_nombre')) if x)},
                    'asignaturas': asignaturas_todas,
                    'pagos': out})


@app.route('/api/movimiento/<int:id>/justificar', methods=['POST'])
@login_required
@socio_admin_required
def justificar_movimiento(id):
    data = request.get_json() or {}
    texto = (data.get('justificacion', '') or '').strip()
    if not texto:
        return jsonify({'success': False, 'error': 'Falta la justificación'})
    supabase.table('movimientos_cuenta').update({
        'estado_conciliacion': 'justificado', 'justificacion': texto
    }).eq('id', id).execute()
    return jsonify({'success': True})

@app.route('/api/movimiento/<int:id>/conciliar', methods=['POST'])
@login_required
@socio_admin_required
def conciliar_manual(id):
    data = request.get_json() or {}
    tipo = data.get('tipo')      # 'pago' | 'gasto' | 'cita' | 'devolucion'
    ref_id = data.get('ref_id')
    if tipo == 'pago' and ref_id and int(ref_id) in _pagos_ya_conciliados():
        return jsonify({'success': False, 'error': 'Ese pago ya está enlazado a otro movimiento.'})
    supabase.table('movimientos_cuenta').update({
        'estado_conciliacion': 'conciliado', 'conciliado_tipo': tipo,
        'conciliado_id': int(ref_id) if ref_id else None
    }).eq('id', id).execute()
    return jsonify({'success': True})

@app.route('/api/movimiento/<int:id>/pendiente', methods=['POST'])
@login_required
@socio_admin_required
def revertir_movimiento(id):
    supabase.table('movimientos_cuenta').update({
        'estado_conciliacion': 'pendiente', 'conciliado_tipo': None,
        'conciliado_id': None, 'justificacion': None
    }).eq('id', id).execute()
    return jsonify({'success': True})

@app.route('/api/movimiento/<int:id>/eliminar', methods=['POST'])
@login_required
@admin_required  # eliminar movimientos: SOLO administrador
def eliminar_movimiento(id):
    supabase.table('movimientos_cuenta').delete().eq('id', id).execute()
    return jsonify({'success': True})

@app.route('/movimientos-cuenta/lote/<lote_id>/eliminar', methods=['POST'])
@login_required
@admin_required  # eliminar el estado de cuenta completo: SOLO administrador
def eliminar_lote_movimientos(lote_id):
    supabase.table('movimientos_cuenta').delete().eq('lote_id', lote_id).execute()
    flash('🗑️ Estado de cuenta eliminado', 'info')
    return redirect(url_for('movimientos_cuenta'))


# ========== INICIALIZACIÓN ==========
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)