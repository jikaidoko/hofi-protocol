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
