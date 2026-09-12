# Atlas — aplicación móvil (Android e iOS)

Desarrollado por Marco Antonio Posligua San Martín.

## Qué es esto

Atlas ya funciona como **PWA**: desde el navegador del teléfono se instala
en la pantalla de inicio y se abre como una aplicación, sin pasar por ninguna
tienda. Eso cubre Android e iPhone y es la vía recomendada para el uso interno.

Esta carpeta añade lo que la PWA no puede dar: un **paquete firmado** (`.apk` /
`.aab` para Google Play, `.ipa` para App Store). El contenedor —Capacitor— abre
la misma aplicación desplegada, así que **no hay dos versiones que mantener**:
una corrección en el servidor llega al teléfono sin volver a publicar.

## Requisitos

| | Android | iOS |
|---|---|---|
| Sistema | Windows, macOS o Linux | **solo macOS** |
| Herramientas | JDK 17+, Android SDK (API 34+) | Xcode 15+ |
| Cuenta | Google Play Console (25 USD, pago único) | Apple Developer (99 USD/año) |

> iOS **no se puede compilar desde Windows**: Apple solo permite firmar con
> Xcode sobre macOS. El flujo de CI incluido usa un runner `macos-latest` de
> GitHub Actions, que sí sirve para esto sin tener un Mac propio.

## Si la aplicación abre en blanco

La aplicación no lleva Atlas dentro: abre el servidor. Así que una pantalla en
blanco casi nunca es un fallo del paquete, sino que el WebView no consiguió
cargar https://atlas.pensamiento-libre.org.

Desde 2026 eso ya **no se ve como una pantalla en blanco**: `server.errorPath`
en `capacitor.config.ts` hace que aparezca `www/error.html`, que dice qué pasó,
a qué dirección intentó conectarse y deja reintentar. Si alguien reporta una
pantalla blanca *sin ese mensaje*, está usando un paquete anterior a este
cambio: hay que reinstalarle el APK.

Para ver la causa real hace falta poder inspeccionar el WebView, y eso viene
apagado a propósito en los paquetes que se publican. Se enciende al compilar:

```bash
# Windows (PowerShell):
$env:CAP_DEBUG = "1"
npm run apk:debug:win
```

Con ese APK instalado, se conecta el teléfono por USB y se abre `chrome://inspect`
en el Chrome del computador: ahí sale la consola del WebView con el error exacto.
Sin esto no hay forma de averiguarlo, que es justamente lo que hacía que una
pantalla en blanco no se pudiera diagnosticar.

Comprobaciones rápidas antes de llegar a eso:

| Síntoma | Qué mirar |
|---|---|
| Sale la pantalla de error con «Reintentar» | El servidor o la red. Abre https://atlas.pensamiento-libre.org/version en el navegador del teléfono. |
| Blanco total, sin ningún mensaje | Paquete viejo (sin `errorPath`), o el WebView del sistema está desactualizado. |
| Abre y se cierra sola | Compila con `CAP_DEBUG=1` y mira `adb logcat`. |

## Construir el APK localmente

La app abre el despliegue en Coolify, **https://atlas.pensamiento-libre.org**, que
viene fijado en `capacitor.config.ts`. No hace falta configurar nada para
compilar contra producción:

```bash
cd movil
npm install

# Windows (PowerShell):
npm run cap:android
npm run apk:debug:win

# macOS / Linux:
npm run cap:android
npm run apk:debug
```

Para compilar contra otro destino —una prueba, un dominio nuevo— define
`APP_URL` antes de `cap:android`: `$env:APP_URL = "https://otro.ejemplo.com"`
en PowerShell, `export APP_URL="https://otro.ejemplo.com"` en macOS o Linux.

El APK queda en `android/app/build/outputs/apk/debug/app-debug.apk`.

Para el APK firmado de release hace falta un almacén de claves:

```bash
# OJO: fuera del repositorio. Si lo creas dentro de movil/ acabará en la
# imagen de Docker (los Dockerfile copian todo el contexto) aunque .gitignore
# lo mantenga fuera de git.
mkdir -p ~/claves
keytool -genkey -v -keystore ~/claves/atlas.keystore -alias atlas \
        -keyalg RSA -keysize 2048 -validity 10000
```

Quien tenga ese archivo puede publicar actualizaciones en tu nombre. Y si lo
pierdes, la app ya publicada en Google Play **no se puede volver a actualizar
nunca**: guárdalo junto con sus contraseñas en sitio seguro y con copia.

## Construir desde GitHub Actions

Los flujos `.github/workflows/movil-android-atlas.yml` y
`movil-ios-atlas.yml` compilan en la nube. Configura en *Settings → Secrets and variables → Actions*:

| Nombre | Tipo | Para qué |
|---|---|---|
| `APP_URL` | variable *(opcional)* | otro destino en vez del de Coolify, que ya viene fijado |
| `ANDROID_KEYSTORE_BASE64` | secreto | `base64 -w0 ~/claves/atlas.keystore` |
| `ANDROID_KEYSTORE_PASSWORD` | secreto | clave del almacén |
| `ANDROID_KEY_ALIAS` | secreto | alias de la clave |
| `ANDROID_KEY_PASSWORD` | secreto | clave del alias |

Para iOS, además: `IOS_CERTIFICATE_BASE64`, `IOS_CERTIFICATE_PASSWORD`,
`IOS_PROVISIONING_PROFILE_BASE64` y `IOS_TEAM_ID`. Sin ellos el flujo de iOS
compila sin firmar (sirve para verificar que el proyecto está sano, no para
distribuir).

## Iconos

Coloca un PNG cuadrado de 1024×1024 en `assets/icon.png` (y opcionalmente
`assets/splash.png` de 2732×2732) y ejecuta:

```bash
npm run iconos
```

Genera todos los tamaños que piden Android e iOS.
