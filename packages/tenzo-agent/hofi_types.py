"""Datums y redeemers de HoFi — espejo de lib/hofi/types.ak.

Fuente única de verdad off-chain (Python). CONSTR_ID = índice del constructor en
Aiken. El blueprint CIP-57 (plutus.json) es la fuente de verdad de los esquemas;
estas clases lo implementan para PyCardano.
"""
from dataclasses import dataclass
from typing import Union

from pycardano import PlutusData


@dataclass
class HolonState(PlutusData):
    """`emission` — contador de emisión por holón."""
    CONSTR_ID = 0
    holon_id: bytes
    total_emitido: int


# Aiken `Bool`: False = Constr 0, True = Constr 1 (sin campos).
@dataclass
class BFalse(PlutusData):
    CONSTR_ID = 0


@dataclass
class BTrue(PlutusData):
    CONSTR_ID = 1


AikenBool = Union[BFalse, BTrue]


@dataclass
class MembershipDatum(PlutusData):
    """`membership` — SBT: rol, actividad, reputación."""
    CONSTR_ID = 0
    holon_id: bytes
    role: bytes
    active: AikenBool
    reputation: int


# TokenAction (holon_token / membership mint)
@dataclass
class Mint(PlutusData):
    CONSTR_ID = 0


@dataclass
class Burn(PlutusData):
    CONSTR_ID = 1


# EmissionAction
@dataclass
class Operate(PlutusData):
    CONSTR_ID = 0


# MembershipAction
@dataclass
class UpdateReputation(PlutusData):
    CONSTR_ID = 0
    new_reputation: int


@dataclass
class Deactivate(PlutusData):
    CONSTR_ID = 1


@dataclass
class Unit(PlutusData):
    """Redeemer Void para task_reward (`_redeemer: Data`)."""
    CONSTR_ID = 0
