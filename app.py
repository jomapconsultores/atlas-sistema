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

# ========== CONSTANTES DE PAGOS ==========
PAGO_DOCENCIA_POR_HORA = 7
PORCENTAJE_PSICOLOGIA = 0.4018  # 40.18%
COMISION_CLIENTE_EXTERNO = 0.25

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
    if request.method == 'POST':
        try:
            tipo = request.form.get('tipo_sesion', 'clase')
            num_sesiones = int(request.form.get('num_sesiones', 1))
            num_estudiantes = int(request.form.get('num_estudiantes', 1))
            primera_fecha = None
            atencion = request.form.get('atencion_psicologica', '')
            es_paquete = (atencion == 'Paquete 4 terapias')
            if es_paquete:
                num_sesiones = 4
            
            for sesion_num in range(1, num_sesiones + 1):
                fecha = request.form.get(f'fecha_{sesion_num}')
                h_ini = request.form.get(f'hora_inicio_{sesion_num}')
                h_fin = request.form.get(f'hora_fin_{sesion_num}')
                if fecha and h_ini and h_fin and h_fin <= h_ini:
                    flash(f'❌ Error en Sesión {sesion_num}: La hora de fin debe ser mayor a la hora de inicio', 'error')
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
                es_terapia = tipo in ['terapia', 'ambos']
                
                if es_terapia:
                    tema = request.form.get('atencion_psicologica', '')
                    asignatura = request.form.get('asignatura', '') if tipo == 'ambos' else ''
                    if tema == 'Paquete 4 terapias':
                        precio = 160 / 4
                    else:
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
                        supabase.table('sesiones').insert({
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

@app.route('/editar-planificacion-masiva')
@login_required
@socio_admin_required
def editar_planificacion_masiva():
    estudiantes = supabase.table('estudiantes').select('*').eq('activo', True).order('apellidos').execute()
    return render_template('editar_planificacion_masiva.html',
                         estudiantes=estudiantes.data or [],
                         asignaturas=ASIGNATURAS,
                         atencion_psicologica=ATENCION_PSICOLOGICA,
                         profesores=PROFESORES,
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
        
        if horas <= 0:
            return jsonify({'success': False, 'error': 'La duración de la sesión debe ser mayor a 0 horas'})
        
        valor_total = data.get('valor_total', 0)
        precio_hora = data.get('precio_hora', 10)
        es_terapia = data['tipo_sesion'] in ['terapia', 'ambos']
        
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
        
        # Auditoría
        supabase.table('correcciones_pagos').insert({
            'pago_id': id,
            'monto_anterior': 0,
            'monto_nuevo': valor_total,
            'cambiado_por': responsable,
            'motivo': f'EDICION SESION #{id}'
        }).execute()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/sesion/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar_sesion(id):
    try:
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
            if sd.get('cobro_por_sesion') or sd.get('tipo_sesion') in ['terapia', 'ambos']:
                updates['valor_total'] = sd.get('precio_hora', 40) or 40
            else:
                updates['valor_total'] = round((sd.get('horas', 1) or 1) * (sd.get('precio_hora', 10) or 10), 2)
    elif estado == 'Cancelado':
        updates['valor_total'] = 0
    
    supabase.table('sesiones').update(updates).eq('id', id).execute()
    return jsonify({'success': True})

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
    todas = supabase.table('sesiones').select('*, estudiantes(*)').eq('fecha', fecha).order('hora_inicio').execute()
    sesiones_filtradas = []
    for s in (todas.data or []):
        profesor = (s.get('profesor_terapeuta') or '').strip().lower()
        if nombre_usuario in profesor or profesor in nombre_usuario:
            sesiones_filtradas.append(s)
    return render_template('modulo2.html', sesiones=sesiones_filtradas, fecha=fecha,
                         estudiantes=estudiantes_lista, profesores=PROFESORES)

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

# ========== MÓDULO 5: PAGOS DOCENTES ==========
@app.route('/modulo5')
@login_required
def modulo5():
    mes = request.args.get('mes', '')
    anio = request.args.get('anio', '')
    filtro_profesor = request.args.get('filtro_profesor', '')
    
    query = supabase.table('sesiones').select('*, estudiantes(*)').eq('estado', 'Realizado')
    
    if current_user.rol in ['profesor', 'psicologo']:
        query = query.eq('profesor_terapeuta', current_user.nombre)
    
    if mes and mes != '':
        mes_int = int(mes)
        anio_int = int(anio) if anio else date.today().year
        fecha_inicio = f"{anio_int}-{mes_int:02d}-01"
        ultimo_dia = monthrange(anio_int, mes_int)[1]
        fecha_fin = f"{anio_int}-{mes_int:02d}-{ultimo_dia}"
        query = query.gte('fecha', fecha_inicio).lte('fecha', fecha_fin)
    
    sesiones = query.order('fecha', desc=True).execute()
    sesiones_data = sesiones.data or []
    
    if filtro_profesor and filtro_profesor != '' and current_user.rol in ['admin', 'socio']:
        sesiones_filtradas = []
        for s in sesiones_data:
            if filtro_profesor.lower() in s.get('profesor_terapeuta', '').lower():
                sesiones_filtradas.append(s)
        sesiones_data = sesiones_filtradas
    
    pagos = []
    total_docencia = 0
    total_psicologia = 0
    total_adeudado = 0
    consolidado = {}
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
        else:
            pago_docente = 0
            pago_psicologia = valor * PORCENTAJE_PSICOLOGIA
            total_psicologia += pago_psicologia
        
        total_pagar = pago_docente + pago_psicologia
        total_adeudado += total_pagar
        
        est = s.get('estudiantes', {})
        pagos.append({
            'fecha': s['fecha'],
            'profesor': profesor,
            'estudiante': f"{est.get('apellidos', '')} {est.get('nombres', '')}".title(),
            'tipo': tipo,
            'horas': horas,
            'valor_total': valor,
            'pago_docente': pago_docente,
            'pago_psicologia': pago_psicologia,
            'total_pagar': total_pagar
        })
        
        if profesor not in consolidado:
            consolidado[profesor] = {
                'pago_docencia': 0, 'pago_psicologia': 0, 'total_pagar': 0
            }
        consolidado[profesor]['pago_docencia'] += pago_docente
        consolidado[profesor]['pago_psicologia'] += pago_psicologia
        consolidado[profesor]['total_pagar'] += total_pagar
    
    return render_template('modulo5.html',
                         pagos=pagos,
                         total_docencia=total_docencia,
                         total_psicologia=total_psicologia,
                         total_adeudado=total_adeudado,
                         consolidado=consolidado,
                         profesores_lista=sorted(list(profesores_lista)) if current_user.rol in ['admin', 'socio'] else [],
                         mes=mes, anio=anio, filtro_profesor=filtro_profesor)

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
    total_pago_docentes = 0
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
                    total_docencia += pago_docente
                else:
                    pago_docente = 0
                    pago_psicologia = valor * PORCENTAJE_PSICOLOGIA
                    total_psicologia += pago_psicologia
                
                total_pagar = pago_docente + pago_psicologia
                total_pago_docentes += total_pagar
                
                if prof not in pagos_por_docente:
                    pagos_por_docente[prof] = {
                        'pago_docencia': 0, 'pago_psicologia': 0, 'total_pagar': 0
                    }
                pagos_por_docente[prof]['pago_docencia'] += pago_docente
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
    
    total_por_pagar_estudiantes = total_cobrar_estudiantes - total_pagado_estudiantes
    balance = total_pagado_estudiantes - total_gastos - total_pago_docentes
    porcentaje_cobrado = round((total_pagado_estudiantes / max(total_cobrar_estudiantes, 1)) * 100, 2)
    porcentaje_cumplimiento = round((cumplimiento.get('realizado', 0) / max(cumplimiento.get('planificado', 1), 1)) * 100, 2)
    
    correcciones = supabase.table('correcciones_pagos').select('*').order('fecha_correccion', desc=True).limit(30).execute()
    observaciones = supabase.table('sesiones').select('*, estudiantes(apellidos, nombres)').not_.is_('observaciones', 'null').order('fecha', desc=True).limit(30).execute()
    nuevos_usuarios = supabase.table('usuarios').select('*').gte('fecha_registro', f"{anio}-{mes:02d}-01").lte('fecha_registro', f"{anio}-{mes:02d}-31").execute()
    
    return render_template('reportes.html',
                         datos_estudiantes=datos_estudiantes, total_estudiantes=len(datos_estudiantes),
                         total_horas_estudiantes=total_horas_estudiantes,
                         total_cobrar_estudiantes=total_cobrar_estudiantes,
                         total_pagado_estudiantes=total_pagado_estudiantes,
                         total_por_pagar_estudiantes=total_por_pagar_estudiantes,
                         porcentaje_cobrado=porcentaje_cobrado, total_ingresos=total_pagado_estudiantes,
                         total_gastos=total_gastos, balance=balance,
                         gastos=gastos_mes.data or [], mes=mes, anio=anio,
                         ingresos_por_tipo=ingresos_por_tipo, gastos_por_categoria=gastos_por_categoria,
                         horas_por_materia=horas_por_materia, asignaturas_detalle=asignaturas_detalle,
                         cumplimiento=cumplimiento, porcentaje_cumplimiento=porcentaje_cumplimiento,
                         pagos_por_docente=pagos_por_docente, total_pago_docentes=total_pago_docentes,
                         total_docencia=total_docencia, total_psicologia=total_psicologia,
                         correcciones=correcciones.data or [], observaciones=observaciones.data or [],
                         nuevos_usuarios=nuevos_usuarios.data or [], total_planificado=0)

# ========== MIS CLIENTES ==========
@app.route('/mis-clientes')
@login_required
def mis_clientes():
    if current_user.rol != 'psicologo':
        flash('❌ Solo psicólogos pueden acceder', 'error')
        return redirect(url_for('dashboard'))
    return render_template('mis_clientes.html', clientes=[], citas=[], today=date.today().isoformat())

# ========== GASTOS ==========
@app.route('/gastos', methods=['GET', 'POST'])
@login_required
def gestion_gastos():
    if request.method == 'POST':
        fecha = request.form['fecha']
        fecha_obj = datetime.strptime(fecha, '%Y-%m-%d')
        supabase.table('gastos').insert({
            'concepto': request.form['concepto'],
            'monto': float(request.form['monto']),
            'fecha': fecha,
            'categoria': request.form.get('categoria', ''),
            'persona': request.form.get('persona', ''),
            'reembolso': request.form.get('reembolso') == 'true',
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
def eliminar_gasto(id):
    supabase.table('gastos').delete().eq('id', id).execute()
    return jsonify({'success': True})

# ========== INICIALIZACIÓN ==========
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)