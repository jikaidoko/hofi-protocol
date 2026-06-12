#!/usr/bin/env python3
"""Tests off-chain del cierre de decisión (`withdraw`) — corren sin red ni secretos.

Cubren las piezas con lógica propia del módulo (lo que NO depende de Blockfrost):
  - `decode_decision_datum`: decodifica el inline datum en sus distintas formas.
  - `find_decision_utxo`: filtra por (holon_id, sequence) y desambigua/explota bien.
  - la matemática de la quema: MultiAsset con cantidad negativa de PARTICIPATION.

La parte on-chain (spend Withdraw + burn) ya la cubren los tests de Aiken
(consensus_registry: withdraw_*, participation_minting: burn_*).

Correr:  python withdraw_test.py      (o con pytest)
"""
from pycardano import (
    Address,
    AssetName,
    MultiAsset,
    Network,
    RawCBOR,
    ScriptHash,
    TransactionInput,
    TransactionId,
    TransactionOutput,
    UTxO,
    Value,
    VerificationKeyHash,
)

from consensus_types import (
    PARTICIPATION_ASSET,
    BurnParticipation,
    DecisionDatum,
    ProtocolMeta,
    Withdraw,
    compute_protocol_hash,
)
from withdraw import decode_decision_datum, find_decision_utxo

META = ProtocolMeta(level=1, blocks=[0, 1, 2, 3, 4, 5, 6],
                    modalities=[b"p2", b"i1", b"s4", b"d3", b"n2", b"c1", b"r1"])
VKH_A = bytes.fromhex("aa" * 28)
VKH_B = bytes.fromhex("bb" * 28)
VKH_C = bytes.fromhex("cc" * 28)
POLICY = bytes.fromhex("37c8b11521a9a57f07e5dfbe45a4d95b01fbde5c82ae712e14bdc576")
# dirección dummy (no se usa para filtrar: find_decision_utxo confía en el datum)
DUMMY_ADDR = Address(VerificationKeyHash(VKH_A), network=Network.TESTNET)


def make_datum(holon: str = "el-pantano", sequence: int = 1) -> DecisionDatum:
    return DecisionDatum(
        decision_text=b"El Pantano adopta turno de cocina rotativo",
        protocol_hash=compute_protocol_hash(META),
        protocol_meta=META,
        participants=[VKH_A, VKH_B, VKH_C],
        facilitator=VKH_A,
        timestamp_slot=131_000_000,
        holon_id=holon.encode(),
        sequence=sequence,
        quorum=2,
        participation_policy=POLICY,
    )


def _cbor(d: DecisionDatum) -> bytes:
    raw = d.to_cbor()
    return bytes.fromhex(raw) if isinstance(raw, str) else raw


def _utxo(datum_obj, *, tx_hex: str, index: int = 0) -> UTxO:
    """UTxO con N tokens de participación + min-ADA, como lo deja record_decision."""
    value = Value(
        2_000_000,
        MultiAsset.from_primitive({POLICY: {PARTICIPATION_ASSET: 3}}),
    )
    out = TransactionOutput(DUMMY_ADDR, value, datum=datum_obj)
    return UTxO(TransactionInput(TransactionId(bytes.fromhex(tx_hex)), index), out)


class FakeContext:
    """Stub de ChainContext: solo necesita .utxos(addr) para find_decision_utxo."""
    def __init__(self, utxos):
        self._utxos = utxos

    def utxos(self, _addr):
        return self._utxos


# ── decode_decision_datum ─────────────────────────────────────────

def test_decode_inline_rawcbor():
    # Forma de producción: Blockfrost entrega el inline datum como CBOR crudo.
    d = make_datum()
    out = TransactionOutput(DUMMY_ADDR, Value(2_000_000), datum=RawCBOR(_cbor(d)))
    assert decode_decision_datum(out) == d


def test_decode_inline_typed():
    # Forma ya tipada (PlutusData): atajo por isinstance.
    d = make_datum()
    out = TransactionOutput(DUMMY_ADDR, Value(2_000_000), datum=d)
    assert decode_decision_datum(out) == d


def test_decode_no_datum_is_none():
    out = TransactionOutput(DUMMY_ADDR, Value(2_000_000))
    assert decode_decision_datum(out) is None


def test_decode_garbage_is_none():
    # Un datum que no es un DecisionDatum no debe explotar — devuelve None.
    out = TransactionOutput(DUMMY_ADDR, Value(2_000_000), datum=RawCBOR(b"\x01\x02\x03"))
    assert decode_decision_datum(out) is None


# ── find_decision_utxo ────────────────────────────────────────────

def test_find_by_holon_and_sequence():
    a = _utxo(make_datum("el-pantano", 1), tx_hex="11" * 32)
    b = _utxo(make_datum("archi-brazo", 2), tx_hex="22" * 32)
    ctx = FakeContext([a, b])
    u, d = find_decision_utxo(ctx, "addr_dummy", holon_id="archi-brazo", sequence=2)
    assert d.holon_id == b"archi-brazo" and d.sequence == 2
    assert u.input.index == 0


def test_find_none_raises():
    ctx = FakeContext([_utxo(make_datum("el-pantano", 1), tx_hex="11" * 32)])
    try:
        find_decision_utxo(ctx, "addr_dummy", holon_id="otro", sequence=9)
        assert False, "debería haber lanzado LookupError"
    except LookupError:
        pass


def test_find_ambiguous_raises_without_txhash():
    # Dos UTXOs con la MISMA identidad (holon, seq) → ambiguo sin --tx-hash.
    a = _utxo(make_datum("el-pantano", 1), tx_hex="11" * 32)
    b = _utxo(make_datum("el-pantano", 1), tx_hex="22" * 32)
    ctx = FakeContext([a, b])
    try:
        find_decision_utxo(ctx, "addr_dummy", holon_id="el-pantano", sequence=1)
        assert False, "debería haber lanzado LookupError por ambigüedad"
    except LookupError:
        pass


def test_find_txhash_disambiguates():
    a = _utxo(make_datum("el-pantano", 1), tx_hex="11" * 32)
    b = _utxo(make_datum("el-pantano", 1), tx_hex="22" * 32)
    ctx = FakeContext([a, b])
    u, _ = find_decision_utxo(
        ctx, "addr_dummy", holon_id="el-pantano", sequence=1, tx_hash="22" * 32
    )
    assert str(u.input.transaction_id) == "22" * 32


def test_find_holon_only_when_unique():
    # Sin sequence: filtra solo por holon (sirve si hay una sola decisión del holon).
    ctx = FakeContext([_utxo(make_datum("el-pantano", 7), tx_hex="33" * 32)])
    _, d = find_decision_utxo(ctx, "addr_dummy", holon_id="el-pantano")
    assert d.sequence == 7


# ── matemática de la quema ────────────────────────────────────────

def test_burn_is_negative():
    # El validador exige quantity_of(mint, policy, "PARTICIPA") < 0.
    n = 3
    burn = MultiAsset.from_primitive({POLICY: {PARTICIPATION_ASSET: -n}})
    qty = burn[ScriptHash(POLICY)][AssetName(PARTICIPATION_ASSET)]
    assert qty == -3 and qty < 0


def test_burn_redeemer_constr_ids():
    # BurnParticipation=1 (mint policy), Withdraw=0 (spend) — espejo de types.ak.
    assert BurnParticipation.CONSTR_ID == 1
    assert Withdraw.CONSTR_ID == 0


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    ok = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS {fn.__name__}")
            ok += 1
        except Exception as e:
            print(f"  FAIL {fn.__name__}: {e}")
    print(f"{ok}/{len(fns)} tests OK")
