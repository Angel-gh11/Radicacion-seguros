# radicacion.py
# Recibe una radicación: valida datos y archivos, crea el caso (o usa el que
# ya está abierto), guarda los documentos sin duplicarlos y registra cada paso.

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

from postgrest.exceptions import APIError

from config import supabase

ZONA_COLOMBIA = timezone(timedelta(hours=-5))
TAMANO_MAXIMO = 10 * 1024 * 1024  # 10 MB
MAXIMO_ARCHIVOS = 15

# Se revisan los primeros bytes del archivo y no solo la extensión,
# porque cualquiera puede renombrar un archivo peligroso a "cedula.pdf".
FIRMAS = {
    "pdf": b"%PDF",
    "jpg": b"\xff\xd8\xff",
    "png": b"\x89PNG",
}
TIPOS_MIME = {"pdf": "application/pdf", "jpg": "image/jpeg", "png": "image/png"}


class ErrorValidacion(Exception):
    """Error que se le muestra al beneficiario con un mensaje claro."""


def ahora():
    return datetime.now(ZONA_COLOMBIA)


def registrar_evento(caso_id, tipo_evento, responsable, detalle=None):
    """Guarda en la historia del caso qué pasó, quién lo hizo y cuándo."""
    supabase.table("eventos").insert({
        "caso_id": caso_id,
        "tipo_evento": tipo_evento,
        "responsable": responsable,
        "detalle": detalle or {},
    }).execute()


def validar_datos(datos):
    obligatorios = {
        "nombre_beneficiario": "tu nombre",
        "documento_beneficiario": "tu número de documento",
        "correo_beneficiario": "tu correo",
        "nombre_asegurado": "el nombre del asegurado",
        "documento_asegurado": "el documento del asegurado",
        "relato": "qué pasó",
    }
    for campo, etiqueta in obligatorios.items():
        if not datos.get(campo):
            raise ErrorValidacion(f"Nos falta {etiqueta}.")
    for campo in ("documento_beneficiario", "documento_asegurado"):
        if not re.fullmatch(r"\d{5,12}", datos[campo]):
            raise ErrorValidacion("Los números de documento deben tener solo números (entre 5 y 12).")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", datos["correo_beneficiario"]):
        raise ErrorValidacion("El correo no parece válido. ¿Puedes revisarlo?")
    if len(datos["relato"]) < 20:
        raise ErrorValidacion("Cuéntanos un poco más de lo que pasó (mínimo 20 caracteres).")
    if len(datos["relato"]) > 3000:
        raise ErrorValidacion("El relato es muy largo. Resúmelo en máximo 3000 caracteres.")


def validar_archivos(archivos):
    """Recibe una lista de (nombre, contenido) y devuelve (nombre, contenido, extension)."""
    archivos = [(nombre, contenido) for nombre, contenido in archivos if contenido]
    if not archivos:
        raise ErrorValidacion("Adjunta al menos un documento.")
    if len(archivos) > MAXIMO_ARCHIVOS:
        raise ErrorValidacion(f"Puedes adjuntar máximo {MAXIMO_ARCHIVOS} archivos a la vez.")
    validos = []
    for nombre, contenido in archivos:
        if len(contenido) > TAMANO_MAXIMO:
            raise ErrorValidacion(f"El archivo «{nombre}» pesa más de 10 MB.")
        extension = next((ext for ext, firma in FIRMAS.items() if contenido.startswith(firma)), None)
        if extension is None:
            raise ErrorValidacion(f"El archivo «{nombre}» no es un PDF, JPG o PNG válido.")
        validos.append((nombre, contenido, extension))
    return validos


def buscar_caso_abierto(documento_asegurado, documento_beneficiario):
    resultado = (
        supabase.table("casos").select("*")
        .eq("documento_asegurado", documento_asegurado)
        .eq("documento_beneficiario", documento_beneficiario)
        .in_("estado", ["incompleto", "completo"])
        .limit(1).execute()
    )
    return resultado.data[0] if resultado.data else None


def obtener_o_crear_caso(datos):
    """Si ya hay un caso abierto para el mismo asegurado y beneficiario, lo reutiliza.
    Así un reenvío no crea un expediente nuevo ni reinicia el plazo."""
    existente = buscar_caso_abierto(datos["documento_asegurado"], datos["documento_beneficiario"])
    if existente:
        return existente, False

    fila = dict(datos)
    fila["numero_radicado"] = f"RAD-{ahora():%Y%m%d}-{secrets.token_hex(3).upper()}"
    fila["codigo_seguimiento"] = secrets.token_urlsafe(16)  # código difícil de adivinar
    try:
        resultado = supabase.table("casos").insert(fila).execute()
        return resultado.data[0], True
    except APIError as error:
        # 23505 = la base rechazó un duplicado (dos envíos casi al mismo tiempo)
        if error.code == "23505":
            return buscar_caso_abierto(datos["documento_asegurado"], datos["documento_beneficiario"]), False
        raise


def guardar_documento(caso_id, nombre, contenido, extension, responsable="beneficiario"):
    """Guarda el archivo solo si no se había recibido antes en este caso."""
    huella = hashlib.sha256(contenido).hexdigest()  # huella única del contenido

    repetido = (
        supabase.table("documentos").select("id")
        .eq("caso_id", caso_id).eq("huella_archivo", huella).execute()
    )
    if repetido.data:
        registrar_evento(caso_id, "documento_repetido", "sistema", {
            "archivo": nombre,
            "mensaje": "Este mismo archivo ya se había recibido; no se guardó otra vez.",
        })
        return None

    ruta = f"{caso_id}/{huella}.{extension}"
    supabase.storage.from_("documentos").upload(
        ruta, contenido, {"content-type": TIPOS_MIME[extension], "upsert": "true"}
    )
    try:
        resultado = supabase.table("documentos").insert({
            "caso_id": caso_id,
            "nombre_archivo": nombre,
            "ubicacion_archivo": ruta,
            "huella_archivo": huella,
        }).execute()
    except APIError as error:
        if error.code == "23505":
            return None
        raise

    documento = resultado.data[0]
    registrar_evento(caso_id, "documento_recibido", responsable, {
        "archivo": nombre, "documento_id": documento["id"],
    })
    return documento


def registrar_radicacion(datos, archivos):
    validar_datos(datos)
    archivos_validos = validar_archivos(archivos)

    caso, es_nuevo = obtener_o_crear_caso(datos)
    if es_nuevo:
        registrar_evento(caso["id"], "radicado", "beneficiario", {
            "canal": "web", "numero_radicado": caso["numero_radicado"],
        })
    else:
        registrar_evento(caso["id"], "radicacion_repetida", "beneficiario", {
            "mensaje": "Llegó otra radicación para un caso abierto. No se creó un caso nuevo ni se reinició el plazo.",
            "relato_nuevo": datos["relato"],
        })

    for nombre, contenido, extension in archivos_validos:
        guardar_documento(caso["id"], nombre, contenido, extension)

    return caso, es_nuevo


def buscar_por_codigo(codigo):
    resultado = supabase.table("casos").select("*").eq("codigo_seguimiento", codigo).limit(1).execute()
    return resultado.data[0] if resultado.data else None


def documentos_del_caso(caso_id):
    # ✏️ CORREGIDO: ahora trae todas las columnas (el motor necesita el estado y el tipo de cada documento)
    resultado = (
        supabase.table("documentos")
        .select("*")
        .eq("caso_id", caso_id).order("fecha_subida").execute()
    )
    return resultado.data