"""
HoFi — Billing Kill-Switch (Cloud Function Gen2, Python 3.12)

Patrón oficial de Google para "cortar el gasto de verdad":
  Budget  →  Pub/Sub topic 'billing-alerts'  →  esta función  →  deshabilita
  el billing del proyecto entero cuando el costo supera el presupuesto.

Deshabilitar el billing apaga TODOS los recursos facturables del proyecto
(Cloud Run, etc.). Es el botón rojo de último recurso: una vez disparado,
hay que re-habilitar el billing a mano desde la Console para volver a operar.

⚠️ Latencia: los datos de costo de GCP no son tiempo real — la notificación
del budget puede tardar algunas horas tras cruzar el umbral. No es instantáneo,
pero corta en horas en vez de days/semanas (que fue lo que pasó con los $1500).

Variables de entorno:
  BILLING_PROJECT_ID  — el project id a apagar (ej. 'hofi-v3-2026')
"""

import base64
import json
import os

import functions_framework
from googleapiclient import discovery

PROJECT_ID = os.environ.get("BILLING_PROJECT_ID", "").strip()
PROJECT_NAME = f"projects/{PROJECT_ID}"


@functions_framework.cloud_event
def stop_billing(cloud_event):
    """Handler disparado por cada notificación del budget vía Pub/Sub."""
    if not PROJECT_ID:
        print("ERROR: BILLING_PROJECT_ID no seteado — no puedo actuar.")
        return

    # El payload del budget viene base64 en message.data
    message = cloud_event.data.get("message", {})
    data_b64 = message.get("data", "")
    if not data_b64:
        print("Mensaje sin data — ignorado.")
        return

    # Fail-safe: si el payload no es JSON válido, logueamos y salimos SIN tocar
    # el billing. Los mensajes reales del budget de GCP siempre son JSON válido;
    # esto solo protege contra mensajes de prueba o malformados.
    try:
        payload = json.loads(base64.b64decode(data_b64).decode("utf-8"))
    except (ValueError, TypeError) as e:
        print(f"Payload no parseable ({e}) — sin acción (fail-safe).")
        return

    cost_amount = float(payload.get("costAmount", 0) or 0)
    budget_amount = float(payload.get("budgetAmount", 0) or 0)
    print(f"Budget check | cost={cost_amount} budget={budget_amount} project={PROJECT_ID}")

    if cost_amount <= budget_amount:
        print("Dentro del presupuesto — sin acción.")
        return

    billing = discovery.build("cloudbilling", "v1")
    projects = billing.projects()

    info = projects.getBillingInfo(name=PROJECT_NAME).execute()
    if not info.get("billingEnabled", False):
        print("Billing ya estaba deshabilitado — nada que hacer.")
        return

    # El corte: vaciar billingAccountName deshabilita el billing del proyecto.
    res = projects.updateBillingInfo(
        name=PROJECT_NAME,
        body={"billingAccountName": ""},
    ).execute()
    print(f"🔴 BILLING DESHABILITADO para {PROJECT_NAME}: {json.dumps(res)}")
