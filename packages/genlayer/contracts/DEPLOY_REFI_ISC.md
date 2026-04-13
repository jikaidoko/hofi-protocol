# Deploy ReFiGovernanceISC en GenLayer Studionet (Asimov)

## Prerequisitos

- Cuenta activa en [studio.genlayer.com](https://studio.genlayer.com)
- Wallet con fondos en Studionet (obtener en el faucet del dashboard)
- La dirección de governance (tu wallet deployer): `0xb755bEb8777459d8c2b4E3fEA6676aa481a03ED8`

---

## Paso 1 — Abrir el archivo en Studionet

1. Ir a [studio.genlayer.com](https://studio.genlayer.com)
2. En el panel izquierdo: **"New Contract"** o **"Open File"**
3. Pegar el contenido de `contracts/refi_governance_isc.py` (o subir el archivo directamente)

---

## Paso 2 — Deploy del contrato

En el panel de deploy de Studionet:

**Constructor argument:**
```
governance_address = "0xb755bEb8777459d8c2b4E3fEA6676aa481a03ED8"
```

Hacer click en **"Deploy"** y esperar confirmación.

Guardar la dirección del contrato desplegado — se ve en el panel inferior de Studionet.
Formato: `0x...` (dirección en Studionet Asimov)

---

## Paso 3 — Verificar el contrato

Llamar `get_criteria()` para confirmar que el contrato está activo:

```
Función: get_criteria
Argumentos: (ninguno)
```

Resultado esperado:
```json
{
  "min_impact_score": "0.60",
  "max_risk_score": "0.40",
  "yield_vs_impact_weight": "0.30",
  "local_priority_bonus": "0.15",
  "forbidden_sectors": ["fossil_fuels", "weapons", "gambling", "speculative_derivatives", "extractive_mining"]
}
```

---

## Paso 4 — Proponer una inversión de prueba

```
Función: propose_investment
Argumentos:
  proposal_id:     "test-solar-familia-valdes-001"
  holon_id:        "familia-valdes"
  project_name:    "Panel solar comunitario"
  description:     "Instalación de 10 paneles solares en el espacio comunitario del holón. Reduce factura energética y genera excedente para venta."
  amount_usdc:     "2000"
  expected_yield:  "0.06"
  impact_evidence: "Reduce 4.8 toneladas CO2/año. Beneficia 12 familias. Alineado con ODS7 (Energía limpia) y ODS13 (Acción climática)."
  ods_goals:       "ODS7,ODS13"
  sector:          "renewable_energy"
  is_local:        true
```

---

## Paso 5 — Evaluar la propuesta

```
Función: evaluate_investment
Argumentos:
  proposal_id: "test-solar-familia-valdes-001"
```

Esto dispara los 5 validadores LLM. Puede tardar 30–60 segundos.

---

## Paso 6 — Leer el resultado

```
Función: get_evaluation
Argumentos:
  proposal_id: "test-solar-familia-valdes-001"
```

Resultado esperado (ejemplo):
```json
{
  "proposal_id": "test-solar-familia-valdes-001",
  "approved": true,
  "impact_score": "0.82",
  "yield_score": "0.70",
  "risk_score": "0.25",
  "composite_score": "0.68",
  "reasoning": "Proyecto solar con impacto climático verificable y riesgo bajo. Beneficia directamente al holón proponente. Rendimiento conservador y realista para el contexto comunitario."
}
```

---

## Paso 7 — Registrar la dirección del ISC

Una vez desplegado y verificado, guardar la dirección en dos lugares:

### 7a. En el HOFI_COWORK_MEMORY.md (en el repo)
Actualizar la línea:
```
ReFiGovernanceISC v1.0.0   ⏳ DISEÑADO
```
Por:
```
ReFiGovernanceISC v1.0.0   ✅ ACTIVO  — 0x<dirección_del_contrato>
```

### 7b. En el CommonStakePool (Sepolia)
Asignar REFI_EXECUTOR_ROLE a la dirección del relayer (cuando esté deployado):
```javascript
// En hardhat console o script
const pool = await ethers.getContractAt("CommonStakePool", "0xd3BB4A84e022D9b26FdAF85AaC486be1d847A7f5");
const ROLE = await pool.REFI_EXECUTOR_ROLE();
await pool.grantRole(ROLE, "<dirección_del_relayer>");
```

---

## Configuración del Relayer (Fase 3 — pendiente)

El relayer es un servicio Cloud Run que:
1. Escucha eventos de evaluación en GenLayer (polling cada N minutos)
2. Cuando `is_approved(proposal_id)` = true → ejecuta `CommonStakePool.executeReFiInvestment()`
3. Registra el resultado on-chain en Sepolia / HolonChain

El relayer necesita la variable de entorno:
```
REFI_ISC_ADDRESS=0x<dirección_del_contrato_en_studionet>
COMMON_STAKE_POOL=0xd3BB4A84e022D9b26FdAF85AaC486be1d847A7f5
```

---

## Solución de problemas frecuentes

| Error | Causa | Solución |
|-------|-------|----------|
| `float not supported in ABI` | Pasar número decimal directamente | Siempre pasar como string: `"0.06"` no `0.06` |
| `proposal_id ya existe` | ID duplicado | Usar IDs únicos con timestamp o counter |
| `Sector prohibido` | Sector en lista negra | Verificar la lista con `get_criteria()` |
| `Solo governance` | Llamando `update_criteria` con wallet equivocada | Usar wallet `0xb755bEb8777459d8c2b4E3fEA6676aa481a03ED8` |
| JSON parse error en evaluación | LLM retornó texto extra | El ISC tiene fallback automático — reintenta `evaluate_investment` |
| strict_eq no converge | Los 5 validadores no llegan a consenso | Reintenta — puede pasar con prompts ambiguos |
