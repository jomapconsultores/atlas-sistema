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
        
        fecha = datos.get('fecha', '')
        h_ini = datos.get('hora_inicio', '')[:5]
        h_fin = datos.get('hora_fin', '')[:5]
        
        # Verificar si ya existe un evento similar
        existing = service.events().list(
            calendarId='atlas.cenest@gmail.com',
            timeMin=f"{fecha}T00:00:00-05:00",
            timeMax=f"{fecha}T23:59:59-05:00",
            q=datos.get('asignatura', '')
        ).execute()
        
        for ev in existing.get('items', []):
            start = ev['start'].get('dateTime', '')
            end = ev['end'].get('dateTime', '')
            if h_ini in start and h_fin in end:
                print(f'⚠️ Ya existe: {ev.get("id")}')
                return ev['id']
        
        # Crear nuevo evento
        summary = f"🔑 {datos.get('encargado_apertura', 'ATLAS')} | 📚 {datos.get('asignatura', 'Sesión')}"
        description = f"👨‍🎓 Estudiante: {datos.get('estudiantes', '')}\n👨‍🏫 Profesor: {datos.get('profesor', '')}\n🕐 {h_ini} - {h_fin}"
        
        nuevo_evento = {
            'summary': summary,
            'description': description,
            'start': {
                'dateTime': f"{fecha}T{h_ini}:00-05:00",
                'timeZone': 'America/Guayaquil',
            },
            'end': {
                'dateTime': f"{fecha}T{h_fin}:00-05:00",
                'timeZone': 'America/Guayaquil',
            },
        }
        
        event = service.events().insert(
            calendarId='atlas.cenest@gmail.com',
            body=nuevo_evento
        ).execute()
        print(f'✅ Google Calendar: {event.get("id")}')
        return event['id']
    except Exception as e:
        print(f'⚠️ Google Calendar: {e}')
        return None

def eliminar_evento_calendar(evento_id):
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
        print('✅ Eliminado de Google Calendar')
        return True
    except Exception as e:
        print(f'⚠️ Error al eliminar: {e}')
        return False