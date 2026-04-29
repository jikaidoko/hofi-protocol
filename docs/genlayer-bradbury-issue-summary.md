# Bradbury: TXs con `feeCap 0` rechazadas y view functions revierten

**Fecha:** 29 de abril de 2026
**Proyecto:** HoFi Protocol — TenzoEquityOracle v0.2.2
**Contrato:** `0x68396D5f7e1887054F54f9a55A71faE08C6a07B7` (Bradbury)
**SDK en uso:** `genlayer-py==0.17.0`, `web3==7.15.0`, Python 3.12
**Reportado por:** equipo HoFi (jikaidoko)

## Síntomas observados

Tras instalar `genlayer-py` en producción y empezar a invocar
`validate_task_equity()` desde el Tenzo Agent, la TX vuelve siempre con:

```
GenLayerError: eth_sendRawTransaction failed (code=-32602):
  [<txhash>]: transaction feeCap 0 below chain minimum
```

Replicamos el comportamiento desde un script local (`test_genlayer_v10.py`)
que envía calldata cruda con `eth_sendRawTransaction`, `gas=90M`, `gasPrice=0`,
firmada con cuenta efímera (`Account.create()`).

**Resultado completo del diagnóstico local:**

```
--- 1. View functions (calldata crudo) ---
  get_owner: excepcion eth_call failed (code=3): execution reverted
  get_holon_rules: excepcion eth_call failed (code=3): execution reverted

--- 2. eth_call sobre validate_task_equity (capturar stderr) ---
  [crudo]       excepcion: GenLayerError: eth_call failed (code=3): execution reverted
  [rlp_wrapped] excepcion: GenLayerError: eth_call failed (code=3): execution reverted

--- 3. eth_sendRawTransaction: crudo vs RLP wrapper ---
  [crudo]       error: transaction feeCap 0 below chain minimum
  [rlp_wrapped] error: transaction feeCap 0 below chain minimum

--- 4. gen_call ---
  gen_call response: { "message": "Internal Server Error" }
```

## Contexto histórico

El patrón de `gas=21000, gasPrice=0` con cuenta efímera funcionaba en abril
(cuando Bradbury reemplazó a Asimov, 22-abr-2026). Documentado en la memoria
del repo:

> "GenLayer Studio Studionet acepta TXs sin gas porque los ISCs con LLM no
> usan el modelo de gas de EVM."

Hoy esa premisa parece haber dejado de ser cierta.

Adicionalmente, las view functions (`get_owner`, `get_holon_rules`) que el
22-abr respondían correctamente, hoy revierten también en `eth_call` —
sugiriendo que el problema podría ir más allá del fee mínimo.

## Preguntas concretas

1. **¿Bradbury cambió las reglas de fees?** ¿Cuál es el mínimo actual de
   `feeCap` / `gasPrice`? ¿Cómo lo consultamos en runtime?

2. **¿Las cuentas efímeras siguen soportadas para invocar ISCs?**
   Con fee mínimo > 0, `Account.create()` sin fondos no puede pagar.
   ¿Hay faucet de Bradbury? ¿Hay una wallet system para tests?

3. **¿El contrato `0x68396D5f...` (TenzoEquityOracle v0.2.2) sigue
   deployado y operativo?** `get_owner()` revierte con `execution reverted`,
   sin razón aparente. ¿Bradbury fue resetada? Si sí, necesitamos
   redeploy + `set_holon_rules` para los holones `familia-valdes` y
   `familia-mourino`.

4. **¿`gen_call` cambió de signature?** Devuelve `Internal Server Error`
   con args canónicos. ¿La forma del request cambió en el RPC de Bradbury?

5. **¿`genlayer-py 0.17.0` está al día con el protocolo/encoding actual
   de Bradbury?** Si el formato de calldata cambió (ULEB128, RLP wrappers),
   tal vez hay que upgradear el SDK.

## Stack actualmente desplegado

- Servicio: `hofi-tenzo` en Cloud Run, revisión `hofi-tenzo-00026-57n`
- URL: https://hofi-tenzo-1080243330445.us-central1.run.app
- Imagen: `us-central1-docker.pkg.dev/hofi-v2-2026/hofi-repo/hofi-tenzo:fix-genlayer-py-29abr`
  - digest: `sha256:225ef738724498cca2c113f3626034ad612ee1a574769a4ef189469a119a965a`
- Wallet del Tenzo (mintea CUIDA en HolonChain, **no** se usa para Bradbury):
  `0xb755bEb8777459d8c2b4E3fEA6676aa481a03ED8`
- Cuenta usada en TX a Bradbury: efímera, sin balance.

## Snapshot adjunto

- `docs/test-genlayer-v10-local.txt` — output crudo del diagnóstico.
- `docs/tenzo-service-snapshot.yaml` — config completa del servicio Cloud Run.
- `docs/genlayer-py-version.txt` — versión exacta del SDK.
