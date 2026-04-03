"""
bot_flujo_tarea_patch.py — Flujo de tarea con validación comunitaria por quórum
=================================================================================

Reemplaza _flujo_tarea() en bot.py e implementa el panel de avalistas.

MODELO DE VALIDACIÓN COMUNITARIA:
  Cuando el pipeline Gemini + GenLayer no llega a una decisión definitiva,
  la tarea se somete a votación de los avalistas del holón.

  Configuración (variables de entorno):
    AVALISTAS_QUORUM_MIN     = 2    mínimo de votos para resolver
    AVALISTAS_QUORUM_RATIO   = 0.5  fracción de aprobación requerida (mayoría simple)
    AVALISTAS_TIMEOUT_HORAS  = 24   tiempo máximo antes de expirar

  Flujo:
    1. Tarea escalada → se guarda en DB con estado "pendiente_quorum"
    2. Se notifica a TODOS los avalistas del holón registrados
    3. Cada avalista vota Aprobar / Rechazar via botones inline en Telegram
    4. Cuando votos_total >= QUORUM_MIN y ratio > QUORUM_RATIO → resuelto
    5. Si el timeout expira sin quórum → "expirada", se notifica al usuario

  Los avalistas se obtienen de la DB (tabla holon_members, role="avalista").
  En modo DB_MOCK se usa AVALISTA_TELEGRAM_IDS (lista separada por comas en .env).

CÓMO INTEGRAR EN bot.py:
  1. Reemplazar _flujo_tarea() con la de este archivo
  2. Agregar el handler:
       app.add_handler(CallbackQueryHandler(
           manejar_voto_avalista, pattern="^quorum:"
       ))
  3. Agregar job periódico para timeouts:
       app.job_queue.run_repeating(verificar_timeouts_quorum, interval=3600)
  4. Añadir a .env / Cloud Run:
       AVALISTAS_QUORUM_MIN=2
       AVALISTAS_QUORUM_RATIO=0.5
       AVALISTAS_TIMEOUT_HORAS=24
       AVALISTA_TELEGRAM_IDS=2012212775,OTRO_ID
"""

import os
import uuid
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

# ── Configuración de quórum ───────────────────────────────────────────────────
QUORUM_MIN    = int(os.getenv("AVALISTAS_QUORUM_MIN", "2"))
QUORUM_RATIO  = float(os.getenv("AVALISTAS_QUORUM_RATIO", "0.5"))
TIMEOUT_HORAS = int(os.getenv("AVALISTAS_TIMEOUT_HORAS", "24"))

_MOCK_IDS_RAW     = os.getenv("AVALISTA_TELEGRAM_IDS", "2012212775")
MOCK_AVALISTA_IDS = [int(x.strip()) for x in _MOCK_IDS_RAW.split(",") if x.strip()]

# Almacén en memoria para modo mock (en producción → PostgreSQL tabla task_votes)
_TAREAS_PENDIENTES: dict[str, dict] = {}


# ── Flujo principal ───────────────────────────────────────────────────────────

async def _flujo_tarea(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    texto_tarea: str,
    perfil: dict,
):
    """
    Evalúa la tarea y responde al usuario. Tres caminos:
      - aprobada: True  → recompensar inmediatamente
      - aprobada: False → explicar rechazo
      - aprobada: None  → abrir ronda de votación de avalistas (quórum)
    """
    await update.message.reply_text("Analizando tu tarea...")

    # Mantener indicador de escritura activo mientras el Tenzo procesa
    # (GenLayer puede tardar 30-60 s; el typing cubre ese silencio)
    stop_typing = asyncio.Event()

    async def _pulsar_typing():
        while not stop_typing.is_set():
            try:
                await update.message.chat.send_action(ChatAction.TYPING)
            except Exception:
                pass
            await asyncio.sleep(4)

    typing_task = asyncio.create_task(_pulsar_typing())

    try:
        resultado = await _llamar_tenzo_evaluar(
            descripcion=texto_tarea,
            holon_id=perfil.get("holon_id", "holon-piloto"),
            persona_nombre=perfil.get("nombre", "miembro"),
            persona_id=str(update.effective_user.id),
        )
    finally:
        stop_typing.set()
        typing_task.cancel()

    aprobada     = resultado.get("aprobada")
    hoca         = resultado.get("recompensa_hoca", resultado.get("hoca", 0))
    razon        = resultado.get("razonamiento", resultado.get("razon", ""))
    advertencias = resultado.get("advertencias", [])
    categoria    = resultado.get("categoria", "")
    narracion    = resultado.get("narracion", [])
    nota         = ("\n\nNota: " + " / ".join(advertencias)) if advertencias else ""

    # Reproducir narracion: el Tenzo explica su razonamiento antes del veredicto
    for linea in narracion:
        await update.message.reply_text(linea)
        await asyncio.sleep(0.6)

    if aprobada is True:
        await update.message.reply_text(
            f"Tarea reconocida: {categoria.replace('_', ' ')}.\n"
            f"Recompensa: {int(hoca)} HoCa.\n{razon}{nota}"
        )
        await _guardar_tarea_aprobada(perfil, texto_tarea, int(hoca), categoria)
        return

    if aprobada is False:
        await update.message.reply_text(
            f"Esta tarea no fue reconocida como trabajo de cuidado.\n{razon}{nota}"
        )
        return

    # Escalada → votación de avalistas
    tarea_id = str(uuid.uuid4())[:8]
    expira   = datetime.now(timezone.utc) + timedelta(hours=TIMEOUT_HORAS)

    _TAREAS_PENDIENTES[tarea_id] = {
        "tarea_id":       tarea_id,
        "descripcion":    texto_tarea,
        "hoca_sugerido":  int(hoca),
        "categoria":      categoria,
        "razon_escalada": razon,
        "holon_id":       perfil.get("holon_id", "holon-piloto"),
        "persona_nombre": perfil.get("nombre", "miembro"),
        "reporter_id":    update.effective_user.id,
        "votos":          {},   # {str(telegram_id): "aprobar" | "rechazar"}
        "expira":         expira.isoformat(),
        "estado":         "pendiente_quorum",
    }

    await update.message.reply_text(
        f"Tu tarea fue enviada a los avalistas del holón para votación.\n"
        f"Se necesitan al menos {QUORUM_MIN} votos "
        f"(>{QUORUM_RATIO:.0%} deben aprobar).\n"
        f"Recibirás una notificación en hasta {TIMEOUT_HORAS} horas.\n"
        f"Referencia: {tarea_id}{nota}"
    )

    avalistas = await _obtener_avalistas(perfil.get("holon_id", "holon-piloto"))
    await _notificar_avalistas(context, tarea_id, _TAREAS_PENDIENTES[tarea_id], avalistas)


# ── Notificación y votación ───────────────────────────────────────────────────

async def _notificar_avalistas(
    context: ContextTypes.DEFAULT_TYPE,
    tarea_id: str,
    tarea: dict,
    avalistas: list[int],
):
    """Envía solicitud de votación a todos los avalistas del holón."""
    texto = (
        f"Tarea pendiente de validación — holón {tarea['holon_id']}\n\n"
        f"Persona: {tarea['persona_nombre']}\n"
        f"Descripción: {tarea['descripcion']}\n"
        f"HoCa sugerido: {tarea['hoca_sugerido']}\n"
        f"Motivo de escalada: {tarea['razon_escalada']}\n"
        f"ID: {tarea_id}\n\n"
        f"Se necesitan {QUORUM_MIN} votos (>{QUORUM_RATIO:.0%} para aprobar)."
    )
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            f"Aprobar ({tarea['hoca_sugerido']} HoCa)",
            callback_data=f"quorum:aprobar:{tarea_id}",
        ),
        InlineKeyboardButton(
            "Rechazar",
            callback_data=f"quorum:rechazar:{tarea_id}",
        ),
    ]])

    enviados = 0
    for avalista_id in avalistas:
        try:
            await context.bot.send_message(
                chat_id=avalista_id, text=texto, reply_markup=keyboard,
            )
            enviados += 1
        except Exception as e:
            logger.warning("No se pudo notificar al avalista %s: %s", avalista_id, e)

    logger.info("Quórum %s: notificados %d/%d avalistas", tarea_id, enviados, len(avalistas))


async def manejar_voto_avalista(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """
    Handler para los botones inline de votación de avalistas.
    Registrar en Application con:
      app.add_handler(CallbackQueryHandler(manejar_voto_avalista, pattern="^quorum:"))
    """
    query    = update.callback_query
    await query.answer()

    partes   = query.data.split(":")
    accion   = partes[1]   # "aprobar" | "rechazar"
    tarea_id = partes[2]
    voter_id = str(query.from_user.id)

    tarea = _TAREAS_PENDIENTES.get(tarea_id)
    if not tarea:
        await query.edit_message_text(f"Tarea {tarea_id} no encontrada o ya resuelta.")
        return
    if tarea["estado"] != "pendiente_quorum":
        await query.edit_message_text(f"Esta tarea ya fue resuelta ({tarea['estado']}).")
        return

    # Registrar voto — si ya votó, reemplaza su voto anterior
    tarea["votos"][voter_id] = accion
    votos_total   = len(tarea["votos"])
    votos_aprobar = sum(1 for v in tarea["votos"].values() if v == "aprobar")
    votos_rechazar = votos_total - votos_aprobar

    await query.edit_message_text(
        f"Voto registrado: {accion}.\n"
        f"Estado: {votos_aprobar} aprueban / {votos_rechazar} rechazan "
        f"({votos_total} votos totales, mínimo: {QUORUM_MIN})."
    )

    logger.info(
        "Quórum %s | voter=%s accion=%s | %d total, %d aprobar",
        tarea_id, voter_id, accion, votos_total, votos_aprobar,
    )

    await _verificar_y_resolver(context, tarea_id, tarea)


async def _verificar_y_resolver(
    context: ContextTypes.DEFAULT_TYPE,
    tarea_id: str,
    tarea: dict,
):
    """
    Resuelve la tarea si se alcanzó el quórum y hay mayoría clara.

    Condiciones:
      votos_total >= QUORUM_MIN
        AND ratio_aprobacion > QUORUM_RATIO → aprobada
        AND ratio_rechazo    > QUORUM_RATIO → rechazada
      Si hay empate exacto con QUORUM_RATIO = 0.5 → esperar más votos (o timeout)
    """
    votos_total   = len(tarea["votos"])
    if votos_total < QUORUM_MIN:
        return

    votos_aprobar  = sum(1 for v in tarea["votos"].values() if v == "aprobar")
    votos_rechazar = votos_total - votos_aprobar
    ratio_ap       = votos_aprobar  / votos_total
    ratio_re       = votos_rechazar / votos_total

    if ratio_ap > QUORUM_RATIO:
        await _cerrar_votacion(context, tarea_id, tarea, aprobada=True)
    elif ratio_re > QUORUM_RATIO:
        await _cerrar_votacion(context, tarea_id, tarea, aprobada=False)
    # Si ninguno supera el ratio → esperar más votos o timeout


async def _cerrar_votacion(
    context: ContextTypes.DEFAULT_TYPE,
    tarea_id: str,
    tarea: dict,
    aprobada: bool,
):
    """Cierra la votación, actualiza la DB y notifica al usuario."""
    votos_total   = len(tarea["votos"])
    votos_aprobar = sum(1 for v in tarea["votos"].values() if v == "aprobar")
    tarea["estado"] = "aprobada" if aprobada else "rechazada"

    if aprobada:
        hoca = tarea["hoca_sugerido"]
        await context.bot.send_message(
            chat_id=tarea["reporter_id"],
            text=(
                f"Tu tarea fue validada por los avalistas del holón.\n"
                f"Votos: {votos_aprobar}/{votos_total} aprobaron.\n"
                f"Recompensa: {hoca} HoCa."
            ),
        )
        await _guardar_tarea_aprobada(
            perfil={"holon_id": tarea["holon_id"], "nombre": tarea["persona_nombre"]},
            descripcion=tarea["descripcion"],
            hoca=hoca,
            categoria=tarea["categoria"],
        )
    else:
        votos_rechazar = votos_total - votos_aprobar
        await context.bot.send_message(
            chat_id=tarea["reporter_id"],
            text=(
                f"Tu tarea fue revisada por los avalistas del holón y no fue aprobada.\n"
                f"Votos: {votos_rechazar}/{votos_total} rechazaron."
            ),
        )

    logger.info(
        "Quórum %s cerrado | aprobada=%s | %d/%d votos",
        tarea_id, aprobada, votos_aprobar, votos_total,
    )


async def verificar_timeouts_quorum(context: ContextTypes.DEFAULT_TYPE):
    """
    Job periódico (cada hora) que expira tareas sin quórum en tiempo.
    Registrar con:
      app.job_queue.run_repeating(verificar_timeouts_quorum, interval=3600)
    """
    ahora = datetime.now(timezone.utc)
    for tarea_id, tarea in list(_TAREAS_PENDIENTES.items()):
        if tarea["estado"] != "pendiente_quorum":
            continue
        if ahora > datetime.fromisoformat(tarea["expira"]):
            tarea["estado"] = "expirada"
            votos_total   = len(tarea["votos"])
            votos_aprobar = sum(1 for v in tarea["votos"].values() if v == "aprobar")
            try:
                await context.bot.send_message(
                    chat_id=tarea["reporter_id"],
                    text=(
                        f"La votación de tu tarea (ref: {tarea_id}) expiró sin quórum.\n"
                        f"Votos recibidos: {votos_aprobar}/{votos_total} "
                        f"(se necesitaban {QUORUM_MIN}).\n"
                        f"Podés reportarla nuevamente si la considerás válida."
                    ),
                )
            except Exception as e:
                logger.error("Error notificando timeout %s: %s", tarea_id, e)


# ── Stubs de DB ───────────────────────────────────────────────────────────────

async def _obtener_avalistas(holon_id: str) -> list[int]:
    """
    Obtiene los telegram_ids de los avalistas del holón.
    Producción: SELECT telegram_user_id FROM holon_members
                WHERE holon_id = %s AND role = 'avalista'
    """
    return MOCK_AVALISTA_IDS


async def _llamar_tenzo_evaluar(
    descripcion: str, holon_id: str, persona_nombre: str, persona_id: str,
) -> dict:
    import httpx
    TENZO_URL = os.getenv("TENZO_API_URL", "https://hofi-tenzo-1080243330445.us-central1.run.app")
    API_KEY   = os.getenv("DEMO_API_KEY", "")
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            resp = await client.post(
                f"{TENZO_URL}/evaluar",
                json={
                    "descripcion_libre": descripcion,
                    "holon_id":          holon_id,
                    "persona_nombre":    persona_nombre,
                    "persona_id":        persona_id,
                },
                headers={"X-API-Key": API_KEY},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error("Error llamando al Tenzo: %s", e)
        return {
            "aprobada": False, "recompensa_hoca": 0, "categoria": "default",
            "razonamiento": "Error de comunicación con el Tenzo. Intenta de nuevo.",
            "escalada_humana": False, "advertencias": [],
        }


async def _guardar_tarea_aprobada(perfil, descripcion, hoca, categoria):
    logger.info("[DB] Tarea aprobada: %s → %d HoCa (%s)", descripcion[:40], hoca, categoria)
