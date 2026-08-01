/* ------------------------------------------------------------
 * Desarrollado por Marco Antonio Posligua San Martín
 * ------------------------------------------------------------ */

/* Service worker de Atlas.
 *
 * Hace que Atlas se instale y se abra como una aplicación en Android y en
 * iPhone, y le da una pantalla propia cuando no hay conexión.
 *
 * ── Por qué ya NO se guarda el HTML ──────────────────────────────────────
 * La versión anterior guardaba en el disco del teléfono TODA página que se
 * visitara, incluidas las de dinero: pagos, gastos, liquidación, reportes. Esa
 * copia sobrevivía al cierre de sesión, así que en un equipo compartido la
 * siguiente persona podía ver, sin conexión, las pantallas de la anterior.
 * Tampoco comprobaba que la respuesta fuese correcta: una redirección al login
 * o un error del servidor se guardaban igual y luego se servían como si fueran
 * la página buena.
 *
 * Ahora el HTML no se guarda nunca. Se guardan solo los archivos estáticos
 * —imágenes, hojas de estilo, guiones—, que no dicen nada de nadie. Sin
 * conexión se muestra una pantalla que lo explica, en vez de datos viejos que
 * podrían llevar a decidir sobre cifras que ya cambiaron.
 */

const VERSION = 'atlas-v4';
const CACHE_ESTATICOS = `${VERSION}-estaticos`;
const OFFLINE = '/static/offline.html';

/* Lo mínimo para que la pantalla de "sin conexión" se vea bien aunque el
   teléfono esté incomunicado desde el primer momento. */
const ARMAZON = [
  OFFLINE,
  '/static/img/icon-192.png',
  '/static/img/logo_atlas.png',
];

/* Extensiones que sí conviene guardar: nada de esto contiene datos de nadie. */
const ESTATICO = /\.(?:css|js|mjs|png|jpe?g|gif|svg|webp|avif|ico|woff2?|ttf|otf)$/i;

/* Rutas que jamás deben tocarse: sesión, datos y cierre de sesión. */
const NUNCA = ['/api/', '/logout', '/login'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_ESTATICOS)
      // Uno a uno: si un archivo falta, no debe impedir la instalación entera.
      .then((c) => Promise.all(ARMAZON.map((u) => c.add(u).catch(() => null))))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((claves) => Promise.all(
        // Se borran las cachés de versiones anteriores, incluida `atlas-v3`,
        // que es donde quedó el HTML autenticado de la versión vieja.
        claves.filter((k) => !k.startsWith(VERSION)).map((k) => caches.delete(k)),
      ))
      .then(() => self.clients.claim()),
  );
});

/* La página puede pedir dos cosas: activar ya la versión nueva, o vaciar todo
   al cerrar sesión. */
self.addEventListener('message', (event) => {
  const tipo = event.data && event.data.tipo;
  if (tipo === 'ACTIVAR_YA') {
    self.skipWaiting();
  } else if (tipo === 'LIMPIAR') {
    event.waitUntil(caches.keys().then((ks) => Promise.all(ks.map((k) => caches.delete(k)))));
  }
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (NUNCA.some((p) => url.pathname.startsWith(p))) return;

  const esNavegacion = req.mode === 'navigate'
    || (req.headers.get('accept') || '').includes('text/html');

  /* Navegación: siempre a la red. Si no hay, la pantalla de sin conexión.
     No se guarda ni se sirve HTML desde la caché: ver la nota de arriba. */
  if (esNavegacion) {
    event.respondWith(
      fetch(req).catch(() => caches.match(OFFLINE)),
    );
    return;
  }

  /* Estáticos: primero la caché, que es donde esto rinde de verdad. */
  if (ESTATICO.test(url.pathname)) {
    event.respondWith(
      caches.match(req).then((cacheado) => {
        if (cacheado) return cacheado;
        return fetch(req).then((res) => {
          // Solo se guarda lo que llegó bien. Guardar un 404 o un 500 dejaba
          // el error pegado hasta el siguiente cambio de versión.
          if (res.ok && res.type === 'basic') {
            const copia = res.clone();
            caches.open(CACHE_ESTATICOS).then((c) => c.put(req, copia));
          }
          return res;
        });
      }),
    );
  }
  /* Lo demás (peticiones de datos, descargas) va directo a la red, sin tocar. */
});
