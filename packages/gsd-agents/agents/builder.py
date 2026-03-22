"""
HoFi - Agente Constructor · v2
Genera código usando delimitadores en lugar de JSON embebido.
Más robusto: evita errores de parsing por comillas/backslashes en código.
"""
import re


SYSTEM_PROMPT = """
Sos un programador Python/FastAPI senior especializado en microservicios.
Tu trabajo es escribir el código mínimo necesario para cumplir exactamente los criterios del plan.

Reglas estrictas:
- Sin gold-plating: no agregás features que no estén en los criterios.
- Sin TODOs: el código que entregás funciona o falla con un error claro.
- Seguridad básica siempre: inputs validados, secrets en env vars, errores sin stack traces al cliente.

Formato de respuesta OBLIGATORIO — usá exactamente estos delimitadores:

===ARCHIVO: ruta/archivo.py===
contenido completo del archivo aquí
===FIN===

===ARCHIVO: ruta/otro.py===
contenido completo aquí
===FIN===

===INSTALACION===
pip install paquete==version
===FIN===

===VARIABLES===
NOMBRE_VAR=descripcion
===FIN===

===NOTAS===
decisiones técnicas relevantes
===FIN===

No uses JSON. No uses markdown adicional. Solo los delimitadores exactos.
""".strip()


def run_builder(client, plan: dict, memoria: str) -> dict:
    import json
    prompt = f"""
Plan a implementar:
{json.dumps(plan, ensure_ascii=False, indent=2)}

Contexto del proyecto:
{memoria[:2000]}

Generá el código usando los delimitadores indicados.
""".strip()

    resp = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    texto = resp.content[0].text

    # Parsear archivos
    archivos = {}
    patron_archivo = r'===ARCHIVO: (.+?)===\n(.*?)===FIN==='
    for match in re.finditer(patron_archivo, texto, re.DOTALL):
        ruta     = match.group(1).strip()
        contenido = match.group(2).strip()
        archivos[ruta] = contenido

    # Parsear instalación
    instalacion = []
    match_inst = re.search(r'===INSTALACION===\n(.*?)===FIN===', texto, re.DOTALL)
    if match_inst:
        instalacion = [l.strip() for l in match_inst.group(1).strip().splitlines() if l.strip()]

    # Parsear variables
    variables = []
    match_vars = re.search(r'===VARIABLES===\n(.*?)===FIN===', texto, re.DOTALL)
    if match_vars:
        variables = [l.strip() for l in match_vars.group(1).strip().splitlines() if l.strip()]

    # Parsear notas
    notas = ""
    match_notas = re.search(r'===NOTAS===\n(.*?)===FIN===', texto, re.DOTALL)
    if match_notas:
        notas = match_notas.group(1).strip()

    if not archivos:
        # Fallback: si no encontró delimitadores, guardar el texto completo
        archivos["output.txt"] = texto

    return {
        "archivos": archivos,
        "comandos_instalacion": instalacion,
        "variables_entorno_requeridas": variables,
        "notas": notas,
    }
