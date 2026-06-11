"""Selector de settlement y consenso para el Tenzo (líneas EVM/GenLayer + Cardano).

Conmuta por variables de entorno SIN acoplar pycardano cuando se corre en modo EVM
(import lazy). Permite que el MISMO Tenzo corra en cualquiera de las dos cadenas:

    CHAIN=cardano   -> settlement vía cardano_bridge (PyCardano)   | default: EVM
    CONSENSUS=...    -> genlayer | local | none                     (ver consensus.py)
"""
import logging
import os

logger = logging.getLogger("chain_selector")


def get_chain_bridge():
    """Bridge de settlement según CHAIN."""
    if os.getenv("CHAIN", "").lower() == "cardano":
        from cardano_bridge import get_bridge  # lazy: pycardano solo en modo Cardano
        logger.info("Settlement: Cardano (cardano_bridge)")
        return get_bridge()
    from onchain_bridge import get_bridge       # EVM / GenLayer (web3)
    logger.info("Settlement: EVM/GenLayer (onchain_bridge)")
    return get_bridge()


def get_consensus():
    """ConsensusAdapter según CONSENSUS (genlayer | local | none)."""
    from consensus import get_consensus_adapter
    adapter = get_consensus_adapter()
    logger.info("Consenso: %s", type(adapter).__name__)
    return adapter


def resolve_executor(persona_id, provided_address):
    """Dirección Cardano del executor para approve_task:
    - login-wallet (trae su dirección)  -> esa (self-custody).
    - voz/mail (sin dirección)          -> deriva/recupera su custodial (HD por persona).
    Solo aplica en modo Cardano; en EVM se usa `provided_address` tal cual.
    """
    if provided_address:
        return provided_address
    if not persona_id:
        return None
    try:
        from custodial_wallet import CustodialWallets   # lazy (pycardano)
        from custodial_store import NeonIndexStore
        cw = CustodialWallets()                          # HOFI_MASTER_MNEMONIC
        store = NeonIndexStore()
        idx, addr = cw.get_or_create(persona_id, store)
        try:
            store.save_address(persona_id, str(addr))
        except Exception:
            pass  # best-effort; el índice ya quedó asignado
        return str(addr)
    except Exception as e:
        logger.error("resolve_executor (custodial) falló para %s: %s", persona_id, e)
        return None  # sin custodial -> se saltea el mint, no rompe la evaluación
