"""Datums y redeemers del Protocolo Modular de Consenso — espejo de
packages/contracts-consensus/lib/consensus_registry/types.ak.

Fuente única de verdad off-chain (Python) para PyCardano. CONSTR_ID = índice del
constructor en Aiken; el ORDEN de los campos debe coincidir exactamente con el
type de Aiken (los Constr de Plutus Data son posicionales).

El blueprint CIP-57 (contracts-consensus/plutus.json) es la fuente de verdad de
los esquemas; estas clases lo implementan.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import List

from pycardano import PlutusData

# Asset name de los tokens de participación (== participation_prefix en types.ak).
# El validador chequea quantity_of(mint, policy, PARTICIPATION_ASSET) == N.
PARTICIPATION_ASSET: bytes = b"PARTICIPA"


@dataclass
class ProtocolMeta(PlutusData):
    """La estructura que se hashea para el protocol_hash.

    protocol_hash = Blake2b-256(CBOR(ProtocolMeta)). Determinista: los mismos
    parámetros siempre producen el mismo hash (ver `compute_protocol_hash`).
    """
    CONSTR_ID = 0
    level: int
    blocks: List[int]
    modalities: List[bytes]


@dataclass
class DecisionDatum(PlutusData):
    """El datum que vive en cada UTXO del consensus_registry. Cada UTXO ES una
    decisión, inmutable. Propiedad colectiva: el Withdraw exige quórum M-de-N de
    `participants`. `participation_policy` vive acá (no como param del validador)
    para romper la dependencia circular de hashes (ver Fase A)."""
    CONSTR_ID = 0
    decision_text: bytes
    protocol_hash: bytes
    protocol_meta: ProtocolMeta
    participants: List[bytes]    # VKHs de los participantes (co-titulares)
    facilitator: bytes           # VKH del facilitador (metadato, no firma Withdraw)
    timestamp_slot: int
    holon_id: bytes              # puente semántico con HoFi
    sequence: int
    quorum: int
    participation_policy: bytes  # policy id de los NFT de participación de ESTA decisión


# ── Redeemer del spend validator (consensus_registry) ─────────────────────────
@dataclass
class Withdraw(PlutusData):
    """El holon (quórum M-de-N) cierra el UTXO y quema los NFT de participación."""
    CONSTR_ID = 0


# ── Redeemer de la minting policy (participation_minting) ──────────────────────
@dataclass
class MintParticipation(PlutusData):
    """Mintea N NFTs de participación al registrar una decisión."""
    CONSTR_ID = 0


@dataclass
class BurnParticipation(PlutusData):
    """Quema todos los NFTs de participación al hacer Withdraw."""
    CONSTR_ID = 1


def compute_protocol_hash(meta: ProtocolMeta) -> bytes:
    """Blake2b-256(CBOR(ProtocolMeta)) sobre el CBOR canónico de Plutus Data.

    On-chain el validador solo verifica `length(hash) == 32` (no recomputa), así
    que este hash es una convención compartida entre off-chain y el frontend: la
    huella del proceso. El frontend (protocolo-constructor) debe producir el MISMO
    CBOR de ProtocolMeta y el mismo blake2b-256 para que el hash coincida.
    """
    raw = meta.to_cbor()
    if isinstance(raw, str):  # tolerancia a versiones de pycardano que devuelven hex
        raw = bytes.fromhex(raw)
    return hashlib.blake2b(raw, digest_size=32).digest()
