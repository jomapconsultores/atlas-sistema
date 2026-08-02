# ------------------------------------------------------------
# Desarrollado por Marco Antonio Posligua San Martín
# ------------------------------------------------------------
import os
from datetime import timedelta


class Config:
    # Clave de firma de sesiones. Debe venir siempre de la variable de entorno
    # SECRET_KEY. Sin fallback: una clave hardcodeada en el código permitiría
    # forjar cookies de sesión válidas para cualquier usuario si el env var
    # falta en algún despliegue.
    SECRET_KEY = os.environ['SECRET_KEY']

    # Cookies de sesión endurecidas: solo HTTPS, inaccesibles desde JS y con
    # SameSite (mitiga robo de sesión y CSRF básico). Para desarrollo local
    # por http: set FLASK_INSECURE_COOKIES=1
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = os.environ.get('FLASK_INSECURE_COOKIES') != '1'
    SESSION_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = os.environ.get('FLASK_INSECURE_COOKIES') != '1'

    # ── Cierre de sesión por inactividad: 20 minutos ──────────────────────
    # Hasta ahora el único corte era un temporizador de JavaScript, y eso no
    # cierra nada: la cookie de sesión no llevaba caducidad, así que bastaba
    # cerrar la pestaña y volver a abrirla para seguir dentro. Peor aún, Chrome
    # y Edge la restauran solos con «continuar donde lo dejaste», sin que nadie
    # lo intente siquiera.
    #
    # Flask firma la cookie con una marca de tiempo y, al leerla, la rechaza si
    # supera PERMANENT_SESSION_LIFETIME. Ese rechazo ocurre en el SERVIDOR: no
    # se puede evadir desde el navegador.
    #
    # Para que la ventana sea DESLIZANTE (que cuente inactividad y no tiempo
    # desde el ingreso) hacen falta las tres cosas juntas:
    #   1. este plazo,
    #   2. session.permanent = True  -> lo pone el before_request de app.py,
    #   3. SESSION_REFRESH_EACH_REQUEST = True -> reemite la cookie en cada
    #      petición, renovando la marca de tiempo.
    # Con solo la primera, la sesión moriría 20 minutos después de entrar
    # aunque el usuario estuviera trabajando sin parar.
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=20)
    SESSION_REFRESH_EACH_REQUEST = True

    # El "recuérdame" de flask_login crea una cookie aparte que revive la sesión
    # saltándose lo anterior. Se acota al mismo plazo para que no sea una puerta
    # trasera al cierre por inactividad.
    REMEMBER_COOKIE_DURATION = timedelta(minutes=20)

    # Límite de tamaño de request/archivo subido (estados de cuenta XLSX/PDF).
    # Sin esto, un archivo muy pesado (o mal intencionado) podía agotar la
    # memoria del proceso y tumbar la app para todos los usuarios.
    MAX_CONTENT_LENGTH = 15 * 1024 * 1024  # 15 MB
