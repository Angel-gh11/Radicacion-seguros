# panel.py
# Panel interno del analista. Solo entra quien inicia sesión.
# La IA sugiere; aquí la PERSONA confirma el tipo y toma la decisión, y queda registrado quién fue.

import json
import time
import uuid
from urllib.parse import urlencode

import bcrypt
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import motor
import plazos
from config import supabase
from radicacion import registrar_evento

router = APIRouter(prefix="/panel")
plantillas = Jinja2Templates(directory="templates")
plantillas.env.filters["fecha"] = lambda t: plazos.fecha_local(t).strftime("%Y-%m-%d %H:%M") if t else "—"
plantillas.env.filters["json_bonito"] = lambda d: json.dumps(d, ensure_ascii=False, indent=2)

ESTADOS = {"incompleto": "Incompleto", "completo": "Completo", "pagado": "Pagado", "objetado": "Objetado"}
DECISIONES = {"pagar": "pagado", "objetar": "objetado", "pedir_documentos": "incompleto"}
ABIERTOS = ["incompleto", "completo"]
UMBRAL_CONFIANZA = 0.7

# Protección contra adivinar contraseñas: 5 intentos fallidos = 15 minutos bloqueado
INTENTOS_FALLIDOS = {}
MAXIMO_INTENTOS = 5
BLOQUEO_SEGUNDOS = 15 * 60


def esta_bloqueado(correo):
    limite = time.time() - BLOQUEO_SEGUNDOS
    INTENTOS_FALLIDOS[correo] = [t for t in INTENTOS_FALLIDOS.get(correo, []) if t > limite]
    return len(INTENTOS_FALLIDOS[correo]) >= MAXIMO_INTENTOS


def analista_en_sesion(request):
    return request.session.get("analista")


def ir_al_login():
    return RedirectResponse("/panel/login", status_code=303)


def volver_al_caso(caso_id, error=None, ok=None):
    parametros = urlencode({k: v for k, v in {"error": error, "ok": ok}.items() if v})
    return RedirectResponse(f"/panel/caso/{caso_id}?{parametros}", status_code=303)


def buscar_caso(caso_id):
    try:
        uuid.UUID(caso_id)
    except ValueError:
        return None
    filas = supabase.table("casos").select("*").eq("id", caso_id).limit(1).execute().data
    return filas[0] if filas else None


# ---------- Inicio y cierre de sesión ----------

@router.get("/login", response_class=HTMLResponse)
def ver_login(request: Request):
    return plantillas.TemplateResponse(request, "panel_login.html", {})


@router.post("/login", response_class=HTMLResponse)
def iniciar_sesion(request: Request, correo: str = Form(""), contrasena: str = Form("")):
    correo = correo.strip().lower()
    if esta_bloqueado(correo):
        return plantillas.TemplateResponse(request, "panel_login.html", {
            "error": "Demasiados intentos fallidos. Espera 15 minutos e intenta de nuevo.",
        }, status_code=429)

    filas = (supabase.table("analistas").select("*")
             .eq("correo", correo).eq("activo", True).limit(1).execute().data)
    valido = bool(filas) and bcrypt.checkpw(contrasena.encode(), filas[0]["contrasena_cifrada"].encode())
    if not valido:
        INTENTOS_FALLIDOS.setdefault(correo, []).append(time.time())
        # Mismo mensaje si el correo no existe o si la contraseña está mal: no damos pistas
        return plantillas.TemplateResponse(request, "panel_login.html", {
            "error": "Correo o contraseña incorrectos.",
        }, status_code=401)

    INTENTOS_FALLIDOS.pop(correo, None)
    analista = filas[0]
    request.session.clear()
    request.session["analista"] = {"id": analista["id"], "correo": analista["correo"], "nombre": analista["nombre"]}
    return RedirectResponse("/panel", status_code=303)


@router.get("/salir")
def cerrar_sesion(request: Request):
    request.session.clear()
    return ir_al_login()


# ---------- Lista de casos ----------

@router.get("", response_class=HTMLResponse)
def lista_casos(request: Request):
    analista = analista_en_sesion(request)
    if not analista:
        return ir_al_login()

    casos = (supabase.table("casos")
             .select("id, numero_radicado, nombre_beneficiario, tipo_sugerido_ia, tipo_confirmado, "
                     "confianza_ia, estado, fecha_radicacion, fecha_expediente_completo, fecha_vencimiento")
             .in_("estado", ABIERTOS).execute().data)
    for caso in casos:
        caso["plazo"] = plazos.estado_plazo(caso)
    casos.sort(key=lambda c: c["plazo"]["orden"])

    semaforos = [c["plazo"]["semaforo"] for c in casos]
    resumen = {
        "abiertos": len(casos),
        "en_riesgo": semaforos.count("riesgo"),
        "vencidos": semaforos.count("vencido"),
        "sin_iniciar": semaforos.count("sin_iniciar"),
    }
    return plantillas.TemplateResponse(request, "panel_lista.html", {
        "analista": analista, "casos": casos, "resumen": resumen,
        "nombres_tipo": motor.NOMBRES_TIPO, "estados": ESTADOS, "umbral": UMBRAL_CONFIANZA,
    })


# ---------- Detalle de un caso ----------

@router.get("/caso/{caso_id}", response_class=HTMLResponse)
def ver_caso(request: Request, caso_id: str, error: str = "", ok: str = ""):
    analista = analista_en_sesion(request)
    if not analista:
        return ir_al_login()
    caso = buscar_caso(caso_id)
    if not caso:
        return RedirectResponse("/panel", status_code=303)

    documentos = (supabase.table("documentos").select("*")
                  .eq("caso_id", caso_id).order("fecha_subida").execute().data)
    for documento in documentos:
        # Enlace temporal: deja ver el archivo solo durante 5 minutos
        firmado = supabase.storage.from_("documentos").create_signed_url(documento["ubicacion_archivo"], 300)
        documento["enlace"] = firmado.get("signedURL") or firmado.get("signedUrl")

    eventos = (supabase.table("eventos").select("*")
               .eq("caso_id", caso_id).order("fecha_evento").execute().data)
    decisiones = (supabase.table("decisiones").select("*, analistas(nombre, correo)")
                  .eq("caso_id", caso_id).order("fecha_decision").execute().data)

    return plantillas.TemplateResponse(request, "panel_caso.html", {
        "analista": analista, "caso": caso, "documentos": documentos,
        "resumen": motor.resumen_expediente(caso, documentos),
        "plazo": plazos.estado_plazo(caso),
        "eventos": eventos, "decisiones": decisiones,
        "nombres": motor.NOMBRES, "nombres_tipo": motor.NOMBRES_TIPO,
        "estados": ESTADOS, "umbral": UMBRAL_CONFIANZA,
        "abierto": caso["estado"] in ABIERTOS,
        "error": error, "ok": ok,
    })


@router.post("/caso/{caso_id}/tipo")
def confirmar_tipo(request: Request, caso_id: str, tipo: str = Form("")):
    """El analista confirma o corrige el tipo que sugirió la IA."""
    analista = analista_en_sesion(request)
    if not analista:
        return ir_al_login()
    caso = buscar_caso(caso_id)
    if not caso or caso["estado"] not in ABIERTOS:
        return volver_al_caso(caso_id, error="Este caso ya está cerrado.")
    if tipo not in motor.NOMBRES_TIPO:
        return volver_al_caso(caso_id, error="Tipo de reclamación no válido.")

    supabase.table("casos").update({"tipo_confirmado": tipo}).eq("id", caso_id).execute()
    registrar_evento(caso_id, "tipo_confirmado", analista["correo"], {
        "sugerido_por_ia": caso["tipo_sugerido_ia"],
        "confirmado": tipo,
        "corrigio_a_la_ia": tipo != caso["tipo_sugerido_ia"],  # sirve para medir qué tan bien clasifica la IA
    })
    motor.procesar_caso(caso_id)  # con el tipo confirmado se recalcula qué falta
    return volver_al_caso(caso_id, ok="Tipo de reclamación confirmado.")


@router.post("/caso/{caso_id}/decision")
def registrar_decision(request: Request, caso_id: str, decision: str = Form(""), comentario: str = Form("")):
    """La decisión la toma una persona y queda registrada a su nombre."""
    analista = analista_en_sesion(request)
    if not analista:
        return ir_al_login()
    caso = buscar_caso(caso_id)
    comentario = comentario.strip()

    if not caso or caso["estado"] not in ABIERTOS:
        return volver_al_caso(caso_id, error="Este caso ya tiene una decisión final.")
    if decision not in DECISIONES:
        return volver_al_caso(caso_id, error="Decisión no válida.")
    if len(comentario) < 10:
        return volver_al_caso(caso_id, error="Escribe un comentario de al menos 10 caracteres que explique la decisión.")
    if decision in ("pagar", "objetar") and not caso["tipo_confirmado"]:
        return volver_al_caso(caso_id, error="Antes de pagar u objetar, confirma el tipo de reclamación.")
    if decision == "pagar" and caso["estado"] != "completo":
        return volver_al_caso(caso_id, error="Solo se puede aprobar el pago cuando el expediente está completo.")

    supabase.table("decisiones").insert({
        "caso_id": caso_id, "analista_id": analista["id"],
        "decision": decision, "comentario": comentario,
    }).execute()
    supabase.table("casos").update({"estado": DECISIONES[decision]}).eq("id", caso_id).execute()
    registrar_evento(caso_id, "decision_registrada", analista["correo"], {
        "decision": decision, "comentario": comentario, "analista": analista["nombre"],
    })
    return volver_al_caso(caso_id, ok="Decisión registrada.")



# ---------- Indicadores: las 4 preguntas del punto 7 ----------

import random


@router.get("/indicadores", response_class=HTMLResponse)
def ver_indicadores(request: Request):
    analista = analista_en_sesion(request)
    if not analista:
        return ir_al_login()

    casos = (supabase.table("casos")
             .select("id, numero_radicado, estado, tipo_sugerido_ia, tipo_confirmado, fecha_radicacion, "
                     "fecha_primera_respuesta, fecha_expediente_completo, fecha_vencimiento")
             .execute().data)

    # 1. ¿Cuántos abiertos, en qué día va cada uno, cuántos en riesgo y vencidos?
    abiertos = [c for c in casos if c["estado"] in ABIERTOS]
    for caso in abiertos:
        caso["plazo"] = plazos.estado_plazo(caso)
    abiertos.sort(key=lambda c: c["plazo"]["orden"])
    semaforos = [c["plazo"]["semaforo"] for c in abiertos]
    conteo_plazo = {s: semaforos.count(s) for s in ("en_tiempo", "riesgo", "vencido", "sin_iniciar")}

    # 2. ¿Cuántas clasificaciones de la IA tuvo que corregir una persona?
    confirmados = [c for c in casos if c["tipo_confirmado"] and c["tipo_sugerido_ia"]]
    corregidos = [c for c in confirmados if c["tipo_confirmado"] != c["tipo_sugerido_ia"]]
    correccion = {
        "confirmados": len(confirmados),
        "corregidos": len(corregidos),
        "porcentaje": round(100 * len(corregidos) / len(confirmados), 1) if confirmados else None,
    }

    # 3. ¿Cuánto se demora en decirle al beneficiario qué le falta?
    minutos = sorted(
        (plazos.fecha_local(c["fecha_primera_respuesta"]) - plazos.fecha_local(c["fecha_radicacion"])).total_seconds() / 60
        for c in casos if c["fecha_primera_respuesta"]
    )
    respuesta = {
        "casos": len(minutos),
        "promedio": round(sum(minutos) / len(minutos), 1) if minutos else None,
        "mediana": round(minutos[len(minutos) // 2], 1) if minutos else None,
        "maximo": round(minutos[-1], 1) if minutos else None,
    }

    # Estado de la tarea automática
    ultima = (supabase.table("ejecuciones").select("*")
              .eq("tarea", "vigilar").order("fin", desc=True).limit(1).execute().data)

    return plantillas.TemplateResponse(request, "panel_indicadores.html", {
        "analista": analista, "abiertos": abiertos, "conteo_plazo": conteo_plazo,
        "correccion": correccion, "respuesta": respuesta,
        "ultima": ultima[0] if ultima else None, "total_casos": len(casos),
    })


@router.get("/caso-al-azar")
def caso_al_azar(request: Request):
    """Pregunta 4: escoge un caso al azar para reconstruir su historia."""
    if not analista_en_sesion(request):
        return ir_al_login()
    ids = [c["id"] for c in supabase.table("casos").select("id").execute().data]
    if not ids:
        return RedirectResponse("/panel", status_code=303)
    return RedirectResponse(f"/panel/caso/{random.choice(ids)}", status_code=303)