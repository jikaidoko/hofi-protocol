"""ConsensusAdapter — capa de consenso del Tenzo (chain-agnóstica).

Simetría con el ChainAdapter: así como el ChainAdapter abstrae el *settlement*
(Cardano vs EVM), el ConsensusAdapter abstrae *quién dirime las dudas* del Tenzo:

- `GenLayerConsensus`   — ISC de GenLayer (consenso descentralizado de LLMs).
- `LocalQuorumConsensus`— quórum multi-LLM local (futuro; placeholder).
- `NoConsensus`         — confía en la evaluación de Gemini (sin segunda opinión).

El pipeline del Tenzo queda así (consenso y settlement independientes):

    gemini    = evaluar_con_gemini(tarea)              # {recompensa_hoca, clasificacion, razonamiento, certeza}
    veredicto = await consensus.evaluate(tarea, gemini, catalogo=..., historial=...)
    if veredicto.aprobada is True:
        chain.approve_task_onchain(... reward=veredicto.recompensa_hoca ...)   # Cardano
    elif veredicto.aprobada is None:
        escalar_a_community_approval(...)
    # False -> rechazada

Selección por entorno:  CONSENSUS = genlayer | local | none   (default: none)

Nota: `GenLayerConsensus` usa `genlayer_bridge.consultar_oracle`, que vive en el
Tenzo. Al portar el Tenzo al fork se trae el bridge (con el fix del -32602:
`_get_gl_client()` lee `TENZO_WALLET_KEY` con GEN, RPC rpc-bradbury.genlayer.com,
chainId 4221). Hasta entonces este módulo importa el bridge de forma lazy.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional, Protocol


@dataclass
class ConsensusResult:
    """Veredicto del consenso, agnóstico de quién lo produjo."""
    aprobada: Optional[bool]          # True (aprobada) | None (escalar a humano) | False (rechazada)
    recompensa_hoca: int              # monto consensuado (entero, unidades del token)
    clasificacion: str = ""           # cuidado | regenerativa | comunitaria
    razonamiento: str = ""
    fuente: str = ""                  # "genlayer" | "local-quorum" | "gemini"
    votos: dict = field(default_factory=dict)


class ConsensusAdapter(Protocol):
    async def evaluate(self, tarea: dict, gemini: dict, **kwargs) -> ConsensusResult: ...


class NoConsensus:
    """Sin capa de consenso: confía en Gemini. Aprueba si la certeza supera el umbral;
    si no, escala a aprobación comunitaria (aprobada=None)."""

    def __init__(self, umbral: float = 0.0) -> None:
        self.umbral = umbral

    async def evaluate(self, tarea: dict, gemini: dict, **_) -> ConsensusResult:
        certeza = float(gemini.get("certeza", 1.0))
        return ConsensusResult(
            aprobada=True if certeza >= self.umbral else None,
            recompensa_hoca=int(round(float(gemini.get("recompensa_hoca", 0)))),
            clasificacion=gemini.get("clasificacion", ""),
            razonamiento=gemini.get("razonamiento", ""),
            fuente="gemini",
        )


class GenLayerConsensus:
    """Consenso vía el ISC de GenLayer (consenso descentralizado de LLMs)."""

    async def evaluate(
        self, tarea: dict, gemini: dict, *, catalogo=None, historial=None
    ) -> ConsensusResult:
        from genlayer_bridge import consultar_oracle  # disponible al portar el Tenzo

        r = await consultar_oracle(
            tarea, catalogo or [], historial or [], float(gemini.get("certeza", 0.5))
        )
        return ConsensusResult(
            aprobada=r.aprobada,
            recompensa_hoca=int(r.hoca_sugerido),
            clasificacion=gemini.get("clasificacion", ""),  # GenLayer no clasifica; viene de Gemini
            razonamiento=r.razon,
            fuente="genlayer",
            votos={
                "total": r.nodos_total,
                "aprobaron": r.nodos_aprobaron,
                "confianza": r.confianza,
                "escalada_humana": r.escalada_humana,
                "apelacion_usada": r.apelacion_usada,
            },
        )


class LocalQuorumConsensus:
    """Quórum multi-LLM local (futuro): consulta N modelos distintos y vota por
    mayoría. Reproduce el espíritu del ISC sin la cadena de GenLayer. Placeholder."""

    async def evaluate(self, tarea: dict, gemini: dict, **_) -> ConsensusResult:
        raise NotImplementedError("LocalQuorumConsensus aún no implementado")


def get_consensus_adapter() -> ConsensusAdapter:
    mode = os.getenv("CONSENSUS", "none").lower()
    if mode == "genlayer":
        return GenLayerConsensus()
    if mode == "local":
        return LocalQuorumConsensus()
    return NoConsensus()
