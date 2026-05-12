import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from config import Config
from models import check_password, Usuario
from supabase_client import supabase
try:
    from google_calendar import crear_evento_calendar, eliminar_evento_calendar
except ImportError:
    crear_evento_calendar = None
    eliminar_evento_calendar = None
from datetime import datetime, date
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

@app.route('/')
def inicio():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
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
                flash('✅ Solicitud enviada', 'success')
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
        flash('❌ Error', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout(): logout_user(); return redirect(url_for('inicio'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', rol=current_user.rol)

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
            for sesion_num in range(1, num_sesiones + 1):
                fecha = request.form.get(f'fecha_{sesion_num}')
                h_ini = request.form.get(f'hora_inicio_{sesion_num}')
                h_fin = request.form.get(f'hora_fin_{sesion_num}')
                profesor = request.form.get(f'profesor_{sesion_num}', '')
                nuevo_prof = request.form.get(f'nuevo_profesor_{sesion_num}', '')
                encargado = request.form.get(f'encargado_{sesion_num}', '')
                if nuevo_prof and profesor == 'nuevo': profesor = nuevo_prof
                if not fecha or not h_ini or not h_fin: continue
                if not primera_fecha: primera_fecha = fecha
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
                            'encargado_apertura': encargado
                        })
                        if evento_id:
                            for est_num in range(1, num_estudiantes + 1):
                                eid = request.form.get(f'estudiante_id_{est_num}', '')
                                if eid and eid != 'nuevo':
                                    supabase.table('sesiones').update({'evento_calendar_id': evento_id}).eq('estudiante_id', int(eid)).eq('fecha', fecha).eq('hora_inicio', h_ini).execute()
                    except: pass
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

@app.route('/modulo2')
@login_required
def modulo2():
    fecha = request.args.get('fecha', str(date.today()))
    if current_user.rol in ['admin', 'socio']:
        sesiones = supabase.table('sesiones').select('*, estudiantes(*)').eq('fecha', fecha).order('hora_inicio').execute()
        return render_template('modulo2.html', sesiones=sesiones.data or [], fecha=fecha)
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
                        sesiones_filtradas.append(s); break
        elif current_user.rol in ['estudiante', 'padre']:
            if nombre_usuario in nombre_est or nombre_est in nombre_usuario:
                sesiones_filtradas.append(s)
            else:
                for palabra in palabras_usuario:
                    if len(palabra) >= 3:
                        if palabra in apellidos_est or palabra in nombres_est:
                            sesiones_filtradas.append(s); break
    return render_template('modulo2.html', sesiones=sesiones_filtradas, fecha=fecha)

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
        s = supabase.table('sesiones').select('evento_calendar_id').eq('id', id).execute()
        if s.data and s.data[0].get('evento_calendar_id'):
            if eliminar_evento_calendar:
                try:
                    eliminar_evento_calendar(s.data[0]['evento_calendar_id'])
                    updates['evento_calendar_id'] = None
                except: pass
    supabase.table('sesiones').update(updates).eq('id', id).execute()
    return jsonify({'success': True})

@app.route('/api/sesion/<int:id>/modificar', methods=['POST'])
@login_required
@socio_admin_required
def modificar_sesion(id):
    try:
        data = request.get_json()
        fecha, h_ini, h_fin = data['fecha'], data['hora_inicio'][:5], data['hora_fin'][:5]
        inicio = datetime.strptime(f"{fecha} {h_ini}", '%Y-%m-%d %H:%M')
        fin = datetime.strptime(f"{fecha} {h_fin}", '%Y-%m-%d %H:%M')
        updates = {'fecha': fecha, 'hora_inicio': h_ini, 'hora_fin': h_fin, 'horas': round((fin - inicio).total_seconds() / 3600, 2)}
        supabase.table('sesiones').update(updates).eq('id', id).execute()
        sesion = supabase.table('sesiones').select('evento_calendar_id, asignatura, tema_terapia, profesor_terapeuta, encargado_apertura, estudiantes(apellidos, nombres)').eq('id', id).execute()
        if sesion.data:
            s = sesion.data[0]
            if s.get('evento_calendar_id') and eliminar_evento_calendar:
                try: eliminar_evento_calendar(s['evento_calendar_id'])
                except: pass
            if crear_evento_calendar:
                try:
                    est = s.get('estudiantes', {})
                    nuevo_id = crear_evento_calendar({
                        'asignatura': s.get('asignatura') or s.get('tema_terapia') or 'Sesión',
                        'profesor': s.get('profesor_terapeuta', ''),
                        'estudiantes': f"{est.get('apellidos', '')} {est.get('nombres', '')}" if est else '',
                        'fecha': fecha, 'hora_inicio': h_ini, 'hora_fin': h_fin,
                        'encargado_apertura': s.get('encargado_apertura', '')
                    })
                    if nuevo_id:
                        supabase.table('sesiones').update({'evento_calendar_id': nuevo_id}).eq('id', id).execute()
                except: pass
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/sesion/<int:id>/eliminar', methods=['GET', 'POST', 'DELETE'])
@login_required
@socio_admin_required
def eliminar_sesion(id):
    try:
        sesion = supabase.table('sesiones').select('evento_calendar_id').eq('id', id).execute()
        evento_id = sesion.data[0].get('evento_calendar_id') if sesion.data else None
        if evento_id and eliminar_evento_calendar: eliminar_evento_calendar(evento_id)
        supabase.table('sesiones').delete().eq('id', id).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

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
            inicio = datetime.strptime(f"{nueva_fecha} {nueva_h_ini}", '%Y-%m-%d %H:%M')
            fin = datetime.strptime(f"{nueva_fecha} {nueva_h_fin}", '%Y-%m-%d %H:%M')
            nuevas_horas = round((fin - inicio).total_seconds() / 3600, 2)
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
                flash(f'✅ Sesión actualizada. Horas: {nuevas_horas}, Valor: ${nuevo_valor:.2f}', 'success')
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

@app.route('/modulo4')
@login_required
def modulo4():
    sesiones = supabase.table('sesiones').select('*, estudiantes(*)').gte('fecha', str(date.today())).order('fecha').execute()
    reuniones = []
    if current_user.rol in ['admin', 'socio']:
        reuniones = supabase.table('reuniones').select('*').gte('fecha', str(date.today())).order('fecha').execute()
    return render_template('modulo4.html', sesiones=sesiones.data or [], reuniones=reuniones.data if reuniones else [])

@app.route('/modulo5')
@login_required
def modulo5():
    query = supabase.table('sesiones').select('*, estudiantes(*)').eq('estado', 'Realizado')
    if current_user.rol in ['profesor', 'psicologo']:
        nombre_usuario = current_user.nombre.strip().lower()
        todas = query.order('fecha', desc=True).execute()
        sesiones_filtradas = []
        for s in (todas.data or []):
            profesor = (s.get('profesor_terapeuta') or '').strip().lower()
            if nombre_usuario in profesor or profesor in nombre_usuario:
                sesiones_filtradas.append(s)
        sesiones_data = sesiones_filtradas
    else:
        sesiones = query.order('fecha', desc=True).execute()
        sesiones_data = sesiones.data or []
    pagos, total, consolidado = [], 0, {}
    for s in sesiones_data:
        horas, valor, tipo = s.get('horas', 0) or 0, s.get('valor_total', 0) or 0, s.get('tipo_sesion', 'clase')
        profesor = s.get('profesor_terapeuta', 'Desconocido')
        pago = horas * 7 if tipo in ['clase', 'preuniversitario'] else valor * 0.35
        total += pago
        est = s.get('estudiantes', {})
        pagos.append({'fecha': s['fecha'], 'profesor': profesor, 'estudiante': f"{est.get('apellidos', '')} {est.get('nombres', '')}",
                     'tipo': tipo, 'horas': horas, 'valor_total': valor, 'pago_docente': pago})
        if profesor not in consolidado: consolidado[profesor] = {'sesiones': 0, 'horas': 0, 'pago': 0, 'pagado': 0}
        consolidado[profesor]['sesiones'] += 1; consolidado[profesor]['horas'] += horas; consolidado[profesor]['pago'] += pago
    return render_template('modulo5.html', pagos=pagos, total_adeudado=total, consolidado=consolidado)

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

@app.route('/reportes')
@login_required
@socio_admin_required
def reportes():
    mes = int(request.args.get('mes', date.today().month))
    anio = int(request.args.get('anio', date.today().year))
    estudiantes = supabase.table('estudiantes').select('*').eq('activo', True).order('apellidos').execute()
    datos, tc, tp, th = [], 0, 0, 0
    horas_por_materia = {}
    pagos_por_docente = {}
    cumplimiento = {'planificado': 0, 'realizado': 0, 'cancelado': 0}
    ingresos_por_tipo = {}
    gastos_por_categoria = {}
    for e in (estudiantes.data or []):
        ses = supabase.table('sesiones').select('*').eq('estudiante_id', e['id']).execute()
        ses_todas = [s for s in (ses.data or []) if s['fecha'][:7] == f"{anio}-{mes:02d}"]
        ses_realizadas = [s for s in ses_todas if s['estado'] == 'Realizado']
        ses_canceladas = [s for s in ses_todas if s['estado'] == 'Cancelado']
        pag = supabase.table('pagos').select('*').eq('estudiante_id', e['id']).execute()
        pag_filtrados = [p for p in (pag.data or []) if p['fecha_pago'][:7] == f"{anio}-{mes:02d}"]
        horas_plan = sum(s.get('horas', 0) or 0 for s in ses_todas)
        horas_real = sum(s.get('horas', 0) or 0 for s in ses_realizadas)
        horas_canc = sum(s.get('horas', 0) or 0 for s in ses_canceladas)
        cobrar = sum(s.get('valor_total', 0) or 0 for s in ses_realizadas)
        pagado = sum(p.get('monto', 0) or 0 for p in pag_filtrados)
        tc += cobrar; tp += pagado; th += horas_real
        for s in ses_todas:
            asig = s.get('asignatura') or s.get('tema_terapia') or 'Sin registro'
            horas_por_materia[asig] = horas_por_materia.get(asig, 0) + (s.get('horas', 0) or 0)
            cumplimiento[s.get('estado', 'Planificado').lower()] = cumplimiento.get(s.get('estado', 'Planificado').lower(), 0) + 1
            prof = s.get('profesor_terapeuta', 'Desconocido')
            tipo = s.get('tipo_sesion', 'clase')
            valor = s.get('valor_total', 0) or 0
            pago = (s.get('horas', 0) or 0) * 7 if tipo in ['clase', 'preuniversitario'] else valor * 0.35
            if prof not in pagos_por_docente: pagos_por_docente[prof] = {'horas': 0, 'pago': 0, 'sesiones': 0, 'pagado': 0}
            pagos_por_docente[prof]['horas'] += s.get('horas', 0) or 0
            pagos_por_docente[prof]['pago'] += pago
            pagos_por_docente[prof]['sesiones'] += 1
            if tipo not in ingresos_por_tipo: ingresos_por_tipo[tipo] = 0
            ingresos_por_tipo[tipo] += valor
        if cobrar > 0 or pagado > 0 or horas_real > 0:
            datos.append({'id': e['id'], 'estudiante': f"{e['apellidos']} {e['nombres']}",
                         'horas_plan': horas_plan, 'horas_real': horas_real, 'horas_canc': horas_canc,
                         'cobrar': cobrar, 'pagado': pagado, 'saldo': cobrar - pagado})
    gastos_mes = supabase.table('gastos').select('*').eq('mes', mes).eq('anio', anio).order('fecha').execute()
    total_gastos = sum(g.get('monto', 0) or 0 for g in (gastos_mes.data or []))
    for g in (gastos_mes.data or []):
        cat = g.get('categoria', 'Sin categoría')
        gastos_por_categoria[cat] = gastos_por_categoria.get(cat, 0) + (g.get('monto', 0) or 0)
    pagos_mes = supabase.table('pagos').select('*').gte('fecha_pago', f"{anio}-{mes:02d}-01").lte('fecha_pago', f"{anio}-{mes:02d}-31").execute()
    total_ingresos = sum(p.get('monto', 0) or 0 for p in (pagos_mes.data or []))
    correcciones = supabase.table('correcciones_pagos').select('*').order('fecha_correccion', desc=True).limit(30).execute()
    observaciones = supabase.table('sesiones').select('*, estudiantes(apellidos, nombres)').not_.is_('observaciones', 'null').order('fecha', desc=True).limit(30).execute()
    nuevos_usuarios = supabase.table('usuarios').select('*').gte('fecha_registro', f"{anio}-{mes:02d}-01").lte('fecha_registro', f"{anio}-{mes:02d}-31").execute()
    total_pago_docentes = sum(d['pago'] for d in pagos_por_docente.values())
    return render_template('reportes.html',
                         datos=datos, total_estudiantes=len(datos),
                         total_horas=th, total_ingresos=total_ingresos,
                         total_gastos=total_gastos, balance=total_ingresos - total_gastos,
                         gastos=gastos_mes.data or [], mes=mes, anio=anio,
                         ingresos_por_tipo=ingresos_por_tipo,
                         horas_por_materia=horas_por_materia,
                         pagos_por_docente=pagos_por_docente,
                         total_pago_docentes=total_pago_docentes,
                         cumplimiento=cumplimiento,
                         correcciones=correcciones.data or [],
                         observaciones=observaciones.data or [],
                         nuevos_usuarios=nuevos_usuarios.data or [],
                         gastos_por_categoria=gastos_por_categoria)

@app.route('/gastos', methods=['GET', 'POST'])
@login_required
@socio_admin_required
def gestion_gastos():
    if request.method == 'POST':
        fecha = request.form['fecha']
        fecha_obj = datetime.strptime(fecha, '%Y-%m-%d')
        reembolso = request.form.get('reembolso') == 'true'
        supabase.table('gastos').insert({
            'concepto': request.form['concepto'], 'monto': float(request.form['monto']),
            'fecha': fecha, 'categoria': request.form.get('categoria', ''),
            'persona': request.form.get('persona', ''), 'reembolso': reembolso,
            'reembolsado_a': request.form.get('reembolsado_a', '') if reembolso else '',
            'registrado_por': current_user.nombre, 'mes': fecha_obj.month, 'anio': fecha_obj.year
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
            if password: updates['password_hash'] = password
            supabase.table('usuarios').update(updates).eq('id', int(edit_id)).execute()
            flash('✅ Usuario actualizado', 'success')
        return redirect(url_for('gestion_usuarios'))
    usuarios = supabase.table('usuarios').select('*').order('fecha_registro', desc=True).execute()
    return render_template('usuarios.html', usuarios=usuarios.data or [])

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
        if mes != 0 and s['fecha'][:7] != f"{anio}-{mes:02d}": continue
        profesor = (s.get('profesor_terapeuta') or '').strip().lower()
        est = s.get('estudiantes', {})
        nombre_est = f"{est.get('apellidos', '')} {est.get('nombres', '')}".strip().lower()
        incluir = False
        if current_user.rol in ['profesor', 'psicologo']:
            if nombre_usuario in profesor or profesor in nombre_usuario: incluir = True
            else:
                for p in palabras_usuario:
                    if len(p) >= 3 and p in profesor: incluir = True; break
        elif current_user.rol in ['estudiante', 'padre']:
            apellidos_est = (est.get('apellidos', '') or '').strip().lower()
            nombres_est = (est.get('nombres', '') or '').strip().lower()
            if nombre_usuario in nombre_est or nombre_est in nombre_usuario: incluir = True
            else:
                for p in palabras_usuario:
                    if len(p) >= 3 and (p in apellidos_est or p in nombres_est): incluir = True; break
        if incluir:
            datos.append({'fecha': s['fecha'], 'estudiante': nombre_est, 'tipo': s['tipo_sesion'],
                         'asignatura': s.get('asignatura') or s.get('tema_terapia') or '-',
                         'horas': s.get('horas', 0) or 0, 'valor': s.get('valor_total', 0) or 0, 'estado': s['estado']})
            total_horas += s.get('horas', 0) or 0
            total_cobrar += s.get('valor_total', 0) or 0
    return render_template('mi_reporte.html', datos=datos, total_cobrar=total_cobrar,
                         total_pagado=total_pagado, total_horas=total_horas, mes=mes, anio=anio,
                         saldo=total_cobrar - total_pagado)

@app.route('/editar-perfil', methods=['GET', 'POST'])
@login_required
def editar_perfil():
    if request.method == 'POST':
        nuevo_nombre = request.form['nombre']
        nuevo_email = request.form['email']
        nueva_password = request.form.get('password', '')
        updates = {'nombre': nuevo_nombre, 'email': nuevo_email}
        if nueva_password: updates['password_hash'] = nueva_password
        supabase.table('usuarios').update(updates).eq('id', current_user.id).execute()
        if current_user.rol in ['profesor', 'psicologo']:
            supabase.table('sesiones').update({'profesor_terapeuta': nuevo_nombre}).eq('profesor_terapeuta', current_user.nombre).execute()
        flash('✅ Perfil actualizado correctamente.', 'success')
        return redirect(url_for('dashboard'))
    return render_template('editar_perfil.html')

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

@app.route('/api/sesiones/pendientes')
@login_required
def api_sesiones_pendientes():
    query = supabase.table('sesiones').select('*, estudiantes(*)').eq('estado', 'Planificado')
    nombre_usuario = current_user.nombre.strip().lower()
    palabras_usuario = nombre_usuario.split()
    if current_user.rol in ['admin', 'socio']:
        sesiones = query.order('fecha').order('hora_inicio').execute()
        sesiones_data = sesiones.data or []
    else:
        todas = query.order('fecha').order('hora_inicio').execute()
        sesiones_data = []
        for s in (todas.data or []):
            profesor = (s.get('profesor_terapeuta') or '').strip().lower()
            est = s.get('estudiantes', {})
            nombre_est = f"{est.get('apellidos', '')} {est.get('nombres', '')}".strip().lower()
            apellidos_est = (est.get('apellidos', '') or '').strip().lower()
            nombres_est = (est.get('nombres', '') or '').strip().lower()
            if current_user.rol in ['profesor', 'psicologo']:
                if nombre_usuario in profesor or profesor in nombre_usuario: sesiones_data.append(s)
                else:
                    for p in palabras_usuario:
                        if len(p) >= 3 and p in profesor: sesiones_data.append(s); break
            elif current_user.rol in ['estudiante', 'padre']:
                if nombre_usuario in nombre_est or nombre_est in nombre_usuario: sesiones_data.append(s)
                else:
                    for p in palabras_usuario:
                        if len(p) >= 3 and (p in apellidos_est or p in nombres_est): sesiones_data.append(s); break
    resultado = []
    for s in sesiones_data:
        est = s.get('estudiantes', {})
        resultado.append({'id': s['id'], 'fecha': s['fecha'], 'hora_inicio': s['hora_inicio'], 'hora_fin': s['hora_fin'],
                         'estudiante': f"{est.get('apellidos', '')} {est.get('nombres', '')}",
                         'estudiante_id': s['estudiante_id'], 'tipo_sesion': s['tipo_sesion'],
                         'asignatura': s.get('asignatura', ''), 'tema_terapia': s.get('tema_terapia', ''),
                         'profesor_terapeuta': s['profesor_terapeuta']})
    return jsonify(resultado)

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

@app.route('/api/sesion/<int:id>/cambiar-estudiante', methods=['POST'])
@login_required
@socio_admin_required
def cambiar_estudiante_sesion(id):
    try:
        data = request.get_json()
        estudiante_id = data.get('estudiante_id')
        nuevo_nombre = data.get('nuevo_nombre', '')
        nuevo_apellido = data.get('nuevo_apellido', '')
        
        if estudiante_id == 'nuevo' and nuevo_nombre and nuevo_apellido:
            result = supabase.table('estudiantes').insert({
                'nombres': nuevo_nombre, 'apellidos': nuevo_apellido,
                'nivel_curso': data.get('nuevo_nivel', ''), 'procedencia': data.get('nuevo_procedencia', ''),
                'activo': True, 'usuario_id': int(current_user.id)
            }).execute()
            if result.data:
                estudiante_id = result.data[0]['id']
            else:
                return jsonify({'success': False, 'error': 'No se pudo crear'})
        
        if not estudiante_id or estudiante_id == 'nuevo':
            return jsonify({'success': False, 'error': 'ID requerido'})
        
        estudiante_id = int(estudiante_id)
        est = supabase.table('estudiantes').select('apellidos, nombres').eq('id', estudiante_id).execute()
        nombre_est = f"{est.data[0]['apellidos']} {est.data[0]['nombres']}" if est.data else ''
        
        supabase.table('sesiones').update({'estudiante_id': estudiante_id}).eq('id', id).execute()
        
        sesion = supabase.table('sesiones').select('*').eq('id', id).execute()
        if sesion.data:
            s = sesion.data[0]
            if s.get('evento_calendar_id') and eliminar_evento_calendar and crear_evento_calendar:
                try:
                    eliminar_evento_calendar(s['evento_calendar_id'])
                    nuevo_id = crear_evento_calendar({
                        'asignatura': s.get('asignatura') or s.get('tema_terapia') or 'Sesión',
                        'profesor': s.get('profesor_terapeuta', ''),
                        'estudiantes': nombre_est,
                        'fecha': s['fecha'], 'hora_inicio': s['hora_inicio'],
                        'hora_fin': s['hora_fin'], 'encargado_apertura': s.get('encargado_apertura', '')
                    })
                    if nuevo_id:
                        supabase.table('sesiones').update({'evento_calendar_id': nuevo_id}).eq('id', id).execute()
                except: pass
        
        return jsonify({'success': True, 'nombre': nombre_est})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/sesion/<int:id>/cambiar-profesor', methods=['POST'])
@login_required
@socio_admin_required
def cambiar_profesor_sesion(id):
    try:
        data = request.get_json()
        nuevo_profesor = data.get('profesor', '')
        if not nuevo_profesor:
            return jsonify({'success': False, 'error': 'Nombre requerido'})
        
        profesor_anterior = supabase.table('sesiones').select('profesor_terapeuta').eq('id', id).execute()
        anterior = profesor_anterior.data[0]['profesor_terapeuta'] if profesor_anterior.data else ''
        
        supabase.table('sesiones').update({
            'profesor_terapeuta': nuevo_profesor
        }).eq('id', id).execute()
        
        # Registrar en observaciones quién hizo el cambio
        supabase.table('sesiones').update({
            'observaciones': f"CAMBIO PROFESOR: {anterior} → {nuevo_profesor} por {current_user.nombre} el {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        }).eq('id', id).execute()
        
        sesion = supabase.table('sesiones').select('*, estudiantes(apellidos, nombres)').eq('id', id).execute()
        if sesion.data:
            s = sesion.data[0]
            if s.get('evento_calendar_id') and eliminar_evento_calendar and crear_evento_calendar:
                try:
                    eliminar_evento_calendar(s['evento_calendar_id'])
                    est = s.get('estudiantes', {})
                    nuevo_id = crear_evento_calendar({
                        'asignatura': s.get('asignatura') or s.get('tema_terapia') or 'Sesión',
                        'profesor': nuevo_profesor,
                        'estudiantes': f"{est.get('apellidos', '')} {est.get('nombres', '')}" if est else '',
                        'fecha': s['fecha'], 'hora_inicio': s['hora_inicio'],
                        'hora_fin': s['hora_fin'], 'encargado_apertura': s.get('encargado_apertura', '')
                    })
                    if nuevo_id:
                        supabase.table('sesiones').update({'evento_calendar_id': nuevo_id}).eq('id', id).execute()
                except: pass
        
        return jsonify({'success': True, 'profesor': nuevo_profesor})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)