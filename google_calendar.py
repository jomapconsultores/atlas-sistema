import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar']

def get_service_account_info():
    env_creds = os.environ.get('GOOGLE_SERVICE_ACCOUNT', '')
    if env_creds:
        return json.loads(env_creds)
    if os.path.exists('service-account.json'):
        with open('service-account.json', 'r') as f:
            return json.load(f)
    return None

def get_calendar_service():
    info = get_service_account_info()
    if not info:
        return None
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build('calendar', 'v3', credentials=creds)

def crear_evento_calendar(datos):
    try:
        service = get_calendar_service()
        if not service:
            return None
        evento = {
            'summary': f"🔑 {datos.get('encargado_apertura', '')} | 📚 {datos.get('asignatura', 'Sesión')}",
            'description': (
                f"👨‍🎓 Estudiante: {datos.get('estudiantes', '')}\n"
                f"👨‍🏫 Profesor: {datos.get('profesor', '')}\n"
                f"🕐 {datos['hora_inicio']} - {datos['hora_fin']}"
            ),
            'start': {
                'dateTime': f"{datos['fecha']}T{datos['hora_inicio']}:00",
                'timeZone': 'America/Guayaquil',
            },
            'end': {
                'dateTime': f"{datos['fecha']}T{datos['hora_fin']}:00",
                'timeZone': 'America/Guayaquil',
            },
        }
        event = service.events().insert(
            calendarId='atlas.cenest@gmail.com',
            body=evento
        ).execute()
        print('✅ Google Calendar OK')
        return event['id']
    except Exception as e:
        print(f'⚠️ Google Calendar: {e}')
def eliminar_evento_calendar(evento_id):
    """Elimina un evento de Google Calendar"""
    if not evento_id:
        return False
    try:
        service = get_calendar_service()
        if not service:
            return False
        service.events().delete(
            calendarId='atlas.cenest@gmail.com',
            eventId=evento_id
        ).execute()
        print('✅ Evento eliminado de Google Calendar')
        return True
    except Exception as e:
        print(f'⚠️ Error al eliminar de Google Calendar: {e}')
        return False
        return None