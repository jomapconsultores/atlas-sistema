import os


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

    # Límite de tamaño de request/archivo subido (estados de cuenta XLSX/PDF).
    # Sin esto, un archivo muy pesado (o mal intencionado) podía agotar la
    # memoria del proceso y tumbar la app para todos los usuarios.
    MAX_CONTENT_LENGTH = 15 * 1024 * 1024  # 15 MB
