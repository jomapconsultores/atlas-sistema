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
PORCENTAJE_PSICOLOGIA = 0.4018
COMISION_CLIENTE_EXTERNO = 0.25

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
                         asignaturas=ASIGNATURAS, atencion_psicologica=psicologia,
                         precios_clase=precios_clase, precios_matricula=precios_matricula,
                         precios_pension=precios_pension, profesores=PROFESORES,
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
                         asignaturas=ASIGNATURAS,
                         atencion_psicologica=psicologia,
                         precios_clase=precios_clase,
                         profesores=PROFESORES,
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
                         asignaturas=ASIGNATURAS,
                         atencion_psicologica=psicologia,
                         precios_clase=precios_clase,
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
                valor_total_sesion = sd.get('precio_hora', 40) or 40
            else:
                horas = sd.get('horas', 1) or 1
                precio_hora = sd.get('precio_hora', 10) or 10
                valor_total_sesion = round(horas * precio_hora, 2)
            updates['valor_total'] = valor_total_sesion
            updates['valor_pagar_docente'] = valor_total_sesion
            updates['valor_atlas'] = 0
    elif estado == 'Cancelado':
        updates['valor_total'] = 0
        updates['valor_pagar_docente'] = 0
        updates['valor_atlas'] = 0
    elif estado == 'Cancelado-Pagado':
        s = supabase.table('sesiones').select('*').eq('id', id).execute()
        if s.data:
            sd = s.data[0]
            # Calcular el valor total de la sesión (lo que debe pagar el estudiante)
            if sd.get('cobro_por_sesion') or sd.get('tipo_sesion') in ['terapia', 'ambos']:
                valor_total_sesion = sd.get('precio_hora', 40) or 40
            else:
                horas = sd.get('horas', 1) or 1
                precio_hora = sd.get('precio_hora', 10) or 10
                valor_total_sesion = round(horas * precio_hora, 2)
            
            # Calcular pago al docente: 50% del valor, máximo $7 para clases
            if sd.get('tipo_sesion') in ['clase', 'preuniversitario']:
                pago_docente = round(valor_total_sesion * 0.5, 2)
                pago_docente = min(pago_docente, 7.00)
            else:
                # Psicología: 40.18% del valor
                pago_docente = round(valor_total_sesion * PORCENTAJE_PSICOLOGIA, 2)
            
            valor_atlas = round(valor_total_sesion - pago_docente, 2)
            
            # IMPORTANTE: valor_total mantiene el valor que debe pagar el estudiante
            updates['valor_total'] = valor_total_sesion
            updates['valor_pagar_docente'] = pago_docente
            updates['valor_atlas'] = valor_atlas
    
    supabase.table('sesiones').update(updates).eq('id', id).execute()
    return jsonify({'success': True})

@app.route('/api/sesion/<int:id>/sincronizar', methods=['POST'])
@login_required
def sincronizar_calendario(id):
    try:
        sesion = supabase.table('sesiones').select('*, estudiantes(apellidos, nombres)').eq('id', id).execute()
        if not sesion.data:
            return jsonify({'success': False, 'error': 'Sesión no encontrada'})
        s = sesion.data[0]
        if not s.get('fecha') or not s.get('hora_inicio') or not s.get('hora_fin'):
            return jsonify({'success': False, 'error': 'Faltan datos'})
        est = s.get('estudiantes', {})
        nombre_est = f"{est.get('apellidos', '')} {est.get('nombres', '')}".strip()
        encargado = s.get('encargado_apertura', '').strip() or 'Por definir'
        hora_inicio = s.get('hora_inicio', '')[:5]
        hora_fin = s.get('hora_fin', '')[:5]
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
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'No se pudo crear/actualizar'})
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
    todas = supabase.table('sesiones').select('*, estudiantes(*)').eq('fecha', fecha).order('hora_inicio').execute()
    sesiones_filtradas = []
    for s in (todas.data or []):
        profesor = (s.get('profesor_terapeuta') or '').strip().lower()
        if nombre_usuario in profesor or profesor in nombre_usuario:
            sesiones_filtradas.append(s)
    return render_template('modulo2.html', sesiones=sesiones_filtradas, fecha=fecha,
                         estudiantes=estudiantes_lista, profesores=PROFESORES)

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
            supabase.table('pagos').update({'monto': nuevo_monto}).eq('id', pago_id).execute()
            supabase.table('correcciones_pagos').insert({
                'pago_id': pago_id, 'monto_anterior': 0, 'monto_nuevo': nuevo_monto,
                'cambiado_por': cambiado_por, 'motivo': motivo
            }).execute()
            flash('✅ Pago corregido', 'success')
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
            flash('✅ Sesión actualizada', 'success')
        return redirect(url_for('modulo3'))
    
    estudiantes = supabase.table('estudiantes').select('*').eq('activo', True).order('apellidos').execute()
    datos = []
    for e in (estudiantes.data or []):
        ses = supabase.table('sesiones').select('*').eq('estudiante_id', e['id']).in_('estado', ['Realizado', 'Cancelado-Pagado']).execute()
        pag = supabase.table('pagos').select('*').eq('estudiante_id', e['id']).order('fecha_pago', desc=True).execute()
        cobrar = sum(s.get('valor_total', 0) or 0 for s in (ses.data or []) if s.get('estado') in ['Realizado', 'Cancelado-Pagado'])
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
        pagos.append({
            'fecha': s['fecha'],
            'profesor': profesor,
            'estudiante': f"{est.get('apellidos', '')} {est.get('nombres', '')}".title(),
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
    reunion = supabase.table('reuniones').select('*').eq('id', id).execute()
    if not reunion.data:
        return jsonify({'success': False, 'error': 'Reunión no encontrada'})
    r = reunion.data[0]
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
    return jsonify({'success': False})

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
    for s in (sesiones.data or []):
        if s.get('fecha', '')[:7] == f"{anio_actual}-{mes_actual:02d}":
            tipo = s.get('tipo_sesion', 'clase')
            if s.get('estado') == 'Cancelado-Pagado':
                total_pagar_mes += s.get('valor_pagar_docente', 0) or 0
            elif tipo in ['clase', 'preuniversitario']:
                total_pagar_mes += (s.get('horas', 0) or 0) * 7
            else:
                total_pagar_mes += (s.get('valor_total', 0) or 0) * 0.4018
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
                    pago_psicologia = valor * 0.4018
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
    
    total_ingresos = total_facturado
    
    gastos_mes = supabase.table('gastos').select('*').eq('mes', mes).eq('anio', anio).execute()
    total_gastos = sum(g.get('monto', 0) or 0 for g in (gastos_mes.data or []))
    for g in (gastos_mes.data or []):
        cat = g.get('categoria', 'Sin categoría')
        gastos_por_categoria[cat] = gastos_por_categoria.get(cat, 0) + (g.get('monto', 0) or 0)
    
    balance = total_ingresos - total_gastos - total_pago_docentes
    
    correcciones = supabase.table('correcciones_pagos').select('*').order('fecha_correccion', desc=True).limit(30).execute()
    observaciones = supabase.table('sesiones').select('*, estudiantes(apellidos, nombres)').not_.is_('observaciones', 'null').order('fecha', desc=True).limit(30).execute()
    nuevos_usuarios = supabase.table('usuarios').select('*').gte('fecha_registro', f"{anio}-{mes:02d}-01").lte('fecha_registro', f"{anio}-{mes:02d}-31").execute()

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
                         nuevos_usuarios=nuevos_usuarios.data or [], total_planificado=0)


# ========== GASTOS ==========


# ========== GASTOS ==========
@app.route('/gastos', methods=['GET', 'POST'])
@login_required
def gestion_gastos():
    if request.method == 'POST':
        fecha = request.form['fecha']
        fecha_obj = datetime.strptime(fecha, '%Y-%m-%d')
        supabase.table('gastos').insert({
            'concepto': request.form['concepto'], 'monto': float(request.form['monto']),
            'fecha': fecha, 'categoria': request.form.get('categoria', ''),
            'persona': request.form.get('persona', ''), 'reembolso': request.form.get('reembolso') == 'true',
            'registrado_por': current_user.nombre, 'mes': fecha_obj.month, 'anio': fecha_obj.year
        }).execute()
        flash('✅ Gasto registrado', 'success')
        return redirect(url_for('gestion_gastos'))
    
    mes = int(request.args.get('mes', date.today().month))
    anio = int(request.args.get('anio', date.today().year))
    gastos = supabase.table('gastos').select('*').eq('mes', mes).eq('anio', anio).order('fecha', desc=True).execute()
    total = sum(g.get('monto', 0) or 0 for g in (gastos.data or []))
    
    # Obtener pagos a docentes del mes
    sesiones_mes = supabase.table('sesiones').select('*').in_('estado', ['Realizado', 'Cancelado-Pagado']).gte('fecha', f"{anio}-{mes:02d}-01").lte('fecha', f"{anio}-{mes:02d}-31").execute()
    
    pagos_docentes_detalle = {}
    total_sesiones_docentes = 0
    total_docencia_mes = 0
    total_psicologia_mes = 0
    total_pago_docentes_mes = 0
    
    for s in (sesiones_mes.data or []):
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
    
    return render_template('gastos.html', 
                         gastos=gastos.data or [], total=total, mes=mes, anio=anio, today=date.today(),
                         pagos_docentes_detalle=pagos_docentes_detalle,
                         total_pago_docentes_mes=total_pago_docentes_mes,
                         total_docencia_mes=total_docencia_mes,
                         total_psicologia_mes=total_psicologia_mes,
                         total_sesiones_docentes=total_sesiones_docentes)

@app.route('/api/gasto/<int:id>/eliminar', methods=['POST'])
@login_required
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
        'padre_nombre': data.get('padre_nombre', ''), 'activo': True, 'usuario_id': current_user.id
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
        'nivel_curso': request.form.get('nivel_curso', ''), 'procedencia': request.form.get('procedencia', ''),
        'padre_nombre': request.form.get('padre_nombre', ''), 'activo': True, 'usuario_id': current_user.id
    }).execute()
    flash('✅ Estudiante creado', 'success')
    return redirect(url_for('gestion_estudiantes'))

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
    
    anticipos = supabase.table('anticipos_solicitudes').select('*').eq('usuario_id', current_user.id).eq('estado', 'aprobado').execute()
    for a in (anticipos.data or []):
        anticipos_aprobados += a.get('monto', 0)
    
    for s in (sesiones.data or []):
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
                mi_pago = valor * 0.4018
                
            total_a_pagar += mi_pago
            total_horas += horas
            datos.append({
                'fecha': s['fecha'],
                'estudiante': nombre_est,
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
    try:
        # Guardar en tabla de fechas_pago
        supabase.table('fechas_pago_docentes').upsert({
            'docente_nombre': docente,
            'fecha_pago': fecha,
            'mes': date.today().month,
            'anio': date.today().year,
            'registrado_por': current_user.nombre
        }).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/pago-docente/toggle', methods=['POST'])
@login_required
def api_toggle_pago_docente():
    data = request.get_json()
    docente = data.get('docente')
    try:
        # Verificar estado actual
        existente = supabase.table('fechas_pago_docentes').select('*').eq('docente_nombre', docente).eq('mes', date.today().month).eq('anio', date.today().year).execute()
        if existente.data and existente.data[0].get('pagado'):
            supabase.table('fechas_pago_docentes').update({'pagado': False}).eq('id', existente.data[0]['id']).execute()
        elif existente.data:
            supabase.table('fechas_pago_docentes').update({'pagado': True}).eq('id', existente.data[0]['id']).execute()
        else:
            supabase.table('fechas_pago_docentes').insert({
                'docente_nombre': docente,
                'pagado': True,
                'mes': date.today().month,
                'anio': date.today().year,
                'registrado_por': current_user.nombre
            }).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ========== INICIALIZACIÓN ==========
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)