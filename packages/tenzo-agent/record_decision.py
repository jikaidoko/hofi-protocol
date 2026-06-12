#!/usr/bin/env python3
"""Bloque Registro -> on-chain: tx `record_decision` (PyCardano).

Cuando el Protocolo Modular de Consenso llega al bloque Registro (tipo 6), esta tx
deja la decisión asentada en preview de forma atómica:

  - 1 output al `consensus_registry` con el `DecisionDatum` (InlineDatum).
  - mint de N tokens de participación (`MintParticipation`), N = #participants,
    adjuntos al mismo output del registry (se queman juntos en el Withdraw).
  - firmada por el quórum M-de-N de participantes (extra_signatories).
  - metadata CIP-20 (label 674) legible.

El cross-link atómico lo hace cumplir `participation_minting`: solo deja mintear si
en la misma tx hay un output al registry con un DecisionDatum válido y el quórum
firma. El firmado se delega a un `DecisionSigner` (custodial ahora, CIP-30 después).

Este módulo expone:
  - `submit_record_decision(...)` -> core reutilizable (lo usa el CLI y, más
    adelante, la ruta /api/consensus/record del frontend).
  - CLI (`main`) para correrlo a mano / validar end-to-end en preview.

El pagador (fee/colateral/change) es la wallet del Tenzo (TENZO_SKEY_FILE), igual
que approve_task; los participantes solo aportan la firma de quórum. Se funda una
sola wallet (el Tenzo), no la tesorería de cada holon.

Entorno (CLI):
    BLOCKFROST_PROJECT_ID   project id (preview/preprod/mainnet)
    TENZO_SKEY_FILE         signing key del Tenzo (pagador de la tx)
    HOFI_MASTER_MNEMONIC    seed maestro de wallets custodiales (KMS) [participantes]
    CONSENSUS_SIGNER        custodial | cip30   (default custodial)
"""
import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

from pycardano import (
    Address,
    AlonzoMetadata,
    AuxiliaryData,
    BlockFrostChainContext,
    ChainContext,
    Metadata,
    MultiAsset,
    Network,
    PaymentSigningKey,
    PaymentVerificationKey,
    PlutusV3Script,
    Redeemer,
    ScriptHash,
    TransactionBuilder,
    TransactionOutput,
    Value,
    VerificationKeyHash,
)

from consensus_types import (
    PARTICIPATION_ASSET,
    DecisionDatum,
    MintParticipation,
    ProtocolMeta,
    compute_protocol_hash,
)
from decision_signer import DecisionSigner, signer_from_env
from custodial_wallet import CustodialWallets, InMemoryIndexStore

# La decisión + sus tokens de participación viven juntos en el UTXO del registry.
REGISTRY_MIN_ADA = 2_000_000

# Protocolo "Media" por defecto (válido: 1 sil, 1 div, terminales Dec+Reg).
DEFAULT_LEVEL = 1
DEFAULT_BLOCKS = [0, 1, 2, 3, 4, 5, 6]
DEFAULT_MODALITIES = ["p2", "i1", "s4", "d3", "n2", "c1", "r1"]


def blockfrost_base(network: str) -> str:
    return f"https://cardano-{network}.blockfrost.io/api"


def submit_record_decision(
    *,
    dep: dict,
    holon_id: str,
    decision_text: str,
    participant_ids: List[str],
    quorum: int,
    signer_ids: List[str],
    signer: DecisionSigner,
    context: ChainContext,
    level: int = DEFAULT_LEVEL,
    blocks: Optional[List[int]] = None,
    modalities: Optional[List[str]] = None,
    facilitator_id: str = "",
    sequence: int = 0,
    timestamp_slot: Optional[int] = None,
) -> dict:
    """Core: arma la tx atómica de registro de decisión, la firma y la envía.

    No lee variables de entorno — recibe `context` y `signer` ya construidos (así
    lo reusa la ruta del frontend). `signer_ids` son los participantes que firman;
    deben ser ⊆ `participant_ids` y len ≥ `quorum`.
    """
    blocks = blocks if blocks is not None else DEFAULT_BLOCKS
    modalities = modalities if modalities is not None else DEFAULT_MODALITIES

    # ── invariantes que el validador exige (fallar acá da mejor error) ──────────
    n = len(participant_ids)
    if n < 1:
        raise ValueError("se necesita al menos un participante")
    if not (1 <= quorum <= n):
        raise ValueError(f"quorum {quorum} fuera de rango [1, {n}]")
    if not set(signer_ids) <= set(participant_ids):
        raise ValueError("signer_ids debe ser subconjunto de participant_ids")
    if len(signer_ids) < quorum:
        raise ValueError(f"firman {len(signer_ids)} < quorum {quorum}")
    if len(blocks) != len(modalities):
        raise ValueError("blocks y modalities deben tener la misma longitud")

    registry = dep["consensus_registry"]
    pm = dep["participation_minting"]
    registry_addr = registry["address"]
    participation_script = PlutusV3Script(bytes.fromhex(pm["compiled_code"]))
    participation_policy = ScriptHash(bytes.fromhex(pm["policy_id"]))

    participants = [signer.resolve_vkh(pid) for pid in participant_ids]
    facilitator = signer.resolve_vkh(facilitator_id) if facilitator_id else b""
    signer_vkhs = [VerificationKeyHash(signer.resolve_vkh(pid)) for pid in signer_ids]

    meta = ProtocolMeta(level=level, blocks=blocks,
                        modalities=[m.encode() for m in modalities])
    protocol_hash = compute_protocol_hash(meta)

    if timestamp_slot is None:
        timestamp_slot = getattr(context, "last_block_slot", 0) or 0

    datum = DecisionDatum(
        decision_text=decision_text.encode(),
        protocol_hash=protocol_hash,
        protocol_meta=meta,
        participants=participants,
        facilitator=facilitator,
        timestamp_slot=timestamp_slot,
        holon_id=holon_id.encode(),
        sequence=sequence,
        quorum=quorum,
        participation_policy=participation_policy.payload,
    )

    # N tokens de participación, adjuntos al output del registry (se queman juntos
    # en el Withdraw). El validador solo exige minted == n.
    mint = MultiAsset.from_primitive(
        {bytes(participation_policy): {PARTICIPATION_ASSET: n}}
    )
    registry_value = Value(REGISTRY_MIN_ADA, mint)

    builder = TransactionBuilder(context)
    builder.add_input_address(signer.change_address())
    builder.add_output(TransactionOutput(registry_addr, registry_value, datum=datum))
    builder.mint = mint
    builder.add_minting_script(participation_script, redeemer=Redeemer(MintParticipation()))
    builder.required_signers = signer_vkhs
    builder.auxiliary_data = AuxiliaryData(
        AlonzoMetadata(
            metadata=Metadata(
                {
                    674: {
                        "msg": [
                            f"HoFi consenso: decision en {holon_id}",
                            decision_text[:64],
                            f"participantes={n} quorum={quorum} seq={sequence}",
                            f"protocol_hash={protocol_hash.hex()[:48]}",
                        ]
                    }
                }
            )
        )
    )

    tx_id = signer.finalize(builder, signer_ids, context)
    return {
        "tx_id": tx_id,
        "holon_id": holon_id,
        "decision_text": decision_text,
        "participants": n,
        "quorum": quorum,
        "signers": len(signer_ids),
        "protocol_hash": protocol_hash.hex(),
        "participation_policy": pm["policy_id"],
        "registry_address": registry_addr,
        "network": dep.get("network", "preview"),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    # No required: --addresses no lo necesita. Se valida abajo en el modo real.
    ap.add_argument("--deployment", help="deployment.consensus.json")
    ap.add_argument("--holon", required=True)
    ap.add_argument("--decision", required=True, help="texto de la decisión adoptada")
    ap.add_argument("--participants", required=True,
                    help="person_ids separados por coma (custodial)")
    ap.add_argument("--quorum", type=int, required=True)
    ap.add_argument("--signers", default="",
                    help="person_ids que firman (default: todos los participants)")
    ap.add_argument("--facilitator", default="")
    ap.add_argument("--sequence", type=int, default=0)
    ap.add_argument("--addresses", action="store_true",
                    help="imprime las direcciones (pagador Tenzo + participantes) y "
                         "sale, para fondear el pagador. No necesita Blockfrost.")
    args = ap.parse_args()

    def env(n: str) -> str:
        v = os.environ.get(n)
        if not v:
            sys.exit(f"ERROR: falta la variable de entorno {n}")
        return v

    participant_ids = [p.strip() for p in args.participants.split(",") if p.strip()]
    signer_ids = ([s.strip() for s in args.signers.split(",") if s.strip()]
                  or participant_ids)

    # Orden CANÓNICO de asignación de índices HD de los PARTICIPANTES. Idéntico en
    # --addresses y en la corrida real → la misma persona obtiene SIEMPRE el mismo
    # índice/dirección entre procesos (el InMemoryIndexStore es efímero; en prod el
    # store es Neon). El pagador (Tenzo) NO es custodial: es TENZO_SKEY_FILE.
    canonical = list(dict.fromkeys(
        participant_ids + ([args.facilitator] if args.facilitator else [])
    ))

    def seeded_store() -> InMemoryIndexStore:
        store = InMemoryIndexStore()
        for pid in canonical:
            store.assign_index(pid)
        return store

    wallets = CustodialWallets(env("HOFI_MASTER_MNEMONIC"))

    # Modo helper: derivar y mostrar direcciones (no toca red ni deployment).
    if args.addresses:
        store = seeded_store()
        print("Direcciones (preview) — fondeá el PAGADOR (Tenzo) con ADA:")
        if os.environ.get("TENZO_SKEY_FILE"):
            tkey = PaymentSigningKey.load(env("TENZO_SKEY_FILE"))
            taddr = Address(PaymentVerificationKey.from_signing_key(tkey).hash(),
                            network=Network.TESTNET)
            print(f"  {'tenzo (pagador)':18}      {taddr}  <- fondear acá")
        else:
            print("  (set TENZO_SKEY_FILE para ver la dirección del pagador)")
        for pid in canonical:
            idx = store.get_index(pid)
            print(f"  {pid:18} idx {idx:>3}  {wallets.address(idx)}")
        return

    if not args.deployment:
        sys.exit("ERROR: --deployment es requerido (salvo con --addresses)")
    dep = json.loads(Path(args.deployment).read_text())
    context = BlockFrostChainContext(
        env("BLOCKFROST_PROJECT_ID"),
        base_url=blockfrost_base(dep.get("network", "preview")),
    )

    # Pagador = Tenzo (TENZO_SKEY_FILE). Participantes firman el quórum (custodial).
    payer_skey = PaymentSigningKey.load(env("TENZO_SKEY_FILE"))
    payer_address = Address(
        PaymentVerificationKey.from_signing_key(payer_skey).hash(), network=context.network
    )
    store = seeded_store()  # el Tenzo inyecta el store de Neon en producción
    signer = signer_from_env(
        wallets=wallets, store=store, payer_skey=payer_skey, payer_address=payer_address
    )

    r = submit_record_decision(
        dep=dep, holon_id=args.holon, decision_text=args.decision,
        participant_ids=participant_ids, quorum=args.quorum, signer_ids=signer_ids,
        signer=signer, context=context, facilitator_id=args.facilitator,
        sequence=args.sequence,
    )
    print(f"record_decision OK. tx_id={r['tx_id']}")
    print(f"  holon={r['holon_id']} participantes={r['participants']} quorum={r['quorum']}")
    print(f"  protocol_hash={r['protocol_hash']}")
    print(f"  https://preview.cardanoscan.io/transaction/{r['tx_id']}")


if __name__ == "__main__":
    main()
