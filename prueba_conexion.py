# prueba_conexion.py
# Prueba rápida: confirma que la base de datos y la IA responden.

from config import supabase, cliente_ia, MODELO_IA

print("1. Probando Supabase...")
resultado = supabase.table("requisitos").select("*").execute()
print(f"   OK: la tabla 'requisitos' tiene {len(resultado.data)} filas")

print("2. Probando Gemini...")
respuesta = cliente_ia.models.generate_content(
    model=MODELO_IA,
    contents="Responde solo con esta palabra: funcionando",
)
print(f"   OK: Gemini respondió: {respuesta.text}")