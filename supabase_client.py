# ------------------------------------------------------------
# Desarrollado por Marco Antonio Posligua San Martín
# ------------------------------------------------------------
import os
from supabase import create_client, Client

# Credenciales siempre por variable de entorno. Sin fallback hardcodeado: la
# clave anon de este proyecto quedó expuesta en el historial de git y debe
# rotarse en el dashboard de Supabase; un fallback en el código volvería a
# comprometerla en el próximo commit.
SUPABASE_URL = os.environ['SUPABASE_URL']
SUPABASE_KEY = os.environ['SUPABASE_KEY']

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
