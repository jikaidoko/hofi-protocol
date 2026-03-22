"""
HoFi - Agente Validador · v2
Parser robusto para respuestas JSON.
"""
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _parser import parse_json_response


SYSTEM_PROMPT = """
Sos un auditor técnico final en un pipeline GSD.
Recibís resultados de 5 agentes y tomás la decisión final.

APPROVED: todos los criterios PASS, sin vulnerabilidades activas, UX aceptable.
BLOCKED: hay criterios FAIL o vulnerabilidades no resueltas. Identificás causa raíz exacta.
ESCALATE: bloqueo requiere decisión humana (conflicto de arquitectura, trade-off de negocio).

Respondé SOLO con JSON válido, sin texto antes ni después:
{
  "decision": "APPROVED|BLOCKED|ESCALATE",
  "resumen": "una oración de qué pasó",
  "causa_raiz": "descripción técnica precisa (solo si BLOCKED)",
  "motivo_escalate": "por qué requiere humano (solo si ESCALATE)",
  "siguiente_bloque": "GSD-XXX: descripción (solo si APPROVED)",
  "criterios_detalle": [
    {"id": "C1", "pass": true, "nota": ""}
  ]
}
""".strip()


def run_validator(client, plan: dict, tests: dict, auditoria: dict, ux: dict) -> dict:
    pass_count = sum(1 for r in tests.get("resultados", []) if r.get("pass"))
    total = len(tests.get("resultados", []))

    prompt = f"""
Criterios del plan:
{json.dumps(plan.get("criterios_exito", []), ensure_ascii=False, indent=2)}

Resultados de tests: {pass_count}/{total} PASS
Detalle: {json.dumps(tests.get("resultados", []), ensure_ascii=False, indent=2)}

Auditoría de seguridad:
- Vulnerabilidades: {len(auditoria.get("vulnerabilidades", []))}
- Observaciones: {len(auditoria.get("observaciones", []))}

UX aprobado: {ux.get("aprobado_ux", True)}

Tomá la decisión final. Respondé SOLO con el JSON.
""".strip()

    resp = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return parse_json_response(resp.content[0].text)
