"""Firmado de decisiones — abstracción híbrida (custodial ahora, CIP-30 después).

El consensus_registry exige firmas reales de quórum M-de-N (extra_signatories).
Quién las produce define la arquitectura, así que lo abstraemos igual que el
ChainAdapter / ConsensusAdapter del repo:

- `CustodialSigner`  — el servidor deriva las wallets HD de los participantes
  (un único seed maestro en KMS, índice por person_id) y produce las M firmas.
  Registro de un clic. Es el modo del MVP.
- `Cip30Signer`      — stub: self-custody real, cada participante firma su witness
  en el navegador. Pendiente el flujo de recolección multi-parte.

Selección por env `CONSENSUS_SIGNER` (custodial | cip30); default custodial.

`record_decision.py` depende solo de la interfaz `DecisionSigner`, no de la
implementación: para swappear a CIP-30 no se toca la construcción de la tx.
"""
from __future__ import annotations

import os
from typing import List, Protocol, runtime_checkable

from pycardano import (
    Address,
    ChainContext,
    Transaction,
    TransactionBuilder,
)

# Mismo directorio (backend único del Tenzo): reutilizamos las wallets custodiales.
from custodial_wallet import CustodialWallets, IndexStore


@runtime_checkable
class DecisionSigner(Protocol):
    """Resuelve participantes -> VKH y finaliza (firma + envía) la tx de registro."""

    def resolve_vkh(self, person_id: str) -> bytes:
        """VKH (28 bytes) del participante. Va al datum y a extra_signatories."""
        ...

    def change_address(self) -> Address:
        """Dirección que paga fees y recibe el change (el holon / la tesorería)."""
        ...

    def finalize(
        self, builder: TransactionBuilder, signer_ids: List[str], context: ChainContext
    ) -> str:
        """Firma con las claves del quórum (`signer_ids`) y envía. Devuelve tx_id."""
        ...


class CustodialSigner:
    """Quórum custodial + pagador desacoplado.

    Los participantes firman con sus claves HD re-derivadas del seed maestro. El
    fee / colateral / change los aporta un PAGADOR separado (`payer_skey` +
    `payer_address`, típicamente el Tenzo), que firma como dueño de los inputs.

    Así 'quién paga' queda desacoplado de 'quién decide': el contrato solo exige el
    quórum de participantes en extra_signatories; la firma del pagador es solo para
    gastar sus UTXOs. Se funda una sola wallet (el Tenzo), no la de cada holon."""

    def __init__(self, wallets: CustodialWallets, store: IndexStore,
                 payer_skey, payer_address: Address):
        self.wallets = wallets
        self.store = store
        self.payer_skey = payer_skey          # PaymentSigningKey | ExtendedSigningKey
        self.payer_address = payer_address

    def _index(self, person_id: str) -> int:
        idx = self.store.get_index(person_id)
        if idx is None:
            idx = self.store.assign_index(person_id)
        return idx

    def resolve_vkh(self, person_id: str) -> bytes:
        skey = self.wallets.signing_key(self._index(person_id))
        return skey.to_verification_key().hash().payload

    def change_address(self) -> Address:
        return self.payer_address

    def finalize(
        self, builder: TransactionBuilder, signer_ids: List[str], context: ChainContext
    ) -> str:
        # pagador (dueño de inputs/colateral) + quórum de participantes
        keys = [self.payer_skey] + [
            self.wallets.signing_key(self._index(pid)) for pid in signer_ids
        ]
        signed: Transaction = builder.build_and_sign(
            keys, change_address=self.payer_address
        )
        return str(context.submit_tx(signed.to_cbor()))


class Cip30Signer:
    """Self-custody multi-firma (CIP-30) — pendiente.

    El flujo correcto: construir la tx SIN firmar, enviarla al navegador de cada
    participante para que aporte su witness (CIP-30 signTx con partialSign), y
    ensamblar los witnesses antes de submit. Requiere coordinación multi-parte
    (no cabe en una llamada server-side), por eso queda como stub explícito."""

    def resolve_vkh(self, person_id: str) -> bytes:
        raise NotImplementedError(
            "Cip30Signer: la resolución de VKH viene del navegador (getUsedAddresses)."
        )

    def change_address(self) -> Address:
        raise NotImplementedError("Cip30Signer pendiente.")

    def finalize(
        self, builder: TransactionBuilder, signer_ids: List[str], context: ChainContext
    ) -> str:
        raise NotImplementedError(
            "CIP-30 multi-firma pendiente: construir tx sin firmar, recolectar "
            "witnesses de cada wallet (partialSign) y ensamblar antes de submit."
        )


def signer_from_env(
    *, wallets: CustodialWallets | None = None,
    store: IndexStore | None = None,
    payer_skey=None,
    payer_address: Address | None = None,
) -> DecisionSigner:
    """Selecciona la implementación por env CONSENSUS_SIGNER (default custodial)."""
    mode = os.environ.get("CONSENSUS_SIGNER", "custodial").lower()
    if mode == "cip30":
        return Cip30Signer()
    if mode == "custodial":
        if wallets is None or store is None or payer_skey is None or payer_address is None:
            raise ValueError(
                "CustodialSigner requiere `wallets`, `store`, `payer_skey` y `payer_address`"
            )
        return CustodialSigner(wallets, store, payer_skey, payer_address)
    raise ValueError(f"CONSENSUS_SIGNER desconocido: {mode!r} (usa custodial|cip30)")
