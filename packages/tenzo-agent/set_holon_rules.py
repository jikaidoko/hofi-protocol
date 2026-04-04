"""
set_holon_rules.py — Registra reglas de familia-valdes en el ISC ya deployado

Uso:
    set BRADBURY_PRIVATE_KEY=0x<tu_private_key>
    python set_holon_rules.py
"""

import os, sys
from genlayer_py import create_client, create_account, testnet_bradbury
from genlayer_py.types import TransactionStatus

ORACLE_ADDRESS = "0x68396D5f7e1887054F54f9a55A71faE08C6a07B7"

HOLON_ID    = "familia-valdes"
HOLON_RULES = (
    "Holón familiar orientado al cuidado regenerativo. "
    "Se valoran tareas de cuidado humano (cocinar, cuidar niños, acompañar enfermos), "
    "cuidado animal, cuidado ecológico (huerta, compostaje, semillas), "
    "y mantenimiento del hogar. "
    "Tasa base: ~60 HoCa/hora. El cuidado emocional y el trabajo invisible "
    "reciben el mismo reconocimiento que el trabajo físico visible."
)

WAIT_INTERVAL_MS = 10_000
WAIT_RETRIES     = 60

def main():
    pk = os.getenv("BRADBURY_PRIVATE_KEY")
    if not pk:
        print("ERROR: falta BRADBURY_PRIVATE_KEY")
        sys.exit(1)

    account = create_account(account_private_key=pk)
    client  = create_client(chain=testnet_bradbury, account=account)
    print(f"Cuenta: {account.address}")

    # Patch eth_estimateGas y gen_call response
    original = client.provider.make_request
    def patched(method, *args, **kwargs):
        if method == "eth_estimateGas":
            return {"result": 90_000_000}
        resp = original(method, *args, **kwargs)
        if method == "gen_call" and isinstance(resp.get("result"), dict):
            resp["result"] = resp["result"].get("data", "")
        return resp
    client.provider.make_request = patched

    print(f"\nLlamando set_holon_rules en {ORACLE_ADDRESS}...")
    print(f"  holon_id: {HOLON_ID}")

    tx_hash = client.write_contract(
        address=ORACLE_ADDRESS,
        function_name="set_holon_rules",
        args=[HOLON_ID, HOLON_RULES],
    )
    print(f"  TX hash: {tx_hash}")
    print(f"  Esperando FINALIZED (hasta {WAIT_RETRIES * WAIT_INTERVAL_MS // 1000}s)...")

    receipt = client.wait_for_transaction_receipt(
        transaction_hash=tx_hash,
        status=TransactionStatus.FINALIZED,
        interval=WAIT_INTERVAL_MS,
        retries=WAIT_RETRIES,
        full_transaction=True,
    )
    r = receipt if isinstance(receipt, dict) else vars(receipt) if hasattr(receipt, '__dict__') else {}
    print(f"\n  set_holon_rules: status={r.get('status_name','?')} result={r.get('result_name','?')}")
    print("\n✅ Reglas de familia-valdes registradas en el oracle.")

if __name__ == "__main__":
    main()
