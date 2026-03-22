"""
HoFi · Supervisor GSD — SDK de Anthropic
Orquesta el bucle completo: Planificador → Constructor → Ejecutor
→ Auditor de Seguridad → Mediador UX → Validador

Uso:
    python supervisor.py --bloque "GSD-005: conectar Cloud SQL"
    python supervisor.py --bloque "GSD-005: conectar Cloud SQL" --max-reintentos 3
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import anthropic

from agents.planner   import run_planner
from agents.builder   import run_builder
from agents.runner    import run_runner
from agents.security  import run_security_auditor
from agents.ux        import run_ux_mediator
from agents.validator import run_validator

# ── Config ─────────────────────────────────────────────────────────────────
MAX_REINTENTOS_DEFAULT = 3
MEMORY_FILE = Path("memory.md")
REPORT_DIR  = Path("reports")
REPORT_DIR.mkdir(exist_ok=True)

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


# ── Memoria compartida ──────────────────────────────────────────────────────
def leer_memoria() -> str:
    if MEMORY_FILE.exists():
        return MEMORY_FILE.read_text(encoding="utf-8")
    return "# HoFi · Memoria del proyecto\n\n(sin contexto previo)"

def actualizar_memoria(seccion: str, contenido: str):
    mem = leer_memoria()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entrada = f"\n\n## {seccion} — {timestamp}\n{contenido}"
    MEMORY_FILE.write_text(mem + entrada, encoding="utf-8")


# ── Reporte de bucle ────────────────────────────────────────────────────────
def generar_reporte(bloque: str, resultado: dict, duracion: float) -> str:
    estado   = "APROBADO" if resultado["aprobado"] else "BLOQUEADO"
    reinten  = resultado.get("reintentos", 0)
    bloqueos = resultado.get("bloqueos", [])
    deuda    = resultado.get("deuda_seguridad", [])

    lineas = [
        "═" * 54,
        f"  {bloque}",
        f"  Estado      : {estado}",
        f"  Tiempo      : {duracion:.1f}s",
        f"  Reintentos  : {reinten}",
        "═" * 54,
    ]
    if bloqueos:
        lineas.append("  BLOQUEOS DETECTADOS:")
        for b in bloqueos:
            lineas.append(f"    → {b}")
    if deuda:
        lineas.append("  DEUDA DE SEGURIDAD REGISTRADA:")
        for d in deuda:
            lineas.append(f"    · {d}")
    if resultado.get("siguiente"):
        lineas.append(f"  Siguiente    : {resultado['siguiente']}")
    lineas.append("═" * 54)
    return "\n".join(lineas)


# ── Bucle principal ─────────────────────────────────────────────────────────
def ejecutar_bucle(bloque: str, max_reintentos: int) -> dict:
    memoria = leer_memoria()
    resultado = {
        "aprobado": False,
        "reintentos": 0,
        "bloqueos": [],
        "deuda_seguridad": [],
        "siguiente": "",
    }
    contexto_actual = {}

    for intento in range(1, max_reintentos + 1):
        print(f"\n{'─'*54}")
        print(f"  Intento {intento}/{max_reintentos} — {bloque}")
        print(f"{'─'*54}")

        # ── 1. Planificador ────────────────────────────────────────────
        print("\n[1/6] Planificador...")
        plan = run_planner(client, bloque, memoria, contexto_actual.get("bloqueos", []))
        print(f"      Tarea: {plan.get('tarea_atomica', '')[:60]}...")
        contexto_actual["plan"] = plan

        # ── 2. Constructor ─────────────────────────────────────────────
        print("\n[2/6] Constructor...")
        codigo = run_builder(client, plan, memoria)
        contexto_actual["codigo"] = codigo
        print(f"      Archivos: {', '.join(codigo.get('archivos', {}).keys())}")

        # ── 3. Ejecutor ────────────────────────────────────────────────
        print("\n[3/6] Ejecutor...")
        tests = run_runner(client, plan, codigo)
        contexto_actual["tests"] = tests
        pass_count = sum(1 for r in tests.get("resultados", []) if r.get("pass"))
        total      = len(tests.get("resultados", []))
        print(f"      Tests: {pass_count}/{total} PASS")

        # ── 4. Auditor de Seguridad ────────────────────────────────────
        print("\n[4/6] Auditor de seguridad...")
        auditoria = run_security_auditor(client, plan, codigo, memoria)
        vuln      = auditoria.get("vulnerabilidades", [])
        obs       = auditoria.get("observaciones", [])
        print(f"      Vulnerabilidades: {len(vuln)} | Observaciones: {len(obs)}")
        contexto_actual["auditoria"] = auditoria

        if obs:
            resultado["deuda_seguridad"].extend(
                [f"[{o.get('prioridad','?')}] {o.get('descripcion','')}" for o in obs]
            )
            actualizar_memoria(
                f"Deuda de seguridad — {bloque}",
                "\n".join(f"- [{o.get('prioridad')}] {o.get('descripcion')} → GSD futuro obligatorio"
                          for o in obs)
            )

        if vuln:
            bloqueo_msg = f"Vulnerabilidad [{vuln[0].get('severidad')}]: {vuln[0].get('descripcion','')}"
            print(f"      BLOQUEADO: {bloqueo_msg}")
            resultado["bloqueos"].append(bloqueo_msg)
            resultado["reintentos"] = intento
            contexto_actual["bloqueos"] = [
                f"Fix de seguridad requerido: {v.get('fix_minimo','')}" for v in vuln
            ]
            continue

        # ── 5. Mediador UX ─────────────────────────────────────────────
        print("\n[5/6] Mediador UX...")
        ux = run_ux_mediator(client, plan, codigo, auditoria)
        ajustes = ux.get("ajustes", [])
        print(f"      Ajustes UX: {len(ajustes)}")
        if ajustes:
            contexto_actual["codigo"] = ux.get("codigo_ajustado", codigo)

        # ── 6. Validador ───────────────────────────────────────────────
        print("\n[6/6] Validador...")
        validacion = run_validator(client, plan, tests, auditoria, ux)
        decision   = validacion.get("decision", "BLOCKED")
        print(f"      Decision: {decision}")

        if decision == "APPROVED":
            resultado["aprobado"]  = True
            resultado["reintentos"] = intento - 1
            resultado["siguiente"] = validacion.get("siguiente_bloque", "")
            actualizar_memoria(
                f"Completado — {bloque}",
                f"Archivos: {list(codigo.get('archivos', {}).keys())}\n"
                f"Siguiente: {resultado['siguiente']}"
            )
            return resultado

        elif decision == "ESCALATE":
            print("\n  ESCALATE: requiere decision humana.")
            print(f"  Motivo: {validacion.get('motivo_escalate', '')}")
            resultado["bloqueos"].append(
                f"ESCALATE: {validacion.get('motivo_escalate', '')}"
            )
            return resultado

        else:
            bloqueo_msg = validacion.get("causa_raiz", "Criterios no cumplidos")
            resultado["bloqueos"].append(bloqueo_msg)
            resultado["reintentos"] = intento
            contexto_actual["bloqueos"] = [bloqueo_msg]

    return resultado


# ── Entry point ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="HoFi GSD Supervisor")
    parser.add_argument("--bloque", required=True, help='Ej: "GSD-005: conectar Cloud SQL"')
    parser.add_argument("--max-reintentos", type=int, default=MAX_REINTENTOS_DEFAULT)
    args = parser.parse_args()

    print(f"\n{'═'*54}")
    print(f"  HoFi · Supervisor GSD")
    print(f"  Bloque: {args.bloque}")
    print(f"  Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'═'*54}")

    t0 = time.time()
    resultado = ejecutar_bucle(args.bloque, args.max_reintentos)
    duracion  = time.time() - t0

    reporte = generar_reporte(args.bloque, resultado, duracion)
    print(f"\n{reporte}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_bloque = args.bloque.replace(" ", "_").replace(":", "").replace("/", "-")
    ruta_reporte  = REPORT_DIR / f"{nombre_bloque}_{ts}.txt"
    ruta_reporte.write_text(reporte, encoding="utf-8")
    print(f"\n  Reporte guardado: {ruta_reporte}")

    sys.exit(0 if resultado["aprobado"] else 1)


if __name__ == "__main__":
    main()
