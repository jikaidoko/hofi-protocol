#!/usr/bin/env python3
"""Fase 2 — tx `approve_task` del Tenzo (PyCardano).

Reemplaza approveTask() de TaskRegistry.sol. En eUTXO la "aprobacion de tarea" es
UNA transaccion atomica que el Tenzo construye y firma, y que los 4 validadores
hacen cumplir en conjunto: spend del estado de `emission` (+reward), mint de
`holon_token` (cap), spend de la membresia (reputation +1, NFT no sale), y mint
del recibo `task_reward`. + metadata CIP-20.

Este modulo expone:
  - `submit_approve_task(...)`  -> core reutilizable (lo usa el CLI y el
    CardanoBridge del Tenzo); construye, firma y envia la tx.
  - CLI (`main`) para correrlo a mano.

Entorno (CLI / bridge):
    BLOCKFROST_PROJECT_ID   project id (preview/preprod/mainnet)
    TENZO_SKEY_FILE         signing key del Tenzo
"""
import argparse
import json
import os
import sys
from pathlib import Path

from pycardano import (
    Address,
    AlonzoMetadata,
    AuxiliaryData,
    BlockFrostChainContext,
    ChainContext,
    Metadata,
    MultiAsset,
    PaymentSigningKey,
    PaymentVerificationKey,
    PlutusV3Script,
    Redeemer,
    ScriptHash,
    Transaction,
    TransactionBuilder,
    TransactionOutput,
    UTxO,
    Value,
)

from hofi_types import (
    HolonState, MembershipDatum, Mint, Operate, Unit, UpdateReputation,
)

STATE_MIN_ADA = 2_000_000
EXECUTOR_MIN_ADA = 2_000_000


def blockfrost_base(network: str) -> str:
    """URL base de Blockfrost segun la red declarada en deployment.json."""
    return f"https://cardano-{network}.blockfrost.io/api"


def _find_state_utxo(context: ChainContext, address: Address) -> UTxO:
    utxos = context.utxos(str(address))
    if not utxos:
        raise RuntimeError(f"no hay UTXO de estado en {address} (¿corriste bootstrap_state?)")
    return utxos[0]


def _find_member_utxo(context: ChainContext, address: Address, policy: ScriptHash, asset_name: bytes) -> UTxO:
    for u in context.utxos(str(address)):
        ma = u.output.amount.multi_asset
        if policy in ma and any(an.payload == asset_name for an in ma[policy]):
            return u
    raise RuntimeError(f"no encontre la membresia {asset_name.hex()} en {address}")


def submit_approve_task(
    *,
    dep: dict,
    holon: str,
    executor: str,
    member_asset: str,        # hex del asset_name del NFT de membresia
    reward: int,
    task_id: str,
    categoria: str = "",
    duracion: int = 0,
    razonamiento: str = "",
    context: ChainContext,
    skey: PaymentSigningKey,
) -> dict:
    """Core: arma la tx atomica de approve_task, la firma y la envia.

    Devuelve un dict con el resultado. No lee variables de entorno — recibe el
    `context` y la `skey` ya construidos (asi lo reusa el CardanoBridge).
    """
    h = dep["holons"][holon]
    asset_name = h["asset_name"].encode()
    member_asset_b = bytes.fromhex(member_asset)
    task_id_b = task_id.encode()

    emission_script = PlutusV3Script(bytes.fromhex(h["emission"]["compiled_code"]))
    token_script = PlutusV3Script(bytes.fromhex(h["holon_token"]["compiled_code"]))
    membership_script = PlutusV3Script(bytes.fromhex(dep["membership"]["compiled_code"]))
    receipt_script = PlutusV3Script(bytes.fromhex(h["task_reward"]["compiled_code"]))

    token_policy = ScriptHash(bytes.fromhex(h["holon_token"]["policy_id"]))
    receipt_policy = ScriptHash(bytes.fromhex(h["task_reward"]["policy_id"]))
    membership_policy = ScriptHash(bytes.fromhex(dep["membership"]["policy_id"]))

    vkey = PaymentVerificationKey.from_signing_key(skey)
    tenzo_vkh = vkey.hash()
    tenzo_addr = Address(payment_part=tenzo_vkh, network=context.network)
    emission_addr = Address.from_primitive(h["emission"]["address"])
    membership_addr = Address.from_primitive(dep["membership"]["address"])
    executor_addr = Address.from_primitive(executor)

    # leer estado on-chain real (los validadores exigen valores exactos)
    state_utxo = _find_state_utxo(context, emission_addr)
    before_state = HolonState.from_cbor(state_utxo.output.datum.cbor)
    member_utxo = _find_member_utxo(context, membership_addr, membership_policy, member_asset_b)
    before_member = MembershipDatum.from_cbor(member_utxo.output.datum.cbor)

    new_total = before_state.total_emitido + reward
    new_rep = before_member.reputation + 1

    after_state = HolonState(holon_id=holon.encode(), total_emitido=new_total)
    after_member = MembershipDatum(
        holon_id=before_member.holon_id,
        role=before_member.role,
        active=before_member.active,
        reputation=new_rep,
    )

    mint = MultiAsset.from_primitive(
        {bytes(token_policy): {asset_name: reward}, bytes(receipt_policy): {task_id_b: 1}}
    )

    builder = TransactionBuilder(context)
    builder.add_input_address(tenzo_addr)
    builder.add_script_input(state_utxo, emission_script, redeemer=Redeemer(Operate()))
    builder.add_output(
        TransactionOutput(emission_addr, Value(state_utxo.output.amount.coin), datum=after_state)
    )
    builder.add_script_input(
        member_utxo, membership_script, redeemer=Redeemer(UpdateReputation(new_rep))
    )
    builder.add_output(
        TransactionOutput(membership_addr, member_utxo.output.amount, datum=after_member)
    )
    builder.mint = mint
    builder.add_minting_script(token_script, redeemer=Redeemer(Mint()))
    builder.add_minting_script(receipt_script, redeemer=Redeemer(Unit()))

    payout = MultiAsset.from_primitive(
        {bytes(token_policy): {asset_name: reward}, bytes(receipt_policy): {task_id_b: 1}}
    )
    builder.add_output(TransactionOutput(executor_addr, Value(EXECUTOR_MIN_ADA, payout)))
    builder.required_signers = [tenzo_vkh]
    builder.auxiliary_data = AuxiliaryData(
        AlonzoMetadata(
            metadata=Metadata(
                {
                    674: {
                        "msg": [
                            f"HoFi approve_task {task_id}",
                            f"holon={holon} categoria={categoria}",
                            f"duracion_horas={duracion} reward={reward}",
                            razonamiento[:64],
                        ]
                    }
                }
            )
        )
    )

    signed: Transaction = builder.build_and_sign([skey], change_address=tenzo_addr)
    tx_id = context.submit_tx(signed.to_cbor())
    return {
        "tx_id": str(tx_id),
        "task_id": task_id,
        "holon_id": holon,
        "reward": reward,
        "policy_id": h["holon_token"]["policy_id"],
        "total_emitido_before": before_state.total_emitido,
        "total_emitido_after": new_total,
        "reputation_before": before_member.reputation,
        "reputation_after": new_rep,
        "network": dep.get("network", "preview"),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--deployment", required=True)
    ap.add_argument("--holon", required=True)
    ap.add_argument("--executor", required=True, help="addr_test... del executor")
    ap.add_argument("--member-asset", required=True, help="asset_name hex del NFT de membresia")
    ap.add_argument("--reward", type=int, required=True)
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--categoria", default="")
    ap.add_argument("--duracion", type=int, default=0)
    ap.add_argument("--razonamiento", default="")
    args = ap.parse_args()

    def env(n: str) -> str:
        v = os.environ.get(n)
        if not v:
            sys.exit(f"ERROR: falta la variable de entorno {n}")
        return v

    dep = json.loads(Path(args.deployment).read_text())
    skey = PaymentSigningKey.load(env("TENZO_SKEY_FILE"))
    context = BlockFrostChainContext(
        env("BLOCKFROST_PROJECT_ID"), base_url=blockfrost_base(dep.get("network", "preview"))
    )

    r = submit_approve_task(
        dep=dep, holon=args.holon, executor=args.executor, member_asset=args.member_asset,
        reward=args.reward, task_id=args.task_id, categoria=args.categoria,
        duracion=args.duracion, razonamiento=args.razonamiento, context=context, skey=skey,
    )
    print(f"approve_task OK. tx_id={r['tx_id']}")
    print(f"  total_emitido {r['total_emitido_before']} -> {r['total_emitido_after']} (cap se valida on-chain)")
    print(f"  reputacion {r['reputation_before']} -> {r['reputation_after']}")
    print(f"  https://preview.cardanoscan.io/transaction/{r['tx_id']}")


if __name__ == "__main__":
    main()
