"""
HoFi - Agente Mediador UX · v2
Usa delimitadores en lugar de JSON con código embebido.
"""
import re
import json


SYSTEM_PROMPT = """
Sos un diseñador de producto especializado en seguridad UX.
Revisás que las medidas de seguridad implementadas no generen fricción innecesaria.

Principios:
- La seguridad no es negociable. Solo ajustás presentación y flujo, nunca el nivel de protección.
- Los errores deben explicar qué hacer a continuación, no solo qué salió mal.
- Los límites (rate limiting) deben comunicarse claramente al usuario.

Evaluá el código recibido y respondé con este formato EXACTO usando delimitadores:

===EVALUACION===
descripción breve del estado UX actual (2-3 oraciones)
===FIN===

===AJUSTE: tipo===
archivo: ruta/archivo.py
descripcion: qué ajustar y por qué
cambio: fragmento exacto antes → después
===FIN===

===APROBADO===
true
===FIN===

Si no hay ajustes necesarios, no incluyas bloques ===AJUSTE===.
Tipos válidos: mensaje_error, flujo, validacion, documentacion.
Máximo 3 ajustes. Sé conciso.
""".strip()


def run_ux_mediator(client, plan: dict, codigo: dict, auditoria: dict) -> dict:
    archivos_resumen = {
        k: v[:400] + ("..." if len(v) > 400 else "")
        for k, v in codigo.get("archivos", {}).items()
    }

    restricciones = auditoria.get("observaciones", [])

    prompt = f"""
Plan implementado:
{json.dumps(plan.get("criterios_exito", []), ensure_ascii=False, indent=2)}

Archivos (resumen):
{json.dumps(list(archivos_resumen.keys()), indent=2)}

Restricciones de seguridad aplicadas:
{len(restricciones)} observaciones registradas

Evaluá la experiencia de usuario del rate limiting y mensajes de error.
""".strip()

    resp = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    texto = resp.content[0].text

    # Parsear evaluación
    evaluacion = ""
    match_eval = re.search(r'===EVALUACION===\s*(.*?)\s*===FIN===', texto, re.DOTALL)
    if match_eval:
        evaluacion = match_eval.group(1).strip()

    # Parsear ajustes
    ajustes = []
    for match in re.finditer(r'===AJUSTE: (.+?)===\s*(.*?)\s*===FIN===', texto, re.DOTALL):
        tipo = match.group(1).strip()
        contenido = match.group(2).strip()
        ajustes.append({"tipo": tipo, "contenido": contenido})

    # Parsear aprobación
    aprobado = True
    match_aprov = re.search(r'===APROBADO===\s*(.*?)\s*===FIN===', texto, re.DOTALL)
    if match_aprov:
        aprobado = match_aprov.group(1).strip().lower() == "true"

    return {
        "evaluacion_general": evaluacion,
        "ajustes": ajustes,
        "codigo_ajustado": codigo,
        "aprobado_ux": aprobado,
    }
