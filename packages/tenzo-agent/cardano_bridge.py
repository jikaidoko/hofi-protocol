#!/usr/bin/env python3
"""CardanoBridge — adaptador on-chain del Tenzo para la línea Cardano.

Es el `CardanoAdapter` del addendum: misma interfaz que `onchain_bridge.TenzoBridge`
de la línea EVM (`approve_task_onchain`, `get_stats`, `get_bridge`), pero
implementado con PyCardano. Así el pipeline del Tenzo no cambia: solo se elige qué
bridge instanciar.

A diferencia del bridge EVM (que solo minteaba), este arma la tx ATÓMICA completa
(emission + holon_token + membership + task_reward) reusando
`approve_task.submit_approve_task`.

Entorno:
    CHAIN                   "cardano" para activar este bridge
    BLOCKFROST_PROJECT_ID   project id (preview/preprod/mainnet)
    TENZO_SKEY_FILE         signing key del Tenzo (o material desde KMS)
    HOFI_DEPLOYMENT         ruta a deployment.json (policy_ids/direcciones/scripts)

El mapeo persona→member_asset (qué NFT de membresía es del executor) lo conoce el
Tenzo off-chain; se pasa como `member_asset` (hex). El `task_id` puede venir del
registro de la tarea en la DB; si no, se genera uno.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path

from pycardano import (
    Address,
    BlockFrostChainContext,
    PaymentSigningKey,
)

from approve_task import blockfrost_base, submit_approve_task
from hofi_types import HolonState

logger = logging.getLogger("cardano_bridge")


class CardanoBridge:
    def __init__(self) -> None:
        dep_path = os.getenv("HOFI_DEPLOYMENT", "deployment.json")
        self.dep = json.loads(Path(dep_path).read_text())
        skey_file = os.environ["TENZO_SKEY_FILE"]
        self.skey = PaymentSigningKey.load(skey_file)
        self.context = BlockFrostChainContext(
            os.environ["BLOCKFROST_PROJECT_ID"],
            base_url=blockfrost_base(self.dep.get("network", "preview")),
        )
        logger.info(
            "CardanoBridge listo | red=%s | holones=%s",
            self.dep.get("network"), list(self.dep["holons"]),
        )

    def approve_task_onchain(
        self,
        executor: str,
        holon_id: str,
        categoria: str,
        duracion_horas: float,
        recompensa_hoca: float,
        razonamiento: str,
        *,
        member_asset: str,
        task_id: str | None = None,
    ) -> dict:
        """Arma+firma+envía la tx atómica de approve_task. Misma forma de llamada
        que el bridge EVM, con dos extras que la línea Cardano necesita:
        `member_asset` (NFT de membresía del executor) y `task_id` (recibo)."""
        task_id = task_id or f"task-{uuid.uuid4().hex[:12]}"
        # los native assets son enteros; el reward del holón va en unidades enteras
        reward = int(round(recompensa_hoca))
        r = submit_approve_task(
            dep=self.dep,
            holon=holon_id,
            executor=executor,
            member_asset=member_asset,
            reward=reward,
            task_id=task_id,
            categoria=categoria,
            duracion=int(duracion_horas),
            razonamiento=razonamiento,
            context=self.context,
            skey=self.skey,
        )
        logger.info(
            "approve_task on-chain | executor=%s holon=%s reward=%s tx=%s",
            executor, holon_id, reward, r["tx_id"],
        )
        # forma de retorno compatible/legible para el pipeline del Tenzo
        return {
            "tx_hash": r["tx_id"],
            "hoca_minted": reward,
            "policy_id": r["policy_id"],
            "reputation": r["reputation_after"],
            "task_id": r["task_id"],
            "network": r["network"],
        }

    def get_stats(self, holon_id: str = "familia-mourino") -> dict:
        """Total emitido del holón, leído del UTXO de estado de `emission`."""
        h = self.dep["holons"][holon_id]
        emission_addr = Address.from_primitive(h["emission"]["address"])
        utxos = self.context.utxos(str(emission_addr))
        total = 0
        if utxos:
            total = HolonState.from_cbor(utxos[0].output.datum.cbor).total_emitido
        return {
            "holon_id": holon_id,
            "total_emitido": total,
            "policy_id": h["holon_token"]["policy_id"],
            "network": self.dep.get("network", "preview"),
        }


_bridge: CardanoBridge | None = None


def get_bridge() -> CardanoBridge | None:
    """Factory: devuelve el bridge Cardano si el entorno está configurado.

    En el Tenzo, el selector de cadena hace:
        if os.getenv("CHAIN") == "cardano":
            from cardano_bridge import get_bridge
        else:
            from onchain_bridge import get_bridge   # EVM/GenLayer
    """
    global _bridge
    if _bridge is not None:
        return _bridge
    if not (os.getenv("TENZO_SKEY_FILE") and os.getenv("BLOCKFROST_PROJECT_ID")):
        return None
    try:
        _bridge = CardanoBridge()
        return _bridge
    except Exception as e:  # noqa: BLE001
        logger.error("No se pudo inicializar CardanoBridge: %s", e)
        return None
