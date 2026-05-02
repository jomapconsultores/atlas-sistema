from werkzeug.security import check_password_hash
from supabase_client import supabase

class Usuario:
    def __init__(self):
        self.id = None
        self.nombre = None
        self.email = None
        self.password_hash = None
        self.rol = None
        self.activo = True
    
    @staticmethod
    def get_by_id(user_id):
        result = supabase.table('usuarios').select('*').eq('id', user_id).execute()
        if result.data:
            data = result.data[0]
            user = Usuario()
            user.id = data['id']
            user.nombre = data['nombre']
            user.email = data['email']
            user.password_hash = data['password_hash']
            user.rol = data['rol']
            user.activo = data.get('activo', True)
            return user
        return None
    
    def is_authenticated(self):
        return True
    def is_active(self):
        return self.activo
    def is_anonymous(self):
        return False
    def get_id(self):
        return str(self.id)

def check_password(password_hash, password):
    if password_hash == password:
        return True
    try:
        return check_password_hash(password_hash, password)
    except:
        return False