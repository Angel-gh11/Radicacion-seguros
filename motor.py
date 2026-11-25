# motor.py
# Reglas del negocio: revisa documentos, determina el tipo, decide si el
# expediente está completo y arranca el reloj legal.

import calendar

import ia
from config import MODELO_IA, supabase
from radicacion import TIPOS_MIME, ahora, registrar_evento

NOMBRES = {
    "formato_reclamacion": "Formato de reclamación diligenciado",
    "registro_civil_defuncion": "Registro civil de defunción",
    "certificado_medico_defuncion": "Certificado médico de defunción",
    "cedula_asegurado": "Documento de identidad del asegurado",
    "cedula_beneficiario": "Documento de identidad del beneficiario",
    "sarlaft": "Formulario SARLAFT firmado",
    "certificacion_bancaria": "Certificación bancaria del beneficiario",
    "informe_autoridad": "Informe de la autoridad (policía o fiscalía)",
    "dictamen_perdida_capacidad": "Dictamen de pérdida de capacidad laboral",
    "historia_clinica": "Historia clínica resumida",
    "cedula": "Documento de identidad",
    "otro": "Documento no identificado",
}
NOMBRES_TIPO = {
    "muerte_natural": "Muerte natural",
    "muerte_accidental": "Muerte accidental",
    "incapacidad": "Incapacidad total y permanente",
}
DOCUMENTOS_DEL_ASEGURADO = {"registro_civil_defuncion", "certificado_medico_defuncion",
                            "dictamen_perdida_capacidad", "historia_clinica"}
REQUIEREN_FIRMA = {"sarlaft", "formato_reclamacion"}


def sumar_un_mes(fecha):
    """20 de octubre -> 20 de noviembre. Si el día no existe (31 de enero), usa el último del mes."""
    anio = fecha.year + fecha.month // 12
    mes = fecha.month % 12 + 1
    dia = min(fecha.day, calendar.monthrange(anio, mes)[1])
    return fecha.replace(year=anio, month=mes, day=dia)


def aplicar_reglas_documento(revision, caso):
    """La IA dijo qué vio. Estas reglas deciden si el documento sirve."""
    tipo = revision["tipo_documento"]
    numero = revision.get("numero_documento_persona")
    asegurado = caso["documento_asegurado"]
    beneficiario = caso["documento_beneficiario"]

    if not revision["legible"]:
        return tipo, "invalido", "No se puede leer bien. Envía una foto más clara o el documento en PDF."
    if tipo == "otro":
        return tipo, "invalido", "No pudimos identificar qué documento es. Un analista lo revisará."
    if tipo in REQUIEREN_FIRMA and revision.get("tiene_firma") is False:
        return tipo, "invalido", "Este documento llegó sin firma. Envíalo firmado, por favor."
    if tipo == "cedula":
        if numero == asegurado:
            return "cedula_asegurado", "valido", None
        if numero == beneficiario:
            return "cedula_beneficiario", "valido", None
        if numero is None:
            return tipo, "invalido", "No pudimos leer el número de la cédula. Envía una foto más clara."
        return tipo, "invalido", "La cédula no corresponde al asegurado ni al beneficiario."
    if tipo in DOCUMENTOS_DEL_ASEGURADO and numero and numero != asegurado:
        return tipo, "invalido", "El documento es de otra persona, no del asegurado."
    if tipo == "certificacion_bancaria" and numero and numero != beneficiario:
        return tipo, "invalido", "La cuenta bancaria no está a nombre del beneficiario."
    return tipo, "valido", None


def revisar_documentos_pendientes(caso):
    pendientes = (supabase.table("documentos").select("*")
                  .eq("caso_id", caso["id"]).eq("estado", "pendiente").execute().data)
    for documento in pendientes:
        try:
            contenido = supabase.storage.from_("documentos").download(documento["ubicacion_archivo"])
            extension = documento["ubicacion_archivo"].rsplit(".", 1)[-1]
            revision = ia.revisar_documento(contenido, TIPOS_MIME[extension])
        except ia.IANoDisponible as error:
            # El documento queda pendiente y se vuelve a intentar en la revisión automática
            registrar_evento(caso["id"], "ia_no_disponible", "sistema", {
                "documento_id": documento["id"], "error": str(error)[:300],
            })
            continue

        modelo = revision.pop("modelo", MODELO_IA)
        tipo, estado, motivo = aplicar_reglas_documento(revision, caso)
        supabase.table("documentos").update({
            "tipo_documento": tipo, "estado": estado, "motivo_rechazo": motivo,
        }).eq("id", documento["id"]).execute()
        registrar_evento(caso["id"], "documento_revisado", "ia", {
            "documento_id": documento["id"],
            "archivo": documento["nombre_archivo"],
            "modelo": modelo,
            "lo_que_vio_la_ia": revision,
            "decision_de_las_reglas": {"tipo": tipo, "estado": estado, "motivo": motivo},
        })


def clasificar_caso(caso, tipos_recibidos):
    if caso.get("tipo_confirmado"):
        return caso  # el analista ya confirmó el tipo; la IA no lo cambia
    try:
        resultado = ia.clasificar_reclamacion(caso["relato"], tipos_recibidos)
        responsable, modelo = "ia", resultado.pop("modelo", MODELO_IA)
    except ia.IANoDisponible as error:
        registrar_evento(caso["id"], "ia_no_disponible", "sistema", {"error": str(error)[:300]})
        if caso.get("tipo_sugerido_ia"):
            return caso  # ya tenía una clasificación; no se reemplaza por una peor
        resultado = ia.clasificar_por_palabras(caso["relato"], tipos_recibidos)
        responsable, modelo = "sistema", "palabras_clave"

    cambios = {
        "tipo_sugerido_ia": resultado["tipo"],
        "confianza_ia": resultado["confianza"],
        "explicacion_ia": resultado["explicacion"],
    }
    if (resultado["tipo"] != caso.get("tipo_sugerido_ia")
            or resultado["confianza"] != caso.get("confianza_ia")):
        supabase.table("casos").update(cambios).eq("id", caso["id"]).execute()
        registrar_evento(caso["id"], "clasificado", responsable, {
            **resultado, "modelo": modelo, "documentos_considerados": tipos_recibidos,
        })
    caso.update(cambios)
    return caso


def resumen_expediente(caso, documentos):
    """Compara lo recibido con lo que exige el tipo de reclamación."""
    tipo = caso.get("tipo_confirmado") or caso.get("tipo_sugerido_ia")
    validos = {d["tipo_documento"] for d in documentos if d["estado"] == "valido"}
    if "cedula_asegurado" in validos and caso["documento_asegurado"] == caso["documento_beneficiario"]:
        validos.add("cedula_beneficiario")  # el asegurado reclama su propia incapacidad

    requeridos = []
    if tipo:
        filas = supabase.table("requisitos").select("documento").eq("tipo_reclamacion", tipo).execute().data
        requeridos = [f["documento"] for f in filas]

    invalidos = [d for d in documentos if d["estado"] == "invalido"]
    tipos_invalidos = {d["tipo_documento"] for d in invalidos}
    faltantes = [r for r in requeridos if r not in validos]
    return {
        "tipo": tipo,
        "nombre_tipo": NOMBRES_TIPO.get(tipo, "En revisión"),
        "faltantes": [r for r in faltantes if r not in tipos_invalidos],  # sin repetir los que llegaron mal
        "invalidos": invalidos,
        "pendientes": [d for d in documentos if d["estado"] == "pendiente"],
        "completo": bool(tipo) and not faltantes,
    }


def mensaje_para_beneficiario(caso, resumen):
    """Lo arma el código, no la IA: así nunca se le dice algo inventado."""
    if resumen["completo"]:
        return ("Tu expediente está completo. Un analista ya está revisando tu reclamación "
                "y te avisaremos por correo cuando haya una decisión.")
    lineas = []
    if resumen["faltantes"]:
        lineas.append("Para continuar nos falta:")
        lineas += [f"- {NOMBRES.get(d, d)}" for d in resumen["faltantes"]]
    if resumen["invalidos"]:
        lineas.append("Estos documentos llegaron, pero no los podemos usar:")
        lineas += [f"- {d['nombre_archivo']}: {d['motivo_rechazo']}" for d in resumen["invalidos"]]
    if resumen["pendientes"]:
        lineas.append("Algunos documentos todavía están en revisión.")
    lineas.append("Puedes enviar lo que falta desde tu enlace de seguimiento.")
    return "\n".join(lineas)


def procesar_caso(caso_id):
    caso = supabase.table("casos").select("*").eq("id", caso_id).single().execute().data
    if caso["estado"] not in ("incompleto", "completo"):
        return None  # el caso ya tiene decisión

    revisar_documentos_pendientes(caso)
    documentos = supabase.table("documentos").select("*").eq("caso_id", caso_id).execute().data
    tipos_recibidos = sorted({d["tipo_documento"] for d in documentos if d["tipo_documento"]})
    caso = clasificar_caso(caso, tipos_recibidos)
    resumen = resumen_expediente(caso, documentos)

    cambios = {}
    if resumen["completo"] and not caso["fecha_expediente_completo"]:
        # EL RELOJ ARRANCA AQUÍ: cuando el expediente queda completo, no cuando se radicó
        momento = ahora()
        vence = sumar_un_mes(momento.date())
        cambios.update({
            "estado": "completo",
            "fecha_expediente_completo": momento.isoformat(),
            "fecha_vencimiento": vence.isoformat(),
        })
        registrar_evento(caso_id, "expediente_completo", "sistema", {
            "inicio_plazo": momento.isoformat(),
            "vence": vence.isoformat(),
            "regla": "Art. 1080 del Código de Comercio: un mes desde que el expediente queda completo",
        })

    mensaje = mensaje_para_beneficiario(caso, resumen)
    if not caso["fecha_primera_respuesta"]:
        cambios["fecha_primera_respuesta"] = ahora().isoformat()
    if cambios:
        supabase.table("casos").update(cambios).eq("id", caso_id).execute()
    registrar_evento(caso_id, "respuesta_al_beneficiario", "sistema", {
        "mensaje": mensaje, "faltantes": resumen["faltantes"],
    })
    return resumen