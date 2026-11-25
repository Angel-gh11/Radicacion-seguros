# verificar.py
# Compara lo que se esperaba de cada caso de prueba con lo que hizo el sistema.
# Sirve para medir qué tan bien clasificó la IA (contra el tipo real de cada caso).
#
# Uso (desde la carpeta del proyecto):  python datos_prueba/verificar.py

import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import supabase  # noqa: E402

CARPETA = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(CARPETA, "casos.json"), encoding="utf-8") as f:
    radicaciones = [r for r in json.load(f) if not r.get("repite")]

filas, aciertos, clasificados = [], 0, 0
for r in radicaciones:
    casos = (supabase.table("casos").select("*")
             .eq("documento_asegurado", r["datos"]["documento_asegurado"])
             .eq("documento_beneficiario", r["datos"]["documento_beneficiario"]).execute().data)
    if not casos:
        filas.append({"id": r["id"], "casos_creados": 0, "esperado": r["esperado"]})
        continue
    caso = casos[0]
    documentos = supabase.table("documentos").select("estado, motivo_rechazo").eq("caso_id", caso["id"]).execute().data
    acierto = caso["tipo_sugerido_ia"] == r["tipo_real"]
    if caso["tipo_sugerido_ia"]:
        clasificados += 1
        aciertos += acierto
    filas.append({
        "id": r["id"],
        "radicado": caso["numero_radicado"],
        "casos_creados": len(casos),
        "tipo_real": r["tipo_real"],
        "tipo_sugerido_ia": caso["tipo_sugerido_ia"],
        "confianza_ia": caso["confianza_ia"],
        "ia_acerto": "si" if acierto else "no",
        "estado": caso["estado"],
        "expediente_completo": "si" if caso["fecha_expediente_completo"] else "no",
        "documentos": len(documentos),
        "validos": sum(d["estado"] == "valido" for d in documentos),
        "no_sirven": sum(d["estado"] == "invalido" for d in documentos),
        "pendientes": sum(d["estado"] == "pendiente" for d in documentos),
        "motivos": " | ".join(d["motivo_rechazo"] for d in documentos if d["motivo_rechazo"]),
        "esperado": r["esperado"],
    })

columnas = ["id", "radicado", "casos_creados", "tipo_real", "tipo_sugerido_ia", "confianza_ia", "ia_acerto",
            "estado", "expediente_completo", "documentos", "validos", "no_sirven", "pendientes", "motivos", "esperado"]
with open(os.path.join(CARPETA, "verificacion.csv"), "w", newline="", encoding="utf-8") as f:
    escritor = csv.DictWriter(f, fieldnames=columnas, extrasaction="ignore")
    escritor.writeheader()
    escritor.writerows(filas)

for fila in filas:
    print(f"{fila['id']}: IA={fila.get('tipo_sugerido_ia')} ({fila.get('ia_acerto')}) · "
          f"completo={fila.get('expediente_completo')} · no sirven={fila.get('no_sirven')} · "
          f"pendientes={fila.get('pendientes')} · casos creados={fila['casos_creados']}")
if clasificados:
    print(f"\nLa IA acertó el tipo en {aciertos} de {clasificados} casos ({100 * aciertos / clasificados:.0f} %).")
print("Detalle completo en datos_prueba/verificacion.csv")
