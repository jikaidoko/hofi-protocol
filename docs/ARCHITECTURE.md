# HoFi Protocol - Architecture

## Overview
HoFi es un sistema ReFi (Regenerative Finance) de 3 capas para tokenizar la economia del cuidado comunitario.

## Capas

### Capa 1 - Agente Tenzo (Off-chain)
- FastAPI + Python 3.11 en Cloud Run (GCP us-central1)
- LLM: Gemini 2.5 Flash para evaluacion de tareas
- PostgreSQL (Cloud SQL) para historial
- Auth JWT Bearer

### Capa 2 - Smart Contracts (Ethereum Sepolia)
- HoCaToken: ERC-20 de cuidado comunitario
- HolonSBT: Soul Bound Token de membresia holonica
- TaskRegistry: Registro on-chain de tareas completadas

### Capa 3 - Intelligent Smart Contracts (GenLayer)
- TenzoEquityOracle: Evalua equidad de recompensas
- HolonSBT ISC: Verificacion de membresia con IA
- InterHolonTreasury: Tesoreria cross-holon descentralizada

## Flujo Principal
1. Usuario propone tarea en el frontend
2. Tenzo Agent evalua con Gemini 2.5 Flash
3. Si aprobada: mintea HoCa tokens al contribuyente
4. TaskRegistry registra la tarea on-chain
5. GenLayer ISCs auditan la equidad del proceso
