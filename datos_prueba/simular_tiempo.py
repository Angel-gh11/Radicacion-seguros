# simular_tiempo.py
# SOLO PARA PRUEBAS. Un caso real tarda semanas en entrar en riesgo o vencerse.
# Este script corre hacia atrás la fecha en que quedó completo el expediente de
# algunos casos de prueba, para poder ver las alertas de riesgo y vencimiento.
# Cada cambio queda registrado en la historia del caso como "fechas_simuladas_para_prueba".
#
# Uso (desde la carpeta del proyecto):  python datos_prueba/simular_tiempo.py

import json
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import motor  # noqa: E402
import plazos  # noqa: E402
from config import supabase  # noqa: E402
from radicacion import registrar_evento  # noqa: E402

CARPETA = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(CARPETA, "casos.json"), encoding="utf-8") as f:
    radicaciones = [r for r in json.load(f) if r.get("dias_atras")]

for r in radicaciones:
    filas = (supabase.table("casos").select("*")
             .eq("documento_asegurado", r["datos"]["documento_asegurado"])
             .eq("documento_beneficiario", r["datos"]["documento_beneficiario"])
             .limit(1).execute().data)
    if not filas:
        print(f"{r['id']}: no se encontró el caso. ¿Ya corriste cargar.py?")
        continue
    caso = filas[0]
    if not caso["fecha_expediente_completo"]:
        print(f"{r['id']}: todavía no está completo (puede que la IA no haya terminado). Intenta más tarde.")
        continue
    ya_simulado = (supabase.table("eventos").select("id").eq("caso_id", caso["id"])
                   .eq("tipo_evento", "fechas_simuladas_para_prueba").execute().data)
    if ya_simulado:
        print(f"{r['id']}: ya se había simulado antes; no se mueve otra vez.")
        continue

    original = plazos.fecha_local(caso["fecha_expediente_completo"])
    nueva = original - timedelta(days=r["dias_atras"])
    vence = motor.sumar_un_mes(nueva.date())
    supabase.table("casos").update({
        "fecha_expediente_completo": nueva.isoformat(),
        "fecha_vencimiento": vence.isoformat(),
    }).eq("id", caso["id"]).execute()
    registrar_evento(caso["id"], "fechas_simuladas_para_prueba", "script_de_prueba", {
        "aviso": "Fechas movidas hacia atrás solo para probar las alertas. No es un caso real.",
        "dias_atras": r["dias_atras"],
        "fecha_completo_original": original.isoformat(),
        "fecha_completo_simulada": nueva.isoformat(),
        "vence_simulado": vence.isoformat(),
    })
    print(f"{caso['numero_radicado']} ({r['id']}): completo hace {r['dias_atras']} días, vence {vence}")

print("\nAhora ejecuta la vigilancia para que salgan las alertas.")
