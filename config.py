import os


class Config:
    # Clave de firma de sesiones. EN PRODUCCIÓN debe venir de la variable de
    # entorno SECRET_KEY (Render → Environment). El valor de respaldo solo
    # existe para no romper el arranque local; cualquier clave escrita en el
    # código se considera comprometida.
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'atlas-dev-cambiar-en-render-no-usar-en-produccion'

    # Cookies de sesión endurecidas: solo HTTPS, inaccesibles desde JS y con
    # SameSite (mitiga robo de sesión y CSRF básico). Para desarrollo local
    # por http: set FLASK_INSECURE_COOKIES=1
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = os.environ.get('FLASK_INSECURE_COOKIES') != '1'
    SESSION_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = os.environ.get('FLASK_INSECURE_COOKIES') != '1'

    SQLALCHEMY_DATABASE_URI = 'https://naubddczohedvtywmmmy.supabase.co'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
