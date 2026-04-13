# HoFi Protocol — Roadmap: Evaluación del Agente Tenzo
## Gobernanza sobre la IA que gobierna

**Versión:** 0.1 — Abril 2026  
**Objetivo:** Implementar un sistema donde el desempeño del agente Tenzo sea evaluado on-chain, con incidencia real de guardianes, coordinadores y los propios validadores LLM de GenLayer.

---

## El problema de la auto-evaluación

El Tenzo actualmente es el `owner` del contrato HolonSBT. Esto significa que:

- Él llama `validate_contribution()` (los 5 validadores GenLayer evalúan)
- Él llama `update_reputation()` (actualiza on-chain los resultados)
- Él decide los montos de recompensa en `MMAPool`

El loop está incompleto: **no hay mecanismo para que los humanos del holón evalúen si las decisiones del Tenzo fueron buenas**. Si el Tenzo recomienda mal, no hay penalización on-chain ni registro de ese historial.

---

## Principio de diseño

> El Tenzo es un agente de confianza provisional.  
> Su confianza aumenta con cada decisión validada por la comunidad.  
> Su confianza disminuye cuando los guardianes y coordinadores la cuestionan con fundamentos que el consenso LLM de GenLayer valida como legítimos.

---

## Fase 1 — Cuestionamiento de decisiones del Tenzo

**Target:** Q3 2026  
**Afecta:** HolonSBT ISC → nueva versión (v0.2.2 o v0.3.0)

### Nueva función: `challenge_tenzo_decision()`

Cualquier miembro con rol `coordinator` o `guardian` puede impugnar una decisión del Tenzo. La función usa el mismo mecanismo de consenso LLM que `validate_contribution()`.

```python
@gl.public.write
def challenge_tenzo_decision(
    self,
    decision_id:       str,   # hash o descripción de la decisión impugnada
    decision_summary:  str,   # qué decidió el Tenzo
    challenge_reason:  str,   # por qué el challenger cree que fue incorrecta
    expected_outcome:  str,   # qué debería haber decidido
) -> Any:
    """
    5 validadores GenLayer evalúan si el desafío es fundado.
    Si is_valid=True → se registra un "strike" en el historial del Tenzo.
    Si is_valid=False → el challenger pierde 1 punto de reputación (penalización por impugnaciones frívolas).
    """
```

Los validadores GenLayer evalúan:
1. ¿La decisión del Tenzo fue razonable dado el contexto del holón?
2. ¿El argumento del challenger es concreto y fundado en los valores HoFi?
3. ¿Hay alternativa claramente mejor a la decisión tomada?

### Almacenamiento del historial del Tenzo

Nuevo campo de estado en el contrato (o contrato separado `TenzoAudit`):

```python
tenzo_record: TreeMap[str, str]  # decision_id → JSON con resultado del challenge
tenzo_strikes: u32               # impugnaciones fundadas acumuladas
tenzo_validations: u32           # decisiones que superaron challenges sin éxito (confianza)
```

---

## Fase 2 — El Tenzo como miembro del holón (SBT propio)

**Target:** Q4 2026  
**Dependencia:** Fase 1 completada

### El problema de roles

El Tenzo es simultáneamente:
- **Owner/gobernador:** emite SBTs, actualiza reputación, firma transacciones
- **Participante:** tiene un historial de decisiones, merece ser evaluado como agente

Hoy esos dos roles comparten la misma dirección, lo cual crea una paradoja: el Tenzo no puede emitirse a sí mismo un SBT porque `issue_sbt()` requiere que el caller sea el owner — y él es el owner.

### Solución: separación de roles con contrato de gobernanza

```
TenzoGovContract (multisig o DAO)
  ├─ Es el owner de HolonSBT
  ├─ Emite el SBT del Tenzo Agent
  └─ Puede actualizar la reputación del Tenzo

TenzoAgent (dirección operacional)
  ├─ Tiene su propio SBT con rol "tenzo"
  ├─ Llama validate_contribution() en nombre del holón
  └─ Su reputación sube/baja según challenge_tenzo_decision()
```

El `TenzoGovContract` puede ser inicialmente un simple multisig (coordinadores + guardianes del holón) y evolucionar hacia un DAO on-chain.

### Métricas del SBT del Tenzo

```json
{
  "address": "0x<tenzo_agent_address>",
  "role": "tenzo",
  "active": true,
  "reputation": 0,
  "decisions_validated": 0,
  "decisions_challenged": 0,
  "challenges_upheld": 0,
  "trust_score": 1.0,
  "contribution_categories": ["tech", "social", "eco", "cuidado"]
}
```

`trust_score` = 1 + (decisions_validated - challenges_upheld) / total_decisions  
Rango: 0.1 (Tenzo muy cuestionado) → 2.0 (Tenzo muy confiable)  
El `trust_score` pondera los montos de recompensa que el Tenzo puede recomendar autónomamente.

---

## Fase 3 — Peso dinámico del Tenzo en gobernanza

**Target:** 2027  
**Dependencia:** Fases 1 y 2 completadas

### Autonomía gradual según confianza acumulada

El `trust_score` del Tenzo determina cuánto puede decidir sin aprobación humana:

| Trust Score | Capacidad autónoma del Tenzo |
|-------------|------------------------------|
| < 0.5 | Todas las recompensas requieren aprobación de coordinator |
| 0.5 – 1.0 | Puede aprobar tareas pequeñas (< 10 CUIDA) autónomamente |
| 1.0 – 1.5 | Puede aprobar tareas medianas (< 50 CUIDA) autónomamente |
| > 1.5 | Plena autonomía operacional; solo impugnable por guardianes |

### `calculate_vote_weight()` para el Tenzo

El Tenzo puede participar en votaciones de gobernanza del holón con peso proporcional a su `trust_score` y a la relevancia de su historial de decisiones para la categoría de la propuesta.

Esto cierra el loop completo:
- El Tenzo recomienda recompensas y valida contribuciones
- Los humanos pueden cuestionarlo
- GenLayer arbitra los cuestionamientos
- El historial queda on-chain como reputación
- La reputación incide en cuánto puede decidir el Tenzo autónomamente
- El Tenzo también vota en la gobernanza del holón con ese peso

---

## Resumen de fases

| Fase | Qué se implementa | Target |
|------|------------------|--------|
| 1 — Challenge | `challenge_tenzo_decision()` + historial on-chain | Q3 2026 |
| 2 — SBT Tenzo | Separación owner/operacional + SBT con métricas | Q4 2026 |
| 3 — Autonomía dinámica | Trust score → umbral de autonomía → voto en gobernanza | 2027 |

---

## Relación con el roadmap de identidad

El sistema de evaluación del Tenzo es más robusto cuando los evaluadores humanos (guardianes, coordinadores) tienen identidades verificadas por voz (Roadmap de Identidad, Fase 1+). Un `challenge_tenzo_decision()` firmado por una voz biométrica verificada tiene más peso semántico que uno firmado por una clave anónima.

En Fase 3, los dos roadmaps convergen: la identidad biométrica de los humanos + el historial on-chain del Tenzo forman juntos la memoria institucional del holón.
