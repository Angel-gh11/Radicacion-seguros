# cargar.py
# Envía las radicaciones de casos.json al formulario real de la aplicación,
# igual que lo haría una persona desde el navegador.
#
# Uso (desde la carpeta del proyecto, con el servidor encendido):
#   python datos_prueba/cargar.py                      -> envía a http://127.0.0.1:8000
#   python datos_prueba/cargar.py https://tu-app.onrender.com
#
# Entre un envío y otro espera unos segundos para no saturar la IA del plan gratuito.

import csv
import json
import os
import sys
import time

import httpx

CARPETA = os.path.dirname(os.path.abspath(__file__))
URL = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
PAUSA_SEGUNDOS = int(sys.argv[2]) if len(sys.argv) > 2 else 25
TIPOS = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg"}

with open(os.path.join(CARPETA, "casos.json"), encoding="utf-8") as f:
    radicaciones = json.load(f)

resultados = []
with httpx.Client(timeout=120) as cliente:
    for numero, r in enumerate(radicaciones, start=1):
        archivos = []
        for nombre in r["documentos"]:
            with open(os.path.join(CARPETA, "archivos", nombre), "rb") as archivo:
                archivos.append(("archivos", (nombre, archivo.read(), TIPOS[os.path.splitext(nombre)[1]])))
        datos = {**r["datos"], "autoriza_datos": "si"}

        respuesta = cliente.post(f"{URL}/radicar", data=datos, files=archivos, follow_redirects=False)
        enlace = respuesta.headers.get("location", "")
        if respuesta.status_code == 303:
            resultado = "caso nuevo"
        elif respuesta.status_code == 200 and "Recibimos tus documentos" in respuesta.text:
            resultado = "agregado a un caso abierto (no se creó caso nuevo)"
        else:
            resultado = f"error {respuesta.status_code}"

        print(f"[{numero:02d}/{len(radicaciones)}] {r['id']}: {resultado}")
        resultados.append({"id": r["id"], "resultado": resultado, "esperado": r["esperado"],
                           "enlace_seguimiento": f"{URL}{enlace}" if enlace else ""})
        if numero < len(radicaciones):
            time.sleep(PAUSA_SEGUNDOS)

with open(os.path.join(CARPETA, "resultado_carga.csv"), "w", newline="", encoding="utf-8") as f:
    escritor = csv.DictWriter(f, fieldnames=["id", "resultado", "esperado", "enlace_seguimiento"])
    escritor.writeheader()
    escritor.writerows(resultados)
print("\nListo. Resultados en datos_prueba/resultado_carga.csv")
