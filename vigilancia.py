# vigilancia.py
# Tarea automática. La llama GitHub Actions cada hora, sin que nadie lo pida:
#   1. Reintenta los documentos que la IA no alcanzó a revisar.
#   2. Revisa el plazo de cada caso y avisa ANTES de que venza.
#   3. Deja registro de cada ejecución para saber si algo dejó de funcionar.

import httpx
from postgrest.exceptions import APIError

import motor
import plazos
from config import URL_AVISOS, supabase
from radicacion import ahora, registrar_evento


def enviar_aviso(texto):
    """Manda la alerta al canal del equipo (Discord). Si no está configurado, no pasa nada."""
    if not URL_AVISOS:
        return False
    try:
        httpx.post(URL_AVISOS, json={"content": texto}, timeout=10).raise_for_status()
        return True
    except httpx.HTTPError:
        return False


def vigilar():
    inicio = ahora()
    resultado = {"casos_reprocesados": 0, "alertas_riesgo": 0, "alertas_vencido": 0, "errores": []}

    # 1. Documentos que quedaron pendientes (por ejemplo, porque la IA no respondió)
    pendientes = supabase.table("documentos").select("caso_id").eq("estado", "pendiente").execute().data
    for caso_id in {p["caso_id"] for p in pendientes}:
        try:
            motor.procesar_caso(caso_id)
            resultado["casos_reprocesados"] += 1
        except Exception as error:
            resultado["errores"].append(f"Caso {caso_id}: {str(error)[:200]}")

    # 2. Plazo de los casos abiertos cuyo reloj ya arrancó
    casos = (supabase.table("casos").select("*")
             .in_("estado", ["incompleto", "completo"]).execute().data)
    for caso in casos:
        if not caso["fecha_expediente_completo"]:
            continue  # el plazo todavía no empieza
        plazo = plazos.estado_plazo(caso)
        if plazo["semaforo"] not in ("riesgo", "vencido"):
            continue
        nivel = plazo["semaforo"]
        try:
            # La tabla no deja guardar la misma alerta dos veces: así no se repite el aviso
            supabase.table("alertas").insert({"caso_id": caso["id"], "nivel": nivel}).execute()
        except APIError as error:
            if error.code == "23505":
                continue
            raise
        texto = (f"⚠️ Caso {caso['numero_radicado']} "
                 f"{'EN RIESGO' if nivel == 'riesgo' else 'VENCIDO'}: {plazo['texto']}. "
                 f"Vence el {plazo['vence']}.")
        enviado = enviar_aviso(texto)
        registrar_evento(caso["id"], f"alerta_{nivel}", "sistema", {
            "mensaje": texto, "aviso_enviado_al_equipo": enviado,
        })
        resultado[f"alertas_{nivel}"] += 1

    # 3. Registro de la ejecución
    supabase.table("ejecuciones").insert({
        "tarea": "vigilar",
        "inicio": inicio.isoformat(),
        "fin": ahora().isoformat(),
        "exitosa": not resultado["errores"],
        "resultado": resultado,
    }).execute()
    return resultado