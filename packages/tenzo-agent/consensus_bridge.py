#!/usr/bin/env python3
"""ConsensusBridge — settlement on-chain de decisiones del Protocolo Modular de
Consenso (línea Cardano). Análogo a cardano_bridge.CardanoBridge pero para
record_decision: arma/firma/envía la tx que asienta una decisión en el registry.

El pagador (fee/colateral/change) es el Tenzo (TENZO_SKEY_FILE); los participantes
firman el quórum con sus wallets custodiales HD (índices en Neon vía NeonIndexStore).
Import de pycardano: este módulo SOLO se importa desde el endpoint /consensus/record
(lazy), así la imagen EVM nunca lo carga.

Entorno:
    BLOCKFROST_PROJECT_ID       project id (preview/preprod/mainnet)
    TENZO_SKEY_FILE             signing key del Tenzo (pagador)
    HOFI_MASTER_MNEMONIC        seed maestro de wallets custodiales (participantes)
    HOFI_CONSENSUS_DEPLOYMENT   ruta a deployment.consensus.json
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from pycardano import (
    Address,
    BlockFrostChainContext,
    Network,
    PaymentSigningKey,
    PaymentVerificationKey,
)

from record_decision import blockfrost_base, submit_record_decision
from custodial_wallet import CustodialWallets
from custodial_store import NeonIndexStore

logger = logging.getLogger("consensus_bridge")


class _MixedSigner:
    """DecisionSigner con custodia mixta.

    - Participantes CUSTODIALES: el Tenzo deriva su clave HD y firma por ellos.
    - Participantes SELF-CUSTODY: su VKH se toma de su propia dirección, pero el
      Tenzo NO firma por ellos (sus dueños aprueban manualmente vía CIP-30).

    El pagador (fee/colateral) es el Tenzo. `custody` mapea person_id ->
    {mode, address, index}. `finalize` solo recibe signer_ids custodiales."""

    def __init__(self, wallets, payer_skey, payer_address, custody: dict):
        self.wallets = wallets
        self.payer_skey = payer_skey
        self.payer_address = payer_address
        self.custody = custody

    def resolve_vkh(self, person_id: str) -> bytes:
        c = self.custody[person_id]
        if c["mode"] == "self":
            # VKH del payment credential de su propia dirección (no la firmamos).
            return Address.from_primitive(c["address"]).payment_part.payload
        return self.wallets.signing_key(c["index"]).to_verification_key().hash().payload

    def change_address(self) -> Address:
        return self.payer_address

    def finalize(self, builder, signer_ids, context) -> str:
        keys = [self.payer_skey] + [
            self.wallets.signing_key(self.custody[pid]["index"]) for pid in signer_ids
        ]
        signed = builder.build_and_sign(keys, change_address=self.payer_address)
        return str(context.submit_tx(signed.to_cbor()))


class ConsensusBridge:
    def __init__(self) -> None:
        dep_path = os.getenv("HOFI_CONSENSUS_DEPLOYMENT", "deployment.consensus.json")
        self.dep = json.loads(Path(dep_path).read_text())
        self.skey = PaymentSigningKey.load(os.environ["TENZO_SKEY_FILE"])
        self.context = BlockFrostChainContext(
            os.environ["BLOCKFROST_PROJECT_ID"],
            base_url=blockfrost_base(self.dep.get("network", "preview")),
        )
        net = Network.MAINNET if self.dep.get("network") == "mainnet" else Network.TESTNET
        self.payer_address = Address(
            PaymentVerificationKey.from_signing_key(self.skey).hash(), network=net
        )
        self.wallets = CustodialWallets()  # HOFI_MASTER_MNEMONIC
        logger.info(
            "ConsensusBridge listo | red=%s | registry=%s",
            self.dep.get("network"), self.dep["consensus_registry"]["address"],
        )

    def _resolve_custody(self, store: NeonIndexStore, person_id: str) -> dict:
        """Custodia del participante. Si no existe, se auto-provisiona una custodial
        (mismo criterio que voz/mail en chain_selector.resolve_executor)."""
        c = store.get_custody(person_id)
        if c is None:
            idx = store.assign_index(person_id)
            return {"mode": "custodial", "address": None, "index": idx}
        return c

    def record_decision_onchain(
        self,
        *,
        holon_id: str,
        decision_text: str,
        participants: list[str],
        quorum: int,
        facilitator: str = "",
        sequence: int = 0,
        protocol: dict | None = None,
    ) -> dict:
        """Registra la decisión on-chain con custodia mixta.

        El Tenzo firma SOLO por los participantes custodiales. Si esos custodiales no
        alcanzan el quórum, NO se envía la tx: se devuelve `pending_manual_approval`
        con los participantes self-custody que deben aprobar manualmente (CIP-30).
        Las wallets self-custody nunca se firman del lado del servidor."""
        store = NeonIndexStore()

        # Custodia de participantes (+ facilitador, que también se resuelve a VKH).
        people = list(dict.fromkeys(participants + ([facilitator] if facilitator else [])))
        custody = {pid: self._resolve_custody(store, pid) for pid in people}

        custodial = [p for p in participants if custody[p]["mode"] != "self"]
        non_custodial = [p for p in participants if custody[p]["mode"] == "self"]

        # ¿Alcanzan los custodiales el quórum? Si no, hace falta aprobación manual.
        if len(custodial) < quorum:
            return {
                "status": "pending_manual_approval",
                "reason": "Faltan firmas de participantes self-custody para el quórum.",
                "needs_approval_from": non_custodial,
                "custodial_signers": len(custodial),
                "quorum": quorum,
                "participants": len(participants),
            }

        signer = _MixedSigner(self.wallets, self.skey, self.payer_address, custody)

        kwargs: dict = {}
        if protocol and all(k in protocol for k in ("level", "blocks", "modalities")):
            kwargs = {
                "level": protocol["level"],
                "blocks": protocol["blocks"],
                "modalities": protocol["modalities"],
            }

        r = submit_record_decision(
            dep=self.dep,
            holon_id=holon_id,
            decision_text=decision_text,
            participant_ids=participants,
            quorum=quorum,
            signer_ids=custodial[:quorum],  # el Tenzo firma solo custodiales (M de N)
            signer=signer,
            context=self.context,
            facilitator_id=facilitator,
            sequence=sequence,
            **kwargs,
        )
        r["status"] = "recorded"
        # Self-custody que participan pero no firmaron este quórum (informativo).
        r["non_custodial_participants"] = non_custodial
        return r

    def withdraw_decision_onchain(
        self,
        *,
        holon_id: str,
        sequence: int,
        tx_hash: str | None = None,
        signers: list[str] | None = None,
    ) -> dict:
        """Cierra una decisión on-chain (Withdraw) con custodia mixta.

        Los participantes NO viajan desde el frontend: se leen del datum on-chain
        (lista de VKH). El Tenzo cruza esos VKH con las wallets custodiales para
        saber quién puede firmar el quórum y firma SOLO por los custodiales. Si no
        alcanzan el quórum, NO se envía la tx: devuelve `pending_manual_approval`
        con los participantes self-custody que deben aprobar (CIP-30)."""
        from withdraw import find_decision_utxo, submit_withdraw

        registry_addr = self.dep["consensus_registry"]["address"]
        utxo, datum = find_decision_utxo(
            self.context, registry_addr,
            holon_id=holon_id, sequence=sequence, tx_hash=tx_hash,
        )
        participant_vkhs = set(datum.participants)  # VKHs (bytes) co-titulares

        # Cruzar los VKH del datum con las personas custodiales conocidas.
        store = NeonIndexStore()
        custodial_matches: dict[str, dict] = {}  # person_id -> custody
        non_custodial: list[str] = []            # person_ids self-custody que participan
        for p in store.list_people():
            if p["mode"] == "self":
                if not p["address"]:
                    continue
                vkh = Address.from_primitive(p["address"]).payment_part.payload
                if vkh in participant_vkhs:
                    non_custodial.append(p["person_id"])
            else:
                vkh = self.wallets.signing_key(p["index"]).to_verification_key().hash().payload
                if vkh in participant_vkhs:
                    custodial_matches[p["person_id"]] = {
                        "mode": "custodial", "address": p["address"], "index": p["index"],
                    }

        # Firmantes explícitos (opcional): deben ser custodiales y participantes.
        if signers:
            invalid = [s for s in signers if s not in custodial_matches]
            if invalid:
                raise ValueError(
                    f"firmantes inválidos (no custodiales o no participantes): {invalid}"
                )
            chosen = {s: custodial_matches[s] for s in signers}
        else:
            chosen = custodial_matches

        # ¿Alcanzan los custodiales el quórum? Si no, hace falta aprobación manual.
        if len(chosen) < datum.quorum:
            return {
                "status": "pending_manual_approval",
                "reason": "Los participantes custodiales no alcanzan el quórum para cerrar.",
                "needs_approval_from": non_custodial,
                "custodial_signers": len(chosen),
                "quorum": datum.quorum,
                "participants": len(datum.participants),
            }

        signer_ids = list(chosen.keys())[:datum.quorum]
        custody = {pid: chosen[pid] for pid in signer_ids}
        signer = _MixedSigner(self.wallets, self.skey, self.payer_address, custody)

        r = submit_withdraw(
            dep=self.dep,
            holon_id=holon_id,
            signer_ids=signer_ids,
            signer=signer,
            context=self.context,
            decision_utxo=utxo,
            decision_datum=datum,
        )
        r["status"] = "withdrawn"
        r["non_custodial_participants"] = non_custodial
        return r


_bridge: ConsensusBridge | None = None


def get_bridge() -> ConsensusBridge | None:
    """Factory singleton. Devuelve None si el entorno Cardano no está configurado."""
    global _bridge
    if _bridge is not None:
        return _bridge
    if not (os.getenv("TENZO_SKEY_FILE") and os.getenv("BLOCKFROST_PROJECT_ID")
            and os.getenv("HOFI_MASTER_MNEMONIC")):
        return None
    try:
        _bridge = ConsensusBridge()
        return _bridge
    except Exception as e:  # noqa: BLE001
        logger.error("No se pudo inicializar ConsensusBridge: %s", e)
        return None
