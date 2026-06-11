import os
from supabase import create_client, Client

# Credenciales por variable de entorno (Render → Environment). Los valores de
# respaldo mantienen el funcionamiento actual, pero lo recomendado es definir
# SUPABASE_URL y SUPABASE_KEY en el entorno y rotar la clave del proyecto.
SUPABASE_URL = os.environ.get('SUPABASE_URL') or "https://naubddczohedvtywmmmy.supabase.co"
SUPABASE_KEY = os.environ.get('SUPABASE_KEY') or "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5hdWJkZGN6b2hlZHZ0eXdtbW15Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzc2ODc3NTMsImV4cCI6MjA5MzI2Mzc1M30.wWaCU5YvJdFKDL_dDObPOHCUylevNMVk_hCXuEtOEk8"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
