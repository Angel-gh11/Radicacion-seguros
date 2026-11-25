# config.py
# Lee las claves del archivo .env y crea las conexiones a Supabase y a Gemini.
# Todos los demás archivos importan las conexiones desde aquí.

import os

from dotenv import load_dotenv
from google import genai
from supabase import create_client

load_dotenv()  # lee el archivo .env

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODELO_IA = os.getenv("MODELO_IA", "gemini-3.8-flash")
MODELO_IA_RESPALDO = os.getenv("MODELO_IA_RESPALDO", "gemini-3.5-flash-lite")
CLAVE_SESION = os.getenv("CLAVE_SESION")
TOKEN_TAREAS = os.getenv("TOKEN_TAREAS")    # protege la tarea automática
URL_AVISOS = os.getenv("URL_AVISOS")        # webhook de Discord para las alertas (opcional)

# Si falta alguna clave obligatoria, el programa se detiene con un mensaje claro
variables = {
    "SUPABASE_URL": SUPABASE_URL,
    "SUPABASE_KEY": SUPABASE_KEY,
    "GEMINI_API_KEY": GEMINI_API_KEY,
    "CLAVE_SESION": CLAVE_SESION,
    "TOKEN_TAREAS": TOKEN_TAREAS,
}
faltantes = [nombre for nombre, valor in variables.items() if not valor]
if faltantes:
    raise RuntimeError(f"Faltan estas variables en el archivo .env: {faltantes}")

# Conexiones
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
cliente_ia = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options={"timeout": 60_000},  # máximo 60 segundos esperando a la IA
)