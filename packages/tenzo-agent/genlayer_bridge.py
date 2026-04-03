"""
genlayer_bridge.py — Puente con los ISCs de GenLayer
Sincronizado con TenzoEquityOracle v0.2.2

Flujo completo:
  1. Tenzo llama a consultar_oracle(tarea_data, certeza_gemini)
  2. ISC evalua via Optimistic Democracy (Pending → Proposing → Committing → Revealing)
  3. Ventana de Acceptance & Appeal:
       - Si ISC aprueba → aceptar siempre (Tenzo nunca apela hacia abajo)
       - Si ISC rechaza:
           certeza_gemini < 0.55  → aceptar rechazo (duda > certeza)
           certeza_gemini 0.55–0.75 → APELAR (Tenzo tiene argumento fundado)
           certeza_gemini > 0.75  → escalar a avalista humano (probable valida)
       - Sin consenso → escalar a avalista humano
  4. Si se apela: validadores adicionales re-evaluan con evidencia del Tenzo
  5. Finalization → on-chain irreversible

Contratos deployados en Studionet Asimov:
  TenzoEquityOracle v0.1.0: 0x6707c1a04dC387aD666758A392B43Aa0660DFECE  (deprecado)
  TenzoEquityOracle v0.2.0: 0xFEE2E2e510781E760604D115723151A09a233a72  (deprecado)
  TenzoEquityOracle v0.2.1: 0x5b125045739238fb6d6664bD1718ff18b883C1C7  (deprecado)
  TenzoEquityOracle v0.2.2: 0x7A037d1dDbda728f16e6F980a28eB8D1e29F4F28  (activo)

Fix v0.2.2 bridge:
  - Import corregido: genlayer_py (no genlayer.Client que no existe)
  - create_client usa chain=testnet_asimov (no endpoint=str)
  - write_contract es sincrono en genlayer_py (no async/await)
  - wait_for_transaction_receipt es sincrono, se ejecuta en executor
  - TransactionStatus importado desde genlayer_py.types
"""

import os
import json
import logging
import asyncio
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

ORACLE_ADDRESS      = os.getenv("TENZO_ORACLE_ADDRESS", "0x7A037d1dDbda728f16e6F980a28eB8D1e29F4F28")
CONSENSUS_TIMEOUT   = int(os.getenv("GENLAYER_TIMEOUT_SECONDS", "90"))
APPEAL_TIMEOUT      = int(os.getenv("GENLAYER_APPEAL_TIMEOUT_SECONDS", "120"))

# Umbrales de certeza para la decision de apelar
CERTEZA_MIN_APELAR  = float(os.getenv("CERTEZA_MIN_APELAR",  "0.55"))
CERTEZA_MAX_APELAR  = float(os.getenv("CERTEZA_MAX_APELAR",  "0.75"))
REJECTION_QUORUM    = float(os.getenv("GENLAYER_REJECTION_QUORUM", "0.67"))
CONFIANZA_DIRECTA   = float(os.getenv("CONFIANZA_APROBACION_DIRECTA", "0.85"))

# ─────────────────────────────────────────────────────────────────────────────
# SDK genlayer-py — import correcto
# pip install genlayer-py
# ─────────────────────────────────────────────────────────────────────────────
try:
    from genlayer_py import create_client, create_account, testnet_asimov
    from genlayer_py.types import TransactionStatus as GLTransactionStatus
    _GL_SDK_AVAILABLE = True
    logger.info("genlayer-py cargado OK — testnet Asimov")
except ImportError:
    _GL_SDK_AVAILABLE = False
    logger.warning(
        "genlayer-py no instalado — GenLayer bridge desactivado. "
        "Instalar con: pip install genlayer-py"
    )


@dataclass
class ConsensusResult:
    """Resultado final del pipeline GenLayer, incluyendo posible apelacion."""
    aprobada:         Optional[bool]
    confianza:        float
    hoca_sugerido:    int
    razon:            str
    nodos_total:      int
    nodos_aprobaron:  int
    escalada_humana:  bool
    apelacion_usada:  bool = False
    pipeline_pasos:   list = field(default_factory=list)


def _patch_skip_gas(client) -> None:
    """
    Parchea client.provider.make_request para saltear eth_estimateGas.

    Por que es necesario:
      genlayer_py llama eth_estimateGas antes de enviar cualquier write_contract.
      Los ISCs con gl.nondet.exec_prompt() no pueden simularse durante estimacion
      de gas → OutOfNativeResourcesDuringValidation.
      Con este patch se provee un gas fijo alto y GenLayer maneja el limite real
      durante la ejecucion del consenso en Studionet Asimov.
    """
    original = client.provider.make_request

    def patched(method, *args, **kwargs):
        if method == "eth_estimateGas":
            logger.debug("[GenLayer] eth_estimateGas puenteado → gas fijo 500M")
            return {"result": 90_000_000}  # block gas limit de Studionet Asimov = 100M
        return original(method, *args, **kwargs)

    client.provider.make_request = patched


def _get_gl_client():
    """Crea un cliente GenLayer con cuenta efimera apuntando a testnet Asimov."""
    if not _GL_SDK_AVAILABLE:
        raise RuntimeError("genlayer-py no instalado")
    account = create_account()
    # create_client recibe chain= (objeto GenLayerChain), no endpoint= string
    client = create_client(chain=testnet_asimov, account=account)
    # Puentear eth_estimateGas: los ISCs con LLM calls no pueden estimarse
    _patch_skip_gas(client)
    return client


# ─────────────────────────────────────────────────────────────────────────────
# Llamadas al ISC — write_contract es sincrono en genlayer_py,
# lo ejecutamos en un thread executor para no bloquear el event loop
# ─────────────────────────────────────────────────────────────────────────────

def _write_and_wait(function_name: str, args: list, timeout: int) -> dict:
    """
    Llama a function_name en el ISC de forma sincrona.
    Se usa en asyncio.wait_for(...executor...) desde el caller async.
    """
    client = _get_gl_client()
    tx_hash = client.write_contract(
        address=ORACLE_ADDRESS,
        function_name=function_name,
        args=args,
    )
    logger.info("GenLayer TX enviada [%s]: %s", function_name, tx_hash)

    receipt = client.wait_for_transaction_receipt(
        transaction_hash=tx_hash,
        status=GLTransactionStatus.ACCEPTED,
        interval=5000,
        retries=max(6, timeout // 5),
    )
    return _parsear_receipt_sdk(receipt)


async def _llamar_isc(
    tarea_data: dict,
    catalogo: list,
    historial: list,
    timeout: int = None,
) -> dict:
    """Llama a validate_task_equity() via SDK genlayer-py (thread executor)."""
    if not _GL_SDK_AVAILABLE:
        return _resultado_sin_consenso(
            "genlayer-py no instalado. Instalar: pip install genlayer-py"
        )

    payload = _construir_payload(tarea_data, catalogo, historial)
    _timeout = timeout or CONSENSUS_TIMEOUT

    try:
        loop = asyncio.get_event_loop()
        resultado = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                _write_and_wait,
                payload["function"],
                payload["args"],
                _timeout,
            ),
            timeout=_timeout * 2,
        )
        return resultado

    except asyncio.TimeoutError:
        logger.warning("GenLayer timeout en validate_task_equity")
        return _resultado_sin_consenso("Timeout en consulta GenLayer")
    except Exception as e:
        logger.error("GenLayer error en validate_task_equity: %s", e)
        return _resultado_sin_consenso(f"Error de comunicacion: {str(e)[:100]}")


async def _presentar_apelacion(evidencia: dict) -> dict:
    """Envia la apelacion a GenLayer via appeal_rejection() del ISC v0.2.2."""
    if not _GL_SDK_AVAILABLE:
        return _resultado_sin_consenso("genlayer-py no instalado")

    tarea = evidencia.get("tarea_original", {})
    matches = evidencia.get("matches_catalogo", [])
    catalog_matches_texto = "\n".join(
        f"- {m.get('nombre','')} ({m.get('categoria','')})"
        for m in matches
    )
    historial_clean = evidencia.get("historial_clean", [])
    historial_texto = "\n".join(
        f"- {h.get('descripcion','')} → {h.get('hoca',0)} HoCa"
        for h in historial_clean
    )
    args = [
        tarea.get("descripcion", tarea.get("actividad", "")),
        tarea.get("holon_id", "familia-valdes"),
        str(float(tarea.get("duracion_horas", 1.0))),
        str(float(evidencia.get("certeza_tenzo", 0.6))),
        evidencia.get("argumento_tenzo", ""),
        catalog_matches_texto,
        historial_texto,
    ]

    try:
        loop = asyncio.get_event_loop()
        resultado = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                _write_and_wait,
                "appeal_rejection",
                args,
                APPEAL_TIMEOUT,
            ),
            timeout=APPEAL_TIMEOUT * 2,
        )
        return resultado
    except asyncio.TimeoutError:
        logger.warning("GenLayer timeout en apelacion")
        return _resultado_sin_consenso("Timeout en apelacion GenLayer")
    except Exception as e:
        logger.error("GenLayer appeal error: %s", e)
        return _resultado_sin_consenso(f"Error en apelacion: {str(e)[:100]}")


# ─────────────────────────────────────────────────────────────────────────────
# Punto de entrada principal
# ─────────────────────────────────────────────────────────────────────────────

async def consultar_oracle(
    tarea_data:        dict,
    catalogo_holon:    list,
    historial_persona: list,
    certeza_gemini:    float = 0.5,
) -> ConsensusResult:
    """
    Punto de entrada principal.
    certeza_gemini determina que hace el Tenzo si el ISC rechaza.
    """
    pipeline = []

    resultado_isc = await _llamar_isc(tarea_data, catalogo_holon, historial_persona)
    pipeline.append({"ronda": "isc_inicial", **_resumir_resultado(resultado_isc)})

    if resultado_isc["aprobada"] is True:
        return ConsensusResult(
            aprobada=True,
            confianza=resultado_isc["ratio_aprobacion"],
            hoca_sugerido=resultado_isc["hoca_mediana"],
            razon=resultado_isc["razon"],
            nodos_total=resultado_isc["total"],
            nodos_aprobaron=resultado_isc["aprobaron"],
            escalada_humana=False,
            pipeline_pasos=pipeline,
        )

    if resultado_isc["aprobada"] is None:
        return ConsensusResult(
            aprobada=None,
            confianza=resultado_isc["ratio_aprobacion"],
            hoca_sugerido=resultado_isc["hoca_mediana"],
            razon=f"Sin consenso ISC. Requiere avalista.",
            nodos_total=resultado_isc["total"],
            nodos_aprobaron=resultado_isc["aprobaron"],
            escalada_humana=True,
            pipeline_pasos=pipeline,
        )

    # ISC rechazo — decision de apelacion
    logger.info(
        "GenLayer rechazo. certeza_gemini=%.2f (rango apelar: %.2f–%.2f)",
        certeza_gemini, CERTEZA_MIN_APELAR, CERTEZA_MAX_APELAR,
    )

    if certeza_gemini < CERTEZA_MIN_APELAR:
        pipeline.append({"decision": "aceptar_rechazo", "certeza": certeza_gemini})
        return ConsensusResult(
            aprobada=False,
            confianza=certeza_gemini,
            hoca_sugerido=0,
            razon=resultado_isc["razon"],
            nodos_total=resultado_isc["total"],
            nodos_aprobaron=resultado_isc["aprobaron"],
            escalada_humana=False,
            pipeline_pasos=pipeline,
        )

    if certeza_gemini > CERTEZA_MAX_APELAR:
        pipeline.append({"decision": "escalar_humano", "certeza": certeza_gemini})
        return ConsensusResult(
            aprobada=None,
            confianza=certeza_gemini,
            hoca_sugerido=resultado_isc["hoca_mediana"],
            razon=(
                f"ISC rechazo pero Tenzo tiene alta certeza ({certeza_gemini:.0%}). "
                f"Escalado a avalista del holon."
            ),
            nodos_total=resultado_isc["total"],
            nodos_aprobaron=resultado_isc["aprobaron"],
            escalada_humana=True,
            pipeline_pasos=pipeline,
        )

    # Certeza media → APELAR
    logger.info("Tenzo apela el rechazo ISC. certeza_gemini=%.2f", certeza_gemini)
    pipeline.append({"decision": "apelar", "certeza": certeza_gemini})

    evidencia = _construir_evidencia_apelacion(
        tarea_data, catalogo_holon, historial_persona, certeza_gemini
    )
    resultado_apelacion = await _presentar_apelacion(evidencia)
    pipeline.append({"ronda": "apelacion", **_resumir_resultado(resultado_apelacion)})

    if resultado_apelacion["aprobada"] is True:
        return ConsensusResult(
            aprobada=True,
            confianza=resultado_apelacion["ratio_aprobacion"],
            hoca_sugerido=resultado_apelacion["hoca_mediana"],
            razon=f"Aprobado en apelacion. {resultado_apelacion['razon']}",
            nodos_total=resultado_apelacion["total"],
            nodos_aprobaron=resultado_apelacion["aprobaron"],
            escalada_humana=False,
            apelacion_usada=True,
            pipeline_pasos=pipeline,
        )
    else:
        return ConsensusResult(
            aprobada=False,
            confianza=resultado_apelacion["ratio_aprobacion"],
            hoca_sugerido=0,
            razon=f"Rechazado tras apelacion. {resultado_apelacion['razon']}",
            nodos_total=resultado_apelacion["total"],
            nodos_aprobaron=resultado_apelacion["aprobaron"],
            escalada_humana=False,
            apelacion_usada=True,
            pipeline_pasos=pipeline,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Construccion de payloads
# ─────────────────────────────────────────────────────────────────────────────

def _construir_payload(tarea_data: dict, catalogo: list, historial: list) -> dict:
    """Construye el payload para validate_task_equity() del ISC v0.2.2."""
    catalogo_texto = "\n".join(
        f"- {t.get('nombre','')} ({t.get('categoria','')}) "
        f"[{t.get('hoca_min',0)}–{t.get('hoca_max',0)} HoCa, "
        f"max {t.get('duracion_max_min',0)} min/dia]"
        for t in catalogo[:30]
    )
    historial_texto = "\n".join(
        f"- {h.get('descripcion','')} → {h.get('hoca',0)} HoCa ({h.get('fecha','')})"
        for h in historial[-10:]
    )
    return {
        "function": "validate_task_equity",
        "args": [
            tarea_data.get("descripcion", tarea_data.get("actividad", "")),  # task_description
            tarea_data.get("holon_id", "familia-valdes"),                    # holon_id
            str(float(tarea_data.get("duracion_horas", 1.0))),              # duracion_horas (str)
            str(float(tarea_data.get("monto_propuesto", -1.0))),            # amount (str)
            catalogo_texto,                                                   # catalog_context
            historial_texto,                                                  # persona_history
        ],
    }


def _construir_evidencia_apelacion(
    tarea_data: dict,
    catalogo: list,
    historial: list,
    certeza_gemini: float,
) -> dict:
    actividad = tarea_data.get("actividad", "").lower()
    matches = [
        t for t in catalogo
        if any(p in actividad for p in t.get("nombre", "").lower().split())
    ]
    return {
        "tarea_original":   tarea_data,
        "certeza_tenzo":    certeza_gemini,
        "matches_catalogo": matches[:3],
        "historial_clean":  [h for h in historial[-5:] if h.get("aprobada", True)],
        "argumento_tenzo": (
            f"El Tenzo evalua con {certeza_gemini:.0%} de certeza que esta actividad "
            f"corresponde a trabajo de cuidado reconocido por este holon. "
            f"{'Hay ' + str(len(matches)) + ' tarea(s) similares en el catalogo.' if matches else 'No hay match exacto pero el patron es consistente con el historial.'}"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Parsing de respuestas
# ─────────────────────────────────────────────────────────────────────────────

def _parsear_receipt_sdk(receipt) -> dict:
    """
    Convierte el receipt del SDK al formato interno del bridge.
    GenLayerTransaction expone el return value via .result o atributos directos.
    """
    try:
        # genlayer_py devuelve GenLayerTransaction con campo result como dict
        result = None
        if hasattr(receipt, "result"):
            result = receipt.result
        elif hasattr(receipt, "return_value"):
            result = receipt.return_value

        if isinstance(result, str):
            result = json.loads(result)

        if not result:
            # Intentar parsear desde txReceipt raw si result es None
            if hasattr(receipt, "tx_receipt"):
                raw = receipt.tx_receipt
                if isinstance(raw, (bytes, bytearray)):
                    try:
                        result = json.loads(raw.decode("utf-8", errors="replace"))
                    except Exception:
                        pass

        if not result:
            return _resultado_sin_consenso("Respuesta vacia del ISC")

        return _parsear_votos({"result": result})

    except Exception as e:
        logger.error("Error parseando receipt SDK: %s", e)
        return _resultado_sin_consenso(f"Error parseando receipt: {str(e)[:100]}")


def _parsear_votos(raw: dict) -> dict:
    """
    Normaliza la respuesta del ISC v0.2.2 al formato interno.
    El ISC devuelve: {vote, recompensa_hoca, clasificacion, confidence, justification, alerta}
    """
    try:
        if "error" in raw:
            err = raw["error"]
            logger.error("GenLayer JSON-RPC error: %s", err)
            return _resultado_sin_consenso(f"Error JSON-RPC: {str(err)[:80]}")
        result_str = raw.get("result", "{}")
        result = json.loads(result_str) if isinstance(result_str, str) else result_str
    except Exception:
        return _resultado_sin_consenso("Error parseando respuesta GenLayer")

    if not result:
        return _resultado_sin_consenso("Respuesta vacia de GenLayer")

    vote       = result.get("vote", "")
    hoca       = int(result.get("recompensa_hoca", 0))
    confidence = float(result.get("confidence", 0.5))
    razon      = result.get("justification", "Sin razon provista")
    alerta     = result.get("alerta")

    if alerta:
        razon = f"{razon} | Alerta: {alerta}"

    if vote == "APPROVE":
        return dict(aprobada=True,  total=5, aprobaron=5,
                    hoca_mediana=hoca, razon=razon, ratio_aprobacion=confidence)
    elif vote == "REJECT":
        return dict(aprobada=False, total=5, aprobaron=0,
                    hoca_mediana=0,    razon=razon, ratio_aprobacion=confidence)
    else:
        return dict(aprobada=None,  total=5, aprobaron=0,
                    hoca_mediana=hoca, razon=f"Voto desconocido: {vote!r}", ratio_aprobacion=0.5)


def _resultado_sin_consenso(razon: str) -> dict:
    return dict(aprobada=None, total=0, aprobaron=0,
                hoca_mediana=0, razon=razon, ratio_aprobacion=0.0)


def _resumir_resultado(r: dict) -> dict:
    return {
        "aprobada": r["aprobada"],
        "votos":    f"{r['aprobaron']}/{r['total']}",
        "hoca":     r["hoca_mediana"],
        "razon":    r["razon"][:80],
    }
