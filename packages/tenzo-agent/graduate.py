"""Graduación custodial → self-custody.

Barre los activos fungibles (CUIDA + recibos + ADA) de la wallet custodial de una
persona a su wallet propia, firmando con la clave custodial re-derivada del seed
maestro, y marca `custody_mode='self'`. La membresía soul-bound y la reputación
quedan INTACTAS: viven en el validador, atadas al `person_id`, no a la wallet.

Pre-requisito de confianza: este módulo NO verifica la firma de la wallet nueva —
asume que el frontend ya probó el control de `new_address` (Sign-In with Cardano)
antes de invocar. La verificación CIP-30 vive en la ruta del frontend.

Env: BLOCKFROST_PROJECT_ID, HOFI_MASTER_MNEMONIC, HOFI_DEPLOYMENT, DB_* (para el store)
"""
import json
import os
from pathlib import Path

from pycardano import BlockFrostChainContext

from approve_task import blockfrost_base
from custodial_store import NeonIndexStore
from custodial_wallet import CustodialWallets


def graduate_custodial(person_id: str, new_address: str) -> dict:
    """Mueve los fondos de la custodial de `person_id` a `new_address` (self-custody)."""
    if not person_id or not new_address:
        raise ValueError("person_id y new_address son requeridos")

    store = NeonIndexStore()
    idx = store.get_index(person_id)
    if idx is None:
        raise RuntimeError(f"'{person_id}' no tiene wallet custodial; nada que graduar")

    dep = json.loads(Path(os.environ["HOFI_DEPLOYMENT"]).read_text())
    context = BlockFrostChainContext(
        os.environ["BLOCKFROST_PROJECT_ID"],
        base_url=blockfrost_base(dep.get("network", "preview")),
    )

    cw = CustodialWallets()  # HOFI_MASTER_MNEMONIC
    custodial_addr = str(cw.address(idx))
    signed = cw.build_graduation_tx(idx, new_address, context)
    tx_id = context.submit_tx(signed.to_cbor())

    store.set_custody_self(person_id, new_address)  # custody_mode='self'
    return {
        "tx_id": str(tx_id),
        "person_id": person_id,
        "from_custodial": custodial_addr,
        "to_self": new_address,
        "network": dep.get("network", "preview"),
    }
