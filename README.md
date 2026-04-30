# HoFi Protocol

> *"The act of caring is the yield."*

**HoFi (Holistic Finance)** is a regenerative economy protocol that makes invisible care work visible — and rewards it. Caring for an elder, composting, restoring a wetland, teaching a child, tending a community garden: in the conventional economy, none of this appears on any balance sheet. HoFi changes that.

---

## The Vision

The ILO estimates that care work represents over 50% of all labor performed in the world. It sustains civilization. It is invisible to the dominant economic system.

HoFi builds bridges where the conventional economy builds walls. It connects invisible work with the recognition it deserves — through AI, blockchain, and a design philosophy grounded in communities, not corporations.

---

## Core Concepts

### The Holon
The basic unit of HoFi. A **holon** is a sovereign community — a family, a cooperative, an ecovillage — with its own internal economy, its own token, and its own AI arbiter. Each holon defines what care means in its own words.

### The Tenzo
In Zen tradition, the Tenzo is the monastery cook — the one who transforms humble ingredients into nourishment for the community.

In HoFi, the **Tenzo** is an AI agent that evaluates care work impartially, calculates a fair reward in HoCa tokens, and records it permanently on the blockchain. It cannot be corrupted, has no favorites, and its reasoning is always visible and auditable.

### HoCa Tokens
The unit of recognition. Earned by performing care work — human, animal, or ecological. Issued by the Tenzo when a task is evaluated and approved.

---

## How It Works

```
Community member reports care work
         ↓ (voice message on Telegram)
Tenzo Agent evaluates the task
         ↓ (Gemini 2.5 Flash + catalog match)
High confidence → Direct approval → HoCa minted
Medium confidence → GenLayer ISC → 5-LLM jury consensus
Low confidence → Rejected
         ↓
Result recorded on-chain (HolonChain / Ethereum Sepolia)
```

Anyone can report a task by sending a **voice message on Telegram**. No wallet. No password. No screen. Voice biometrics serve as identity — your voice is your key.

---

## Technical Architecture

HoFi operates across three layers:

### Layer 1 — Tokens (Ethereum Sepolia)
| Contract | Address |
|----------|---------|
| HoCaToken (HOCA) | `0x2a6339b63ec0344619923Dbf8f8B27cC5c9b40dc` |
| HolonSBT (membership) | `0x977E4eac99001aD8fe02D8d7f31E42E3d0Ffb036` |
| TaskRegistry | `0xd9B253E6E1b494a7f2030f9961101fC99d3fD038` |

### Layer 2 — AI Consensus (GenLayer / Bradbury)
Three intelligent smart contracts evaluated by a jury of 5 LLMs. The **TenzoEquityOracle v0.2.2** is deployed at `0x68396D5f7e1887054F54f9a55A71faE08C6a07B7` on the Bradbury testnet.

Evaluation thresholds (configurable without redeployment):
- `≥ 0.70` confidence + catalog match → direct approval
- `0.50–0.70` confidence → escalated to GenLayer ISC
- `< 0.50` confidence → rejected

### Layer 3 — Sovereignty (HolonChain — Avalanche L1)
HoFi's own subnet on Avalanche Fuji testnet. Only members holding an active SBT can be validators. Full interoperability with the Ethereum ecosystem.

| Parameter | Value |
|-----------|-------|
| Chain ID | 73621 |
| Subnet ID | `2wMXMZhmuSCF6cf69qntYTJW6GFLKQK99YiCDCEECijNMdzuZu` |
| Token | HoCa |
| VM | subnet-evm v0.8.0 |

### Privacy — ZK (Semaphore)
Members participate without revealing their identity. The care you gave has value. No one needs to know it was you.

---

## Repository Structure

```
hofi-protocol/
├── packages/
│   ├── tenzo-agent/          ← Tenzo Agent v1.0.0 ✅ Production
│   ├── telegram-bot/         ← Telegram Bot ✅ Production (Cloud Run)
│   ├── frontend/             ← Next.js 14 dashboard
│   ├── contracts/            ← Solidity smart contracts (Sepolia)
│   ├── genlayer/             ← GenLayer intelligent smart contracts
│   └── avalanche/            ← HolonChain subnet config
├── HOFI_COWORK_MEMORY.md     ← Live session memory for Claude Cowork
├── ROADMAP.md                ← Detailed pending chats
└── VOICE_TENZO_MEMORY.md     ← Voice and Tenzo technical history
```

---

## Infrastructure

### Cloud Run Services (GCP — `hofi-v2-2026`, `us-central1`)

**Tenzo Agent**
- URL: `https://hofi-tenzo-1080243330445.us-central1.run.app`
- Model: `gemini-2.5-flash`
- DB: Cloud SQL PostgreSQL 15 (`hofi_db`)

**Telegram Bot**
- URL: `https://hofi-bot-qpxiby6ona-uc.a.run.app`
- End-to-end latency: ~19 seconds
- Voice model: librosa + MFCC(40) + YIN pitch + LPC formants (98-dim embedding)

### Voice Biometrics
Authentication works in two layers:
1. Audio says "I am X" → looks up profile by name → verifies voice (threshold: 0.80)
2. No name → pure voice matching (threshold: 0.90)

---

## Current Status

| Component | Status |
|-----------|--------|
| Tenzo Agent v1.0.0 | ✅ Production |
| Telegram Bot | ✅ Production |
| Voice biometrics (Doco) | ✅ Authenticated (0.99+) |
| GenLayer ISC v0.2.2 (Bradbury) | ⏳ Deployed — `set_holon_rules` pending |
| Cloud SQL | ✅ Active |
| Task catalog DB | ⚠️ OperationalError → mock fallback (functional) |
| HolonChain (Fuji) | ✅ Node running — bootstrapping |
| On-chain task minting | ⏳ Pending HolonChain |
| TTS voice responses | ⏳ Pending |
| Next.js dashboard | ✅ Functional |

---

## Immediate Pending Tasks 🔴

1. **`set_holon_rules` on Bradbury** — ISC deployed but holon rules for `familia-valdes` not yet registered.
   ```powershell
   $env:BRADBURY_PRIVATE_KEY = "0x<private_key>"
   python packages/tenzo-agent/deploy_bradbury.py
   ```

2. **Update `TENZO_ORACLE_ADDRESS` in Cloud Run** — point from Asimov to Bradbury address:
   ```powershell
   gcloud run services update hofi-tenzo --project=hofi-v2-2026 --region=us-central1 `
     --update-env-vars="TENZO_ORACLE_ADDRESS=0x68396D5f7e1887054F54f9a55A71faE08C6a07B7"
   ```

3. **Fund GenLayer account** — `write_contract` on Bradbury requires GEN fees. Add account key for `0xb755bEb8777459d8c2b4E3fEA6676aa481a03ED8` (balance: 99.96 GEN).

4. **Validate ISC on Bradbury** — after completing 1–3, run `python test_genlayer_v10.py` to confirm all 3 cases with real Bradbury consensus.

5. **Fix encoding in bot messages** — double UTF-8 encoding produces `???` in user-facing messages.

---

## The Onboarding Ritual

A new holon is configured through a **collective voice conversation** — the whole community gathered, responding together to an intelligent agent that listens, learns, and reflects back what it understood.

The process is guided by an **Assembly of Experts** — five specialized AI agents observing in the background:

| Expert | Role |
|--------|------|
| **The Pedagogue** | Detects how each member learns. Proposes how the Tenzo should speak with this specific community. |
| **The Cooperativist** | Detects the implicit governance model. Proposes voting structures and consensus rules. |
| **The Guardian of Care** | Identifies invisible tasks — human, animal, and ecological. Ensures the planet's care carries equal weight. |
| **The Facilitator** | Reads group dynamics. Detects tensions, silences, leadership. Proposes participation mechanisms that include the quietest voices. |
| **The Regenerator** | Covers the territory as a living system. Wetland restoration, distributed solar, permaculture, biomimetics. |

At the end, the holon's Tenzo is configured with a catalog of at least **20 care tasks** — defined in the community's own words, with their own names, their own value ranges.

**The minimum setup requires only:** one phone and Telegram. Nothing else.

---

## The HoFi Node (Physical Device)

For communities without smartphones, for children we don't want near screens, for elders in the Delta — there is a physical version of the Tenzo.

- **Raspberry Pi Zero W** (~$15)
- One physical button
- A small microphone
- A speaker
- One LED (green = listening, orange = thinking, blue = responding)

Press the button → speak → hear the Tenzo respond. No screen. No password. No account. No app.

**Design principle:** if a 6-year-old can use it alone, anyone can.

---

## The Expert Council — Continuous Intelligence

The Assembly of Experts is not only active during onboarding. It becomes the permanent epistemic nervous system of the Tenzo:

- Each expert maintains its own update cycle (weekly, monthly, or quarterly)
- Experts perform web searches in their specialty domain and synthesize relevant findings
- The Tenzo inherits these updates — its knowledge stays fresh over time
- The Tenzo can become **proactive**: gently surfacing known recurring tasks that haven't been reported, or suggesting new ones that emerge from what the experts observe

When the Tenzo suggests organizing care shifts for a sick member, it sends a **private message** to the two or three people who historically perform that kind of care — not a broadcast to the group. Each response teaches the system:

| Response | What the Tenzo learns |
|----------|-----------------------|
| "Today I can't, Thursday yes" | Temporal availability — ask again Thursday |
| "That's not for me" | Personal limit — don't insist on this task type with this person |
| Already doing it without reporting | Invisible task that needs recognition, not assignment |
| Silence | This person needs another channel, another moment |

---

## Pilot Holons

Three real communities in Argentina:

**Familia Valdés** — intimate high-trust laboratory. Currently testing in production.

**Archi Brazo** — cooperative of regenerative architecture and design in Buenos Aires. Phase 2.

**El Pantano** — ecovillage in development on an island in the Tigre Delta. Limited connectivity, communal living, wetland restoration. Phase 2.

---

## Useful Commands

```powershell
# Live bot logs
gcloud beta run services logs tail hofi-bot --project=hofi-v2-2026 --region=us-central1

# Quick bot restart (renews JWT after Tenzo redeploy)
gcloud run services update hofi-bot --project=hofi-v2-2026 --region=us-central1 `
  --update-env-vars="FORCE_RESTART=$(Get-Date -Format 'yyyyMMddHHmmss')"

# Update Tenzo threshold without rebuild
gcloud run services update hofi-tenzo --project=hofi-v2-2026 --region=us-central1 `
  --update-env-vars="CONFIANZA_APROBACION_DIRECTA=0.70"

# Full Tenzo redeploy
# NOTA: --memory=2Gi requerido desde que /evaluar-voz carga faster-whisper base.
# --cpu-boost acelera la carga inicial del modelo en cold start.
cd C:\dev\hofi-protocol\packages\tenzo-agent
gcloud run deploy hofi-tenzo --source . --region=us-central1 --project=hofi-v2-2026 `
  --add-cloudsql-instances=hofi-v2-2026:us-central1:hofi-db `
  --memory=2Gi --cpu=2 --cpu-boost --timeout=300 --quiet

# Full bot rebuild
cd C:\dev\hofi-protocol\packages\telegram-bot
.\deploy.ps1
```

---

## Frontend (Next.js 14)

```bash
cd packages/frontend
npm run dev   # http://localhost:3000
```

For Vercel deployment, set **Root Directory** to `packages/frontend` and configure environment variables: `JWT_SECRET_KEY`, `TENZO_AGENT_URL`, `DEMO_API_KEY`, `NEXT_PUBLIC_APP_URL`, `NEXT_PUBLIC_CHAIN_ID`, `NEXT_PUBLIC_HOCA_TOKEN`.

---

## The Team

**Pablo Valdés (Doco)** — Architect, Zen monk, cooperative leader. President of Archi Brazo. Founder of El Pantano.

---

> *"Suddhodana built walls so Buddha would not see the suffering.*
> *HoFi builds bridges so that care is finally visible."*
> — Uma, 17

---

*HoFi Protocol · March 2026*# hofi-protocol
