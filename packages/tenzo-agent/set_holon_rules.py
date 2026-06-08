"""
set_holon_rules.py — Registra reglas de holones en el TenzoEquityOracle ISC

Uso (registrar un holón):
    set TENZO_WALLET_KEY=0x<private_key>
    set HOLON_ID=familia-mourino          # opcional, default: familia-mourino
    python set_holon_rules.py

Wallet del Tenzo en Bradbury: 0xb755bEb8777459d8c2b4E3fEA6676aa481a03ED8 (99 GEN)
Oracle:                        0x68396D5f7e1887054F54f9a55A71faE08C6a07B7
"""

import os, sys
from genlayer_py import create_client, create_account, testnet_bradbury
from genlayer_py.types import TransactionStatus

ORACLE_ADDRESS = "0x68396D5f7e1887054F54f9a55A71faE08C6a07B7"

RULES_POR_HOLON = {
    "familia-valdes": (
        "Holón familiar orientado al cuidado regenerativo. "
        "Se valoran tareas de cuidado humano (cocinar, cuidar niños, acompañar enfermos), "
        "cuidado animal, cuidado ecológico (huerta, compostaje, semillas), "
        "y mantenimiento del hogar. "
        "Tasa base: ~60 HoCa/hora. El cuidado emocional y el trabajo invisible "
        "reciben el mismo reconocimiento que el trabajo físico visible."
    ),
    "familia-mourino": (
        "Holón familiar orientado al cuidado regenerativo. "
        "Se valoran tareas de cuidado humano (cocinar, cuidar niños, acompañar enfermos), "
        "cuidado animal, cuidado ecológico (huerta, compostaje, semillas), "
        "y mantenimiento del hogar. "
        "Tasa base: ~60 HoCa/hora. El cuidado emocional y el trabajo invisible "
        "reciben el mismo reconocimiento que el trabajo físico visible."
    ),
}

WAIT_INTERVAL_MS = 10_000
WAIT_RETRIES     = 60


def _make_client(pk: str):
    account = create_account(account_private_key=pk)
    client  = create_client(chain=testnet_bradbury, account=account)
    original = client.provider.make_request
    def patched(method, *args, **kwargs):
        if method == "eth_estimateGas":
            return {"result": 90_000_000}
        resp = original(method, *args, **kwargs)
        if method == "gen_call" and isinstance(resp.get("result"), dict):
            resp["result"] = resp["result"].get("data", "")
        return resp
    client.provider.make_request = patched
    return client, account


def registrar_holon(pk: str, holon_id: str, rules: str):
    client, account = _make_client(pk)
    print(f"Cuenta:   {account.address}")
    print(f"Oracle:   {ORACLE_ADDRESS}")
    print(f"Holón:    {holon_id}")
    print(f"Red:      Bradbury testnet\n")

    tx_hash = client.write_contract(
        address=ORACLE_ADDRESS,
        function_name="set_holon_rules",
        args=[holon_id, rules],
    )
    print(f"TX hash: {tx_hash}")
    print(f"Esperando FINALIZED (hasta {WAIT_RETRIES * WAIT_INTERVAL_MS // 1000}s)...")

    receipt = client.wait_for_transaction_receipt(
        transaction_hash=tx_hash,
        status=TransactionStatus.FINALIZED,
        interval=WAIT_INTERVAL_MS,
        retries=WAIT_RETRIES,
        full_transaction=True,
    )
    r = receipt if isinstance(receipt, dict) else vars(receipt) if hasattr(receipt, "__dict__") else {}
    print(f"status={r.get('status_name','?')} result={r.get('result_name','?')}")
    print(f"✅ Reglas de {holon_id} registradas en el oracle.")


def main():
    pk = os.getenv("TENZO_WALLET_KEY") or os.getenv("BRADBURY_PRIVATE_KEY")
    if not pk:
        print("ERROR: falta TENZO_WALLET_KEY (o BRADBURY_PRIVATE_KEY)")
        sys.exit(1)

    holon_id = os.getenv("HOLON_ID", "familia-mourino")
    if holon_id not in RULES_POR_HOLON:
        print(f"ERROR: holón '{holon_id}' no tiene reglas definidas en este script.")
        print(f"Holones disponibles: {list(RULES_POR_HOLON.keys())}")
        sys.exit(1)

    registrar_holon(pk, holon_id, RULES_POR_HOLON[holon_id])


if __name__ == "__main__":
    main()
