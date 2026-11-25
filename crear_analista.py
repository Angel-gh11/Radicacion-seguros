# crear_analista.py
# Crea (o actualiza) un usuario del panel. Uso: python crear_analista.py

import getpass

import bcrypt

from config import supabase

correo = input("Correo del analista: ").strip().lower()
nombre = input("Nombre completo: ").strip()
contrasena = getpass.getpass("Contraseña (mínimo 10 caracteres, no se ve al escribir): ")

if len(contrasena) < 10:
    raise SystemExit("La contraseña debe tener al menos 10 caracteres.")

cifrada = bcrypt.hashpw(contrasena.encode(), bcrypt.gensalt()).decode()
supabase.table("analistas").upsert(
    {"correo": correo, "nombre": nombre, "contrasena_cifrada": cifrada, "activo": True},
    on_conflict="correo",
).execute()
print(f"Listo: {correo} ya puede entrar al panel.")