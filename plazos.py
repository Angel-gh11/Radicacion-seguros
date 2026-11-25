# plazos.py
# Plazo legal (art. 1080 del Código de Comercio): en qué día va cada caso y si está en riesgo.

from datetime import date, datetime

from radicacion import ZONA_COLOMBIA, ahora

DIAS_ALERTA = 7  # un caso entra "en riesgo" cuando le quedan 7 días o menos


def fecha_local(texto):
    """La base guarda las fechas en hora UTC. Esto las pasa a la hora de Colombia."""
    if not texto:
        return None
    return datetime.fromisoformat(texto).astimezone(ZONA_COLOMBIA)


def estado_plazo(caso, hoy=None):
    hoy = hoy or ahora().date()

    if not caso.get("fecha_expediente_completo"):
        dias = (hoy - fecha_local(caso["fecha_radicacion"]).date()).days
        return {
            "semaforo": "sin_iniciar",
            "texto": f"Sin iniciar (incompleto, radicado hace {dias} días)",
            "dia": None, "total": None, "dias_restantes": None, "vence": None,
            "orden": 10_000 - dias,
        }

    inicio = fecha_local(caso["fecha_expediente_completo"]).date()
    vence = date.fromisoformat(caso["fecha_vencimiento"])
    total = (vence - inicio).days
    dia = (hoy - inicio).days + 1
    restantes = (vence - hoy).days

    if restantes < 0:
        semaforo, texto = "vencido", f"Vencido hace {-restantes} días"
    elif restantes <= DIAS_ALERTA:
        semaforo, texto = "riesgo", f"Día {dia} de {total}: quedan {restantes} días"
    else:
        semaforo, texto = "en_tiempo", f"Día {dia} de {total}: quedan {restantes} días"

    return {
        "semaforo": semaforo, "texto": texto, "dia": dia, "total": total,
        "dias_restantes": restantes, "vence": vence.isoformat(), "orden": restantes,
    }