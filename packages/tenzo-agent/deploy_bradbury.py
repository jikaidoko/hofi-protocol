"""
deploy_bradbury.py — Deploya TenzoEquityOracle en GenLayer Bradbury Testnet

Uso:
    cd packages/tenzo-agent
    set BRADBURY_PRIVATE_KEY=0x<tu_private_key>
    python deploy_bradbury.py

Obtener GEN tokens para Bradbury:
    1. Ir a https://studio.genlayer.com → crear/importar cuenta
    2. Faucet: https://faucet-bradbury.genlayer.com (o pedir en Discord de GenLayer)
    3. Exportar private key desde Studio → pegarlo en BRADBURY_PRIVATE_KEY

Pasos:
    1. Lee el ISC de packages/genlayer/contracts/tenzo_equity_oracle.py
    2. Deploy en Bradbury (chainId=4221)
    3. Espera FINALIZED via SDK (usa consensus_data_contract, no eth_getTransactionByHash)
    4. Llama set_holon_rules para familia-valdes
    5. Imprime la nueva direccion
"""

import sys
import os
import json
import pathlib

from genlayer_py import create_client, create_account, testnet_bradbury
from genlayer_py.types import TransactionStatus

# ── Configuracion ─────────────────────────────────────────────────────────────

ISC_PATH = pathlib.Path(__file__).parent.parent / "genlayer" / "contracts" / "tenzo_equity_oracle.py"

HOLON_ID    = "familia-valdes"
HOLON_RULES = (
    "Holón familiar orientado al cuidado regenerativo. "
    "Se valoran tareas de cuidado humano (cocinar, cuidar niños, acompañar enfermos), "
    "cuidado animal, cuidado ecológico (huerta, compostaje, semillas), "
    "y mantenimiento del hogar. "
    "Tasa base: ~60 HoCa/hora. El cuidado emocional y el trabajo invisible "
    "reciben el mismo reconocimiento que el trabajo físico visible."
)

# SDK defaults son 10s interval × 20 retries = 200s. Aumentamos para deploy lento.
WAIT_INTERVAL_MS = 10_000   # 10 segundos entre polls
WAIT_RETRIES     = 60       # 60 × 10s = 600s max


def main():
    # 1. Leer ISC
    if not ISC_PATH.exists():
        print(f"ERROR: No se encontró el ISC en {ISC_PATH}")
        sys.exit(1)

    isc_code = ISC_PATH.read_text(encoding="utf-8")
    print(f"ISC leído: {ISC_PATH.name} ({len(isc_code)} chars)")

    # 2. Crear cliente Bradbury con cuenta fundada
    pk = os.getenv("BRADBURY_PRIVATE_KEY")
    if not pk:
        print("ERROR: falta BRADBURY_PRIVATE_KEY")
        print("  set BRADBURY_PRIVATE_KEY=0x<tu_private_key>")
        print("  Obtener GEN: https://faucet-bradbury.genlayer.com o Discord de GenLayer")
        sys.exit(1)

    account = create_account(account_private_key=pk)
    client  = create_client(chain=testnet_bradbury, account=account)
    print(f"Cuenta: {account.address} | chainId={testnet_bradbury.id}")

    # Verificar balance
    try:
        balance = client.get_balance(account.address)
        print(f"Balance: {balance} wei ({balance / 10**18:.6f} GEN)")
        if balance == 0:
            print("ADVERTENCIA: balance = 0. El deploy puede fallar por fees.")
    except Exception as e:
        print(f"No se pudo consultar balance: {e}")

    # Parchear eth_estimateGas (ISCs con LLM no pueden estimarse)
    # Parchear gen_call: Bradbury devuelve {"data": "hex", "status": {...}} en lugar de "hex" directo
    original_make_request = client.provider.make_request
    def patched_make_request(method, *args, **kwargs):
        if method == "eth_estimateGas":
            return {"result": 90_000_000}
        resp = original_make_request(method, *args, **kwargs)
        if method == "gen_call" and isinstance(resp.get("result"), dict):
            resp["result"] = resp["result"].get("data", "")
        return resp
    client.provider.make_request = patched_make_request

    # 3. Deploy del ISC
    print("\n=== PASO 1: Deploy del ISC ===")
    try:
        tx_hash = client.deploy_contract(code=isc_code, args=[])
        print(f"  TX hash: {tx_hash}")
    except Exception as e:
        print(f"  ERROR en deploy_contract: {type(e).__name__}: {e}")
        sys.exit(1)

    print(f"  Esperando FINALIZED via SDK (hasta {WAIT_RETRIES * WAIT_INTERVAL_MS // 1000}s)...")
    try:
        receipt = client.wait_for_transaction_receipt(
            transaction_hash=tx_hash,
            status=TransactionStatus.FINALIZED,
            interval=WAIT_INTERVAL_MS,
            retries=WAIT_RETRIES,
            full_transaction=True,
        )
    except Exception as e:
        print(f"  ERROR esperando receipt: {type(e).__name__}: {e}")
        sys.exit(1)

    print(f"  Receipt recibido. Tipo: {type(receipt).__name__}")

    # Extraer contract_address del receipt
    contract_address = None
    receipt_dict = receipt if isinstance(receipt, dict) else vars(receipt) if hasattr(receipt, '__dict__') else {}

    # El SDK puede retornar el address en distintos campos
    for key in ("contract_address", "to_address", "recipient"):
        val = receipt_dict.get(key)
        if val and val != "0x0000000000000000000000000000000000000000":
            contract_address = val
            break

    # Fallback: buscar en campos anidados
    if not contract_address:
        print("  Receipt completo (primeros 2000 chars):")
        print(json.dumps(receipt_dict, indent=2, default=str)[:2000])

        # Intentar desde el explorer usando el tx_hash
        print(f"\n  Buscando address en explorer...")
        try:
            raw = client.provider.make_request("eth_getTransactionByHash", [str(tx_hash)])
            print("  eth_getTransactionByHash:", json.dumps(raw, indent=2, default=str)[:500])
        except Exception as e2:
            print(f"  eth_getTransactionByHash error: {e2}")

        print(f"\n  TX hash para buscar manualmente en el explorer:")
        print(f"  https://explorer-bradbury.genlayer.com/tx/{tx_hash}")
        sys.exit(1)

    print(f"\n  *** ORACLE_ADDRESS (Bradbury): {contract_address} ***")

    # 4. Registrar holon rules
    print("\n=== PASO 2: set_holon_rules ===")
    print(f"  holon_id: {HOLON_ID}")
    try:
        tx_hash2 = client.write_contract(
            address=contract_address,
            function_name="set_holon_rules",
            args=[HOLON_ID, HOLON_RULES],
        )
        print(f"  TX hash: {tx_hash2}")
        receipt2 = client.wait_for_transaction_receipt(
            transaction_hash=tx_hash2,
            status=TransactionStatus.FINALIZED,
            interval=WAIT_INTERVAL_MS,
            retries=WAIT_RETRIES,
            full_transaction=True,
        )
        r2 = receipt2 if isinstance(receipt2, dict) else vars(receipt2) if hasattr(receipt2, '__dict__') else {}
        print(f"  set_holon_rules: result={r2.get('result', '?')}")
    except Exception as e:
        print(f"  ERROR en set_holon_rules: {type(e).__name__}: {e}")
        print("  El contrato fue deployado. Registra las reglas manualmente.")

    # 5. Resumen
    print("\n" + "=" * 60)
    print("RESUMEN — actualiza estos valores en el proyecto:")
    print("=" * 60)
    print(f'ORACLE_ADDRESS (Bradbury) = "{contract_address}"')
    print()
    print("Archivos a actualizar:")
    print("  packages/tenzo-agent/test_genlayer_v10.py  → ORACLE_ADDRESS")
    print("  packages/tenzo-agent/genlayer_bridge.py    → ORACLE_ADDRESS (env var)")
    print("  Cloud Run hofi-tenzo → TENZO_ORACLE_ADDRESS")
    print("  HOFI_COWORK_MEMORY.md → sección TenzoEquityOracle")
    print("=" * 60)


if __name__ == "__main__":
    main()
