/* ------------------------------------------------------------
 * Desarrollado por Marco Antonio Posligua San Martín
 * ------------------------------------------------------------ */

// Empaquetado móvil de Atlas.
//
// La aplicación ya es una web instalable (PWA). El contenedor Capacitor existe
// para poder publicarla en Google Play y App Store, que exigen un paquete
// firmado: la app nativa abre la MISMA aplicación desplegada, de modo que no hay
// dos versiones que mantener y una corrección en el servidor llega al teléfono
// sin volver a publicar en la tienda.
//
// El destino es el despliegue en Coolify: https://atlas.pensamiento-libre.org
// Queda fijado aquí para que el paquete apunte a producción aunque el
// repositorio no tenga configurada la variable APP_URL. Para compilar contra
// otro destino (una prueba, un dominio nuevo) basta con definirla:
//   set APP_URL=https://otro.ejemplo.com  (Windows)
//   APP_URL=https://otro.ejemplo.com npm run apk:release

import type { CapacitorConfig } from '@capacitor/cli';

const APP_URL = process.env.APP_URL || 'https://atlas.pensamiento-libre.org';

const config: CapacitorConfig = {
  appId: 'ec.map.atlas',
  appName: 'Atlas',
  webDir: 'www',
  // El contenedor abre la MISMA aplicación desplegada, no una copia empaquetada.
  server: {
    url: APP_URL,
    cleartext: false,
    androidScheme: 'https',
    // Qué se ve cuando el WebView NO consigue abrir esa dirección. Sin esto la
    // aplicación se quedaba en blanco —sin mensaje y sin reintento— y era
    // imposible distinguir «no hay internet» de «el servidor está caído» o de
    // «la aplicación está rota». Pasa más de lo que parece: basta un wifi con
    // portal cautivo, o abrir la app mientras se está publicando una versión.
    errorPath: 'error.html',
  },
  android: {
    // El WebView de Android no debe permitir contenido mixto.
    allowMixedContent: false,
    // La depuración se enciende a propósito para diagnosticar, nunca en el
    // paquete que se publica. Con esto en falso siempre, una pantalla en blanco
    // no se podía investigar: Chrome no puede inspeccionar el WebView y no hay
    // otra forma de ver el error. Para compilar un paquete que sí se pueda
    // mirar:  set CAP_DEBUG=1  (Windows)  antes de generar el APK.
    webContentsDebuggingEnabled: process.env.CAP_DEBUG === '1',
  },
  ios: {
    contentInset: 'always',
  },
  plugins: {
    StatusBar: { style: 'DARK', backgroundColor: '#1a73e8' },
  },
};

export default config;
