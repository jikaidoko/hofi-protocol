"""
HoFi - Agente Ejecutor · v2
Genera tests como lista simple, ejecuta con subprocess, reporta PASS/FAIL.
"""
import json
import subprocess
import tempfile
from pathlib import Path


SYSTEM_PROMPT = """
Sos un ingeniero de QA especializado en testing de microservicios FastAPI.
Tu trabajo es generar los comandos exactos para verificar cada criterio del plan.

Formato de respuesta OBLIGATORIO — un test por bloque:

===TEST: C1===
DESCRIPCION: qué verifica este test
COMANDO: curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/health
ESPERADO: 200
===FIN===

===TEST: C2===
DESCRIPCION: verifica que /evaluar responde
COMANDO: curl -s -X POST http://localhost:8080/evaluar -H "Content-Type: application/json" -d "{\"titulo\":\"test\",\"descripcion\":\"test\",\"categoria\":\"cocina_comunal\",\"duracion_horas\":1.0}"
ESPERADO: aprobada
===FIN===

===SETUP===
comando de setup previo si es necesario (o dejar vacío)
===FIN===

===TEARDOWN===
comando de limpieza si es necesario (o dejar vacío)
===FIN===

Reglas:
- Usá solo curl, python -c, o comandos básicos de shell disponibles en Windows/PowerShell
- Los comandos deben funcionar contra localhost
- ESPERADO es un string que debe aparecer en el output del comando
""".strip()


def ejecutar_comando(comando: str, timeout: int = 30) -> tuple:
    try:
        result = subprocess.run(
            comando, shell=True, capture_output=True,
            text=True, timeout=timeout,
        )
        output = (result.stdout + result.stderr).strip()
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, f"TIMEOUT después de {timeout}s"
    except Exception as e:
        return False, f"ERROR: {e}"


def escribir_archivos_temp(archivos: dict) -> Path:
    tmpdir = Path(tempfile.mkdtemp(prefix="hofi_gsd_"))
    for ruta, contenido in archivos.items():
        destino = tmpdir / ruta
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(contenido, encoding="utf-8")
    return tmpdir


def run_runner(client, plan: dict, codigo: dict) -> dict:
    import re

    archivos_resumen = {
        k: v[:300] + "..." for k, v in codigo.get("archivos", {}).items()
    }

    prompt = f"""
Plan con criterios a verificar:
{json.dumps(plan.get("criterios_exito", []), ensure_ascii=False, indent=2)}

Archivos generados:
{json.dumps(list(archivos_resumen.keys()), indent=2)}

Los servicios corriendo son:
- Tenzo: http://localhost:8080
- Orquestador: http://localhost:8090

Generá los tests para verificar cada criterio.
""".strip()

    resp = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    texto = resp.content[0].text

    # Parsear tests
    tests_parsed = []
    patron = r'===TEST: (\w+)===\s*DESCRIPCION: (.+?)\s*COMANDO: (.+?)\s*ESPERADO: (.+?)\s*===FIN==='
    for match in re.finditer(patron, texto, re.DOTALL):
        tests_parsed.append({
            "criterio_id": match.group(1).strip(),
            "descripcion":  match.group(2).strip(),
            "comando":      match.group(3).strip(),
            "esperado":     match.group(4).strip(),
        })

    # Setup
    match_setup = re.search(r'===SETUP===\s*(.*?)\s*===FIN===', texto, re.DOTALL)
    if match_setup:
        setup_cmd = match_setup.group(1).strip()
        if setup_cmd:
            ejecutar_comando(setup_cmd)

    # Ejecutar tests
    resultados = []
    for test in tests_parsed:
        exito, output = ejecutar_comando(test["comando"])
        esperado = test["esperado"].lower()
        passed = esperado in output.lower() if esperado else exito

        resultados.append({
            "criterio_id": test["criterio_id"],
            "descripcion": test["descripcion"],
            "comando":     test["comando"],
            "pass":        passed,
            "output":      output[:200],
            "esperado":    test["esperado"],
        })

    # Teardown
    match_tear = re.search(r'===TEARDOWN===\s*(.*?)\s*===FIN===', texto, re.DOTALL)
    if match_tear:
        tear_cmd = match_tear.group(1).strip()
        if tear_cmd:
            ejecutar_comando(tear_cmd)

    return {
        "resultados":  resultados,
        "todos_pass":  all(r["pass"] for r in resultados),
        "raw_tests":   len(tests_parsed),
    }
