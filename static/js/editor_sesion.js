// Compartido por templates/editar_planificaciones.html y
// templates/editar_planificacion_masiva.html: ambos editan una sesión con
// los MISMOS campos (prefijo id="edit_*"), así que esta lógica de
// horas/valor/feriado vivía duplicada casi carácter por carácter en los dos
// templates. Cualquier corrección de tarifa/redondeo se hace una sola vez acá.
let valorCalculado = 0;

function asignaturaCambio() {
    const s = document.getElementById('edit_asignatura_select');
    document.getElementById('edit_asignatura_nuevo').style.display = s.value === 'NUEVO' ? 'block' : 'none';
    if (s.value === 'NUEVO') document.getElementById('edit_asignatura_nuevo').focus();
}
function profesorCambio() {
    const s = document.getElementById('edit_profesor_select');
    document.getElementById('edit_profesor_nuevo').style.display = s.value === 'NUEVO' ? 'block' : 'none';
    if (s.value === 'NUEVO') document.getElementById('edit_profesor_nuevo').focus();
}
function encargadoCambio() {
    const s = document.getElementById('edit_encargado_select');
    document.getElementById('edit_encargado_nuevo').style.display = s.value === 'NUEVO' ? 'block' : 'none';
    if (s.value === 'NUEVO') document.getElementById('edit_encargado_nuevo').focus();
}
function getAsignatura() {
    const s = document.getElementById('edit_asignatura_select');
    return s.value === 'NUEVO' ? document.getElementById('edit_asignatura_nuevo').value : s.value;
}
function getProfesor() {
    const s = document.getElementById('edit_profesor_select');
    return s.value === 'NUEVO' ? document.getElementById('edit_profesor_nuevo').value : s.value;
}
function getEncargado() {
    const s = document.getElementById('edit_encargado_select');
    return s.value === 'NUEVO' ? document.getElementById('edit_encargado_nuevo').value : s.value;
}
function calcularHoras() {
    const hI = document.getElementById('edit_hora_inicio').value, hF = document.getElementById('edit_hora_fin').value;
    if (!hI || !hF) return 0;
    const [h1, m1] = hI.split(':').map(Number), [h2, m2] = hF.split(':').map(Number);
    return Math.round(((h2 + m2 / 60) - (h1 + m1 / 60)) * 100) / 100;
}
function actualizarDuracionEdit() {
    const b = document.getElementById('edit_duracion'),
        iI = document.getElementById('edit_hora_inicio'), iF = document.getElementById('edit_hora_fin'),
        hI = iI.value, hF = iF.value;
    iI.classList.remove('input-error'); iF.classList.remove('input-error');
    if (!hI || !hF) { b.style.background = '#e2e8f0'; b.style.color = '#64748b'; b.textContent = '⏱️ Sin horario'; return 0; }
    const h = calcularHoras();
    if (h < 0) { b.style.background = '#fee2e2'; b.style.color = '#991b1b'; b.textContent = `⛔ Horario en retroceso (${h.toFixed(2)} h)`; iI.classList.add('input-error'); iF.classList.add('input-error'); return h; }
    if (h === 0) { b.style.background = '#fee2e2'; b.style.color = '#991b1b'; b.textContent = '⛔ Duración 0 horas'; iI.classList.add('input-error'); iF.classList.add('input-error'); return 0; }
    if (h < 0.5) { b.style.background = '#fee2e2'; b.style.color = '#991b1b'; b.textContent = `⛔ Muy corta: ${(h * 60).toFixed(0)} min (mín 30)`; iI.classList.add('input-error'); iF.classList.add('input-error'); return h; }
    b.style.background = '#d1fae5'; b.style.color = '#065f46'; b.textContent = `⏱️ ${h.toFixed(2)} h (${(h * 60).toFixed(0)} min)`;
    return h;
}
function calcularValorTotal() {
    actualizarDuracionEdit();
    const tipo = document.getElementById('edit_tipo_sesion').value, et = tipo === 'terapia' || tipo === 'ambos', horas = calcularHoras();
    if (et) {
        const s = document.getElementById('edit_atencion_psicologica'), o = s.options[s.selectedIndex];
        valorCalculado = o ? parseFloat(o.getAttribute('data-precio')) || 0 : 0;
    } else {
        const ph = parseFloat(document.getElementById('edit_precio_hora').value) || 0;
        valorCalculado = Math.round((horas * ph) * 100) / 100;
    }
    document.getElementById('edit_valor_total').value = valorCalculado;
    document.getElementById('info_valor_total').innerText = horas > 0 ? `(Horas: ${horas} × $${document.getElementById('edit_precio_hora').value || 0})` : '';
    verificarValorTotal();
}
function verificarValorTotal() {
    const va = parseFloat(document.getElementById('edit_valor_total').value) || 0,
        ev = document.getElementById('error_valor_total'), iv = document.getElementById('edit_valor_total');
    if (va === 0 && valorCalculado > 0) {
        ev.style.display = 'block'; iv.classList.add('input-error');
        document.getElementById('edit_valor_total').value = valorCalculado;
    } else if (valorCalculado > 0 && Math.abs(va - valorCalculado) > .01) {
        ev.style.display = 'block'; iv.classList.add('input-warning');
    } else {
        ev.style.display = 'none'; iv.classList.remove('input-warning', 'input-error');
    }
}
function cambioTipoSesion() {
    const t = document.getElementById('edit_tipo_sesion').value;
    document.getElementById('div_atencion_psicologica').style.display = (t === 'terapia' || t === 'ambos') ? 'block' : 'none';
    document.getElementById('div_precio_hora').style.display = (t === 'terapia' || t === 'ambos') ? 'none' : 'block';
    calcularValorTotal();
}
function revisarFeriadoEdit() {
    if (!window.ATLAS_FERIADOS) return;
    ATLAS_FERIADOS.pintarNota(document.getElementById('edit_feriado'), document.getElementById('edit_fecha').value);
}
// Validación de horario compartida por el guardado de ambos templates.
function horarioValidoOAlerta() {
    const h = calcularHoras();
    if (h < 0) { alert('❌ Horario en retroceso: la hora de fin no puede ser anterior al inicio'); return false; }
    if (h === 0) { alert('❌ La duración no puede ser 0 horas'); return false; }
    if (h < 0.5) { alert('❌ Duración muy corta (' + (h * 60).toFixed(0) + ' min). El mínimo es 30 minutos'); return false; }
    return true;
}
// Confirmación de feriado compartida por el guardado de ambos templates.
function feriadoConfirmadoOFalse(fecha) {
    const fer = window.ATLAS_FERIADOS ? ATLAS_FERIADOS.getFeriado(fecha) : null;
    if (fer && !confirm('⚠️ La fecha ' + fecha + ' es ' + fer.etiqueta + '.\n\n¿Deseas planificar igual en este día feriado?')) return false;
    return true;
}
