import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from config import Config
from models import check_password, Usuario
from supabase_client import supabase
from google_calendar import crear_evento_calendar, eliminar_evento_calendar, crear_o_actualizar_evento_calendar
from datetime import datetime, date
from calendar import monthrange
from functools import wraps

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
    {'nombre': 'Clínica en evaluación psicopedagógica (normal)', 'precio': 40}
]

PRECIOS_CLASE = [10, 11, 12, 15]
PRECIOS_MATRICULA = [0, 18, 20]
PRECIOS_PENSION = [99, 100, 110]
PROFESORES = ['Carmen Reinoso', 'Rosalía Moscoso', 'Marco Antonio Posligua',
              'Edwin Rumipulla', 'Catherine Alvear', 'Alexander Nivelo',
              'Daniel Castillo', 'Johanna Nievecela']
ENCARGADOS = ['CARMEN', 'ROSALÍA', 'EDWIN', 'MAP', 'JOHANNA']

# ========== CONSTANTES DE PAGOS ==========
PAGO_DOCENCIA_POR_HORA = 7  # $7 por hora para clases
PORCENTAJE_PSICOLOGIA = 0.4018  # 40.18% para terapias psicológicas
COMISION_CLIENTE_EXTERNO = 0.25  # 25% para clientes externos (psicología especial)
PAQUETE_TERAPIAS = {
    'cantidad': 4,
    'precio_total': 160,
    'precio_por_sesion': 40
}

# ========== RUTAS PRINCIPALES ==========

@app.route('/')
def inicio():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('inicio.html')

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
    # Contar solicitudes pendientes para mostrar badge
    solicitudes_pendientes = 0
    if current_user.rol in ['admin', 'socio']:
        solicitudes = supabase.table('anticipos_solicitudes').select('*').eq('estado', 'pendiente').execute()
        solicitudes_pendientes = len(solicitudes.data or [])
    return render_template('dashboard.html', rol=current_user.rol, solicitudes_pendientes=solicitudes_pendientes)

# ========== ANTICIPOS PARA DOCENTES/PSICÓLOGOS ==========

@app.route('/mis-anticipos')
@login_required
def mis_anticipos():
    """Vista para que docentes/psicólogos vean y soliciten anticipos"""
    if current_user.rol not in ['profesor', 'psicologo', 'admin', 'socio']:
        flash('❌ Acceso restringido', 'error')
        return redirect(url_for('dashboard'))
    
    # Obtener anticipos del usuario actual
    anticipos = supabase.table('anticipos_solicitudes').select('*').eq('usuario_id', current_user.id).order('fecha_solicitud', desc=True).execute()
    
    # Calcular total de pagos del mes actual para el docente
    mes_actual = date.today().month
    anio_actual = date.today().year
    sesiones = supabase.table('sesiones').select('*').eq('estado', 'Realizado').eq('profesor_terapeuta', current_user.nombre).execute()
    
    total_pagar_mes = 0
    for s in (sesiones.data or []):
        fecha = s.get('fecha', '')
        if fecha and fecha[:7] == f"{anio_actual}-{mes_actual:02d}":
            tipo = s.get('tipo_sesion', 'clase')
            horas = s.get('horas', 0) or 0
            valor = s.get('valor_total', 0) or 0
            if tipo in ['clase', 'preuniversitario']:
                total_pagar_mes += horas * PAGO_DOCENCIA_POR_HORA
            else:
                total_pagar_mes += valor * PORCENTAJE_PSICOLOGIA
    
    # Calcular anticipos ya aprobados del mes
    anticipos_aprobados = sum(a.get('monto', 0) for a in (anticipos.data or []) if a.get('estado') == 'aprobado')
    
    return render_template('mis_anticipos.html', 
                         anticipos=anticipos.data or [],
                         total_pagar_mes=total_pagar_mes,
                         anticipos_aprobados=anticipos_aprobados,
                         disponible=total_pagar_mes - anticipos_aprobados)

@app.route('/solicitar-anticipo', methods=['POST'])
@login_required
def solicitar_anticipo():
    """Solicitar un anticipo"""
    if current_user.rol not in ['profesor', 'psicologo']:
        flash('❌ Solo docentes y psicólogos pueden solicitar anticipos', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        monto = float(request.form['monto'])
        motivo = request.form['motivo']
        
        supabase.table('anticipos_solicitudes').insert({
            'usuario_id': current_user.id,
            'usuario_nombre': current_user.nombre,
            'monto': monto,
            'motivo': motivo,
            'estado': 'pendiente',
            'fecha_solicitud': date.today().isoformat()
        }).execute()
        
        flash('✅ Solicitud de anticipo enviada. Espera aprobación.', 'success')
    except Exception as e:
        flash(f'❌ Error: {str(e)}', 'error')
    
    return redirect(url_for('mis_anticipos'))

@app.route('/gestion-anticipos')
@login_required
@socio_admin_required
def gestion_anticipos():
    """Vista para que administradores/socios aprueben/rechacen anticipos"""
    solicitudes = supabase.table('anticipos_solicitudes').select('*').order('fecha_solicitud', desc=True).execute()
    return render_template('gestion_anticipos.html', solicitudes=solicitudes.data or [])

@app.route('/aprobar-anticipo/<int:id>', methods=['POST'])
@login_required
@socio_admin_required
def aprobar_anticipo(id):
    try:
        supabase.table('anticipos_solicitudes').update({
            'estado': 'aprobado',
            'fecha_aprobacion': date.today().isoformat(),
            'aprobado_por': current_user.nombre
        }).eq('id', id).execute()
        flash('✅ Anticipo aprobado', 'success')
    except Exception as e:
        flash(f'❌ Error: {str(e)}', 'error')
    return redirect(url_for('gestion_anticipos'))

@app.route('/rechazar-anticipo/<int:id>', methods=['POST'])
@login_required
@socio_admin_required
def rechazar_anticipo(id):
    try:
        motivo_rechazo = request.form.get('motivo_rechazo', 'Sin motivo especificado')
        supabase.table('anticipos_solicitudes').update({
            'estado': 'rechazado',
            'motivo_rechazo': motivo_rechazo
        }).eq('id', id).execute()
        flash('❌ Anticipo rechazado', 'info')
    except Exception as e:
        flash(f'❌ Error: {str(e)}', 'error')
    return redirect(url_for('gestion_anticipos'))

# ========== MÓDULO DE PSICOLOGÍA ESPECIAL (CLIENTES EXTERNOS) ==========

@app.route('/psicologia-especial')
@login_required
@socio_admin_required
def psicologia_especial():
    """Módulo para gestionar clientes externos de psicología"""
    clientes = supabase.table('clientes_externos').select('*').eq('activo', True).order('nombre').execute()
    citas = supabase.table('citas_psicologia').select('*, clientes_externos(*)').order('fecha', desc=True).execute()
    psicologos = supabase.table('usuarios').select('id, nombre').eq('rol', 'psicologo').eq('activo', True).execute()
    
    # Calcular totales
    total_citas = len(citas.data or [])
    total_pagado = sum(c.get('monto_pagado', 0) or 0 for c in (citas.data or []))
    total_comision_centro = sum(c.get('monto_pagado', 0) or 0 for c in (citas.data or [])) * COMISION_CLIENTE_EXTERNO
    
    return render_template('psicologia_especial.html',
                         clientes=clientes.data or [],
                         citas=citas.data or [],
                         psicologos=psicologos.data or [],
                         total_citas=total_citas,
                         total_pagado=total_pagado,
                         total_comision_centro=total_comision_centro,
                         comision_porcentaje=int(COMISION_CLIENTE_EXTERNO * 100))

@app.route('/api/cliente-externo', methods=['POST'])
@login_required
@socio_admin_required
def crear_cliente_externo():
    try:
        data = request.get_json()
        result = supabase.table('clientes_externos').insert({
            'nombre': data['nombre'],
            'telefono': data.get('telefono', ''),
            'email': data.get('email', ''),
            'activo': True,
            'usuario_id': current_user.id
        }).execute()
        return jsonify({'success': True, 'id': result.data[0]['id'] if result.data else None})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/cita-psicologia', methods=['POST'])
@login_required
@socio_admin_required
def crear_cita_psicologia():
    try:
        data = request.get_json()
        valor_cita = data.get('valor', 0)
        comision_centro = valor_cita * COMISION_CLIENTE_EXTERNO
        pago_psicologo = valor_cita - comision_centro
        
        result = supabase.table('citas_psicologia').insert({
            'cliente_id': data['cliente_id'],
            'psicologo_id': data['psicologo_id'],
            'psicologo_nombre': data['psicologo_nombre'],
            'fecha': data['fecha'],
            'hora_inicio': data['hora_inicio'],
            'hora_fin': data['hora_fin'],
            'valor': valor_cita,
            'monto_pagado': 0,
            'comision_centro': comision_centro,
            'pago_psicologo': pago_psicologo,
            'estado': 'agendada',
            'usuario_id': current_user.id
        }).execute()
        return jsonify({'success': True, 'id': result.data[0]['id'] if result.data else None})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/cita/<int:id>/pagar', methods=['POST'])
@login_required
@socio_admin_required
def registrar_pago_cita(id):
    try:
        data = request.get_json()
        monto = data.get('monto', 0)
        
        # Obtener cita
        cita = supabase.table('citas_psicologia').select('*').eq('id', id).execute()
        if not cita.data:
            return jsonify({'success': False, 'error': 'Cita no encontrada'})
        
        c = cita.data[0]
        nuevo_pagado = (c.get('monto_pagado', 0) or 0) + monto
        nuevo_estado = 'pagada' if nuevo_pagado >= c.get('valor', 0) else 'parcial'
        
        supabase.table('citas_psicologia').update({
            'monto_pagado': nuevo_pagado,
            'estado': nuevo_estado
        }).eq('id', id).execute()
        
        return jsonify({'success': True, 'nuevo_estado': nuevo_estado, 'pagado': nuevo_pagado})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/cita/<int:id>/completar', methods=['POST'])
@login_required
@socio_admin_required
def completar_cita(id):
    try:
        supabase.table('citas_psicologia').update({
            'estado': 'realizada',
            'fecha_realizacion': date.today().isoformat()
        }).eq('id', id).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ========== MÓDULO 1: PLANIFICACIÓN ==========

@app.route('/modulo1', methods=['GET', 'POST'])
@login_required
@socio_admin_required
def modulo1():
    if request.method == 'POST':
        try:
            tipo = request.form.get('tipo_sesion', 'clase')
            num_sesiones = int(request.form.get('num_sesiones', 1))
            num_estudiantes = int(request.form.get('num_estudiantes', 1))
            primera_fecha = None
            
            # Validaciones de horas
            for sesion_num in range(1, num_sesiones + 1):
                fecha = request.form.get(f'fecha_{sesion_num}')
                h_ini = request.form.get(f'hora_inicio_{sesion_num}')
                h_fin = request.form.get(f'hora_fin_{sesion_num}')
                
                if fecha and h_ini and h_fin:
                    if h_fin <= h_ini:
                        flash(f'❌ Error en Sesión {sesion_num}: La hora de fin ({h_fin}) no puede ser menor o igual que la hora de inicio ({h_ini})', 'error')
                        return redirect(url_for('modulo1'))
                    
                    inicio = datetime.strptime(f"{fecha} {h_ini}", '%Y-%m-%d %H:%M')
                    fin = datetime.strptime(f"{fecha} {h_fin}", '%Y-%m-%d %H:%M')
                    horas_val = round((fin - inicio).total_seconds() / 3600, 2)
                    
                    if horas_val <= 0:
                        flash(f'❌ Error en Sesión {sesion_num}: La duración debe ser mayor a 0 horas', 'error')
                        return redirect(url_for('modulo1'))
                    
                    if horas_val < 0.5:
                        flash(f'⚠️ Advertencia en Sesión {sesion_num}: La duración es muy corta ({horas_val} horas). Mínimo recomendado: 0.5 horas', 'warning')
            
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
                es_terapia = tipo in ['terapia', 'ambos']
                if es_terapia:
                    tema = request.form.get('atencion_psicologica', '')
                    asignatura = request.form.get('asignatura', '') if tipo == 'ambos' else ''
                    precio = next((item['precio'] for item in ATENCION_PSICOLOGICA if item['nombre'] == tema), 40)
                    valor_inicial = precio
                else:
                    asignatura = request.form.get('asignatura', '')
                    tema = ''
                    precio = float(request.form.get('precio_hora', 10))
                    valor_inicial = 0
                estudiantes_nombres = []
                for est_num in range(1, num_estudiantes + 1):
                    eid = request.form.get(f'estudiante_id_{est_num}', '')
                    if eid and eid != 'nuevo':
                        result = supabase.table('sesiones').insert({
                            'tipo_sesion': tipo, 'asignatura': asignatura,
                            'tema_terapia': tema, 'profesor_terapeuta': profesor,
                            'fecha': fecha, 'hora_inicio': h_ini, 'hora_fin': h_fin,
                            'horas': horas, 'estado': 'Planificado',
                            'encargado_apertura': encargado, 'precio_hora': precio,
                            'valor_total': valor_inicial, 'cobro_por_sesion': es_terapia,
                            'estudiante_id': int(eid), 'usuario_id': int(current_user.id)
                        }).execute()
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
                         asignaturas=ASIGNATURAS, atencion_psicologica=ATENCION_PSICOLOGICA,
                         precios_clase=PRECIOS_CLASE, precios_matricula=PRECIOS_MATRICULA,
                         precios_pension=PRECIOS_PENSION, profesores=PROFESORES,
                         encargados=ENCARGADOS, today=date.today())

# ========== MÓDULO 5: PAGOS DOCENTES ==========

@app.route('/modulo5')
@login_required
def modulo5():
    mes = request.args.get('mes', '')
    anio = request.args.get('anio', '')
    fecha_desde = request.args.get('fecha_desde', '')
    fecha_hasta = request.args.get('fecha_hasta', '')
    filtro_profesor = request.args.get('filtro_profesor', '')
    
    query = supabase.table('sesiones').select('*, estudiantes(*)').eq('estado', 'Realizado')
    
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
    
    if filtro_profesor and filtro_profesor != '':
        sesiones_filtradas = []
        for s in sesiones_data:
            profesor = s.get('profesor_terapeuta', '')
            if filtro_profesor.lower() in profesor.lower():
                sesiones_filtradas.append(s)
        sesiones_data = sesiones_filtradas
    
    # Obtener anticipos aprobados del mes para cada docente
    anticipos_aprobados_por_docente = {}
    anticipos = supabase.table('anticipos_solicitudes').select('*').eq('estado', 'aprobado').execute()
    for a in (anticipos.data or []):
        docente = a.get('usuario_nombre', '')
        if docente not in anticipos_aprobados_por_docente:
            anticipos_aprobados_por_docente[docente] = 0
        anticipos_aprobados_por_docente[docente] += a.get('monto', 0)
    
    pagos = []
    total_docencia = 0
    total_psicologia = 0
    total_adeudado = 0
    total_anticipos = 0
    consolidado = {}
    total_sesiones_clase = 0
    total_sesiones_terapia = 0
    total_horas_clase = 0
    total_horas_terapia = 0
    profesores_lista = set()
    
    for s in sesiones_data:
        horas = s.get('horas', 0) or 0
        valor = s.get('valor_total', 0) or 0
        tipo = s.get('tipo_sesion', 'clase')
        profesor = s.get('profesor_terapeuta', 'Desconocido')
        
        profesores_lista.add(profesor)
        
        if tipo in ['clase', 'preuniversitario']:
            pago_docente = horas * PAGO_DOCENCIA_POR_HORA
            pago_psicologia = 0
            total_docencia += pago_docente
            total_horas_clase += horas
            total_sesiones_clase += 1
        else:
            pago_docente = 0
            pago_psicologia = valor * PORCENTAJE_PSICOLOGIA
            total_psicologia += pago_psicologia
            total_sesiones_terapia += 1
        
        total_pagar = pago_docente + pago_psicologia
        total_adeudado += total_pagar
        
        est = s.get('estudiantes', {})
        pagos.append({
            'fecha': s['fecha'],
            'profesor': profesor,
            'estudiante': f"{est.get('apellidos', '')} {est.get('nombres', '')}",
            'tipo': tipo,
            'horas': horas if tipo in ['clase', 'preuniversitario'] else 1,
            'valor_total': valor,
            'pago_docente': pago_docente,
            'pago_psicologia': pago_psicologia,
            'total_pagar': total_pagar,
            'anticipo_descontado': 0
        })
        
        if profesor not in consolidado:
            consolidado[profesor] = {
                'sesiones_clase': 0, 'sesiones_terapia': 0,
                'horas_clase': 0, 'horas_terapia': 0,
                'pago_docencia': 0, 'pago_psicologia': 0,
                'total_pagar': 0, 'anticipo': 0, 'neto_a_pagar': 0
            }
        
        if tipo in ['clase', 'preuniversitario']:
            consolidado[profesor]['sesiones_clase'] += 1
            consolidado[profesor]['horas_clase'] += horas
            consolidado[profesor]['pago_docencia'] += pago_docente
        else:
            consolidado[profesor]['sesiones_terapia'] += 1
            consolidado[profesor]['horas_terapia'] += 1
            consolidado[profesor]['pago_psicologia'] += pago_psicologia
        
        consolidado[profesor]['total_pagar'] += total_pagar
    
    # Aplicar anticipos al consolidado
    for prof in consolidado:
        anticipo = anticipos_aprobados_por_docente.get(prof, 0)
        consolidado[prof]['anticipo'] = anticipo
        consolidado[prof]['neto_a_pagar'] = consolidado[prof]['total_pagar'] - anticipo
        total_anticipos += anticipo
    
    total_neto = total_adeudado - total_anticipos
    
    return render_template('modulo5.html', 
                         pagos=pagos, total_docencia=total_docencia,
                         total_psicologia=total_psicologia, total_adeudado=total_adeudado,
                         total_anticipos=total_anticipos, total_neto=total_neto,
                         consolidado=consolidado, total_sesiones_clase=total_sesiones_clase,
                         total_sesiones_terapia=total_sesiones_terapia,
                         total_horas_clase=total_horas_clase,
                         total_horas_terapia=total_sesiones_terapia,
                         mes=mes, anio=anio, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
                         filtro_profesor=filtro_profesor,
                         profesores_lista=sorted(list(profesores_lista)))

# ========== EDITOR DE PLANIFICACIONES ==========

@app.route('/editar-planificaciones')
@login_required
@socio_admin_required
def editar_planificaciones():
    estudiantes = supabase.table('estudiantes').select('*').eq('activo', True).order('apellidos').execute()
    return render_template('editar_planificaciones.html', 
                         estudiantes=estudiantes.data or [],
                         asignaturas=ASIGNATURAS,
                         atencion_psicologica=ATENCION_PSICOLOGICA,
                         profesores=PROFESORES,
                         encargados=ENCARGADOS,
                         today=date.today().isoformat())

@app.route('/api/sesiones/todas')
@login_required
@socio_admin_required
def api_sesiones_todas():
    sesiones = supabase.table('sesiones').select('*, estudiantes(apellidos, nombres)').order('fecha', desc=True).execute()
    
    resultado = []
    for s in (sesiones.data or []):
        est = s.get('estudiantes', {})
        hora_inicio = s.get('hora_inicio', '')
        if hora_inicio and len(hora_inicio) > 5:
            hora_inicio = hora_inicio[:5]
        hora_fin = s.get('hora_fin', '')
        if hora_fin and len(hora_fin) > 5:
            hora_fin = hora_fin[:5]
        
        resultado.append({
            'id': s['id'],
            'fecha': s.get('fecha', ''),
            'hora_inicio': hora_inicio,
            'hora_fin': hora_fin,
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
@socio_admin_required
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
        
        if horas <= 0:
            return jsonify({'success': False, 'error': 'La duración de la sesión debe ser mayor a 0 horas'})
        if horas < 0.5:
            return jsonify({'success': False, 'error': 'La duración mínima de la sesión es 30 minutos (0.5 horas)'})
        
        valor_total = data.get('valor_total', 0)
        if valor_total < 0:
            return jsonify({'success': False, 'error': 'El valor total no puede ser negativo'})
        
        precio_hora = data.get('precio_hora', 10)
        if precio_hora < 0:
            return jsonify({'success': False, 'error': 'El precio por hora no puede ser negativo'})
        
        es_terapia = data['tipo_sesion'] in ['terapia', 'ambos']
        if es_terapia:
            pago_docente = 0
            pago_psicologia = valor_total * PORCENTAJE_PSICOLOGIA
        else:
            pago_docente = horas * PAGO_DOCENCIA_POR_HORA
            pago_psicologia = 0
        
        sesion_anterior = supabase.table('sesiones').select('*').eq('id', id).execute()
        datos_anteriores = sesion_anterior.data[0] if sesion_anterior.data else {}
        
        supabase.table('correcciones_pagos').insert({
            'pago_id': id,
            'monto_anterior': datos_anteriores.get('valor_total', 0),
            'monto_nuevo': valor_total,
            'cambiado_por': responsable,
            'motivo': f'EDICION SESION #{id} - Cambios: horas={horas}, precio={precio_hora}, valor_total={valor_total}'
        }).execute()
        
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
        
        if data.get('estado') == 'Realizado' and crear_o_actualizar_evento_calendar:
            sesion = supabase.table('sesiones').select('*, estudiantes(apellidos, nombres)').eq('id', id).execute()
            if sesion.data:
                s = sesion.data[0]
                est = s.get('estudiantes', {})
                nombre_est = f"{est.get('apellidos', '')} {est.get('nombres', '')}".strip() or 'Sin nombre'
                evento_id = crear_o_actualizar_evento_calendar({
                    'asignatura': s.get('asignatura') or s.get('tema_terapia') or 'Sesión',
                    'profesor': s.get('profesor_terapeuta', ''),
                    'estudiantes': nombre_est,
                    'fecha': s['fecha'],
                    'hora_inicio': s['hora_inicio'][:5],
                    'hora_fin': s['hora_fin'][:5],
                    'encargado_apertura': s.get('encargado_apertura', ''),
                    'valor_total': valor_total
                }, s.get('evento_calendar_id'))
                if evento_id:
                    supabase.table('sesiones').update({'evento_calendar_id': evento_id}).eq('id', id).execute()
        
        return jsonify({'success': True, 'mensaje': f'✅ Sesión actualizada - Responsable: {responsable}'})
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
                             estudiantes=estudiantes_lista, profesores=PROFESORES)
    nombre_usuario = current_user.nombre.strip().lower()
    palabras_usuario = nombre_usuario.split()
    todas = supabase.table('sesiones').select('*, estudiantes(*)').eq('fecha', fecha).order('hora_inicio').execute()
    sesiones_filtradas = []
    for s in (todas.data or []):
        profesor = (s.get('profesor_terapeuta') or '').strip().lower()
        est = s.get('estudiantes', {})
        nombre_est = f"{est.get('apellidos', '')} {est.get('nombres', '')}".strip().lower()
        apellidos_est = (est.get('apellidos', '') or '').strip().lower()
        nombres_est = (est.get('nombres', '') or '').strip().lower()
        if current_user.rol in ['profesor', 'psicologo']:
            if nombre_usuario in profesor or profesor in nombre_usuario:
                sesiones_filtradas.append(s)
            else:
                for palabra in palabras_usuario:
                    if len(palabra) >= 3 and palabra in profesor:
                        sesiones_filtradas.append(s)
                        break
        elif current_user.rol in ['estudiante', 'padre']:
            if nombre_usuario in nombre_est or nombre_est in nombre_usuario:
                sesiones_filtradas.append(s)
            else:
                for palabra in palabras_usuario:
                    if len(palabra) >= 3:
                        if palabra in apellidos_est or palabra in nombres_est:
                            sesiones_filtradas.append(s)
                            break
    return render_template('modulo2.html', sesiones=sesiones_filtradas, fecha=fecha,
                         estudiantes=estudiantes_lista, profesores=PROFESORES)

@app.route('/api/sesion/<int:id>/sincronizar', methods=['POST'])
@login_required
@socio_admin_required
def sincronizar_calendario(id):
    try:
        sesion = supabase.table('sesiones').select('*, estudiantes(apellidos, nombres)').eq('id', id).execute()
        if not sesion.data:
            return jsonify({'success': False, 'error': 'Sesión no encontrada'})
        
        s = sesion.data[0]
        
        if not s.get('fecha') or not s.get('hora_inicio') or not s.get('hora_fin'):
            return jsonify({'success': False, 'error': 'Faltan datos de fecha/hora en esta sesión'})
        
        est = s.get('estudiantes')
        if est and isinstance(est, dict):
            nombre_est = f"{est.get('apellidos', '')} {est.get('nombres', '')}".strip()
        else:
            nombre_est = f"Estudiante {s.get('estudiante_id', '')}"
        
        if not nombre_est.strip():
            nombre_est = 'Sin nombre'
        
        encargado = s.get('encargado_apertura', '').strip()
        if not encargado:
            encargado = 'Por definir'
        
        hora_inicio = s.get('hora_inicio', '')
        if hora_inicio and len(hora_inicio) > 5:
            hora_inicio = hora_inicio[:5]
        hora_fin = s.get('hora_fin', '')
        if hora_fin and len(hora_fin) > 5:
            hora_fin = hora_fin[:5]
        
        evento_id_existente = s.get('evento_calendar_id')
        valor_total = s.get('valor_total', 0)
        
        evento_id = crear_o_actualizar_evento_calendar({
            'asignatura': (s.get('asignatura') or s.get('tema_terapia') or 'Sesión')[:50],
            'profesor': (s.get('profesor_terapeuta', 'Profesor'))[:50],
            'estudiantes': nombre_est[:100],
            'fecha': str(s['fecha']),
            'hora_inicio': hora_inicio,
            'hora_fin': hora_fin,
            'encargado_apertura': encargado,
            'valor_total': valor_total
        }, evento_id_existente)
        
        if evento_id:
            supabase.table('sesiones').update({'evento_calendar_id': evento_id}).eq('id', id).execute()
            return jsonify({'success': True, 'mensaje': f'✅ Sincronizado - Encargado: {encargado}, Valor: ${valor_total}'})
        else:
            return jsonify({'success': False, 'error': 'No se pudo crear/actualizar el evento'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/sesion/<int:id>/eliminar', methods=['GET', 'POST', 'DELETE'])
@login_required
@socio_admin_required
def eliminar_sesion(id):
    try:
        sesion = supabase.table('sesiones').select('evento_calendar_id').eq('id', id).execute()
        evento_id = sesion.data[0].get('evento_calendar_id') if sesion.data else None
        if evento_id and eliminar_evento_calendar:
            eliminar_evento_calendar(evento_id)
        supabase.table('sesiones').delete().eq('id', id).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/sesion/<int:id>/toggle', methods=['POST'])
@login_required
def toggle_sesion(id):
    data = request.get_json()
    estado = data.get('estado', 'Realizado')
    updates = {'estado': estado}
    
    if estado == 'Realizado':
        s = supabase.table('sesiones').select('*').eq('id', id).execute()
        if s.data:
            sd = s.data[0]
            if sd.get('valor_total', 0) == 0 or sd.get('valor_total') is None:
                if sd.get('cobro_por_sesion') or sd.get('tipo_sesion') in ['terapia', 'ambos']:
                    updates['valor_total'] = sd.get('precio_hora', 40) or 40
                else:
                    updates['valor_total'] = round((sd.get('horas', 1) or 1) * (sd.get('precio_hora', 10) or 10), 2)
    elif estado == 'Cancelado':
        updates['valor_total'] = 0
        s = supabase.table('sesiones').select('evento_calendar_id').eq('id', id).execute()
        if s.data and s.data[0].get('evento_calendar_id'):
            if eliminar_evento_calendar:
                try:
                    eliminar_evento_calendar(s.data[0]['evento_calendar_id'])
                    updates['evento_calendar_id'] = None
                except:
                    pass
    
    supabase.table('sesiones').update(updates).eq('id', id).execute()
    return jsonify({'success': True})

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
            pago_anterior = supabase.table('pagos').select('monto').eq('id', pago_id).execute()
            monto_anterior = pago_anterior.data[0]['monto'] if pago_anterior.data else 0
            supabase.table('pagos').update({'monto': nuevo_monto}).eq('id', pago_id).execute()
            supabase.table('correcciones_pagos').insert({
                'pago_id': pago_id, 'monto_anterior': monto_anterior,
                'monto_nuevo': nuevo_monto, 'cambiado_por': cambiado_por, 'motivo': motivo
            }).execute()
            flash('✅ Pago corregido', 'success')
        elif accion == 'eliminar_pago':
            pago_id = int(request.form['pago_id'])
            motivo = request.form['motivo_eliminar']
            eliminado_por = request.form.get('eliminado_por', current_user.nombre)
            supabase.table('correcciones_pagos').insert({
                'pago_id': pago_id, 'monto_anterior': 0, 'monto_nuevo': 0,
                'cambiado_por': eliminado_por, 'motivo': f'ELIMINADO: {motivo}'
            }).execute()
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
            
            inicio = datetime.strptime(f"{nueva_fecha} {nueva_h_ini}", '%Y-%m-%d %H:%M')
            fin = datetime.strptime(f"{nueva_fecha} {nueva_h_fin}", '%Y-%m-%d %H:%M')
            nuevas_horas = round((fin - inicio).total_seconds() / 3600, 2)
            
            if nuevas_horas <= 0:
                flash('❌ Error: La duración debe ser mayor a 0 horas', 'error')
                return redirect(url_for('modulo3'))
            
            if nuevas_horas < 0.5:
                flash('⚠️ Advertencia: La duración es muy corta (mínimo 30 minutos)', 'warning')
            
            sesion_actual = supabase.table('sesiones').select('*').eq('id', sesion_id).execute()
            if sesion_actual.data:
                s = sesion_actual.data[0]
                precio_hora = s.get('precio_hora', 10) or 10
                cobro_por_sesion = s.get('cobro_por_sesion', False)
                if cobro_por_sesion or s.get('tipo_sesion') in ['terapia', 'ambos']:
                    nuevo_valor = precio_hora
                else:
                    nuevo_valor = round(nuevas_horas * precio_hora, 2)
                supabase.table('sesiones').update({
                    'fecha': nueva_fecha, 'hora_inicio': nueva_h_ini, 'hora_fin': nueva_h_fin,
                    'horas': nuevas_horas, 'valor_total': nuevo_valor
                }).eq('id', sesion_id).execute()
                flash('✅ Sesión actualizada', 'success')
        return redirect(url_for('modulo3'))
    estudiantes = supabase.table('estudiantes').select('*').eq('activo', True).order('apellidos').execute()
    datos = []
    for e in (estudiantes.data or []):
        ses = supabase.table('sesiones').select('*').eq('estudiante_id', e['id']).eq('estado', 'Realizado').execute()
        pag = supabase.table('pagos').select('*').eq('estudiante_id', e['id']).order('fecha_pago', desc=True).execute()
        cobrar = sum(s.get('valor_total', 0) or 0 for s in (ses.data or []))
        pagado = sum(p.get('monto', 0) or 0 for p in (pag.data or []))
        if cobrar > 0 or pagado > 0:
            datos.append({'id': e['id'], 'nombre': f"{e['apellidos']} {e['nombres']}", 'cobrar': cobrar, 'pagado': pagado, 'saldo': cobrar - pagado, 'pagos': pag.data or [], 'sesiones': ses.data or []})
    return render_template('modulo3.html', estudiantes=datos, today=date.today())

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
                         estudiantes=estudiantes_lista, profesores=PROFESORES)

# ========== MÓDULO 6: REUNIONES ==========

@app.route('/modulo6', methods=['GET', 'POST'])
@login_required
@socio_admin_required
def modulo6():
    if request.method == 'POST':
        try:
            edit_id = request.form.get('edit_id', '')
            datos = {
                'titulo': request.form.get('titulo_otro') or request.form['titulo'], 'fecha': request.form['fecha'],
                'hora_inicio': request.form['hora_inicio'], 'hora_fin': request.form['hora_fin'],
                'asistentes': request.form.get('asistentes', ''), 'tema': request.form.get('tema', ''),
                'encargado': request.form.get('encargado_otro') or request.form.get('encargado', current_user.nombre), 'usuario_id': int(current_user.id)
            }
            if edit_id:
                supabase.table('reuniones').update(datos).eq('id', int(edit_id)).execute()
                flash('✅ Reunión actualizada', 'success')
            else:
                result = supabase.table('reuniones').insert(datos).execute()
                flash('✅ Reunión programada', 'success')
                if crear_evento_calendar and result.data:
                    try:
                        evento_id = crear_evento_calendar({
                            'asignatura': f"{request.form['titulo']} - {request.form.get('tema', '')}",
                            'profesor': request.form.get('encargado', current_user.nombre),
                            'estudiantes': request.form.get('asistentes', ''),
                            'fecha': request.form['fecha'], 'hora_inicio': request.form['hora_inicio'],
                            'hora_fin': request.form['hora_fin'], 'encargado_apertura': request.form.get('encargado', '')
                        })
                        if evento_id and result.data:
                            supabase.table('reuniones').update({'evento_calendar_id': evento_id}).eq('id', result.data[0]['id']).execute()
                    except Exception as e:
                        print(f'⚠️ Google Calendar (reunión): {e}')
        except Exception as e:
            flash(f'❌ Error: {e}', 'error')
        return redirect(url_for('modulo6'))
    reuniones = supabase.table('reuniones').select('*').gte('fecha', str(date.today())).order('fecha').execute()
    return render_template('modulo6.html', reuniones=reuniones.data or [], today=date.today())

@app.route('/api/reunion/<int:id>/eliminar', methods=['POST'])
@login_required
@socio_admin_required
def eliminar_reunion(id):
    try:
        supabase.table('reuniones').delete().eq('id', id).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

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
            return jsonify({'success': False, 'error': 'Faltan datos'})
        
        if crear_evento_calendar:
            evento_id = crear_evento_calendar({
                'asignatura': f"{r.get('titulo', 'Reunión')} - {r.get('tema', '')}",
                'profesor': r.get('encargado', ''),
                'estudiantes': r.get('asistentes', ''),
                'fecha': str(r['fecha']),
                'hora_inicio': str(r['hora_inicio'])[:5],
                'hora_fin': str(r['hora_fin'])[:5],
                'encargado_apertura': r.get('encargado', '')[:10]
            })
            if evento_id:
                supabase.table('reuniones').update({'evento_calendar_id': evento_id}).eq('id', id).execute()
                return jsonify({'success': True})
        
        return jsonify({'success': False, 'error': 'No se pudo crear'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ========== REPORTES ==========

@app.route('/reportes')
@login_required
@socio_admin_required
def reportes():
    mes = int(request.args.get('mes', date.today().month))
    anio = int(request.args.get('anio', date.today().year))
    estudiantes = supabase.table('estudiantes').select('*').eq('activo', True).order('apellidos').execute()
    
    datos_estudiantes = []
    total_horas_estudiantes = 0
    total_cobrar_estudiantes = 0
    total_pagado_estudiantes = 0
    asignaturas_detalle = {}
    horas_por_materia = {}
    cumplimiento = {'planificado': 0, 'realizado': 0, 'cancelado': 0}
    ingresos_por_tipo = {}
    pagos_por_docente = {}
    total_docencia = 0
    total_psicologia = 0
    total_sesiones_clase = 0
    total_sesiones_terapia = 0
    total_horas_clase = 0
    total_horas_terapia = 0
    gastos_por_categoria = {}
    total_gastos = 0
    
    for e in (estudiantes.data or []):
        ses = supabase.table('sesiones').select('*').eq('estudiante_id', e['id']).execute()
        ses_todas = [s for s in (ses.data or []) if s['fecha'][:7] == f"{anio}-{mes:02d}"]
        ses_realizadas = [s for s in ses_todas if s['estado'] == 'Realizado']
        ses_planificadas = [s for s in ses_todas if s['estado'] == 'Planificado']
        ses_canceladas = [s for s in ses_todas if s['estado'] == 'Cancelado']
        
        pag = supabase.table('pagos').select('*').eq('estudiante_id', e['id']).execute()
        pag_filtrados = [p for p in (pag.data or []) if p['fecha_pago'][:7] == f"{anio}-{mes:02d}"]
        
        horas_plan = sum(s.get('horas', 0) or 0 for s in ses_todas)
        horas_real = sum(s.get('horas', 0) or 0 for s in ses_realizadas)
        horas_canc = sum(s.get('horas', 0) or 0 for s in ses_canceladas)
        cobrar = sum(s.get('valor_total', 0) or 0 for s in ses_realizadas)
        pagado = sum(p.get('monto', 0) or 0 for p in pag_filtrados)
        
        total_horas_estudiantes += horas_real
        total_cobrar_estudiantes += cobrar
        total_pagado_estudiantes += pagado
        
        for s in ses_todas:
            asig = s.get('asignatura') or s.get('tema_terapia') or 'Sin registro'
            horas_por_materia[asig] = horas_por_materia.get(asig, 0) + (s.get('horas', 0) or 0)
            
            if asig not in asignaturas_detalle:
                asignaturas_detalle[asig] = {'plan': 0, 'real': 0, 'canc': 0}
            
            if s['estado'] == 'Planificado':
                asignaturas_detalle[asig]['plan'] += s.get('horas', 0) or 0
            elif s['estado'] == 'Realizado':
                asignaturas_detalle[asig]['real'] += s.get('horas', 0) or 0
            elif s['estado'] == 'Cancelado':
                asignaturas_detalle[asig]['canc'] += s.get('horas', 0) or 0
            
            cumplimiento[s.get('estado', 'Planificado').lower()] = cumplimiento.get(s.get('estado', 'Planificado').lower(), 0) + 1
            
            if s['estado'] == 'Realizado':
                tipo = s.get('tipo_sesion', 'clase')
                valor = s.get('valor_total', 0) or 0
                ingresos_por_tipo[tipo] = ingresos_por_tipo.get(tipo, 0) + valor
                
                prof = s.get('profesor_terapeuta', 'Desconocido')
                horas = s.get('horas', 0) or 0
                
                if tipo in ['clase', 'preuniversitario']:
                    pago_docente = horas * PAGO_DOCENCIA_POR_HORA
                    pago_psicologia = 0
                    total_sesiones_clase += 1
                    total_horas_clase += horas
                    total_docencia += pago_docente
                else:
                    pago_docente = 0
                    pago_psicologia = valor * PORCENTAJE_PSICOLOGIA
                    total_sesiones_terapia += 1
                    total_psicologia += pago_psicologia
                
                total_pagar = pago_docente + pago_psicologia
                
                if prof not in pagos_por_docente:
                    pagos_por_docente[prof] = {
                        'sesiones_clase': 0, 'sesiones_terapia': 0,
                        'horas_clase': 0, 'horas_terapia': 0,
                        'pago_docencia': 0, 'pago_psicologia': 0, 'total_pagar': 0
                    }
                
                if tipo in ['clase', 'preuniversitario']:
                    pagos_por_docente[prof]['sesiones_clase'] += 1
                    pagos_por_docente[prof]['horas_clase'] += horas
                    pagos_por_docente[prof]['pago_docencia'] += pago_docente
                else:
                    pagos_por_docente[prof]['sesiones_terapia'] += 1
                    pagos_por_docente[prof]['horas_terapia'] += 1
                    pagos_por_docente[prof]['pago_psicologia'] += pago_psicologia
                
                pagos_por_docente[prof]['total_pagar'] += total_pagar
        
        if cobrar > 0 or pagado > 0 or horas_real > 0:
            datos_estudiantes.append({
                'id': e['id'], 'estudiante': f"{e['apellidos']} {e['nombres']}",
                'horas_plan': horas_plan, 'horas_real': horas_real, 'horas_canc': horas_canc,
                'cobrar': cobrar, 'pagado': pagado, 'saldo': cobrar - pagado
            })
    
    gastos_mes = supabase.table('gastos').select('*').eq('mes', mes).eq('anio', anio).execute()
    total_gastos = sum(g.get('monto', 0) or 0 for g in (gastos_mes.data or []))
    for g in (gastos_mes.data or []):
        cat = g.get('categoria', 'Sin categoría')
        gastos_por_categoria[cat] = gastos_por_categoria.get(cat, 0) + (g.get('monto', 0) or 0)
    
    total_pago_docentes = sum(d['total_pagar'] for d in pagos_por_docente.values())
    total_por_pagar_estudiantes = total_cobrar_estudiantes - total_pagado_estudiantes
    balance = total_pagado_estudiantes - total_gastos - total_pago_docentes
    
    porcentaje_cumplimiento = round((cumplimiento.get('realizado', 0) / max(cumplimiento.get('planificado', 1), 1)) * 100, 2)
    porcentaje_cobrado = round((total_pagado_estudiantes / max(total_cobrar_estudiantes, 1)) * 100, 2)
    porcentaje_gastos_docentes = round((total_pago_docentes / max(total_cobrar_estudiantes, 1)) * 100, 2)
    
    correcciones = supabase.table('correcciones_pagos').select('*').order('fecha_correccion', desc=True).limit(30).execute()
    observaciones = supabase.table('sesiones').select('*, estudiantes(apellidos, nombres)').not_.is_('observaciones', 'null').order('fecha', desc=True).limit(30).execute()
    nuevos_usuarios = supabase.table('usuarios').select('*').gte('fecha_registro', f"{anio}-{mes:02d}-01").lte('fecha_registro', f"{anio}-{mes:02d}-31").execute()
    
    return render_template('reportes.html',
                         datos_estudiantes=datos_estudiantes, total_estudiantes=len(datos_estudiantes),
                         total_horas_estudiantes=total_horas_estudiantes,
                         total_cobrar_estudiantes=total_cobrar_estudiantes,
                         total_pagado_estudiantes=total_pagado_estudiantes,
                         total_por_pagar_estudiantes=total_por_pagar_estudiantes,
                         porcentaje_cobrado=porcentaje_cobrado,
                         asignaturas_detalle=asignaturas_detalle, horas_por_materia=horas_por_materia,
                         cumplimiento=cumplimiento, porcentaje_cumplimiento=porcentaje_cumplimiento,
                         ingresos_por_tipo=ingresos_por_tipo,
                         pagos_por_docente=pagos_por_docente, total_pago_docentes=total_pago_docentes,
                         total_docencia=total_docencia, total_psicologia=total_psicologia,
                         total_sesiones_clase=total_sesiones_clase,
                         total_sesiones_terapia=total_sesiones_terapia,
                         total_horas_clase=total_horas_clase,
                         total_horas_terapia=total_sesiones_terapia,
                         gastos=gastos_mes.data or [], total_gastos=total_gastos,
                         gastos_por_categoria=gastos_por_categoria,
                         porcentaje_gastos_docentes_vs_ingresos=porcentaje_gastos_docentes,
                         balance=balance, mes=mes, anio=anio,
                         correcciones=correcciones.data or [],
                         observaciones=observaciones.data or [],
                         nuevos_usuarios=nuevos_usuarios.data or [])

# ========== GASTOS ==========

@app.route('/gastos', methods=['GET', 'POST'])
@login_required
@socio_admin_required
def gestion_gastos():
    if request.method == 'POST':
        fecha = request.form['fecha']
        fecha_obj = datetime.strptime(fecha, '%Y-%m-%d')
        reembolso = request.form.get('reembolso') == 'true'
        
        supabase.table('gastos').insert({
            'concepto': request.form['concepto'],
            'monto': float(request.form['monto']),
            'fecha': fecha,
            'categoria': request.form.get('categoria', ''),
            'persona': request.form.get('persona', ''),
            'reembolso': reembolso,
            'reembolsado_a': request.form.get('reembolsado_a', '') if reembolso else '',
            'registrado_por': current_user.nombre,
            'mes': fecha_obj.month,
            'anio': fecha_obj.year
        }).execute()
        flash('✅ Gasto registrado', 'success')
        return redirect(url_for('gestion_gastos'))
    
    mes = int(request.args.get('mes', date.today().month))
    anio = int(request.args.get('anio', date.today().year))
    gastos = supabase.table('gastos').select('*').eq('mes', mes).eq('anio', anio).order('fecha', desc=True).execute()
    total = sum(g.get('monto', 0) or 0 for g in (gastos.data or []))
    
    return render_template('gastos.html', gastos=gastos.data or [], total=total, mes=mes, anio=anio, today=date.today())

@app.route('/api/gasto/<int:id>/eliminar', methods=['POST'])
@login_required
@socio_admin_required
def eliminar_gasto(id):
    supabase.table('gastos').delete().eq('id', id).execute()
    return jsonify({'success': True})

# ========== ESTUDIANTES ==========

@app.route('/estudiantes', methods=['GET', 'POST'])
@login_required
def gestion_estudiantes():
    if request.method == 'POST' and current_user.rol in ['admin', 'socio']:
        supabase.table('estudiantes').update({
            'nombres': request.form['nombres'], 'apellidos': request.form['apellidos'],
            'nivel_curso': request.form.get('nivel_curso', ''), 'procedencia': request.form.get('procedencia', ''),
            'padre_nombre': request.form.get('padre_nombre', '')
        }).eq('id', int(request.form['estudiante_id'])).execute()
        flash('✅ Actualizado', 'success')
        return redirect(url_for('gestion_estudiantes'))
    estudiantes = supabase.table('estudiantes').select('*').eq('activo', True).order('apellidos').execute()
    return render_template('estudiantes.html', estudiantes=estudiantes.data or [], rol=current_user.rol)

@app.route('/api/crear_estudiante', methods=['POST'])
@login_required
def api_crear_estudiante():
    data = request.get_json()
    result = supabase.table('estudiantes').insert({
        'nombres': data['nombres'], 'apellidos': data['apellidos'],
        'nivel_curso': data.get('nivel_curso', ''), 'procedencia': data.get('procedencia', ''),
        'padre_nombre': data.get('padre_nombre', ''), 'activo': True, 'usuario_id': int(current_user.id)
    }).execute()
    if result.data:
        e = result.data[0]
        return jsonify({'success': True, 'id': e['id'], 'nombre': f"{e['apellidos']} {e['nombres']}"})
    return jsonify({'success': False}), 400

@app.route('/api/crear_estudiante_form', methods=['POST'])
@login_required
def crear_estudiante_form():
    if current_user.rol not in ['admin', 'socio']:
        flash('❌ Sin permiso', 'error')
        return redirect(url_for('dashboard'))
    try:
        supabase.table('estudiantes').insert({
            'nombres': request.form['nombres'], 'apellidos': request.form['apellidos'],
            'nivel_curso': request.form.get('nivel_curso', ''), 'procedencia': request.form.get('procedencia', ''),
            'padre_nombre': request.form.get('padre_nombre', ''), 'activo': True, 'usuario_id': int(current_user.id)
        }).execute()
        flash('✅ Estudiante creado exitosamente', 'success')
    except Exception as e:
        flash(f'❌ Error: {str(e)}', 'error')
    return redirect(url_for('gestion_estudiantes'))

@app.route('/api/estudiante/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar_estudiante(id):
    if current_user.rol not in ['admin', 'socio']:
        return jsonify({'success': False, 'error': 'Sin permiso'})
    try:
        sesiones = supabase.table('sesiones').select('id').eq('estudiante_id', id).execute()
        if sesiones.data and len(sesiones.data) > 0:
            return jsonify({'success': False, 'error': 'No se puede eliminar: tiene sesiones.'})
        pagos = supabase.table('pagos').select('id').eq('estudiante_id', id).execute()
        if pagos.data and len(pagos.data) > 0:
            return jsonify({'success': False, 'error': 'No se puede eliminar: tiene pagos.'})
        supabase.table('estudiantes').update({'activo': False}).eq('id', id).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

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
            password = request.form.get('password', '')
            if password:
                updates['password_hash'] = password
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
    total_cobrar = total_pagado = total_horas = 0
    nombre_usuario = current_user.nombre.strip().lower()
    palabras_usuario = nombre_usuario.split()
    sesiones = supabase.table('sesiones').select('*, estudiantes(*)').eq('estado', 'Realizado').order('fecha', desc=True).execute()
    for s in (sesiones.data or []):
        if mes != 0 and s['fecha'][:7] != f"{anio}-{mes:02d}":
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
            datos.append({'fecha': s['fecha'], 'estudiante': nombre_est, 'tipo': s['tipo_sesion'],
                         'asignatura': s.get('asignatura') or s.get('tema_terapia') or '-',
                         'horas': s.get('horas', 0) or 0, 'valor': s.get('valor_total', 0) or 0, 'estado': s['estado']})
            total_horas += s.get('horas', 0) or 0
            total_cobrar += s.get('valor_total', 0) or 0
    return render_template('mi_reporte.html', datos=datos, total_cobrar=total_cobrar,
                         total_pagado=total_pagado, total_horas=total_horas, mes=mes, anio=anio,
                         saldo=total_cobrar - total_pagado)

# ========== EDITAR PERFIL ==========

@app.route('/editar-perfil', methods=['GET', 'POST'])
@login_required
def editar_perfil():
    if request.method == 'POST':
        nuevo_nombre = request.form['nombre']
        nuevo_email = request.form['email']
        nueva_password = request.form.get('password', '')
        updates = {'nombre': nuevo_nombre, 'email': nuevo_email}
        if nueva_password:
            updates['password_hash'] = nueva_password
        supabase.table('usuarios').update(updates).eq('id', current_user.id).execute()
        if current_user.rol in ['profesor', 'psicologo']:
            supabase.table('sesiones').update({'profesor_terapeuta': nuevo_nombre}).eq('profesor_terapeuta', current_user.nombre).execute()
        flash('✅ Perfil actualizado correctamente.', 'success')
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
    try:
        data = request.get_json()
        supabase.table('sesiones').update({'observaciones': data.get('observaciones', '')}).eq('id', id).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ========== INICIALIZACIÓN ==========

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)