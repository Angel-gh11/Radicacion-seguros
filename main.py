# main.py
# Rutas de la aplicación: qué se muestra y qué se hace en cada dirección.

import os

from fastapi import BackgroundTasks, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

import motor
import panel
import radicacion
from config import CLAVE_SESION

app = FastAPI(title="Radicación de reclamaciones")
app.add_middleware(
    SessionMiddleware,
    secret_key=CLAVE_SESION,          # firma la cookie de sesión para que no se pueda falsificar
    max_age=8 * 60 * 60,              # la sesión dura máximo 8 horas
    same_site="lax",
    https_only=bool(os.getenv("RENDER")),  # en internet, la cookie solo viaja por HTTPS
)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(panel.router)
plantillas = Jinja2Templates(directory="templates")

ESTADOS = {
    "incompleto": "Faltan documentos",
    "completo": "Expediente completo, en revisión",
    "pagado": "Aprobada para pago",
    "objetado": "Objetada",
}


@app.get("/", response_class=HTMLResponse)
def formulario(request: Request):
    return plantillas.TemplateResponse(request, "radicar.html", {"datos": {}})


@app.post("/radicar", response_class=HTMLResponse)
async def radicar(
    request: Request,
    tareas: BackgroundTasks,
    nombre_beneficiario: str = Form(""),
    documento_beneficiario: str = Form(""),
    correo_beneficiario: str = Form(""),
    telefono_beneficiario: str = Form(""),
    nombre_asegurado: str = Form(""),
    documento_asegurado: str = Form(""),
    relato: str = Form(""),
    autoriza_datos: str = Form(""),
    archivos: list[UploadFile] = File(default=[]),
):
    datos = {
        "nombre_beneficiario": nombre_beneficiario.strip(),
        "documento_beneficiario": documento_beneficiario.strip(),
        "correo_beneficiario": correo_beneficiario.strip().lower(),
        "telefono_beneficiario": telefono_beneficiario.strip() or None,
        "nombre_asegurado": nombre_asegurado.strip(),
        "documento_asegurado": documento_asegurado.strip(),
        "relato": relato.strip(),
    }

    if not autoriza_datos:
        return plantillas.TemplateResponse(request, "radicar.html", {
            "datos": datos,
            "error": "Para continuar necesitamos tu autorización para el tratamiento de datos personales.",
        }, status_code=400)

    archivos_leidos = [(archivo.filename, await archivo.read()) for archivo in archivos]

    try:
        caso, es_nuevo = radicacion.registrar_radicacion(datos, archivos_leidos)
    except radicacion.ErrorValidacion as error:
        return plantillas.TemplateResponse(request, "radicar.html", {
            "datos": datos, "error": str(error),
        }, status_code=400)

    # El motor revisa en segundo plano para no hacer esperar al beneficiario
    tareas.add_task(motor.procesar_caso, caso["id"])

    if not es_nuevo:
        # No mostramos el caso existente: cualquiera que conozca dos cédulas
        # podría ver la reclamación de otra persona.
        return plantillas.TemplateResponse(request, "mensaje.html", {
            "titulo": "Recibimos tus documentos",
            "mensaje": "Ya hay una reclamación abierta para este asegurado a tu nombre. "
                       "Agregamos los documentos a esa misma reclamación, así que no tienes que hacer nada más. "
                       "Para ver el estado, usa el enlace de seguimiento que recibiste al radicar.",
        })

    return RedirectResponse(f"/seguimiento/{caso['codigo_seguimiento']}?nuevo=1", status_code=303)


@app.get("/seguimiento/{codigo}", response_class=HTMLResponse)
def seguimiento(request: Request, codigo: str, nuevo: int = 0, enviado: int = 0):
    caso = radicacion.buscar_por_codigo(codigo)
    if not caso:
        return plantillas.TemplateResponse(request, "mensaje.html", {
            "titulo": "No encontramos la reclamación",
            "mensaje": "Revisa que el enlace esté completo.",
        }, status_code=404)

    documentos = radicacion.documentos_del_caso(caso["id"])
    return plantillas.TemplateResponse(request, "seguimiento.html", {
        "caso": caso,
        "documentos": documentos,
        "resumen": motor.resumen_expediente(caso, documentos),
        "nombres": motor.NOMBRES,
        "estado": ESTADOS.get(caso["estado"], caso["estado"]),
        "nuevo": nuevo,
        "enviado": enviado,
        "enlace": str(request.url).split("?")[0],
    })


@app.post("/seguimiento/{codigo}/documentos", response_class=HTMLResponse)
async def enviar_mas_documentos(request: Request, codigo: str, tareas: BackgroundTasks,
                                archivos: list[UploadFile] = File(default=[])):
    """El beneficiario envía lo que le faltaba, desde su enlace de seguimiento."""
    caso = radicacion.buscar_por_codigo(codigo)
    if not caso or caso["estado"] not in ("incompleto", "completo"):
        return RedirectResponse(f"/seguimiento/{codigo}", status_code=303)

    archivos_leidos = [(archivo.filename, await archivo.read()) for archivo in archivos]
    try:
        for nombre, contenido, extension in radicacion.validar_archivos(archivos_leidos):
            radicacion.guardar_documento(caso["id"], nombre, contenido, extension)
    except radicacion.ErrorValidacion as error:
        return plantillas.TemplateResponse(request, "mensaje.html", {
            "titulo": "No pudimos recibir el archivo", "mensaje": str(error),
        }, status_code=400)

    tareas.add_task(motor.procesar_caso, caso["id"])
    return RedirectResponse(f"/seguimiento/{codigo}?enviado=1", status_code=303)