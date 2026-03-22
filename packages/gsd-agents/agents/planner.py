"""
HoFi - Agente Planificador · v2
Parser robusto para respuestas JSON.
"""
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _parser import parse_json_response


SYSTEM_PROMPT = """
Sos un planificador de software especializado en desarrollo iterativo GSD.
Tomás una descripción de funcionalidad y producís un plan quirúrgico.

Respondé SOLO con JSON válido, sin texto antes ni después:
{
  "tarea_atomica": "descripción de una sola cosa a implementar",
  "criterios_exito": [
    {"id": "C1", "descripcion": "criterio binario verificable con curl o comando"}
  ],
  "archivos_a_crear": ["ruta/archivo.py"],
  "archivos_a_modificar": ["ruta/existente.py"],
  "riesgos": ["riesgo identificado"],
  "notas_seguridad": ["consideración de seguridad"]
}

Principios:
- Tarea mínima con valor comprobable.
- Máximo 4 criterios de éxito, todos verificables con curl o comando simple.
- Si hay bloqueos previos, incorporarlos como restricciones explícitas.
- Las notas de seguridad son obligatorias.
""".strip()


def run_planner(client, bloque: str, memoria: str, bloqueos_previos: list) -> dict:
    bloqueos_texto = ""
    if bloqueos_previos:
        bloqueos_texto = "\n\nBLOQUEOS PREVIOS (incorporar como restricciones):\n"
        bloqueos_texto += "\n".join(f"- {b}" for b in bloqueos_previos)

    prompt = f"""
Contexto del proyecto:
{memoria[:1500]}

Bloque a planificar:
{bloque}
{bloqueos_texto}

Respondé SOLO con el JSON del plan.
""".strip()

    resp = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=3000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return parse_json_response(resp.content[0].text)


