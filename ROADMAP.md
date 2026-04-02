# HoFi Protocol — Hoja de Ruta MVP
*Última actualización: 27 de marzo de 2026*

> **Cómo usar este documento:**
> Cada sección es un chat independiente en Claude Cowork.
> Al iniciar cada chat, adjuntá `HOFI_COWORK_MEMORY.md` + esta sección específica.
> Así Claude tiene todo el contexto necesario sin ruido de los otros temas.

---

## ESTADO GENERAL

```
Tenzo Agent v0.9.0     ✅ PRODUCCIÓN  — https://hofi-tenzo-1080243330445.us-central1.run.app
Bot Telegram           ✅ LOCAL OK    — pendiente deploy Cloud Run
Voice biometrics       ✅ Whisper 512-dim — pendiente test familiar
PostgreSQL             ⏳ En espera  — DB_MOCK=true funcionando
HolonChain (Fuji)      ⏳ Pendiente  — transfer AVAX C-Chain → P-Chain
On-chain tasks         ⏳ Pendiente  — requiere HolonChain
GenLayer ISCs          ⏳ Pendiente  — requiere on-chain base
Dashboard              ⏳ Pendiente  — Fase 3
```

---

## CHAT 1 — Deploy Bot Telegram en Cloud Run
**Estado:** Listo para ejecutar
**Duración estimada:** 1 sesión (30-60 min)

### Contexto
El bot de Telegram está completo y funciona localmente con polling.
Para producción necesita correr en Cloud Run con webhook.
El script `deploy.ps1` está listo en `packages/telegram-bot/`.

### Archivos relevantes
- `packages/telegram-bot/deploy.ps1` — script completo de deploy
- `packages/telegram-bot/Dockerfile` — imagen con Whisper pre-descargado
- `packages/telegram-bot/bot.py` — soporta polling (local) y webhook (Cloud Run)
- `packages/telegram-bot/.env` — variables locales

### Tareas de este chat
1. Ejecutar `.\deploy.ps1` y resolver errores que surjan
2. Verificar que el webhook de Telegram apunta a la URL de Cloud Run
3. Probar /start desde Telegram apuntando al servicio en producción
4. Configurar `min-instances=1` para evitar cold starts con Whisper
5. Verificar logs en Cloud Run: `gcloud logging read ...`

### Comandos útiles
```powershell
cd C:\dev\hofi-protocol\packages\telegram-bot
.\deploy.ps1

# Ver logs post-deploy
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=hofi-bot" `
  --project=hofi-v2-2026 --limit=20 --format="value(textPayload)"
```

---

## CHAT 2 — Voice Biometrics: Test Familiar y Calibración
**Estado:** Listo para testear (requiere familia disponible)
**Duración estimada:** 1 sesión

### Contexto
Se actualizó el motor de voz de MFCC 120-dim (librosa) a Whisper encoder 512-dim.
El cambio fue necesario porque MFCC captura timbre general — voces familiares son
demasiado parecidas. Whisper encoder tiene representaciones de alto nivel entrenadas
en 680.000 horas de voz diversa.

El umbral de similitud subió de 0.82 a 0.90. Los perfiles anteriores (MFCC)
fueron borrados — hay que re-registrarse con el motor nuevo.

### Tareas de este chat
1. Registrar a Pablo (Doko) con el nuevo motor Whisper
2. Registrar al menos una hija con el mismo bot
3. Medir similitud cruzada (voz de Pablo vs perfil de hija)
4. Ajustar VOICE_SIMILARITY_THRESHOLD si hay falsos positivos/negativos
5. Documentar umbrales óptimos para voces familiares

### Variables a ajustar
```
# En .env local o en Cloud Run --update-env-vars
VOICE_SIMILARITY_THRESHOLD=0.90   # subir si hay confusiones (ej: 0.93)
                                   # bajar si hay rechazos legítimos (ej: 0.87)
```

### Qué registrar en los logs
Buscá líneas como:
```
VoiceAuth | similitud con Doko: 0.9823    ← mismo usuario (alto)
VoiceAuth | similitud con Doko: 0.8712    ← diferente usuario (debería ser bajo con Whisper)
```

---

## CHAT 3 — PostgreSQL: Persistencia Real
**Estado:** Bloqueado por Chat 1 y 2 (hacer después del deploy y test de voz)
**Duración estimada:** 1-2 sesiones

### Contexto
Actualmente DB_MOCK=true. Los perfiles se guardan en `mock_profiles.json`
(localmente) o en GCS (Cloud Run). Para producción real se necesita PostgreSQL.

El código ya tiene soporte completo para PostgreSQL en `db.py` — solo hay
que proveer las variables de entorno y crear las tablas.

### Tareas de este chat
1. Crear instancia Cloud SQL (PostgreSQL 15) en GCP proyecto hofi-v2-2026
2. Crear base de datos `hofi` y usuario `hofi_user`
3. Configurar VPC connector para que Cloud Run acceda a Cloud SQL
4. Agregar secrets: DB_HOST, DB_NAME, DB_USER, DB_PASS
5. Cambiar DB_MOCK=false en Cloud Run
6. Migrar perfiles existentes de JSON a PostgreSQL (script de migración)
7. Verificar que tablas se crean con `init_db()`

### Schema de la DB (ya en db.py)
```sql
CREATE TABLE IF NOT EXISTS voice_profiles (
    id                SERIAL PRIMARY KEY,
    telegram_user_id  BIGINT UNIQUE NOT NULL,
    member_name       VARCHAR(100) NOT NULL,
    holon_id          VARCHAR(50) NOT NULL,
    voice_embedding   FLOAT[] NOT NULL,
    created_at        TIMESTAMP DEFAULT NOW()
);
```

### Comandos GCP útiles
```powershell
# Crear instancia Cloud SQL
gcloud sql instances create hofi-db `
  --database-version=POSTGRES_15 `
  --tier=db-f1-micro `
  --region=us-central1 `
  --project=hofi-v2-2026
```

---

## CHAT 4 — HolonChain: Deploy en Fuji (Avalanche)
**Estado:** Pendiente — requiere AVAX en P-Chain
**Duración estimada:** 1-2 sesiones

### Contexto
HolonChain es la subnet de Avalanche para HoFi.
- ChainID: 73621
- Token nativo: HoCa
- VM: subnet-evm v0.8.0
- Configuración lista, pendiente deploy en Fuji testnet

El bloqueante actual es tener AVAX en la P-Chain para pagar el deploy.
Actualmente el AVAX está en C-Chain — hay que transferirlo a P-Chain via Core Wallet.

### Tareas de este chat
1. Abrir Core Wallet → Cross-Chain transfer: C-Chain → P-Chain (mínimo 2 AVAX)
2. Verificar saldo en P-Chain
3. Ejecutar deploy de la subnet en Fuji:
   ```
   avalanche subnet deploy HolonChain --network fuji
   ```
4. Anotar el SubnetID y ChainID asignados por Fuji
5. Agregar la subnet a Core Wallet como red custom
6. Verificar conectividad con `curl http://[node]/ext/bc/[chainID]/rpc`

### Referencia
- Wallet deployer: 0xb755bEb8777459d8c2b4E3fEA6676aa481a03ED8
- Config en: `packages/avalanche/`

---

## CHAT 5 — On-Chain: TaskRegistry + HoCa Minting
**Estado:** Pendiente — requiere Chat 4 completado
**Duración estimada:** 2 sesiones

### Contexto
Cuando el Tenzo aprueba una tarea, el resultado debería:
1. Registrarse en el contrato TaskRegistry en Ethereum Sepolia
2. Mintear HoCa tokens al ejecutor de la tarea

Los contratos ya están deployados en Sepolia:
- HoCaToken: 0x2a6339b63ec0344619923Dbf8f8B27cC5c9b40dc
- TaskRegistry: 0xd9B253E6E1b494a7f2030f9961101fC99d3fD038
- HolonSBT: 0x977E4eac99001aD8fe02D8d7f31E42E3d0Ffb036

El `onchain_bridge.py` en el Tenzo Agent ya tiene la lógica, pero
`ON_CHAIN=false` actualmente.

### Tareas de este chat
1. Revisar `onchain_bridge.py` — verificar ABIs y conexión Web3
2. Testear mint manual de HoCa en Sepolia
3. Activar ON_CHAIN=true en el Tenzo Agent (Cloud Run)
4. Verificar que el flujo completo minta tokens al aprobar una tarea
5. Ver la transacción en Etherscan Sepolia

---

## CHAT 6 — GenLayer ISCs: Oráculos de Equidad
**Estado:** Pendiente — requiere On-Chain base funcionando
**Duración estimada:** 2 sesiones

### Contexto
Los ISCs (Intelligent Smart Contracts) de GenLayer validan decisiones del Tenzo
usando múltiples nodos de IA que votan para llegar a consenso.

ISCs deployados en Studionet:
- TenzoEquityOracle: 0x6707c1a04dC387aD666758A392B43Aa0660DFECE
- HolonSBT ISC: 0x2288A8DA4507f63321685577656bfB6a887E685B
- InterHolonTreasury: 0x491E468AD6e1669f76b155CefB42d1343d4E4AE5

### Tareas de este chat
1. Migrar ISCs de Studionet a mainnet GenLayer
2. Integrar TenzoEquityOracle como segunda opinión después de Gemini
3. Implementar flujo: Gemini evalúa → GenLayer valida → TaskRegistry registra
4. Testear con tareas reales

---

## CHAT 7 — TTS: Respuestas por Voz en Telegram
**Estado:** Pendiente
**Duración estimada:** 1 sesión

### Contexto
Para una experiencia 100% vocal, el bot debería responder con mensajes
de voz además de (o en lugar de) texto. Telegram permite enviar `voice` messages.

### Opciones técnicas
- **gTTS** (Google Text-to-Speech): simple, gratuito, voz robot
- **ElevenLabs API**: alta calidad, costo por carácter
- **OpenAI TTS**: buena calidad, integrado con el stack existente

### Tareas de este chat
1. Elegir motor TTS (recomendación: OpenAI TTS o gTTS para MVP)
2. Implementar `texto_a_voz(texto: str) -> bytes` en el bot
3. Reemplazar `reply_text` por `reply_voice` en respuestas clave
4. Mantener texto como fallback para conexiones lentas

---

## CHAT 8 — Dashboard: Lectura del Holón
**Estado:** Pendiente — Fase 3
**Duración estimada:** 3-4 sesiones

### Contexto
Una interfaz web mínima para que el holón pueda ver:
- Historial de tareas y HoCa acumulados
- Comparación entre miembros
- Saldo de tokens en blockchain

Stack definido: Next.js 14 + Tailwind
Ubicación: `packages/frontend/`

### Tareas de este chat
1. Scaffold Next.js 14 en `packages/frontend/`
2. Página principal: resumen del holón (nombre, miembros, HoCa total)
3. Lista de tareas aprobadas con recompensas
4. Conexión a la API del Tenzo para datos históricos
5. Deploy en Vercel o Cloud Run

---

## HOLONES PILOTO

| Holón | Miembros | Estado |
|-------|----------|--------|
| familia-valdes | Pablo (Doko) + hijos | ✅ Probando |
| archi-brazo | Cooperativa | ⏳ Fase 2 |
| el-pantano | Ecovilla Tigre | ⏳ Fase 2 |

---

## DECISIONES TÉCNICAS CLAVE

| Decisión | Elección | Razón |
|----------|----------|-------|
| Interfaz principal | Telegram bot (No-UI first) | Accesible sin app extra |
| Voice biometrics | Whisper encoder 512-dim | Discrimina voces familiares |
| Evaluación de tareas | Gemini 2.0 Flash via API | Razonamiento en español |
| DB actual | JSON + GCS (mock) | Simple para MVP |
| DB producción | PostgreSQL (Cloud SQL) | Escalable |
| Blockchain L1 | Ethereum Sepolia | Contratos ya deployados |
| Blockchain L2 | HolonChain (Avalanche subnet) | Economía interna del holón |
| Oráculos | GenLayer ISCs | Consenso multi-IA |
