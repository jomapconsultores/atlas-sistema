import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from config import Config
from models import check_password, Usuario
from supabase_client import supabase
try:
    from google_calendar import crear_evento_calendar
except ImportError:
    crear_evento_calendar = None
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

# ============================================
@app.route('/')
def inicio():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    return render_template('inicio.html')

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        supabase.table('usuarios').insert({
            'nombre': request.form['nombre'], 'email': request.form['email'],
            'password_hash': request.form['password'], 'rol': request.form['rol'], 'activo': False
        }).execute()
        flash('✅ Solicitud enviada', 'success')
        return redirect(url_for('inicio'))
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

# ============================================
# MÓDULO 1 - PLANIFICACIÓN
# ============================================
@app.route('/modulo1', methods=['GET', 'POST'])
@login_required
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
                    precio = 40
                    for item in ATENCION_PSICOLOGICA:
                        if item['nombre'] == tema:
                            precio = item['precio']
                            break
                    valor_inicial = precio
                else:
                    asignatura = request.form.get('asignatura', '')
                    tema = ''
                    precio = float(request.form.get('precio_hora', 10))
                    valor_inicial = 0

                for est_num in range(1, num_estudiantes + 1):
                    eid = request.form.get(f'estudiante_id_{est_num}', '')
                    if eid and eid != 'nuevo':
                        supabase.table('sesiones').insert({
                            'tipo_sesion': tipo,
                            'asignatura': asignatura,
                            'tema_terapia': tema,
                            'profesor_terapeuta': profesor,
                            'fecha': fecha,
                            'hora_inicio': h_ini,
                            'hora_fin': h_fin,
                            'horas': horas,
                            'estado': 'Planificado',
                            'encargado_apertura': encargado,
                            'precio_hora': precio,
                            'valor_total': valor_inicial,
                            'cobro_por_sesion': es_terapia,
                            'estudiante_id': int(eid),
                            'usuario_id': int(current_user.id)
                        }).execute()

            # Google Calendar
            if crear_evento_calendar and primera_fecha:
                try:
                    estudiantes_nombres = []
                    for est_num in range(1, num_estudiantes + 1):
                        eid = request.form.get(f'estudiante_id_{est_num}', '')
                        if eid and eid != 'nuevo':
                            est = supabase.table('estudiantes').select('*').eq('id', int(eid)).execute()
                            if est.data:
                                estudiantes_nombres.append(f"{est.data[0]['apellidos']} {est.data[0]['nombres']}")

                    for sesion_num in range(1, num_sesiones + 1):
                        fecha_cal = request.form.get(f'fecha_{sesion_num}')
                        h_ini_cal = request.form.get(f'hora_inicio_{sesion_num}')
                        h_fin_cal = request.form.get(f'hora_fin_{sesion_num}')
                        if fecha_cal and h_ini_cal and h_fin_cal:
                            crear_evento_calendar({
                                'asignatura': request.form.get('asignatura', 'Sesión'),
                                'profesor': request.form.get(f'profesor_{sesion_num}', ''),
                                'estudiantes': ', '.join(estudiantes_nombres),
                                'fecha': fecha_cal,
                                'hora_inicio': h_ini_cal,
                                'hora_fin': h_fin_cal,
                                'encargado_apertura': request.form.get(f'encargado_{sesion_num}', '')
                            })
                except Exception as e:
                    print(f'⚠️ Error Google Calendar: {e}')

            flash(f'✅ {num_sesiones} sesión(es) para {num_estudiantes} estudiante(s)', 'success')
            return redirect(url_for('modulo2', fecha=primera_fecha or str(date.today())))

        except Exception as e:
            flash(f'❌ Error: {str(e)}', 'error')
        return redirect(url_for('modulo1'))

    estudiantes = supabase.table('estudiantes').select('*').eq('activo', True).order('apellidos').execute()
    return render_template('modulo1.html',
                         estudiantes=estudiantes.data or [],
                         asignaturas=ASIGNATURAS,
                         atencion_psicologica=ATENCION_PSICOLOGICA,
                         precios_clase=PRECIOS_CLASE,
                         precios_matricula=PRECIOS_MATRICULA,
                         precios_pension=PRECIOS_PENSION,
                         profesores=PROFESORES,
                         encargados=ENCARGADOS,
                         today=date.today())

# ============================================
# MÓDULO 2 - CALENDARIO
# ============================================
@app.route('/modulo2')
@login_required
def modulo2():
    fecha = request.args.get('fecha', str(date.today()))
    sesiones = supabase.table('sesiones').select('*, estudiantes(*)').eq('fecha', fecha).order('hora_inicio').execute()
    return render_template('modulo2.html', sesiones=sesiones.data or [], fecha=fecha)

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

@app.route('/api/sesion/<int:id>/eliminar', methods=['GET', 'POST', 'DELETE'])
@login_required
def eliminar_sesion(id):
    try:
        supabase.table('sesiones').delete().eq('id', id).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/sesion/<int:id>/modificar', methods=['POST'])
@login_required
def modificar_sesion(id):
    try:
        data = request.get_json()
        inicio = datetime.strptime(f"{data['fecha']} {data['hora_inicio']}", '%Y-%m-%d %H:%M')
        fin = datetime.strptime(f"{data['fecha']} {data['hora_fin']}", '%Y-%m-%d %H:%M')
        updates = {
            'fecha': data['fecha'],
            'hora_inicio': data['hora_inicio'],
            'hora_fin': data['hora_fin'],
            'horas': round((fin - inicio).total_seconds() / 3600, 2)
        }
        supabase.table('sesiones').update(updates).eq('id', id).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ============================================
# MÓDULO 3 - PAGOS
# ============================================
@app.route('/modulo3', methods=['GET', 'POST'])
@login_required
@socio_admin_required
def modulo3():
    if request.method == 'POST':
        supabase.table('pagos').insert({
            'fecha_pago': request.form['fecha_pago'],
            'monto': float(request.form['monto']),
            'tipo_pago': request.form.get('tipo_pago', 'efectivo'),
            'concepto': request.form.get('concepto', ''),
            'estudiante_id': int(request.form['estudiante_id']),
            'usuario_id': int(current_user.id)
        }).execute()
        flash('✅ Pago registrado', 'success')
        return redirect(url_for('modulo3'))

    estudiantes = supabase.table('estudiantes').select('*').eq('activo', True).order('apellidos').execute()
    datos = []
    for e in (estudiantes.data or []):
        ses = supabase.table('sesiones').select('*').eq('estudiante_id', e['id']).eq('estado', 'Realizado').execute()
        pag = supabase.table('pagos').select('*').eq('estudiante_id', e['id']).execute()
        cobrar = sum(s.get('valor_total', 0) or 0 for s in (ses.data or []))
        pagado = sum(p.get('monto', 0) or 0 for p in (pag.data or []))
        if cobrar > 0 or pagado > 0:
            datos.append({'id': e['id'], 'nombre': f"{e['apellidos']} {e['nombres']}", 'cobrar': cobrar, 'pagado': pagado, 'saldo': cobrar - pagado})
    return render_template('modulo3.html', estudiantes=datos, today=date.today())

# ============================================
# MÓDULO 4 - CALENDARIO PÚBLICO
# ============================================
@app.route('/modulo4')
def modulo4():
    sesiones = supabase.table('sesiones').select('*, estudiantes(*)').gte('fecha', str(date.today())).order('fecha').execute()
    return render_template('modulo4.html', sesiones=sesiones.data or [])

# ============================================
# MÓDULO 5 - PAGOS DOCENTES
# ============================================
@app.route('/modulo5')
@login_required
@socio_admin_required
def modulo5():
    sesiones = supabase.table('sesiones').select('*, estudiantes(*)').eq('estado', 'Realizado').order('fecha', desc=True).execute()
    pagos = []
    total = 0
    consolidado = {}

    for s in (sesiones.data or []):
        horas = s.get('horas', 0) or 0
        valor = s.get('valor_total', 0) or 0
        tipo = s.get('tipo_sesion', 'clase')
        profesor = s.get('profesor_terapeuta', 'Desconocido')

        pago = horas * 7 if tipo in ['clase', 'preuniversitario'] else valor * 0.35
        total += pago

        est = s.get('estudiantes', {})
        pagos.append({
            'fecha': s['fecha'], 'profesor': profesor,
            'estudiante': f"{est.get('apellidos', '')} {est.get('nombres', '')}",
            'tipo': tipo, 'horas': horas, 'valor_total': valor, 'pago_docente': pago
        })

        if profesor not in consolidado:
            consolidado[profesor] = {'sesiones': 0, 'horas': 0, 'pago': 0}
        consolidado[profesor]['sesiones'] += 1
        consolidado[profesor]['horas'] += horas
        consolidado[profesor]['pago'] += pago

    return render_template('modulo5.html', pagos=pagos, total_adeudado=total, consolidado=consolidado)

# ============================================
# REPORTES
# ============================================
@app.route('/reportes')
@login_required
@socio_admin_required
def reportes():
    estudiantes = supabase.table('estudiantes').select('*').eq('activo', True).order('apellidos').execute()
    datos = []
    tc = tp = th = 0
    for e in (estudiantes.data or []):
        ses = supabase.table('sesiones').select('*').eq('estudiante_id', e['id']).eq('estado', 'Realizado').execute()
        pag = supabase.table('pagos').select('*').eq('estudiante_id', e['id']).execute()
        asignaturas = {}
        horas = 0
        for s in (ses.data or []):
            asig = s.get('asignatura') or s.get('tema_terapia') or 'Sin registro'
            if asig not in asignaturas: asignaturas[asig] = {'horas': 0, 'fechas': []}
            asignaturas[asig]['horas'] += s.get('horas', 0) or 0
            asignaturas[asig]['fechas'].append(s['fecha'])
            horas += s.get('horas', 0) or 0
        cobrar = sum(s.get('valor_total', 0) or 0 for s in (ses.data or []))
        pagado = sum(p.get('monto', 0) or 0 for p in (pag.data or []))
        tc += cobrar; tp += pagado; th += horas
        if cobrar > 0 or pagado > 0 or horas > 0:
            datos.append({'id': e['id'], 'estudiante': f"{e['apellidos']} {e['nombres']}",
                         'nivel': e.get('nivel_curso', ''), 'procedencia': e.get('procedencia', ''),
                         'asignaturas': asignaturas, 'total_horas': horas,
                         'cobrar': cobrar, 'pagado': pagado, 'saldo': cobrar - pagado})
    return render_template('reportes.html', datos=datos, total_cobrar=tc, total_pagado=tp, total_horas=th)

# ============================================
# ESTUDIANTES, PADRES, USUARIOS
# ============================================
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
        if accion == 'aprobar': supabase.table('usuarios').update({'activo': True}).eq('id', uid).execute()
        elif accion == 'rechazar': supabase.table('usuarios').delete().eq('id', uid).execute()
        elif accion == 'crear':
            supabase.table('usuarios').insert({
                'nombre': request.form['nombre'], 'email': request.form['email'],
                'password_hash': request.form['password'], 'rol': request.form['rol'], 'activo': True
            }).execute()
        return redirect(url_for('gestion_usuarios'))
    usuarios = supabase.table('usuarios').select('*').order('fecha_registro', desc=True).execute()
    return render_template('usuarios.html', usuarios=usuarios.data or [])

# ============================================
# APIs
# ============================================
@app.route('/api/estudiante/<int:id>')
@login_required
def api_estudiante(id):
    ses = supabase.table('sesiones').select('*').eq('estudiante_id', id).eq('estado', 'Realizado').execute()
    pag = supabase.table('pagos').select('*').eq('estudiante_id', id).execute()
    return jsonify({
        'cobrar': sum(s.get('valor_total', 0) or 0 for s in (ses.data or [])),
        'pagado': sum(p.get('monto', 0) or 0 for p in (pag.data or [])),
        'sesiones': [{'id': s['id'], 'fecha': s['fecha'], 'tipo': s['tipo_sesion'], 'asignatura': s.get('asignatura', ''), 'valor': s.get('valor_total', 0)} for s in (ses.data or [])],
        'pagos': [{'fecha': p['fecha_pago'], 'monto': p['monto']} for p in (pag.data or [])]
    })

@app.route('/api/estudiantes')
@login_required
def api_estudiantes():
    est = supabase.table('estudiantes').select('*').eq('activo', True).order('apellidos').execute()
    return jsonify([{'id': e['id'], 'nombre': f"{e['apellidos']} {e['nombres']}"} for e in (est.data or [])])

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)