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

  window.ATLAS_FERIADOS = {
    getFeriado: getFeriado,
    pintarNota: pintarNota,
    attach: attach,
    resumen: resumen
  };
})();
