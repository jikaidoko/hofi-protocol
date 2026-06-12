#!/usr/bin/env python3
"""Cierre de decisión -> on-chain: tx `withdraw` (PyCardano).

Es la otra mitad del ciclo de vida del Protocolo Modular de Consenso. `record_decision`
abre una decisión (UTXO en el registry + N tokens de participación); `withdraw` la
cierra de forma atómica, ejerciendo la PROPIEDAD COLECTIVA:

  - gasta el UTXO de la decisión en `consensus_registry` con el redeemer `Withdraw`.
  - quema los N tokens de participación (`BurnParticipation`), N = #participants.
  - lo autoriza el quórum M-de-N de participantes (extra_signatories) — el holon
    como colectivo, no el facilitador.
  - recupera el min-ADA (2 ADA) que quedó bloqueado en el UTXO de la decisión.

Lo que exige el on-chain (debe cumplirse en la misma tx):
  - `consensus_registry.spend` (redeemer Withdraw):
      valid_quorum_config + quorum_met(participants, extra_signatories, quorum)
      + quantity_of(mint, d.participation_policy, "PARTICIPA") < 0  (se quema)
  - `participation_minting.mint` (redeemer BurnParticipation):
      quantity_of(mint, policy_id, "PARTICIPA") < 0

Una decisión es INMUTABLE: no existe "editar". `withdraw` no la altera, la cierra
(libera el min-ADA y quema la participación). El texto de la decisión ya quedó en la
metadata CIP-20 de la tx de registro y en el índice off-chain (Neon); el cierre solo
recupera el ADA y disuelve los tokens.

Este módulo expone:
  - `submit_withdraw(...)` -> core reutilizable (lo usa el CLI y, más adelante, la
    ruta /api/consensus/withdraw del frontend).
  - `find_decision_utxo(...)` / `decode_decision_datum(...)` -> helpers de lectura.
  - CLI (`main`) para correrlo a mano / validar end-to-end en preview.

El pagador (fee/colateral/change) es la wallet del Tenzo (TENZO_SKEY_FILE), igual
que record_decision; los participantes solo aportan la firma de quórum.

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
    UTxO,
    VerificationKeyHash,
)

from consensus_types import (
    PARTICIPATION_ASSET,
    BurnParticipation,
    DecisionDatum,
    Withdraw,
)
from decision_signer import DecisionSigner, signer_from_env
from custodial_wallet import CustodialWallets, InMemoryIndexStore


def blockfrost_base(network: str) -> str:
    return f"https://cardano-{network}.blockfrost.io/api"


def decode_decision_datum(output) -> Optional[DecisionDatum]:
    """Decodifica el inline datum de un output del registry a `DecisionDatum`.

    Tolerante a las distintas formas en que PyCardano expone un inline datum según
    la versión / el provider (objeto PlutusData ya tipado, RawPlutusData, RawCBOR).
    Devuelve None si el output no tiene un DecisionDatum decodificable.
    """
    d = getattr(output, "datum", None)
    if d is None:
        return None
    if isinstance(d, DecisionDatum):
        return d
    raw = None
    if hasattr(d, "cbor"):           # RawCBOR / Datum con .cbor (bytes)
        raw = d.cbor
    elif hasattr(d, "to_cbor"):      # RawPlutusData / PlutusData
        raw = d.to_cbor()
    if raw is None:
        return None
    if isinstance(raw, str):         # algunas versiones devuelven hex
        raw = bytes.fromhex(raw)
    try:
        return DecisionDatum.from_cbor(raw)
    except Exception:
        return None


def find_decision_utxo(
    context: ChainContext,
    registry_addr: str,
    *,
    holon_id: str,
    sequence: Optional[int] = None,
    tx_hash: Optional[str] = None,
) -> tuple[UTxO, DecisionDatum]:
    """Localiza el UTXO de una decisión en el registry.

    Identidad de una decisión = (holon_id, sequence). Si dos UTXOs comparten ambos
    (no debería pasar), desambiguar con `tx_hash` (el tx_id de su record_decision).
    Falla con un error claro si hay 0 o >1 candidatos sin desambiguar.
    """
    candidates: list[tuple[UTxO, DecisionDatum]] = []
    for u in context.utxos(registry_addr):
        if tx_hash and str(u.input.transaction_id) != tx_hash:
            continue
        d = decode_decision_datum(u.output)
        if d is None:
            continue
        if d.holon_id != holon_id.encode():
            continue
        if sequence is not None and d.sequence != sequence:
            continue
        candidates.append((u, d))

    if not candidates:
        raise LookupError(
            f"no se encontró la decisión holon={holon_id} "
            f"sequence={sequence} tx_hash={tx_hash} en {registry_addr}"
        )
    if len(candidates) > 1:
        refs = ", ".join(f"{u.input.transaction_id}#{u.input.index}" for u, _ in candidates)
        raise LookupError(
            f"{len(candidates)} decisiones coinciden (holon={holon_id} "
            f"sequence={sequence}); desambiguá con --tx-hash. Candidatas: {refs}"
        )
    return candidates[0]


def submit_withdraw(
    *,
    dep: dict,
    holon_id: str,
    signer_ids: List[str],
    signer: DecisionSigner,
    context: ChainContext,
    sequence: Optional[int] = None,
    tx_hash: Optional[str] = None,
    decision_utxo: Optional[UTxO] = None,
    decision_datum: Optional[DecisionDatum] = None,
) -> dict:
    """Core: arma la tx atómica de cierre (spend Withdraw + burn N), firma y envía.

    No lee variables de entorno — recibe `context` y `signer` ya construidos (así lo
    reusa la ruta del frontend). `signer_ids` son los participantes que firman el
    quórum; deben re-derivar a VKHs que estén en `participants` del datum y ser ≥ el
    quórum declarado. La decisión se localiza por (holon_id, sequence[, tx_hash])
    salvo que se pase `decision_utxo`/`decision_datum` ya resueltos.
    """
    registry = dep["consensus_registry"]
    pm = dep["participation_minting"]
    registry_addr = registry["address"]
    registry_script = PlutusV3Script(bytes.fromhex(registry["compiled_code"]))
    participation_script = PlutusV3Script(bytes.fromhex(pm["compiled_code"]))

    if decision_utxo is None or decision_datum is None:
        decision_utxo, decision_datum = find_decision_utxo(
            context, registry_addr, holon_id=holon_id,
            sequence=sequence, tx_hash=tx_hash,
        )

    d = decision_datum
    n = len(d.participants)
    # La policy a quemar vive en el DATUM (fuente de verdad on-chain). El validador
    # exige quemar exactamente esa policy; el compiled_code del deployment es el
    # script de esa misma policy → su hash debe coincidir.
    policy = ScriptHash(d.participation_policy)
    if d.participation_policy != bytes.fromhex(pm["policy_id"]):
        raise ValueError(
            "participation_policy del datum != policy_id del deployment "
            f"({d.participation_policy.hex()} != {pm['policy_id']}); "
            "¿deployment equivocado?"
        )

    # ── el quórum que firma debe estar entre los participantes del datum ────────
    participants = set(d.participants)
    signer_vkhs = []
    for pid in signer_ids:
        vkh = signer.resolve_vkh(pid)
        if vkh not in participants:
            raise ValueError(
                f"el firmante {pid!r} (vkh {vkh.hex()[:16]}…) no está en los "
                "participants de la decisión; no cuenta para el quórum"
            )
        signer_vkhs.append(VerificationKeyHash(vkh))
    if len(signer_vkhs) < d.quorum:
        raise ValueError(f"firman {len(signer_vkhs)} < quorum {d.quorum}")

    # ── quema de los N tokens de participación (cantidad negativa) ──────────────
    burn = MultiAsset.from_primitive({bytes(policy): {PARTICIPATION_ASSET: -n}})

    builder = TransactionBuilder(context)
    builder.add_input_address(signer.change_address())  # pagador: fee + colateral
    builder.add_script_input(
        decision_utxo,
        script=registry_script,
        redeemer=Redeemer(Withdraw()),
    )  # inline datum → no se pasa datum aparte
    builder.mint = burn
    builder.add_minting_script(
        participation_script, redeemer=Redeemer(BurnParticipation())
    )
    builder.required_signers = signer_vkhs
    builder.auxiliary_data = AuxiliaryData(
        AlonzoMetadata(
            metadata=Metadata(
                {
                    674: {
                        "msg": [
                            f"HoFi consenso: cierre de decision en {holon_id}",
                            f"seq={d.sequence} quema={n} quorum={d.quorum}",
                            f"ref={decision_utxo.input.transaction_id}"[:64],
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
        "sequence": d.sequence,
        "burned": n,
        "quorum": d.quorum,
        "signers": len(signer_ids),
        "participation_policy": d.participation_policy.hex(),
        "closed_ref": f"{decision_utxo.input.transaction_id}#{decision_utxo.input.index}",
        "registry_address": registry_addr,
        "network": dep.get("network", "preview"),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--deployment", help="deployment.consensus.json")
    ap.add_argument("--holon", required=True)
    ap.add_argument("--sequence", type=int, default=None,
                    help="secuencia de la decisión a cerrar (identidad con holon)")
    ap.add_argument("--tx-hash", default=None,
                    help="tx_id del record_decision (desambigua si hay colisión)")
    ap.add_argument("--participants", required=True,
                    help="person_ids separados por coma — MISMO orden que en el "
                         "record (siembra canónica de índices HD custodiales)")
    ap.add_argument("--signers", default="",
                    help="person_ids que firman el quórum (default: todos)")
    ap.add_argument("--facilitator", default="",
                    help="person_id del facilitador (parte de la siembra canónica)")
    ap.add_argument("--addresses", action="store_true",
                    help="imprime las direcciones (pagador + participantes) y sale, "
                         "para fondear el pagador. No necesita Blockfrost.")
    args = ap.parse_args()

    def env(n: str) -> str:
        v = os.environ.get(n)
        if not v:
            sys.exit(f"ERROR: falta la variable de entorno {n}")
        return v

    participant_ids = [p.strip() for p in args.participants.split(",") if p.strip()]
    signer_ids = ([s.strip() for s in args.signers.split(",") if s.strip()]
                  or participant_ids)

    # Orden CANÓNICO de asignación de índices HD — IDÉNTICO al de record_decision,
    # para que cada persona obtenga SIEMPRE el mismo índice/VKH entre procesos.
    canonical = list(dict.fromkeys(
        participant_ids + ([args.facilitator] if args.facilitator else [])
    ))

    def seeded_store() -> InMemoryIndexStore:
        store = InMemoryIndexStore()
        for pid in canonical:
            store.assign_index(pid)
        return store

    wallets = CustodialWallets(env("HOFI_MASTER_MNEMONIC"))

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

    payer_skey = PaymentSigningKey.load(env("TENZO_SKEY_FILE"))
    payer_address = Address(
        PaymentVerificationKey.from_signing_key(payer_skey).hash(), network=context.network
    )
    store = seeded_store()
    signer = signer_from_env(
        wallets=wallets, store=store, payer_skey=payer_skey, payer_address=payer_address
    )

    r = submit_withdraw(
        dep=dep, holon_id=args.holon, signer_ids=signer_ids, signer=signer,
        context=context, sequence=args.sequence, tx_hash=args.tx_hash,
    )
    print(f"withdraw OK. tx_id={r['tx_id']}")
    print(f"  holon={r['holon_id']} seq={r['sequence']} quemados={r['burned']} "
          f"quorum={r['quorum']}")
    print(f"  cerró {r['closed_ref']}")
    print(f"  https://preview.cardanoscan.io/transaction/{r['tx_id']}")


if __name__ == "__main__":
    main()
