# HoFi Protocol — Memoria para Claude Cowork
*Actualizado: 13 de abril de 2026 — ReFiGovernanceISC v1.1.0 desplegado en Studionet ✅ + diagnóstico gen_call Bradbury roto ✅*

---

## CONTEXTO DEL PROYECTO

HoFi (Holistic Finance) — protocolo de economía regenerativa que hace visible el
trabajo de cuidado comunitario y lo recompensa con tokens on-chain.

**Filosofía:** "The act of caring is the yield." / Espíritu del bodhisattva: brindarse sin esperar reconocimiento.
**Pablo Valdés (Doco)** — Arquitecto, monje Zen, cooperativista. Telegram user_id: 2012212775

---

## REPOSITORIO

```
C:\dev\hofi-protocol\
├── packages\
│   ├── tenzo-agent\          ← Tenzo Agent v1.0.0 ✅ PRODUCCIÓN | v1.1.0 diseñado (pendiente deploy)
│   ├── telegram-bot\         ← Bot Telegram ✅ PRODUCCIÓN (Cloud Run)
│   ├── frontend\             ← Next.js 14 — UI completa, login email OK
│   ├── contracts\            ← Smart contracts Solidity (Sepolia)
│   ├── genlayer\             ← ISCs GenLayer
│   └── avalanche\            ← HolonChain subnet config
├── HOFI_COWORK_MEMORY.md     ← este archivo
├── ROADMAP.md                ← chats pendientes detallados
└── VOICE_TENZO_MEMORY.md     ← historia técnica de voz y Tenzo
```

---

## CÓMO EDITAR ARCHIVOS DEL PROYECTO DIRECTAMENTE (leer primero ⚠️)

Esta sección es crítica para cualquier sesión de Cowork que trabaje con este proyecto.
Claude Cowork corre en una VM Linux que tiene la carpeta del usuario **montada en vivo**.
Eso significa que leer y escribir en esa ruta == editar directamente los archivos reales
de `C:\Users\valde\dev\hofi-protocol\` en la computadora de Doco, sin pasos intermedios.

### Ruta raíz del proyecto dentro de la VM

```
/sessions/admiring-epic-edison/mnt/hofi-protocol/
```

Esta ruta ES la carpeta `C:\Users\valde\dev\hofi-protocol\` en Windows.
Todo lo que se escriba aquí aparece inmediatamente en el disco del usuario.

### Método de doble acceso directo

Cowork tiene **dos herramientas de acceso directo** a los archivos del proyecto:
`Read` para leer y `Edit` / `Write` para modificar. La regla de oro:

**Para editar un archivo existente — dos pasos obligatorios:**
```
1. Read   → /sessions/admiring-epic-edison/mnt/hofi-protocol/<ruta/al/archivo>
2. Edit   → mismo path, old_string → new_string
```
El paso 1 es obligatorio: `Edit` falla si el archivo no fue leído antes en la misma sesión.

**Para crear un archivo nuevo — un solo paso:**
```
Write → /sessions/admiring-epic-edison/mnt/hofi-protocol/<ruta/al/archivo nuevo>
```

**Para buscar contenido en el proyecto:**
```
Grep  → pattern="texto a buscar"  path="/sessions/admiring-epic-edison/mnt/hofi-protocol"
Glob  → pattern="**/*.py"         (búsqueda por nombre/extensión)
```

### Ejemplos concretos

```
# Leer un archivo
Read: /sessions/admiring-epic-edison/mnt/hofi-protocol/packages/tenzo-agent/tenzo_agent.py

# Editar una línea (siempre después de leer)
Edit: old_string="0.85"  new_string="0.75"
      file_path="/sessions/admiring-epic-edison/mnt/hofi-protocol/packages/tenzo-agent/tenzo_agent.py"

# Crear un archivo nuevo
Write: /sessions/admiring-epic-edison/mnt/hofi-protocol/packages/tenzo-agent/nuevo_modulo.py

# Buscar todos los archivos Python del proyecto
Glob: pattern="**/*.py"  (desde /sessions/admiring-epic-edison/mnt/hofi-protocol)

# Buscar dónde se usa ORACLE_ADDRESS
Grep: pattern="ORACLE_ADDRESS"  path="/sessions/admiring-epic-edison/mnt/hofi-protocol"
```

### Lo que NO hay que hacer

- ❌ No copiar archivos a `/sessions/admiring-epic-edison/` para trabajarlos —
  editar directamente en la ruta `/mnt/hofi-protocol/`.
- ❌ No usar `present_files` ni `computer://` links para archivos del proyecto —
  eso es para archivos que el usuario quiere descargar/abrir desde afuera.
- ❌ No usar Bash con `cat` o `grep` para leer/buscar — usar `Read` y `Grep` que
  tienen los permisos correctos y dan mejor contexto.
- ❌ No intentar editar sin leer primero — `Edit` siempre requiere `Read` previo.

### Por qué funciona así

Cuando Doco abre Cowork y selecciona su carpeta del proyecto, Cowork monta esa carpeta
en la VM bajo `/sessions/<id-de-sesion>/mnt/<nombre-carpeta>/`. El montaje es en vivo:
cualquier cambio que haga Claude en esa ruta aparece instantáneamente en Windows.
La ruta `/sessions/admiring-epic-edison/` puede cambiar entre sesiones si se crea
una nueva, pero el segmento `/mnt/hofi-protocol/` siempre es el mismo porque
es el nombre de la carpeta seleccionada. Para confirmar la ruta en una sesión nueva:

```bash
# En una herramienta Bash, verificar la ruta activa:
ls /sessions/admiring-epic-edison/mnt/
# → debe mostrar: hofi-protocol
```

---

## INFRAESTRUCTURA GCP

**Proyecto:** `hofi-v2-2026` | **Región:** `us-central1`

### Cloud Run — Bot Telegram
- **URL:** `https://hofi-bot-qpxiby6ona-uc.a.run.app`
- **Deploy:** `packages/telegram-bot/deploy.ps1`
- **Config actual:**
  - `--memory=2Gi` (era 1Gi — OOM fix)
  - `--no-cpu-throttling` (crítico para procesamiento en background post-webhook)
  - `--min-instances=1` — siempre activo
  - `DB_MOCK=true` (perfiles en GCS bucket `hofi-bot-data`)
  - `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1` — evita HuggingFace 429
  - `VOICE_SIMILARITY_THRESHOLD=0.90`
- **Webhook:** `https://hofi-bot-qpxiby6ona-uc.a.run.app/<token>`

### Cloud Run — Tenzo Agent
- **URL:** `https://hofi-tenzo-1080243330445.us-central1.run.app`
- **Config actual:**
  - `MODEL_NAME=gemini-2.5-flash`
  - `DB_MOCK=false` → Cloud SQL conectado para voice_profiles y tasks ✅
  - `ON_CHAIN=false`
  - `CONFIANZA_APROBACION_DIRECTA=0.70` (actualizado — era 0.85)
  - `CERTEZA_MIN_APELAR=0.50` | `CERTEZA_MAX_APELAR=0.70` (actualizado)
- **⚠️ Pendiente deploy v1.1.0** — código diseñado, ver sección TENZO AGENT v1.1.0

### Cloud SQL
- **Instancia:** `hofi-db` (PostgreSQL 15)
- **Base:** `hofi` | **Usuario:** `hofi_user`
  - ⚠️ MEMORY anterior tenía DB_NAME=hofi_db y DB_USER=tenzo_user — INCORRECTO
  - Valores reales: `DB_NAME=hofi`, `DB_USER=hofi_user`
- **Conexión Cloud Run:** socket Unix `/cloudsql/hofi-v2-2026:us-central1:hofi-db`
- **Tablas:**
  - `task_catalog` (22 filas familia-valdes) ✅ sin errores — bug resuelto en código pero no documentado
  - `tasks` — migrada v1.1.0 ✅ incluye horas, tenzo_score, carbono_kg, gnh_*
  - `voice_profiles` ✅
  - `sbt_pending` — nueva ✅ acumula impacto antes del flush al SBT on-chain
- **Vistas:** `v_reputacion_persona` — nueva ✅ agrega impacto por persona/holón
- **Migration aplicada:** `migration_v1.1.0.sql` ✅ (7-abril-2026)

### GCS Bucket
- `hofi-bot-data` — persistencia de perfiles de voz en mock mode
- El bot carga/guarda `mock_profiles.json` desde este bucket

### Secrets Manager (hofi-v2-2026)
| Secret | Nota |
|--------|------|
| TELEGRAM_BOT_TOKEN | token del bot ⚠️ ROTAR — expuesto en logs |
| DEMO_API_KEY | `644834adec7c5ad08122f1e1cdf13d19f004bf7f6e6af119e38ca53698b1f1ad` |
| GEMINI_API_KEY | clave Google AI |
| JWT_SECRET_KEY | tokens JWT |
| ADMIN_PASSWORD_HASH | bcrypt hash tenzo-admin |
| DB_HOST / DB_NAME / DB_USER / DB_PASS | Cloud SQL credentials |

---

## TENZO AGENT

### v1.0.0 — EN PRODUCCIÓN ✅

#### Pipeline de evaluación
```
Voz transcripta
  → task_parser.py      → extrae actividad, duración, categoría estructurada
  → Gemini 2.5 Flash    → evalúa con campo "confianza" (0–1)
  → confianza > 0.70    → aprobación directa → mint HoCa
  → 0.50–0.70           → genlayer_bridge.py → apelación al ISC → (ISC v0.2.0 activo)
  → < 0.50              → rechazo
```

#### Estado actual
- Gemini 2.5 Flash: ✅ funcionando
- DB catalogo: ✅ sin errores (fix aplicado en código, no requería acción)
- `task_catalog` se lee de Cloud SQL correctamente con fallback a mock
- Evaluación activa con umbrales calibrados

#### Archivos clave (packages/tenzo-agent/)
```
tenzo_agent.py      ← v1.0.0 | MODEL_NAME="gemini-2.5-flash"
task_parser.py      ← extracción estructurada de tareas
genlayer_bridge.py  ← bridge a ISC (ORACLE_ADDRESS=0xFEE2E2e510781E760604D115723151A09a233a72)
onchain_bridge.py   ← bridge Ethereum Sepolia (ON_CHAIN=false)
```

### v1.1.0 — DISEÑADO, PENDIENTE DEPLOY 🟡

#### Qué agrega
- **Tres dimensiones de impacto** evaluadas por Gemini en cada tarea:
  - `horas_validadas` — horas reales estimadas (valida lo declarado)
  - `carbono_kg` — CO₂ equivalente evitado/capturado (estimación contextual)
  - `gnh` — Índice de Bienestar: generosidad, apoyo_social, calidad_de_vida (0.0–1.0 c/u)
- **Escritura diferida al SBT** — acumula en `sbt_pending` y hace flush al ISC
  solo cuando `tasks_acum >= SBT_UMBRAL_TAREAS` (default: 5, configurable por env)
- **`_guardar_tarea_y_verificar_sbt()`** — nueva función que persiste y controla el umbral
- **`_flush_sbt()`** — llama a `update_reputation()` en HolonSBT ISC (TODO on-chain)

#### Archivos con cambios (ver tenzo_agent_v1.1.0_diff.py)
```
tenzo_agent.py  ← construir_prompt_evaluacion(), _respuesta(),
                  _guardar_tarea_y_verificar_sbt(), _flush_sbt()
                  + constante SBT_UMBRAL_TAREAS
```

#### Para deployar v1.1.0
```powershell
# 1. Aplicar cambios del diff al tenzo_agent.py
# 2. Redeploy
cd C:\dev\hofi-protocol\packages\tenzo-agent
gcloud run deploy hofi-tenzo --source . --region=us-central1 --project=hofi-v2-2026 `
  --add-cloudsql-instances=hofi-v2-2026:us-central1:hofi-db

# 3. Agregar env var nueva (opcional, default=5)
gcloud run services update hofi-tenzo --project=hofi-v2-2026 --region=us-central1 `
  --update-env-vars="SBT_UMBRAL_TAREAS=5"
```

---

## BOT DE TELEGRAM

**URL:** `https://hofi-bot-qpxiby6ona-uc.a.run.app`
**Token:** ⚠️ ROTAR en @BotFather — expuesto en logs de Cloud Run

### Tiempos de procesamiento
| Etapa | Tiempo actual |
|-------|--------------|
| Pitch extraction (YIN) | ~0.1s |
| Formantes LPC | ~0.3s |
| Whisper transcription | ~6s (modelo cacheado en RAM) |
| Auth coseno | <0.1s |
| Tenzo evaluación | ~2-3s |
| **Total end-to-end** | **~19 segundos** |

### Deploy bot
```powershell
cd C:\dev\hofi-protocol\packages\telegram-bot
.\deploy.ps1
```

### Voice biometrics — estado actual
**Motor:** librosa + MFCC(40) + YIN pitch + formantes LPC — embedding 98-dim.
**Algoritmo:** YIN (rápido, ~0.1s) — reemplazó a PYIN (lento).

**Perfiles registrados (mock_profiles.json en GCS — verificado 13-abril):**
| Nombre | F0 (Hz) | Holón | Clave mock | Estado |
|--------|---------|-------|------------|--------|
| Doco (Pablo) | ~124-163 Hz | familia-valdes | `2012212775_doco` | ✅ OK |
| En Yuma (Uma) | — | familia-al-des | `2012212775_en_yuma` | ⚠️ re-registrar — Whisper transcribió mal nombre y holón |
| Luna | ~178 Hz | — | — | ❌ no registrada |
| Gaya | ~256 Hz | — | — | ❌ no registrada |
| Amaro (Amaru) | — | — | — | ❌ no registrada |

> **Raíz del problema "familia-al-des":** Whisper transcribió "soy Yuma, holón familia-valdés"
> como "En Yuma / familia-al-des". El nuevo resolver (ver abajo) previene que esto se
> guarde silenciosamente en el futuro.

**Estrategia de autenticación (dos capas):**
1. Audio dice "Soy X" → busca perfil por nombre → verifica voz (umbral 0.80)
2. Sin nombre → matching puro por voz (umbral 0.90)

**Holón resolver — implementado 13-abril (A+B+C):**

El bot ahora aplica tres estrategias combinadas antes de guardar un holón:

| Canal | Técnica | Implementación |
|-------|---------|----------------|
| A — Fuzzy directo | `SequenceMatcher` sobre texto normalizado sin tildes | `difflib` (stdlib) |
| B — Fonético español | Reglas: v→b, h muda, c/qu/k, ll→y, z→s | `unicodedata` (stdlib) |
| C — Confirmación explícita | Siempre pide confirmación; acepta corrección iterativa | Estado `confirmar_holon` |

Score = 40% canal directo + 60% canal fonético. Threshold sugerencia: ≥ 0.65.
Sin dependencias nuevas — todo stdlib Python.

Ejemplo resuelto: `familia-al-des` → sugiere `familia-valdes` (score ~0.79).

Nuevas funciones: `_quitar_tildes`, `_fonetizar`, `_resolver_holon`, `_normalizar_holon_texto`, `_flujo_confirmar_holon`.
Nuevo estado de sesión: `confirmar_holon` (wired en `manejar_voz` y `manejar_texto`).

**Próximo paso para perfiles:** conectar bot a PostgreSQL (`voice_profiles` table).
Cambiar `DB_MOCK=true` → `DB_MOCK=false` en Cloud Run env vars del bot.

---

## SMART CONTRACTS (Ethereum Sepolia)

### Contratos originales
- **HoCaToken:** `0x2a6339b63ec0344619923Dbf8f8B27cC5c9b40dc`
- **HolonSBT:** `0x977E4eac99001aD8fe02D8d7f31E42E3d0Ffb036`
- **TaskRegistry:** `0xd9B253E6E1b494a7f2030f9961101fC99d3fD038`
- **TenzoAgentRegistry:** ✅ desplegado (sesión 11-abril) — buscar address en deployments/ethSepolia/
- **Wallet deployer:** `0xb755bEb8777459d8c2b4E3fEA6676aa481a03ED8`

### MMA Pool — Arquitectura financiera HoFi (desplegada 11-abril-2026)
Arquitectura de 3 capas: AMM local (x*y=k) + bridge Uniswap V3 (swaps >10k USDC) + CommonStakePool inter-holónico.

#### Contratos Solidity nuevos (packages/contracts/contracts/)
- `MockUSDC.sol` — stablecoin testnet, 6 dec, faucet 10k USDC/llamada
- `HolonTokenFactory.sol` — fábrica ERC-20 holónica (ALGORITHMIC bonding curve | BASKET colateral)
- `HoFiMMAPool.sol` — pool AMM local con fees 0.2% local + 0.1% CommonStakePool
- `CommonStakePool.sol` — pool inter-holónico: crédito mutuo, flash loans (0.05%), inversiones ReFi

#### Deploy Sepolia — Fase 1 ✅ (11-abril)
| Contrato | Address |
|----------|---------|
| MockUSDC | `0x7142b01cF6FDEbD639C819e58A91d7E94C34B516` |
| HolonTokenFactory | `0x7C07783B33E1799fbBa9B946BCb88177Bb0E0303` |
| CuidaCoin CUIDA (familia-valdes, ALGORITHMIC 50% reserveRatio) | `0xa00D1dB9ECce4a6a4753E52Ee07fd509327E8d98` |
| BrazoCoin BRAZO (archi-brazo, BASKET 60%USDC+40%DAI, min 150%) | `0x4d9c71d78A375343c337c2e79d4044Dea56435B3` |

#### Deploy Sepolia — Fase 2 ✅ (11-abril-2026)
| Contrato | Address |
|----------|---------|
| CommonStakePool | `0xd3BB4A84e022D9b26FdAF85AaC486be1d847A7f5` |
| HoFiMMAPool [familia-valdes] | `0x665c9EfF7d9B20D60ed449A76DAC5F9F380949Fd` |
| HoFiMMAPool [archi-brazo] | `0xD0886fD35164f5D0d5d2E434b19Ee2B7e1AA529e` |

Seed de liquidez aplicado: 1000 CUIDA + 100 USDC | 500 BRAZO + 250 USDC.
Uniswap bridge: desactivado (placeholder 0x000) — AMM local funciona. Activar con $env:UNISWAP_ROUTER.

#### Scripts de deploy (packages/contracts/scripts/mma/)
```powershell
$env:PRIVATE_KEY = "0x..."
npm run mma:fase1   # MockUSDC + Factory + tokens
npm run mma:fase2   # CommonStakePool + 2x MMAPool + seed liquidez
# Para HolonChain (cuando bootstrap=true):
npm run mma:holonchain:fase1
npm run mma:holonchain:fase2
```

#### ReFiGovernanceISC v1.1.0 — ✅ DESPLEGADO Studionet (13-abril)
- **Dirección Studionet:** `0x04939aa6983Cbed3C8b30a6ce7389d5B601cE220`
- **TX deploy:** `0xc2d962dacf19072e3d3e9e4071666e2ce31eb8905b856c7bae88b5e347e41d9f`
- **⚠️ Bradbury descartado:** gen_call roto para TODOS los contratos (incluso finalizados)
- ISC Python con 5 validadores LLM, prompt_comparative consensus
- Criterios: min_impact=0.6, max_risk=0.4, yield/impact=30%/70%
- Sectores prohibidos: fossil_fuels, weapons, gambling, speculative_derivatives, extractive_mining
- Archivos creados:
  - `packages/genlayer/contracts/refi_governance_isc.py` ← contrato ISC
  - `packages/genlayer/contracts/DEPLOY_REFI_ISC.md` ← guía deploy paso a paso
  - `packages/genlayer/deploy/deployReFiGovernanceISC.mjs` ← script deploy
  - `packages/genlayer/deploy/callGetReFiCriteria.mjs` ← verificación post-deploy
  - `packages/genlayer/deploy/callProposeInvestment.mjs` ← propuesta de prueba + evaluación
- Governance address: `0xb755bEb8777459d8c2b4E3fEA6676aa481a03ED8`
- CommonStakePool (Sepolia): `0xd3BB4A84e022D9b26FdAF85AaC486be1d847A7f5`

```powershell
# Para deployar:
cd C:\Users\valde\dev\hofi-protocol\packages\genlayer
$env:GENLAYER_PRIVATE_KEY = "0x<tu_clave>"
node deploy/deployReFiGovernanceISC.mjs
# Luego verificar:
$env:REFI_ISC_ADDRESS = "0x<address_del_contrato>"
node deploy/callGetReFiCriteria.mjs
# Luego propuesta de prueba:
node deploy/callProposeInvestment.mjs
```

## GENLAYER ISCs (Studionet Asimov / Bradbury)

⚠️ **Red Bradbury** — desde 11-abril-2026 se usa Bradbury en lugar de Asimov.
Habilitar GenLayer Skills para Claude Code + seleccionar red Bradbury en la UI de GenLayer Studio.

- **TenzoEquityOracle v0.1.0:** `0x6707c1a04dC387aD666758A392B43Aa0660DFECE` (deprecado)
- **TenzoEquityOracle v0.2.2:** `0xFEE2E2e510781E760604D115723151A09a233a72` ← ACTIVO (Bradbury)
- **HolonSBT ISC v0.1.0:** `0x2288A8DA4507f63321685577656bfB6a887E685B` (deprecado)
- **HolonSBT ISC v0.2.0:** `0x4b89EB9f787dF1e3DC834bF82c7a306492Bd1AD1` (deprecado — Bradbury, gen_call roto)
- **HolonSBT ISC v0.2.1:** `0x22ce5caF239AAD7DbEb7Bea3dDBcC69202d8560E` ← ACTIVO (Studionet) ✅
- **InterHolonTreasury:** `0x491E468AD6e1669f76b155CefB42d1343d4E4AE5`

⚠️ **Pendiente:** actualizar Cloud Run con dirección ISC v0.2.0 (tras deploy):
```powershell
gcloud run services update hofi-tenzo --project=hofi-v2-2026 --region=us-central1 `
  --update-env-vars="TENZO_ORACLE_ADDRESS=0xFEE2E2e510781E760604D115723151A09a233a72"
```
Luego llamar `set_holon_rules("familia-valdes", <descripción_reglas>)` para inicializar holón.

### Estado de los ISCs en la red Bradbury
- El problema de NO_MAJORITY/0 rounds era red (sin validadores en Asimov).
- Resuelto habilitando GenLayer Skills para Claude Code + cambiando a Bradbury.
- Todo funcionando 100% en Bradbury al 11-abril-2026. ✅

## HOLON SBT ISC

### v0.2.0 — DEPLOYADO ✅ en Bradbury (11-abril-2026)
- **Dirección:** `0x4b89EB9f787dF1e3DC834bF82c7a306492Bd1AD1`
- **TX deploy:** `0xa1ed834bfd0af8d5661a121d560450e2c51d1f59a22212df6eaf4965a7484af0`
- **Deployer:** `0xb755bEb8777459d8c2b4E3fEA6676aa481a03ED8`
- **Nota:** `txExecutionResultName: FINISHED_WITH_ERROR` es normal para constructores Python que retornan None. El éxito se verifica por `resultName: AGREE` + `status_name: ACCEPTED`.

#### SBTs emitidos (11-abril-2026)
| Dirección | Rol | TX |
|-----------|-----|----|
| `0xb755bEb8777459d8c2b4E3fEA6676aa481a03ED8` | coordinator | `0x38ee1f43652970a7a015cb639775fec42a4c8b9a246dc0117b10758869aa7340` |

#### Qué cambió respecto a v0.1.0
- **`strict_eq` → `prompt_comparative` (Pattern 3):** tolerancia a variaciones menores en LLMs.
  Principio para `validate_contribution`: veredicto (is_valid) idéntico + impact_score ±2.
  Principio para `calculate_vote_weight`: weight ±0.5 (escala 1.0–5.0).
- **`revoke_sbt(member_address)`:** nuevo — desactiva SBT sin borrar historial.
- **`update_sbt_role(member_address, new_role)`:** nuevo — governance cambia roles.
- **`get_owner()` y `get_member_count()`:** nuevas vistas (paridad con TenzoEquityOracle).
- **`member_count: int`:** contador de SBTs emitidos (nuevo state variable).
- **SBT JSON enriquecido:** agrega `contribution_categories` y `join_block`.
- **`contribution_categories` auto-actualizado:** validate_contribution agrega la categoría
  al SBT cuando `is_valid=True`, para que calculate_vote_weight pueda usar el historial.
- **`str(gl.message.sender_address).lower()`:** normalización de dirección (consistencia con v0.2.2 Oracle).
- **`_safe_json_loads()`:** helper robusto (sin fallos silenciosos).
- **NatSpec completo** en todas las funciones públicas.

#### Para deployar v0.2.0
```bash
# Con GenLayer Skills en Claude Code, red Bradbury activa:
# Usar GenLayer Studio o CLI para deploying contracts/holon_sbt_isc.py
# Constructor: holon_name = "familia-valdes"
# Guardar address en esta memory + actualizar HOLON_SBT_ADDRESS en env vars del Tenzo Agent
```

### Diseño v0.3.0 — multi-holón (diseñado 7-abril, pendiente implementar)

#### Un SBT por persona global (multi-holón)
- Un address = un token global con membresía en múltiples holones
- `issue_sbt(address, holon_id, role)` — agrega holón si ya tiene SBT

#### Un SBT por persona global (multi-holón)
- Un address = un token global con membresía en múltiples holones
- `issue_sbt(address, holon_id, role)` — agrega holón si ya tiene SBT

#### Reputación multidimensional (3 ejes)
Cada tarea aprobada aporta a tres dimensiones acumuladas por holón:

| Dimensión | Qué mide | Unidad |
|-----------|----------|--------|
| `horas` | Esfuerzo y tiempo real dedicado | horas float |
| `carbono_kg` | CO₂ eq evitado/capturado | kg float |
| `gnh_score` | Bienestar: generosidad + apoyo_social + calidad_de_vida | 0.0–1.0 |

#### Escritura diferida (batching)
- El Tenzo NO escribe al SBT por cada tarea — acumula en `sbt_pending` (Cloud SQL)
- Cuando `tasks_acum >= SBT_UMBRAL_TAREAS` — flush único a `update_reputation()`
- Reduce gas dramáticamente + alineado filosóficamente (el reconocimiento llega con acumulación)

#### Fórmula de reputación ponderada
```
delta_rep = horas × tenzo_score × CATEGORY_WEIGHT[category]
CATEGORY_WEIGHT = { eco: 1.0, social: 1.0, tech: 1.0, cuidado: 1.2 }
```

#### ZK Proofs (Semaphore) — diseño futuro
- El holón es el grupo Semaphore
- Las tareas se registran como señales anónimas (impacto visible, identidad privada)
- El Tenzo verifica off-chain y emite prueba de "miembro válido realizó contribución"
- Alineado con el espíritu del bodhisattva: el cuidado sin necesidad de reconocimiento

#### Roles y pesos de voto
```python
VALID_ROLES = {
    "member": 1.0, "coordinator": 1.5, "tenzo": 1.3,
    "ambassador": 1.2, "guardian": 1.4
}
```

#### Métodos principales
| Método | Quién puede | Descripción |
|--------|------------|-------------|
| `issue_sbt(address, holon_id, role)` | governance | Emite o agrega holón |
| `update_reputation(address, holon_id, category, hours, hoca, carbono_kg, gnh_score, tenzo_score)` | Tenzo o governance | Actualiza rep (aditivo) |
| `validate_contribution(...)` | cualquiera | LLM consensus 5 validators |
| `calculate_vote_weight(...)` | cualquiera | Peso contextual por propuesta |
| `get_reputation(address, holon_id)` | view | Rep detallada en holón |
| `get_global_stats(address)` | view | Stats globales agregadas |
| `revoke_membership(address, holon_id)` | governance | Revoca holón (no borra historial) |

---

## HOLONCHAIN (Avalanche L1 — Fuji Testnet)
- ChainID: 73621 | Token: HoCa | VM: subnet-evm v0.8.0
- **Estado:** ✅ Nodo corriendo en Fuji (fix crítico aplicado 7-abril)

| Dato | Valor |
|------|-------|
| Subnet ID | `2wMXMZhmuSCF6cf69qntYTJW6GFLKQK99YiCDCEECijNMdzuZu` |
| Blockchain ID | `2iQdZzzFtdvWH2hpDm5ReijM8AtLdVmVMxGV4j4pWMz3LpoRzZ` |
| VM ID | `YuG9gMFUpphbNN39tzaYjq4J8bsuhmjz1zVmjoCBFeJ2CCVro` |
| Node ID bootstrap | `NodeID-qo92VzQ7Snd3q7zvoHBSWu3eCX8Hkg9N` |
| ConvertSubnetToL1Tx | `KN53FZf1CrSvrNg3ynkz6FG14rf7Zjni9jJX9qVc4c8PonzrP` |
| Deployer key (P-Chain) | `P-fuji1lwnp68wkr8f4zsee26fqywcwr3c8le9plvrc2u` |
| Genesis alloc | `0xb755bEb8777459d8c2b4E3fEA6676aa481a03ED8` |
| Validator Manager owner | `0x8db97C7cEcE249c2b98bDC0226Cc4C2A57BF52FC` (ewoq key) |
| BLS Public Key | `0xae7ab10912951cd20c5fd51bc0c7782759d2073a9f5062663aea7466a97f25fbebbc98266a8f12b4986eef25d5a9d3bc` |
| Validation ID | `uTjbdFiXPCmfHnB65d3CtU4pH142xC9MRWRZMDd4wASiT6nHz` |
| Validator Mgr address | `0x0FEEDC0DE0000000000000000000000000000000` (pendiente init) |
| Teleporter | Ready — v1.0.0 |

### Nodo AvalancheGo — holonchain-validator — CORRIENDO (Fuji)
Deployado en GCP. **Fix crítico aplicado el 7-abril:** el nodo estaba bootstrappeando
**mainnet** en lugar de Fuji (faltaba `"network-id": "fuji"` en node.json).
Se borró la DB de mainnet (85GB) y se reinició apuntando a Fuji correctamente.
**Fix 11-abril:** OOM en e2-small → upgrade a **e2-medium** (3.8GB RAM). SSH funciona, AvalancheGo corriendo.

| Dato | Valor |
|------|-------|
| VM GCP | `holonchain-validator` (us-central1-a, **e2-medium** — upgrade desde e2-small por OOM) |
| IP externa | `34.69.27.168` — **cambió** (era 34.122.241.26) |
| Node ID | `NodeID-56Tr8GoAu1zoUFCjMmw39ktzMQ8bhHz5B` |
| AvalancheGo | v1.14.2 |
| subnet-evm plugin | v0.8.0 |
| Estado bootstrap | 🔄 En progreso desde 7-abril ~10:08 UTC (estimado 4-8hs) |
| Config correcta | `"network-id": "fuji"` ✅ |

**node.json actual:**
```json
{
  "http-host": "",
  "public-ip": "34.69.27.168",
  "network-id": "fuji",
  "track-subnets": "2wMXMZhmuSCF6cf69qntYTJW6GFLKQK99YiCDCEECijNMdzuZu"
}
```

**Verificar bootstrap:**
```bash
# SSH al nodo
gcloud compute ssh holonchain-validator --project=hofi-v2-2026 --zone=us-central1-a

# Verificar P-Chain
curl -s -X POST http://localhost:9650/ext/info \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"info.isBootstrapped","params":{"chain":"P"}}'
```

**Diagnóstico del nodo:**
```bash
sudo systemctl status avalanchego
sudo journalctl -u avalanchego --no-pager -n 50
sudo systemctl restart avalanchego
```

### MetaMask / Core Wallet — agregar HolonChain
```
Network Name:    HolonChain (HoFi Protocol — Fuji)
RPC URL:         http://34.69.27.168:9650/ext/bc/2iQdZzzFtdvWH2hpDm5ReijM8AtLdVmVMxGV4j4pWMz3LpoRzZ/rpc
Chain ID:        73621
Currency Symbol: HOCA
```
⚠️ RPC disponible solo cuando el nodo termine bootstrap y P-Chain confirme `isBootstrapped: true`.

### Pasos pendientes para activar la chain
1. ✅ Nodo AvalancheGo corriendo en Fuji (fix aplicado)
2. 🔄 **Esperar bootstrap P-Chain** — verificar con curl de isBootstrapped
3. ⏳ **Inicializar Validator Manager:**
   ```bash
   avalanche contract initValidatorManager HolonChain --network fuji
   ```
4. ⏳ **Deployar contratos HoFi en HolonChain** (HoCaToken, HolonSBT, TaskRegistry)
5. ⏳ **Bridge** HoCaToken Sepolia → HolonChain vía Teleporter

### Costos GCP — lección aprendida
El bootstrap de mainnet (error de config) consumió ~$300 en 15 días agotando los créditos
de prueba. Causas: VM e2-standard-2 24/7 + SSD 100GB + egress masivo de mainnet.
**Fix:** reducir VM a e2-small (~$13/mes) + corregir network-id a fuji (testnet mucho más liviana).
Si se necesitan más créditos en el futuro: cuenta de Luna (lunamourino@gmail.com) tiene
período de prueba disponible — usar solo cuando sea necesario.

---

## FRONTEND NEXT.JS 14 (packages/frontend)

### Stack
- **Next.js 14** App Router + `src/` directory
- **Tailwind CSS v3.4.19** (NO v4 — cuidado con sintaxis)
- **shadcn/ui** + colores HoFi custom
- **next-themes** (modo oscuro/claro)

### Arrancar el servidor de desarrollo
```bash
cd packages/frontend
npm run dev   # http://localhost:3000
```

### Deploy en Vercel
**Root Directory:** `packages/frontend` ← CRÍTICO

**Environment Variables:**
| Variable | Valor |
|---|---|
| `JWT_SECRET_KEY` | Generar nueva en Vercel (32+ chars) |
| `TENZO_AGENT_URL` | `https://hofi-tenzo-1080243330445.us-central1.run.app` |
| `DEMO_API_KEY` | `644834adec7c5ad08122f1e1cdf13d19f004bf7f6e6af119e38ca53698b1f1ad` |
| `NEXT_PUBLIC_APP_URL` | URL que asigne Vercel |
| `NEXT_PUBLIC_CHAIN_ID` | `11155111` |
| `NEXT_PUBLIC_HOCA_TOKEN` | `0x2a6339b63ec0344619923Dbf8f8B27cC5c9b40dc` |

**Qué funciona sin Cloud SQL:**
- ✅ Dashboard completo con orbe, tabs, feed mock
- ✅ Login por email — JWT cookie — sesión persistente
- ✅ Manual Entry — Tenzo Agent real — evaluación con Gemini
- ⚠️ Balance = 0 (esperado sin DB)
- ⚠️ World tab: mapa no carga sin token Mapbox
- ⚠️ Voice login: pendiente endpoint en bot

### Tres métricas de impacto en el frontend
El dashboard ya tiene UI para tres círculos de impacto:
- **Horas** (HoCa) — aporte comunitario en tiempo
- **Huella de carbono** — CO₂ eq evitado/capturado
- **GNH** — Índice de bienestar (generosidad, apoyo social, calidad de vida)

Estas métricas ahora tienen backend real en Tenzo v1.1.0 y DB migrada.
Pendiente: conectar el frontend a los nuevos campos de la respuesta del Tenzo.

---

## ESTADO GENERAL

```
Bot Telegram           ✅ PRODUCCIÓN  — Cloud Run, ~19s end-to-end
Tenzo Agent v1.0.0     ✅ PRODUCCIÓN  — gemini-2.5-flash, evalúa correctamente
Tenzo Agent v1.1.0     🟡 DISEÑADO   — 3 dimensiones + SBT diferido, pendiente deploy
TenzoAgentRegistry     ✅ DESPLEGADO  — Sepolia (ver deployments/ethSepolia/)
Voice biometrics       ✅ Funcionando — Doco autenticado (0.99+). Luna/Gaya pendiente
DB Cloud SQL           ✅ ACTIVO      — migración v1.1.0 aplicada (tasks + sbt_pending)
DB catalogo            ✅ OK          — bug resuelto en código (no era error de DB)
GenLayer ISC v0.2.0    ✅ ACTIVO      — 0xFEE2E2e510781E760604D115723151A09a233a72
HolonSBT ISC v0.2.1    ✅ ACTIVO (Studionet) — 0x22ce5caF239AAD7DbEb7Bea3dDBcC69202d8560E
MMA Pool — Fase 1      ✅ DESPLEGADO  — MockUSDC + Factory + CUIDA + BRAZO en Sepolia (11-abril)
MMA Pool — Fase 2      ✅ DESPLEGADO  — CommonStakePool + 2x MMAPool + seed liquidez (11-abril)
ReFiGovernanceISC      ✅ ACTIVO (Studionet) — 0x04939aa6983Cbed3C8b30a6ce7389d5B601cE220
HolonChain (Fuji)      🔄 BOOTSTRAP  — VM e2-medium, P-Chain sincronizando
On-chain tasks         ⏳ Pendiente   — requiere HolonChain + ON_CHAIN=true
ZK Proofs (Semaphore)  🔵 Diseñado   — para fase posterior
TTS (voz respuesta)    ⏳ Pendiente
Dashboard Next.js      🟡 EN PROGRESO — UI completa, login email ✅, voice auth ⏳
Documento arquitectura ✅ GENERADO    — docs/HoFi_Arquitectura_Financiera_v1.0.docx
```

---

## PRÓXIMAS TAREAS (en orden)

### 🔴 Inmediato
1. **Re-registrar Uma, Luna, Gaya y Amaru** con el bot en producción.
   - Uma: el perfil "En Yuma / familia-al-des" quedó mal — re-registrar para corregir nombre y holón.
   - Luna, Gaya, Amaru: no llegaron a guardarse en GCS, re-registrar desde cero.
   - El nuevo resolver (A+B+C) ya está activo — pedirá confirmación del holón antes de guardar.
2. **Deploy bot** con los cambios del resolver — `.\deploy.ps1` en `packages/telegram-bot`.
3. **Deploy Tenzo v1.1.0** — aplicar diff y redeploy en Cloud Run.
3. **Actualizar Cloud Run Tenzo** con dirección ISC v0.2.0:
   ```powershell
   gcloud run services update hofi-tenzo --project=hofi-v2-2026 --region=us-central1 `
     --update-env-vars="TENZO_ORACLE_ADDRESS=0xFEE2E2e510781E760604D115723151A09a233a72"
   ```
4. **Verificar bootstrap P-Chain** HolonChain — curl isBootstrapped.

### 🟡 Corto plazo
5. **Emitir SBTs restantes** via `callIssueSBT.mjs` para miembros del holón familia-valdes.
   - ✅ Doco/Pablo — `0xb755beb8777459d8c2b4e3fea6676aa481a03ed8` — coordinator (TX: 0x7dfeb67a6b865f7768b2561fabd7a92d092adcc3bb1639d77fb894d86381bbfb)
   - ⏳ Otros miembros — pendiente wallets (Fase 1 del roadmap de identidad)
6. **Bot → PostgreSQL para voice_profiles** — cambiar `DB_MOCK=false` en bot Cloud Run.
7. **Rotar token del bot** — @BotFather — /newtoken.
8. **initValidatorManager** — cuando P-Chain bootstrap=true.

### 🔵 Roadmaps documentados (ver docs/)
- `docs/roadmap_identity_system.md` — Sistema de identidad biométrica on-chain
  - Fase 1 (Q3 2026): wallets custodiales generadas al registrar voz (Opción A)
  - Fase 1+: Opción B configurable (wallet propia / MetaMask) para usuarios Web3
  - Fase 2 (Q4 2026): portabilidad inter-holón
  - Fase 3 (2027): voz → keypair determinístico via ZK/Semaphore (Opción C)
- `docs/roadmap_tenzo_evaluation.md` — Evaluación del agente Tenzo
  - Fase 1 (Q3 2026): `challenge_tenzo_decision()` + historial on-chain de strikes
  - Fase 2 (Q4 2026): SBT propio del Tenzo + separación owner/operacional
  - Fase 3 (2027): trust_score → autonomía dinámica → voto en gobernanza