import os
import json
import pickle
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar']

def get_calendar_service():
    creds = None
    
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Intentar cargar de variable de entorno o archivo
            creds_json = os.environ.get('GOOGLE_CREDENTIALS', '')
            if creds_json:
                creds_dict = json.loads(creds_json)
                flow = InstalledAppFlow.from_client_config(creds_dict, SCOPES)
            elif os.path.exists('credentials.json'):
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            else:
                print('⚠️ Google Calendar no configurado')
                return None
            
            creds = flow.run_local_server(port=0)
        
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    
    return build('calendar', 'v3', credentials=creds)

def crear_evento_calendar(datos):
    try:
        service = get_calendar_service()
        if not service:
            return None
        
        evento = {
            'summary': f"{datos.get('asignatura', 'Sesión')} - {datos.get('profesor', '')}",
            'description': (
                f"📖 {datos.get('asignatura', '')}\n"
                f"👨‍🏫 Profesor: {datos.get('profesor', '')}\n"
                f"👨‍🎓 Estudiantes: {datos.get('estudiantes', '')}\n"
                f"🔑 Encargado: {datos.get('encargado_apertura', '')}"
            ),
            'start': {
                'dateTime': f"{datos['fecha']}T{datos['hora_inicio']}:00",
                'timeZone': 'America/Guayaquil',
            },
            'end': {
                'dateTime': f"{datos['fecha']}T{datos['hora_fin']}:00",
                'timeZone': 'America/Guayaquil',
            },
            'attendees': [{'email': 'atlas.cenest@gmail.com'}],
        }
        
        event = service.events().insert(
            calendarId='atlas.cenest@gmail.com',
            body=evento,
            sendUpdates='all'
        ).execute()
        
        print(f'✅ Evento creado en Google Calendar')
        return event['id']
    except Exception as e:
        print(f'⚠️ Error Google Calendar: {e}')
        return None