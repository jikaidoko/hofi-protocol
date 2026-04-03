"""
HoFi â€” Bot de Telegram con autenticaciÃ³n biomÃ©trica por voz
No-UI first: toda la interacciÃ³n es por voz o texto en Telegram.
"""

import os
import logging
import tempfile
import asyncio
import requests as http_requests

# Cargar variables de entorno desde .env (desarrollo local)
# En Cloud Run las variables vienen de --set-env-vars y --set-secrets
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # En producciÃ³n no es necesario

from telegram import Update, Bot
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

import db
import voice_auth

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s â€” %(message)s"
)
logger = logging.getLogger("HoFiBot")

# â”€â”€ Config â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
TENZO_API_URL    = os.getenv("TENZO_API_URL", "http://localhost:8080")
TENZO_DEMO_KEY   = os.getenv("DEMO_API_KEY", "")
DEFAULT_HOLON    = os.getenv("DEFAULT_HOLON_ID", "holon-piloto")

# Webhook: si WEBHOOK_URL estÃ¡ definido se usa webhook (Cloud Run)
# Si no, se usa polling (desarrollo local)
WEBHOOK_URL      = os.getenv("WEBHOOK_URL", "")    # ej: https://hofi-bot-xxx.run.app
PORT             = int(os.getenv("PORT", "8080"))

# Sesiones en memoria: {telegram_user_id: {state, member_name, holon_id, tenzo_token, ...}}
_sesiones: dict[int, dict] = {}


def get_sesion(user_id: int) -> dict:
    if user_id not in _sesiones:
        _sesiones[user_id] = {"state": "idle", "member_name": None, "holon_id": None, "tenzo_token": None}
    return _sesiones[user_id]


# â”€â”€ Tenzo API â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def tenzo_auth() -> str | None:
    """Obtiene un token JWT del Tenzo Agent usando la DEMO_API_KEY."""
    try:
        resp = http_requests.post(
            f"{TENZO_API_URL}/auth/token",
            json={"username": "tenzo-admin", "password": TENZO_DEMO_KEY},
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()["access_token"]
    except Exception as e:
        logger.error("Error autenticando con Tenzo: %s", str(e))
        return None


def tenzo_evaluar(token: str, titulo: str, descripcion: str, categoria: str,
                  duracion_horas: float, holon_id: str) -> dict | None:
    """EnvÃ­a una tarea al Tenzo para evaluaciÃ³n."""
    try:
        resp = http_requests.post(
            f"{TENZO_API_URL}/evaluar",
            json={
                "titulo": titulo,
                "descripcion": descripcion,
                "categoria": categoria,
                "duracion_horas": duracion_horas,
                "holon_id": holon_id,
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=120
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error("Error evaluando tarea: %s", str(e))
        return None


# â”€â”€ Whisper (transcripciÃ³n de voz a texto) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_faster_whisper_model = None

def _get_whisper_model():
    """Carga faster-whisper una sola vez y lo reutiliza (evita reload en cada audio)."""
    global _faster_whisper_model
    if _faster_whisper_model is None:
        from faster_whisper import WhisperModel
        logger.info("Cargando faster-whisper base (CPU, int8)...")
        _faster_whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
        logger.info("faster-whisper listo.")
    return _faster_whisper_model

def transcribir_audio(audio_path: str) -> str:
    """Transcribe audio a texto usando faster-whisper (CPU, int8 quantized)."""
    try:
        model = _get_whisper_model()
        segments, info = model.transcribe(audio_path, language="es")
        texto = " ".join(seg.text for seg in segments).strip()
        logger.info("TranscripciÃ³n (lang=%s, prob=%.2f): '%s'",
                    info.language, info.language_probability, texto)
        return texto
    except Exception as e:
        logger.error("Error transcribiendo audio: %s", str(e))
        return ""


# â”€â”€ Parseo de registro â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def parsear_registro(texto: str) -> tuple[str, str] | tuple[None, None]:
    """
    Parsea "Soy [nombre], holÃ³n [nombre-holÃ³n]" y retorna (nombre, holon_id).
    Acepta variaciones comunes en espaÃ±ol, incluyendo cuando Whisper transcribe
    "holÃ³n" como "olÃ³n" (pierde la 'h') y holones con espacios ("familia valdes").
    """
    import re
    texto = texto.lower().strip()

    # PatrÃ³n: "soy X, holÃ³n/olÃ³n Y" â€” lazy match en nombre, permite espacios en holÃ³n
    # h? cubre cuando Whisper omite la 'h' de "holÃ³n" â†’ "olÃ³n"
    patrones = [
        r"(?:soy|me llamo)\s+(.+?)[,\s]+h?ol[oÃ³]n\s+([a-zÃ¡Ã©Ã­Ã³ÃºÃ¼Ã±\s0-9\-_]+)",
        r"(?:soy|me llamo)\s+(.+?)[,\.]\s+([a-zÃ¡Ã©Ã­Ã³ÃºÃ¼Ã±\s0-9\-_]+)",
    ]

    for patron in patrones:
        match = re.search(patron, texto)
        if match:
            nombre = match.group(1).strip().title()
            # Normalizar holÃ³n: espacios â†’ guiones, limpiar extremos
            holon  = match.group(2).strip().lower()
            holon  = re.sub(r"\s+", "-", holon)   # "familia valdes" â†’ "familia-valdes"
            holon  = holon.strip("-")              # quitar guiones sobrantes al inicio/fin
            return nombre, holon

    return None, None


# â”€â”€ Handlers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ðŸŒ± Bienvenido a HoFi\n\n"
        "Soy el asistente del protocolo de finanzas regenerativas.\n\n"
        "Enviame un mensaje de voz para comenzar.\n"
        "Si es tu primera vez, te voy a pedir tu nombre y tu holÃ³n.\n\n"
        "The act of caring is the yield."
    )


async def cmd_estado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sesion = get_sesion(user_id)

    if sesion["member_name"]:
        await update.message.reply_text(
            f"âœ… Autenticado como *{sesion['member_name']}*\n"
            f"HolÃ³n: `{sesion['holon_id']}`",
            parse_mode="Markdown"
        )
    else:
        registrado = db.perfil_existe(user_id)
        if registrado:
            await update.message.reply_text("ðŸ” Enviame un audio de voz para autenticarte.")
        else:
            await update.message.reply_text(
                "ðŸ‘¤ No tenÃ©s perfil aÃºn.\n"
                "Enviame un audio diciendo:\n"
                "_\"Soy [nombre], holÃ³n [nombre-holÃ³n]\"_",
                parse_mode="Markdown"
            )


async def cmd_tarea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Permite iniciar el flujo de tarea manualmente (como alternativa al auto-flujo)."""
    user_id = update.effective_user.id
    sesion = get_sesion(user_id)

    if not sesion["member_name"]:
        await update.message.reply_text(
            "Primero necesito reconocerte. Enviame un mensaje de voz."
        )
        return

    sesion["state"] = "esperando_tarea"
    await update.message.reply_text(
        f"Contame la tarea, {sesion['member_name']}. "
        "Decime quÃ© hiciste, cuÃ¡ntas horas y de quÃ© tipo fue el trabajo."
    )


async def manejar_voz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler principal para mensajes de voz."""
    user_id = update.effective_user.id
    sesion  = get_sesion(user_id)

    await update.message.reply_text("ðŸŽ™ï¸ Procesando tu audio...")

    # 1. Descargar el audio
    voice_file = await update.message.voice.get_file()
    with tempfile.NamedTemporaryFile(suffix=".oga", delete=False) as tmp:
        audio_path = tmp.name

    await voice_file.download_to_drive(audio_path)

    try:
        # 2. Extraer embedding (ANTES de cualquier otra operaciÃ³n)
        embedding = voice_auth.extraer_embedding(audio_path)

        # 3. Transcribir para entender el contenido
        texto = transcribir_audio(audio_path)
        logger.info("TranscripciÃ³n user %d: '%s'", user_id, texto)

    finally:
        # 4. Descartar el audio original SIEMPRE (privacidad)
        import os as _os
        if _os.path.exists(audio_path):
            _os.remove(audio_path)
            logger.info("Audio original descartado para user %d", user_id)

    if embedding is None:
        await update.message.reply_text("No pude procesar el audio. IntentÃ¡ de nuevo.")
        return

    # â”€â”€ Registro guiado (multi-paso): no interrumpir con auth â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if sesion["state"] == "registro_nombre":
        await _flujo_registro_nombre(update, user_id, sesion, texto)
        return

    if sesion["state"] == "registro_holon":
        await _flujo_registro_holon(update, user_id, sesion, texto)
        return

    if sesion["state"] == "registro_voz_1":
        await _flujo_registro_voz_1(update, user_id, sesion, embedding)
        return

    if sesion["state"] == "registro_voz_2":
        await _flujo_registro_voz_2(update, user_id, sesion, embedding)
        return

    # â”€â”€ TODO mensaje de voz verifica identidad â€” permite compartir dispositivo â”€
    # La voz ES la identidad. No importa el estado de la sesiÃ³n anterior.
    await _flujo_autenticacion(update, user_id, sesion, embedding, texto)


async def _flujo_autenticacion(update, user_id, sesion, embedding, texto):
    """
    Verifica identidad por voz en cada mensaje.
    Permite que una misma cuenta de Telegram sea compartida por la familia â€”
    la voz (y el nombre) distinguen a cada persona.

    Estrategia de dos capas:
      1. Si el audio dice "Soy X" â†’ buscar perfil por nombre y verificar voz
         con umbral mÃ¡s bajo (0.80). Si X no estÃ¡ registrado â†’ registro directo.
      2. Si no hay nombre â†’ matching puro por voz (threshold 0.90).
    """
    perfiles    = db.obtener_todos_perfiles()
    nombre_dicho = voice_auth.extraer_nombre_audio(texto)

    # â”€â”€ Capa 1: IdentificaciÃ³n por nombre â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if nombre_dicho:
        logger.info("Auth | nombre en audio: '%s' â€” buscando perfil...", nombre_dicho)
        resultado = voice_auth.autenticar_por_nombre(nombre_dicho, embedding, perfiles)

        if resultado is None and not voice_auth.buscar_por_nombre(nombre_dicho, perfiles):
            # El nombre no estÃ¡ registrado â†’ iniciar registro con nombre ya conocido
            logger.info("Auth | '%s' no registrado â†’ inicio registro guiado", nombre_dicho)
            sesion["temp_nombre"] = nombre_dicho
            sesion["state"]       = "registro_holon"   # saltamos la pregunta de nombre
            await update.message.reply_text(
                f"Hola {nombre_dicho}! No tenÃ©s perfil registrado aÃºn. ðŸŒ±\n\n"
                f"Tu nombre: *{nombre_dicho}* âœ…\n\n"
                "Â¿A quÃ© holÃ³n pertenecÃ©s? Decime el nombre del holÃ³n\n"
                "(por voz o texto â€” ej: familia-valdes, el-pantano).",
                parse_mode="Markdown",
            )
            return

        if resultado is None:
            # El nombre SÃ estÃ¡ registrado pero la voz no coincide.
            # Posiblemente alguien que dice el nombre de otro, o audio muy corto.
            perfil_esperado = voice_auth.buscar_por_nombre(nombre_dicho, perfiles)
            logger.warning(
                "Auth | nombre '%s' encontrado pero voz no coincide con su perfil",
                nombre_dicho,
            )
            await update.message.reply_text(
                f"EscuchÃ© que decÃ­s *{nombre_dicho}*, pero tu voz no coincide con ese perfil. ðŸ¤”\n\n"
                "IntentÃ¡ de nuevo con una frase mÃ¡s larga, o hablÃ¡ directamente\n"
                "sin decir tu nombre.",
                parse_mode="Markdown",
            )
            return

    else:
        # â”€â”€ Capa 2: Matching puro por voz â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        logger.info("Auth | sin nombre en audio â€” matching puro por voz")
        resultado = voice_auth.autenticar(embedding, perfiles)

    # â”€â”€ AutenticaciÃ³n exitosa â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if resultado:
        nombre_anterior = sesion.get("member_name")
        nuevo_nombre    = resultado["member_name"]
        cambio_usuario  = nombre_anterior and nombre_anterior != nuevo_nombre

        sesion["member_name"] = nuevo_nombre
        sesion["holon_id"]    = resultado["holon_id"]
        sesion["state"]       = "esperando_tarea"
        if not sesion.get("tenzo_token") or cambio_usuario:
            sesion["tenzo_token"] = tenzo_auth()

        sim_pct  = int(resultado["similitud"] * 100)
        palabras = len(texto.split()) if texto else 0

        if cambio_usuario:
            logger.info("Auth | cambio de usuario: %s â†’ %s", nombre_anterior, nuevo_nombre)

        if palabras >= 6 and _es_descripcion_tarea(texto):
            # El audio describe una tarea directamente â€” auth + tarea en un mensaje
            await update.message.reply_text(f"Hola {nuevo_nombre} ðŸŒ± ({sim_pct}%)")
            await _flujo_tarea(update, user_id, sesion, texto)
        else:
            await update.message.reply_text(
                f"Hola {nuevo_nombre}, te reconozco ðŸŒ± ({sim_pct}%)\n\n"
                "Contame la tarea. Â¿QuÃ© hiciste, cuÃ¡ntas horas y de quÃ© tipo?"
            )
        return

    # â”€â”€ No reconocido â†’ registro guiado â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    sesion["state"] = "registro_nombre"
    await update.message.reply_text(
        "No te reconozco todavÃ­a. Bienvenido/a a HoFi ðŸŒ±\n\n"
        "Â¿CuÃ¡l es tu nombre? PodÃ©s decirlo en un audio o escribirlo."
    )


async def _flujo_registro_nombre(update, user_id, sesion, texto):
    """Paso 1 del registro guiado: captura el nombre del audio/texto."""
    nombre = texto.strip().title() if texto else ""
    # Tomar solo las primeras palabras si transcribiÃ³ algo largo
    palabras = nombre.split()
    nombre = " ".join(palabras[:3]) if palabras else ""

    if not nombre:
        await update.message.reply_text("No pude entender el nombre. Â¿PodÃ©s repetirlo?")
        return

    sesion["temp_nombre"] = nombre
    sesion["state"]       = "registro_holon"
    await update.message.reply_text(
        f"Perfecto, {nombre}. Â¿A quÃ© holÃ³n pertenecÃ©s?\n\n"
        "Decime el nombre del holÃ³n por voz o texto. "
        "Por ejemplo: familia-valdes, el-pantano, archi-brazo."
    )


async def _flujo_registro_holon(update, user_id, sesion, texto):
    """Paso 2 del registro guiado: captura el holÃ³n y solicita las muestras de voz."""
    import re
    holon = texto.strip().lower() if texto else ""
    # Normalizar: espacios â†’ guiones, quitar caracteres invÃ¡lidos
    holon = re.sub(r"\s+", "-", holon)
    holon = re.sub(r"[^a-z0-9\-_Ã¡Ã©Ã­Ã³ÃºÃ¼Ã±]", "", holon)
    holon = holon.strip("-")

    if not holon:
        await update.message.reply_text("No pude entender el holÃ³n. Â¿PodÃ©s repetirlo?")
        return

    # Guardar holÃ³n en sesiÃ³n â€” el perfil se guarda despuÃ©s de las 2 muestras de voz
    nombre = sesion.get("temp_nombre", "Miembro")
    sesion["temp_holon"] = holon
    sesion["state"]      = "registro_voz_1"

    await update.message.reply_text(
        f"Perfecto, {nombre}! HolÃ³n: *{holon}* âœ…\n\n"
        "Ahora voy a registrar tu voz con *2 muestras* para mayor precisiÃ³n.\n\n"
        "ðŸ“£ *Muestra 1/2* â€” DecÃ­ en voz alta:\n"
        "_\"Hoy dediquÃ© tiempo al cuidado de mi comunidad\"_",
        parse_mode="Markdown"
    )


async def _flujo_registro_voz_1(update, user_id, sesion, embedding):
    """
    Paso 3 del registro: primera muestra de voz dedicada.
    El embedding ya fue extraÃ­do en manejar_voz() antes de llegar acÃ¡.
    """
    if embedding is None:
        await update.message.reply_text("No pude procesar el audio. IntentÃ¡ de nuevo.")
        return

    sesion["temp_emb_1"] = embedding.tolist()
    sesion["state"]      = "registro_voz_2"
    nombre = sesion.get("temp_nombre", "Miembro")

    await update.message.reply_text(
        "âœ… Primera muestra recibida.\n\n"
        f"ðŸ“£ *Muestra 2/2* â€” DecÃ­ en voz alta:\n"
        "_\"En mi holÃ³n compartimos el trabajo y el cuidado\"_",
        parse_mode="Markdown"
    )


async def _flujo_registro_voz_2(update, user_id, sesion, embedding):
    """
    Paso 4 del registro: segunda muestra de voz. Promedia ambas y guarda el perfil.
    """
    if embedding is None:
        await update.message.reply_text("No pude procesar el audio. IntentÃ¡ de nuevo.")
        return

    emb_1  = sesion.get("temp_emb_1")
    nombre = sesion.get("temp_nombre", "Miembro")
    holon  = sesion.get("temp_holon", DEFAULT_HOLON)

    if not emb_1:
        sesion["state"] = "idle"
        await update.message.reply_text("Algo saliÃ³ mal. Enviame un audio de voz para empezar de nuevo.")
        return

    # â”€â”€ Calcular centroide de las 2 muestras â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    embedding_final = voice_auth.promediar_embeddings([emb_1, embedding.tolist()])
    logger.info("Registro | %s: pitch promedio del centroide = %.1f Hz",
                nombre, embedding_final[voice_auth.PITCH_MEAN_IDX])

    db.guardar_perfil(user_id, nombre, holon, embedding_final)

    sesion["member_name"] = nombre
    sesion["holon_id"]    = holon
    sesion["state"]       = "esperando_tarea"
    sesion["tenzo_token"] = tenzo_auth()
    sesion.pop("temp_emb_1",    None)
    sesion.pop("temp_nombre",   None)
    sesion.pop("temp_holon",    None)
    sesion.pop("temp_embedding", None)

    await update.message.reply_text(
        f"Listo, {nombre}! ðŸŒ± Tu voz quedÃ³ registrada en *{holon}*\n"
        "RegistrÃ© 2 muestras para mayor precisiÃ³n. Los audios fueron descartados.\n\n"
        "Contame tu primera tarea. Â¿QuÃ© hiciste, cuÃ¡ntas horas y de quÃ© tipo?",
        parse_mode="Markdown"
    )


def _es_descripcion_tarea(texto: str) -> bool:
    """
    Valida que el texto describe una tarea de cuidado comunitario real.
    Filtra introducciones ("Soy Luna"), saludos y texto sin acciÃ³n concreta.

    Estrategia: busca al menos UNA seÃ±al positiva entre:
      - Verbo de acciÃ³n en pasado ("hice", "cuidÃ©", "cocinamos"...)
      - Referencia de tiempo ("hora", "minutos", "media hora"...)
      - Palabra clave de categorÃ­a ("jardÃ­n", "nene", "cocina"...)

    Y descarta patrones tÃ­picos de presentaciÃ³n/saludo.
    """
    texto_lower = texto.lower().strip()
    palabras    = texto_lower.split()

    # Demasiado corto para ser una descripciÃ³n de tarea
    if len(palabras) < 4:
        return False

    # Patrones de presentaciÃ³n / saludo â€” NOT tareas
    INTRO = ["soy ", "me llamo ", "hola ", "buenos ", "buenas ", "mi nombre"]
    if any(texto_lower.startswith(p) for p in INTRO):
        return False

    # SeÃ±ales positivas
    VERBOS_ACCION = [
        "hice", "hicimos", "realicÃ©", "realice", "cocin", "limpiÃ©", "limpie",
        "cuidÃ©", "cuide", "cuidamos", "preparÃ©", "prepare", "ayudÃ©", "ayude",
        "enseÃ±Ã©", "enseÃ±e", "reparÃ©", "repare", "armÃ©", "arme", "sembrÃ©", "sembre",
        "podÃ©", "pode", "recogÃ­", "recogi", "organicÃ©", "organice",
        "acompaÃ±Ã©", "acompaÃ±e", "trabajÃ©", "trabaje", "participÃ©", "participe",
        "fue", "estuve", "pasÃ©", "pase", "dediquÃ©", "dedique",
        "cocinamos", "limpiamos", "preparamos", "ayudamos", "enseÃ±amos",
    ]
    TIEMPO_KW = [
        "hora", "horas", "minuto", "minutos", "media hora", "rato",
    ]
    CATEGORIA_KW = [
        "niÃ±o", "niÃ±a", "nene", "bebe", "cocin", "comida", "almuerzo", "cena",
        "limpi", "barr", "orden", "taller", "clase", "enseÃ±", "aprendiz",
        "reparar", "arreglar", "construi", "pintar", "manteni",
        "jardin", "planta", "huerta", "siembra", "poda",
        "salud", "medic", "botiquin", "primeros auxilios",
    ]

    tiene_verbo     = any(v in texto_lower for v in VERBOS_ACCION)
    tiene_tiempo    = any(t in texto_lower for t in TIEMPO_KW)
    tiene_categoria = any(k in texto_lower for k in CATEGORIA_KW)

    return tiene_verbo or tiene_tiempo or tiene_categoria


async def _flujo_tarea(update, user_id, sesion, texto):
    """Procesa una propuesta de tarea usando el Tenzo Agent."""
    if not texto:
        await update.message.reply_text("No pude entender el audio. Â¿PodÃ©s repetirlo?")
        return

    # â”€â”€ Guardia: verificar que el texto describe una tarea real â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Evita que introducciones, saludos o cualquier texto no-tarea
    # sean enviados al Tenzo y aprobados errÃ³neamente.
    if not _es_descripcion_tarea(texto):
        await update.message.reply_text(
            "No pude identificar una tarea de cuidado en ese audio. ðŸ¤”\n\n"
            "Contame *quÃ© hiciste*, *cuÃ¡nto tiempo* y *de quÃ© tipo* fue.\n\n"
            "Algunos ejemplos:\n"
            "_\"Estuve dos horas cocinando para la reuniÃ³n del holÃ³n\"_\n"
            "_\"CuidÃ© a los nenes por una hora y media\"_\n"
            "_\"Hice media hora de poda en el jardÃ­n\"_",
            parse_mode="Markdown"
        )
        return

    # Parseo bÃ¡sico de la tarea desde el texto transcripto
    tarea_data = _parsear_tarea(texto)

    await update.message.reply_text(
        f"ðŸ“‹ EntendÃ­: _{texto}_\n\nâ³ Consultando al Tenzo...",
        parse_mode="Markdown"
    )

    token = sesion.get("tenzo_token") or tenzo_auth()
    if not token:
        await update.message.reply_text("âŒ Error conectando con el Tenzo. IntentÃ¡ mÃ¡s tarde.")
        return

    resultado = tenzo_evaluar(
        token=token,
        titulo=tarea_data["titulo"],
        descripcion=texto,
        categoria=tarea_data["categoria"],
        duracion_horas=tarea_data["duracion_horas"],
        holon_id=sesion["holon_id"],
    )

    if not resultado:
        await update.message.reply_text("âŒ Error evaluando la tarea. IntentÃ¡ de nuevo.")
        return

    sesion["state"] = "autenticado"

    if resultado["aprobada"]:
        hoca  = resultado["recompensa_hoca"]
        tags  = ", ".join(resultado.get("clasificacion", []))
        razon = resultado.get("razonamiento", "")
        await update.message.reply_text(
            f"Tarea aprobada âœ…\n\n"
            f"Recompensa: {hoca} HoCa\n"
            f"Tipo: {tags}\n\n"
            f"{razon}\n\n"
            "Â¿TenÃ©s otra tarea para reportar?"
        )
    else:
        razon = resultado.get("razonamiento", "")
        await update.message.reply_text(
            f"Tarea no aprobada.\n\n{razon}\n\n"
            "Â¿QuerÃ©s intentar con otra tarea?"
        )


def _parsear_tarea(texto: str) -> dict:
    """
    Parseo bÃ¡sico de texto transcripto para extraer datos de la tarea.
    HeurÃ­stica simple â€” mejorar con NLP o Gemini en iteraciÃ³n siguiente.
    """
    import re

    texto_lower = texto.lower()

    # DuraciÃ³n en horas
    duracion = 1.0
    match_horas = re.search(r"(\d+(?:\.\d+)?)\s*hora", texto_lower)
    match_media = re.search(r"media hora|30 minutos", texto_lower)
    if match_horas:
        duracion = float(match_horas.group(1))
    elif match_media:
        duracion = 0.5

    # CategorÃ­a por palabras clave
    CATEGORIAS = {
        "cuidado_ninos":     ["niÃ±o", "niÃ±a", "nene", "bebe", "cuidado", "guarderia"],
        "cocina_comunal":    ["cocin", "comida", "almuerzo", "cena", "desayuno"],
        "limpieza_espacios": ["limpi", "barr", "orden", "aseo"],
        "taller_educativo":  ["taller", "clase", "enseÃ±", "aprend", "educa"],
        "mantenimiento":     ["reparar", "arreglar", "manteni", "construi", "pintar"],
        "jardineria":        ["jardin", "planta", "huerta", "siembra", "poda"],
        "salud_comunitaria": ["salud", "medic", "primeros auxilios", "botiquin"],
    }

    categoria = "cuidado_ninos"  # default
    for cat, palabras in CATEGORIAS.items():
        if any(p in texto_lower for p in palabras):
            categoria = cat
            break

    # TÃ­tulo: primeras palabras del texto (mÃ¡x 60 chars)
    titulo = texto[:60].strip()
    if len(texto) > 60:
        titulo += "..."

    return {"titulo": titulo, "categoria": categoria, "duracion_horas": duracion}


async def manejar_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para mensajes de texto (cuando el usuario escribe en vez de hablar)."""
    user_id = update.effective_user.id
    sesion  = get_sesion(user_id)
    texto   = update.message.text.strip()

    # Registro guiado: nombre y holÃ³n aceptan texto; las muestras de voz no
    if sesion["state"] == "registro_nombre":
        await _flujo_registro_nombre(update, user_id, sesion, texto)
        return

    if sesion["state"] == "registro_holon":
        await _flujo_registro_holon(update, user_id, sesion, texto)
        return

    if sesion["state"] in ("registro_voz_1", "registro_voz_2"):
        muestra = "1" if sesion["state"] == "registro_voz_1" else "2"
        await update.message.reply_text(
            f"Para la muestra {muestra}/2 necesito un *audio de voz*, no texto.\n"
            "Mandame un mensaje de voz. ðŸŽ™ï¸",
            parse_mode="Markdown"
        )
        return

    if sesion["state"] == "esperando_tarea":
        await _flujo_tarea(update, user_id, sesion, texto)
        return

    if not sesion["member_name"]:
        await update.message.reply_text(
            "Enviame un mensaje de voz para que pueda reconocerte."
        )
        return

    # Autenticado sin estado â†’ pasar a tarea
    sesion["state"] = "esperando_tarea"
    await update.message.reply_text(
        f"Hola {sesion['member_name']} ðŸŒ± Contame la tarea que querÃ©s reportar."
    )


# â”€â”€ Main â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def main():
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN no configurado")

    db.init_db()
    logger.info("HoFi Bot iniciando...")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("estado",  cmd_estado))
    app.add_handler(CommandHandler("tarea",   cmd_tarea))
    app.add_handler(MessageHandler(filters.VOICE, manejar_voz))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_texto))

    if WEBHOOK_URL:
        # Modo webhook (Cloud Run)
        webhook_path = f"/{TELEGRAM_TOKEN}"
        is_placeholder = "placeholder" in WEBHOOK_URL

        if is_placeholder:
            # Deploy inicial: servidor HTTP minimo que responde el health check
            # de Cloud Run inmediatamente, sin depender de Telegram API.
            # Step 5 del deploy actualiza WEBHOOK_URL a la URL real y Cloud Run
            # crea una nueva revision donde se registra el webhook correctamente.
            import asyncio
            from aiohttp import web as aio_web

            async def _health(request):
                return aio_web.Response(text="HoFi Bot OK")

            async def _run_health_server():
                aio_app = aio_web.Application()
                aio_app.router.add_get("/", _health)
                aio_app.router.add_get("/health", _health)
                runner = aio_web.AppRunner(aio_app)
                await runner.setup()
                site = aio_web.TCPSite(runner, "0.0.0.0", PORT)
                await site.start()
                logger.info("Bot modo WEBHOOK placeholder - health server en puerto %d", PORT)
                # Esperar indefinidamente hasta que Cloud Run reinicie con URL real
                while True:
                    await asyncio.sleep(3600)

            asyncio.run(_run_health_server())
        else:
            full_url = f"{WEBHOOK_URL}{webhook_path}"
            logger.info("Bot modo WEBHOOK -> %s (puerto %d)", full_url, PORT)
            app.run_webhook(
                listen="0.0.0.0",
                port=PORT,
                url_path=webhook_path,
                webhook_url=full_url,
                drop_pending_updates=True,
            )
    else:
        # â”€â”€ Modo polling (desarrollo local) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        logger.info("Bot modo POLLING (local)")
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

