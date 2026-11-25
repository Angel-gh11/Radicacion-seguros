# Conjunto de datos de prueba

32 radicaciones: 30 casos distintos y 2 envíos repetidos. Todos los datos y documentos son ficticios
y llevan la marca "MUESTRA - DATOS FICTICIOS".

| Grupo | Casos | Qué prueba |
|---|---|---|
| Muerte natural | C01–C10, C29 | Completos, incompletos, SARLAFT sin firma, cédula borrosa, registro civil de otra persona, intento de manipular a la IA desde el relato |
| Muerte accidental | C11–C20 | Completos con informe de policía, falta el informe, cédula de otra persona, formato sin firma, relato ambiguo (una caída) |
| Incapacidad | C21–C28, C30 | Completos, falta el dictamen, dictamen de otra persona, cuenta bancaria de otra persona, incapacidad por accidente (no es muerte accidental) |
| Repetidos | R01, R02 | El mismo envío dos veces y un reenvío con un archivo nuevo: no crean casos nuevos |

En `casos.json` cada caso trae su tipo real y lo que se espera que haga el sistema.

## Cómo usarlo

Desde la carpeta del proyecto, con el servidor encendido:

1. `python datos_prueba/cargar.py` envía las 32 radicaciones al formulario (tarda unos 15 minutos).
2. Espera a que la IA termine y ejecuta la vigilancia para reintentar lo pendiente.
3. `python datos_prueba/simular_tiempo.py` mueve hacia atrás las fechas de 4 casos completos para ver alertas de riesgo y vencimiento. Queda registrado en la historia de cada caso.
4. `python datos_prueba/verificar.py` compara lo esperado con lo que hizo el sistema y calcula cuántas veces acertó la IA.

`generar_documentos.py` crea los documentos desde cero (necesita `pip install reportlab pillow`).
