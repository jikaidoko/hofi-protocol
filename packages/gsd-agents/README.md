# HoFi · Sistema GSD Automatizado — SDK Anthropic

## Arquitectura

```
supervisor.py
├── agents/planner.py    — Define tarea atómica y criterios
├── agents/builder.py    — Escribe el código mínimo
├── agents/runner.py     — Ejecuta tests y captura resultados
├── agents/security.py   — Red team + custodio de buenas prácticas
├── agents/ux.py         — Balancea seguridad con usabilidad
└── agents/validator.py  — Decisión final: APPROVED / BLOCKED / ESCALATE
```

## Setup

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY="tu-clave"
```

## Uso

```bash
# Ejecutar un bloque GSD
python supervisor.py --bloque "GSD-005: conectar Cloud SQL al Agente Tenzo"

# Con máximo de reintentos personalizado
python supervisor.py --bloque "GSD-006: agregar autenticación JWT" --max-reintentos 5
```

## Salida de cada iteración

```
══════════════════════════════════════════════════════
  GSD-005: conectar Cloud SQL al Agente Tenzo
  Estado      : APROBADO
  Tiempo      : 87.3s
  Reintentos  : 1
══════════════════════════════════════════════════════
  DEUDA DE SEGURIDAD REGISTRADA:
    · [ALTA] Sin rate limiting en /evaluar → GSD futuro obligatorio
    · [MEDIA] Logs sin nivel de severidad → GSD futuro obligatorio
══════════════════════════════════════════════════════
  Siguiente    : GSD-006: agregar autenticación JWT
══════════════════════════════════════════════════════
```

## Flujo del bucle GSD

1. **Planificador** — tarea atómica + criterios binarios
2. **Constructor** — código mínimo sin gold-plating
3. **Ejecutor** — tests reales con subprocess/docker
4. **Auditor de seguridad** — red team + custodio de prácticas
   - Vulnerabilidad → reinicia al Constructor (bloqueo duro)
   - Observación → registra en memory.md como GSD futuro (no bloquea)
5. **Mediador UX** — ajusta friction sin reducir protección
6. **Validador** — APPROVED / BLOCKED / ESCALATE

## Memoria compartida

`memory.md` es el contexto compartido entre todos los agentes y entre bloques GSD.
Se actualiza automáticamente al aprobar cada bloque.
