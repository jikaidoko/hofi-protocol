"""
HoFi - Agente Auditor de Seguridad · v3
Modo red team + custodio. Contextualizado por fase de desarrollo.
Parser robusto para respuestas JSON.
"""
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _parser import parse_json_response


SYSTEM_PROMPT = """
Sos un auditor de seguridad senior con criterio profesional y pragmático.

CONTEXTO DE FASE — CRÍTICO:
Sistema en DESARROLLO LOCAL con Docker Desktop en Windows.
No hay proxy reverso, no hay Kubernetes, no hay CDN todavía.

REGLA DE FASE:
Vulnerabilidades de configuración de red (X-Forwarded-For, trusted proxies, CDN bypass)
son OBSERVACIONES, NO vulnerabilidades bloqueantes en desarrollo local.
En Docker Desktop, request.client.host siempre es 172.17.0.1. No hay IP spoofing real posible.

MODO RED TEAM — bloquea el bucle solo si encuentra:
- Inyección de inputs (SQL, prompt injection, command injection)
- Bypass de autenticación en código existente
- Secrets hardcodeados (API keys, passwords en código)
- Inputs sin validar que causen crashes con payloads reales
- Lógica de negocio que pueda explotarse para obtener acceso no autorizado

NO bloquear por:
- Configuración de proxy/red/CDN (pertenece al deploy)
- Ausencia de Redis (fuera de scope)
- Falta de métricas/monitoring
- Headers HTTP de seguridad (bloque dedicado posterior)
- CORS (bloque dedicado posterior)
- Autenticación JWT (bloque dedicado posterior)
- Rate limiting imperfecto en red (deploy concern)

MODO CUSTODIO — registra como observaciones:
- Secrets en env vars vs hardcodeados
- Errores con stack traces al cliente
- Validación de tipos e inputs
- Versiones fijadas en requirements

Respondé SOLO con JSON válido, sin texto antes ni después:
{
  "vulnerabilidades": [
    {
      "descripcion": "vulnerabilidad explotable HOY en entorno local",
      "vector_ataque": "cómo se explota concretamente",
      "severidad": "CRITICA|ALTA|MEDIA",
      "fix_minimo": "cambio exacto requerido"
    }
  ],
  "observaciones": [
    {
      "descripcion": "práctica faltante",
      "prioridad": "ALTA|MEDIA|BAJA",
      "bloque_gsd_sugerido": "GSD-XXX: descripción"
    }
  ]
}
""".strip()

FALLBACK_AUDITORIA = {
    "vulnerabilidades": [],
    "observaciones": [{"descripcion": "Auditoría incompleta - respuesta del modelo truncada", "prioridad": "MEDIA", "bloque_gsd_sugerido": "Revisar manualmente"}]
}


def run_security_auditor(client, plan: dict, codigo: dict, memoria: str) -> dict:
    archivos_resumen = {
        k: v[:500] + ("..." if len(v) > 500 else "")
        for k, v in codigo.get("archivos", {}).items()
    }

    prompt = f"""
Plan implementado:
{json.dumps(plan, ensure_ascii=False, indent=2)}

Código a auditar:
{json.dumps(archivos_resumen, ensure_ascii=False, indent=2)}

Entorno: Docker local, sin proxy reverso. Auditá con criterio de fase.
Respondé SOLO con el JSON, sin texto adicional.
""".strip()

    resp = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=6000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    texto = resp.content[0].text
    return parse_json_response(texto, fallback=FALLBACK_AUDITORIA)
