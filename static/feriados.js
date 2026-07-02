/* ============================================================
   ATLAS · Feriados de Ecuador (nacionales) y Cuenca (locales)
   ------------------------------------------------------------
   Módulo autónomo. Expone window.ATLAS_FERIADOS con:
     - getFeriado('YYYY-MM-DD')  -> {nombre, tipo, ambito, etiqueta} | null
     - attach(inputEl, noteEl)   -> muestra/actualiza una nota bajo la fecha
     - resumen([fechas])         -> lista de {fecha, ...feriado} para confirmar
   El ámbito local es Cuenca (Azuay). Carnaval y Viernes Santo se
   calculan por año a partir de la Pascua (algoritmo de Meeus).
   ============================================================ */
(function () {
  'use strict';

  // Domingo de Pascua del año dado (algoritmo de Meeus/Butcher, gregoriano)
  function domingoPascua(anio) {
    var a = anio % 19;
    var b = Math.floor(anio / 100);
    var c = anio % 100;
    var d = Math.floor(b / 4);
    var e = b % 4;
    var f = Math.floor((b + 8) / 25);
    var g = Math.floor((b - f + 1) / 3);
    var h = (19 * a + b - d - g + 15) % 30;
    var i = Math.floor(c / 4);
    var k = c % 4;
    var l = (32 + 2 * e + 2 * i - h - k) % 7;
    var m = Math.floor((a + 11 * h + 22 * l) / 451);
    var mes = Math.floor((h + l - 7 * m + 114) / 31); // 3=marzo, 4=abril
    var dia = ((h + l - 7 * m + 114) % 31) + 1;
    return new Date(anio, mes - 1, dia);
  }

  function fmt(fecha) {
    var mm = String(fecha.getMonth() + 1).padStart(2, '0');
    var dd = String(fecha.getDate()).padStart(2, '0');
    return mm + '-' + dd;
  }

  function sumarDias(fecha, dias) {
    var f = new Date(fecha.getTime());
    f.setDate(f.getDate() + dias);
    return f;
  }

  // Devuelve un mapa 'MM-DD' -> {nombre, tipo} para el año indicado.
  var cache = {};
  function feriadosDelAnio(anio) {
    if (cache[anio]) return cache[anio];

    var mapa = {
      // ── Nacionales de fecha fija ──
      '01-01': { nombre: 'Año Nuevo', tipo: 'nacional' },
      '05-01': { nombre: 'Día del Trabajo', tipo: 'nacional' },
      '05-24': { nombre: 'Batalla de Pichincha', tipo: 'nacional' },
      '08-10': { nombre: 'Primer Grito de Independencia', tipo: 'nacional' },
      '10-09': { nombre: 'Independencia de Guayaquil', tipo: 'nacional' },
      '11-02': { nombre: 'Día de los Difuntos', tipo: 'nacional' },
      '11-03': { nombre: 'Independencia de Cuenca', tipo: 'nacional' },
      '12-25': { nombre: 'Navidad', tipo: 'nacional' },
      // ── Local de Cuenca ──
      '04-12': { nombre: 'Fundación de Cuenca', tipo: 'local' }
    };

    // ── Nacionales móviles (según Pascua) ──
    var pascua = domingoPascua(anio);
    mapa[fmt(sumarDias(pascua, -48))] = { nombre: 'Carnaval (lunes)', tipo: 'nacional' };
    mapa[fmt(sumarDias(pascua, -47))] = { nombre: 'Carnaval (martes)', tipo: 'nacional' };
    mapa[fmt(sumarDias(pascua, -2))] = { nombre: 'Viernes Santo', tipo: 'nacional' };

    cache[anio] = mapa;
    return mapa;
  }

  // 'YYYY-MM-DD' -> info del feriado o null
  function getFeriado(fechaStr) {
    if (!fechaStr || fechaStr.length < 10) return null;
    var partes = fechaStr.split('-');
    var anio = parseInt(partes[0], 10);
    if (isNaN(anio)) return null;
    var clave = partes[1] + '-' + partes[2];
    var info = feriadosDelAnio(anio)[clave];
    if (!info) return null;
    var esLocal = info.tipo === 'local';
    return {
      nombre: info.nombre,
      tipo: info.tipo, // 'nacional' | 'local'
      ambito: esLocal ? 'Cuenca' : 'Ecuador',
      etiqueta: esLocal
        ? '📍 Feriado local (Cuenca): ' + info.nombre
        : '🎌 Feriado nacional: ' + info.nombre
    };
  }

  // Pinta/limpia una nota debajo del input de fecha.
  function pintarNota(noteEl, fechaStr) {
    if (!noteEl) return null;
    var fer = getFeriado(fechaStr);
    if (!fer) {
      noteEl.style.display = 'none';
      noteEl.textContent = '';
      noteEl.className = 'feriado-nota';
      return null;
    }
    noteEl.textContent = fer.etiqueta;
    noteEl.className = 'feriado-nota ' + (fer.tipo === 'local' ? 'is-local' : 'is-nacional');
    noteEl.style.display = 'block';
    return fer;
  }

  // Conecta un input date con su nota (crea la nota si no se pasa).
  function attach(inputEl, noteEl) {
    if (!inputEl) return;
    if (!noteEl) {
      noteEl = document.createElement('div');
      noteEl.className = 'feriado-nota';
      noteEl.style.display = 'none';
      inputEl.parentNode.appendChild(noteEl);
    }
    var actualizar = function () { pintarNota(noteEl, inputEl.value); };
    inputEl.addEventListener('change', actualizar);
    inputEl.addEventListener('input', actualizar);
    actualizar();
  }

  // Dado un arreglo de 'YYYY-MM-DD', devuelve los que son feriado.
  function resumen(fechas) {
    var res = [];
    (fechas || []).forEach(function (f) {
      var fer = getFeriado(f);
      if (fer) res.push(Object.assign({ fecha: f }, fer));
    });
    return res;
  }

  // 'YYYY-MM-DD' -> Date local (evita corrimientos por zona horaria)
  function parseLocal(str) {
    var p = str.split('-');
    return new Date(parseInt(p[0], 10), parseInt(p[1], 10) - 1, parseInt(p[2], 10));
  }

  var DOW = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb'];
  var MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

  function etiquetaFecha(fechaStr) {
    var f = parseLocal(fechaStr);
    return DOW[f.getDay()] + ' ' + f.getDate() + ' ' + MESES[f.getMonth()] + ' ' + f.getFullYear();
  }

  // Próximos feriados (desde hoy o desde 'desdeStr'), ordenados por fecha.
  function proximos(cantidad, desdeStr) {
    cantidad = cantidad || 6;
    var hoy = desdeStr ? parseLocal(desdeStr) : new Date();
    hoy.setHours(0, 0, 0, 0);
    var anioBase = hoy.getFullYear();
    var lista = [];
    for (var y = anioBase; y <= anioBase + 1; y++) {
      var mapa = feriadosDelAnio(y);
      Object.keys(mapa).forEach(function (mmdd) {
        var f = parseLocal(y + '-' + mmdd);
        if (f.getTime() >= hoy.getTime()) {
          var info = getFeriado(y + '-' + mmdd);
          lista.push({
            fecha: y + '-' + mmdd, _t: f.getTime(),
            fechaTexto: etiquetaFecha(y + '-' + mmdd),
            nombre: info.nombre, tipo: info.tipo, ambito: info.ambito, etiqueta: info.etiqueta
          });
        }
      });
    }
    lista.sort(function (a, b) { return a._t - b._t; });
    return lista.slice(0, cantidad);
  }

  // Pinta un panel con la lista de próximos feriados dentro de containerEl.
  function pintarLista(containerEl, cantidad, desdeStr) {
    if (!containerEl) return;
    var items = proximos(cantidad, desdeStr);
    if (!items.length) { containerEl.innerHTML = ''; return; }
    var filas = items.map(function (it) {
      var chip = it.tipo === 'local'
        ? '<span class="feriado-chip is-local">Local · Cuenca</span>'
        : '<span class="feriado-chip is-nacional">Nacional</span>';
      return '<li class="feriado-item"><span class="feriado-fecha">' + it.fechaTexto +
        '</span><span class="feriado-nombre">' + it.nombre + '</span>' + chip + '</li>';
    }).join('');
    containerEl.innerHTML =
      '<div class="feriado-panel"><div class="feriado-panel-tit">📅 Próximos feriados</div>' +
      '<ul class="feriado-lista">' + filas + '</ul></div>';
  }

  // ── Auto-cableado: input[type=date][data-feriado] recibe su nota sola ──
  function attachAuto(input) {
    if (!input || input._ferWired) return;
    input._ferWired = true;
    var nota = document.createElement('div');
    nota.className = 'feriado-nota';
    nota.style.display = 'none';
    if (input.nextSibling) input.parentNode.insertBefore(nota, input.nextSibling);
    else input.parentNode.appendChild(nota);
    var upd = function () { pintarNota(nota, input.value); };
    input.addEventListener('change', upd);
    input.addEventListener('input', upd);
    upd();
  }

  function autoInit() {
    var sel = 'input[type="date"][data-feriado]';
    document.querySelectorAll(sel).forEach(attachAuto);
    if (!window.MutationObserver || !document.body) return;
    new MutationObserver(function (muts) {
      muts.forEach(function (m) {
        Array.prototype.forEach.call(m.addedNodes || [], function (n) {
          if (n.nodeType !== 1) return;
          if (n.matches && n.matches(sel)) attachAuto(n);
          if (n.querySelectorAll) n.querySelectorAll(sel).forEach(attachAuto);
        });
      });
    }).observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState !== 'loading') autoInit();
  else document.addEventListener('DOMContentLoaded', autoInit);

  window.ATLAS_FERIADOS = {
    getFeriado: getFeriado,
    pintarNota: pintarNota,
    attach: attach,
    attachAuto: attachAuto,
    resumen: resumen,
    proximos: proximos,
    pintarLista: pintarLista
  };
})();
