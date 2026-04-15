# -*- coding: utf-8 -*-
"""
HoFi -- Bot de Telegram con autenticacion biometrica por voz.
No-UI first: toda la interaccion es por voz o texto en Telegram.
"""

import os
import logging
import tempfile
import asyncio
import unicodedata
from difflib import SequenceMatcher
import requests as http_requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from telegram import Update, Bot
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

import db
import voice_auth

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s"
)
logger = logging.getLogger("HoFiBot")

# ── Config ───────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TENZO_API_URL  = os.getenv("TENZO_API_URL", "http://localhost:8080")
TENZO_DEMO_KEY = os.getenv("DEMO_API_KEY", "")
DEFAULT_HOLON  = os.getenv("DEFAULT_HOLON_ID", "holon-piloto")
WEBHOOK_URL    = os.getenv("WEBHOOK_URL", "")
PORT           = int(os.getenv("PORT", "8080"))

# Sesiones en memoria: {telegram_user_id: {state, member_name, holon_id, tenzo_token, ...}}
_sesiones: dict[int, dict] = {}


def get_sesion(user_id: int) -> dict:
    if user_id not in _sesiones:
        _sesiones[user_id] = {
            "state": "idle",
            "member_name": None,
            "holon_id": None,
            "tenzo_token": None,
        }
    return _sesiones[user_id]


# ── Tenzo API ────────────────────────────────────────────────────────────────

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
    """Envia una tarea al Tenzo para evaluacion."""
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


# ── Whisper ───────────────────────────────────────────────────────────────────

_faster_whisper_model = None


def _get_whisper_model():
    """Carga faster-whisper una sola vez (evita reload en cada audio)."""
    global _faster_whisper_model
    if _faster_whisper_model is None:
        from faster_whisper import WhisperModel
        logger.info("Cargando faster-whisper base (CPU, int8)...")
        _faster_whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
        logger.info("faster-whisper listo.")
    return _faster_whisper_model


def transcribir_audio(audio_path: str) -> str:
    """Transcribe audio a texto usando faster-whisper."""
    try:
        model = _get_whisper_model()
        segments, info = model.transcribe(audio_path, language="es")
        texto = " ".join(seg.text for seg in segments).strip()
        logger.info("Transcripcion (lang=%s, prob=%.2f): '%s'",
                    info.language, info.language_probability, texto)
        return texto
    except Exception as e:
        logger.error("Error transcribiendo audio: %s", str(e))
        return ""


# ── Resolver de holon ─────────────────────────────────────────────────────────

_FONET_REGLAS = [
    ("qu", "k"), ("ch", "x"), ("ll", "y"),
    ("ce", "se"), ("ci", "si"),
    ("ge", "je"), ("gi", "ji"),
    ("z", "s"), ("v", "b"), ("h", ""),
]


def _quitar_tildes(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _fonetizar(s: str) -> str:
    s = _quitar_tildes(s).lower()
    for origen, dest in _FONET_REGLAS:
        s = s.replace(origen, dest)
    return s


def _resolver_holon(holon_raw: str) -> tuple[str | None, float]:
    """
    Dado un holon transcripto por Whisper, retorna el holon registrado mas
    probable y su score de confianza [0.0, 1.0].
    Estrategia: A (fuzzy directo, peso 0.4) + B (fonetico espanol, peso 0.6).
    """
    conocidos = list({p["holon_id"] for p in db.obtener_todos_perfiles()})
    if not conocidos:
        return None, 0.0

    raw_norm = _quitar_tildes(holon_raw).lower()
    raw_fon  = _fonetizar(holon_raw)

    mejor_candidato: str | None = None
    mejor_score = 0.0

    for h in conocidos:
        h_norm = _quitar_tildes(h).lower()
        h_fon  = _fonetizar(h)

        score_directo  = SequenceMatcher(None, raw_norm, h_norm).ratio()
        score_fonetico = SequenceMatcher(None, raw_fon,  h_fon).ratio()
        score = 0.4 * score_directo + 0.6 * score_fonetico

        if score > mejor_score:
            mejor_score     = score
            mejor_candidato = h

    return mejor_candidato, mejor_score


# ── Parseo de registro (metodo legacy, no se usa en flujo guiado actual) ──────

def parsear_registro(texto: str) -> tuple[str, str] | tuple[None, None]:
    import re
    texto = texto.lower().strip()
    patrones = [
        r"(?:soy|me llamo)\s+(.+?)[,\s]+h?ol[oo]n\s+([a-z\s0-9\-_]+)",
        r"(?:soy|me llamo)\s+(.+?)[,\.]\s+([a-z\s0-9\-_]+)",
    ]
    for patron in patrones:
        match = re.search(patron, texto)
        if match:
            nombre = match.group(1).strip().title()
            holon  = match.group(2).strip().lower()
            holon  = re.sub(r"\s+", "-", holon)
            holon  = holon.strip("-")
            return nombre, holon
    return None, None


# ── Helpers async para DB (evita bloquear el event loop) ─────────────────────

async def _db_guardar_perfil(user_id, nombre, holon, embedding):
    """Llama db.guardar_perfil en un thread pool para no bloquear asyncio."""
    try:
        await asyncio.wait_for(
            asyncio.to_thread(db.guardar_perfil, user_id, nombre, holon, embedding),
            timeout=15.0
        )
        return True
    except asyncio.TimeoutError:
        logger.error("DB | timeout guardando perfil de %s", nombre)
        return False
    except Exception as e:
        logger.error("DB | error guardando perfil: %s", str(e))
        return False


async def _db_obtener_todos_perfiles():
    """Llama db.obtener_todos_perfiles en un thread pool."""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(db.obtener_todos_perfiles),
            timeout=10.0
        )
    except asyncio.TimeoutError:
        logger.error("DB | timeout obteniendo perfiles")
        return []
    except Exception as e:
        logger.error("DB | error obteniendo perfiles: %s", str(e))
        return []


async def _db_perfil_existe(user_id):
    """Llama db.perfil_existe en un thread pool."""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(db.perfil_existe, user_id),
            timeout=10.0
        )
    except asyncio.TimeoutError:
        logger.error("DB | timeout verificando perfil")
        return False
    except Exception as e:
        logger.error("DB | error verificando perfil: %s", str(e))
        return False


# ── Handlers de comandos ──────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bienvenido a HoFi\n\n"
        "Soy el asistente del protocolo de finanzas regenerativas.\n\n"
        "Enviame un mensaje de voz para comenzar.\n"
        "Si es tu primera vez, te voy a pedir tu nombre y tu holon.\n\n"
        "The act of caring is the yield."
    )


async def cmd_estado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sesion = get_sesion(user_id)

    if sesion["member_name"]:
        await update.message.reply_text(
            f"Autenticado como {sesion['member_name']}\n"
            f"Holon: {sesion['holon_id']}",
        )
    else:
        registrado = await _db_perfil_existe(user_id)
        if registrado:
            await update.message.reply_text("Enviame un audio de voz para autenticarte.")
        else:
            await update.message.reply_text(
                "No tenes perfil aun.\n"
                "Enviame un audio diciendo:\n"
                "\"Soy [nombre], holon [nombre-holon]\""
            )


async def cmd_tarea(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        "Decime que hiciste, cuantas horas y de que tipo fue el trabajo."
    )


# ── Handler principal de voz ──────────────────────────────────────────────────

async def manejar_voz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler principal para mensajes de voz."""
    user_id = update.effective_user.id
    sesion  = get_sesion(user_id)

    await update.message.reply_text("Procesando tu audio...")

    voice_file = await update.message.voice.get_file()
    with tempfile.NamedTemporaryFile(suffix=".oga", delete=False) as tmp:
        audio_path = tmp.name

    await voice_file.download_to_drive(audio_path)

    try:
        # Extraer embedding y transcribir en threads para no bloquear
        embedding = await asyncio.to_thread(voice_auth.extraer_embedding, audio_path)
        texto     = await asyncio.to_thread(transcribir_audio, audio_path)
        logger.info("Transcripcion user %d: '%s'", user_id, texto)
    finally:
        import os as _os
        if _os.path.exists(audio_path):
            _os.remove(audio_path)
            logger.info("Audio descartado para user %d", user_id)

    if embedding is None:
        await update.message.reply_text("No pude procesar el audio. Intenta de nuevo.")
        return

    # Flujo de registro guiado (multi-paso)
    if sesion["state"] == "registro_nombre":
        await _flujo_registro_nombre(update, user_id, sesion, texto)
        return

    if sesion["state"] == "registro_holon":
        await _flujo_registro_holon(update, user_id, sesion, texto)
        return

    if sesion["state"] == "confirmar_holon":
        await _flujo_confirmar_holon(update, user_id, sesion, texto)
        return

    if sesion["state"] == "registro_voz_1":
        await _flujo_registro_voz_1(update, user_id, sesion, embedding)
        return

    if sesion["state"] == "registro_voz_2":
        await _flujo_registro_voz_2(update, user_id, sesion, embedding)
        return

    # Cualquier otro audio: autenticar por voz
    await _flujo_autenticacion(update, user_id, sesion, embedding, texto)


# ── Flujo de autenticacion ────────────────────────────────────────────────────

async def _flujo_autenticacion(update, user_id, sesion, embedding, texto):
    """
    Verifica identidad por voz. Permite que una misma cuenta de Telegram
    sea compartida por la familia -- la voz distingue a cada persona.

    Capa 1: si el audio dice "Soy X" -> buscar perfil por nombre + verificar voz.
    Capa 2: si no hay nombre -> matching puro por voz (threshold 0.90).
    """
    perfiles     = await _db_obtener_todos_perfiles()
    nombre_dicho = voice_auth.extraer_nombre_audio(texto)

    if nombre_dicho:
        logger.info("Auth | nombre en audio: '%s' -- buscando perfil...", nombre_dicho)
        resultado = voice_auth.autenticar_por_nombre(nombre_dicho, embedding, perfiles)

        if resultado is None and not voice_auth.buscar_por_nombre(nombre_dicho, perfiles):
            # Nombre no registrado -> iniciar registro con nombre ya conocido
            logger.info("Auth | '%s' no registrado -> inicio registro guiado", nombre_dicho)
            sesion["temp_nombre"] = nombre_dicho
            sesion["state"]       = "registro_holon"
            await update.message.reply_text(
                f"Hola {nombre_dicho}! No tenes perfil registrado aun.\n\n"
                f"Tu nombre: {nombre_dicho} OK\n\n"
                "A que holon perteneces? Decime el nombre del holon\n"
                "(por voz o texto -- ej: familia-valdes, el-pantano)."
            )
            return

        if resultado is None:
            logger.warning("Auth | nombre '%s' encontrado pero voz no coincide", nombre_dicho)
            await update.message.reply_text(
                f"Escuche que decis {nombre_dicho}, pero tu voz no coincide con ese perfil.\n\n"
                "Intenta de nuevo con una frase mas larga, o habla directamente\n"
                "sin decir tu nombre."
            )
            return

    else:
        logger.info("Auth | sin nombre en audio -- matching puro por voz")
        resultado = voice_auth.autenticar(embedding, perfiles)

    if resultado:
        nombre_anterior = sesion.get("member_name")
        nuevo_nombre    = resultado["member_name"]
        cambio_usuario  = nombre_anterior and nombre_anterior != nuevo_nombre

        sesion["member_name"] = nuevo_nombre
        sesion["holon_id"]    = resultado["holon_id"]
        sesion["state"]       = "esperando_tarea"

        if not sesion.get("tenzo_token") or cambio_usuario:
            sesion["tenzo_token"] = await asyncio.to_thread(tenzo_auth)

        sim_pct  = int(resultado["similitud"] * 100)
        palabras = len(texto.split()) if texto else 0

        if cambio_usuario:
            logger.info("Auth | cambio de usuario: %s -> %s", nombre_anterior, nuevo_nombre)

        if palabras >= 6 and _es_descripcion_tarea(texto):
            await update.message.reply_text(f"Hola {nuevo_nombre} ({sim_pct}%)")
            await _flujo_tarea(update, user_id, sesion, texto)
        else:
            await update.message.reply_text(
                f"Hola {nuevo_nombre}, te reconozco ({sim_pct}%)\n\n"
                "Contame la tarea. Que hiciste, cuantas horas y de que tipo?"
            )
        return

    # No reconocido -> iniciar registro guiado
    sesion["state"] = "registro_nombre"
    await update.message.reply_text(
        "No te reconozco todavia. Bienvenido/a a HoFi\n\n"
        "Cual es tu nombre? Podes decirlo en un audio o escribirlo."
    )


# ── Flujo de registro guiado ──────────────────────────────────────────────────

async def _flujo_registro_nombre(update, user_id, sesion, texto):
    """Paso 1: captura el nombre del audio/texto."""
    nombre = texto.strip().title() if texto else ""
    palabras = nombre.split()
    nombre = " ".join(palabras[:3]) if palabras else ""

    if not nombre:
        await update.message.reply_text("No pude entender el nombre. Podes repetirlo?")
        return

    sesion["temp_nombre"] = nombre
    sesion["state"]       = "registro_holon"
    await update.message.reply_text(
        f"Perfecto, {nombre}. A que holon perteneces?\n\n"
        "Decime el nombre del holon por voz o texto. "
        "Por ejemplo: familia-valdes, el-pantano, archi-brazo."
    )


def _normalizar_holon_texto(texto: str) -> str:
    """Normaliza texto crudo a formato holon: minusculas, espacios->guiones."""
    import re
    h = texto.strip().lower() if texto else ""
    h = re.sub(r"\s+", "-", h)
    h = re.sub(r"[^a-z0-9\-_]", "", h)
    return h.strip("-")


async def _flujo_registro_holon(update, user_id, sesion, texto):
    """
    Paso 2: captura el holon transcripto, aplica fuzzy + fonetico
    contra holones conocidos, y pide confirmacion.
    """
    holon = _normalizar_holon_texto(texto)

    if not holon:
        await update.message.reply_text("No pude entender el holon. Podes repetirlo?")
        return

    sesion["temp_holon_raw"] = holon

    candidato, score = _resolver_holon(holon)

    if candidato and candidato != holon and score >= 0.65:
        nivel = "alta" if score >= 0.85 else "posible"
        sesion["temp_holon"] = candidato
        sesion["state"]      = "confirmar_holon"
        await update.message.reply_text(
            f"Escuche \"{holon}\" -- quisiste decir \"{candidato}\"? ({nivel} coincidencia)\n\n"
            "Responde \"si\" para confirmar, o escribe el nombre correcto."
        )
    else:
        holon_final = candidato if (candidato and score >= 0.85) else holon
        sesion["temp_holon"] = holon_final
        sesion["state"]      = "confirmar_holon"
        await update.message.reply_text(
            f"Entendi que tu holon es: \"{holon_final}\"\n\n"
            "Es correcto? Responde \"si\" para continuar, o escribe el nombre correcto."
        )


async def _flujo_confirmar_holon(update, user_id, sesion, texto):
    """
    Paso 2b: el usuario confirma o corrige el holon sugerido.
    - Afirmacion -> avanza a muestras de voz.
    - Cualquier otro texto -> correccion; re-aplica fuzzy+fonetico.
    """
    nombre = sesion.get("temp_nombre", "Miembro")
    texto_lower = (texto or "").strip().lower()

    _AFIRMACIONES = {
        "si", "yes", "ok", "dale", "correcto", "exacto",
        "asi", "eso", "claro", "confirmo", "bien",
    }

    if texto_lower in _AFIRMACIONES:
        holon = sesion["temp_holon"]
        sesion["state"] = "registro_voz_1"
        sesion.pop("temp_holon_raw", None)
        await update.message.reply_text(
            f"Perfecto, {nombre}! Holon: {holon} OK\n\n"
            "Ahora voy a registrar tu voz con 2 muestras para mayor precision.\n\n"
            "Muestra 1/2 -- Deci en voz alta:\n"
            "\"Hoy dedique tiempo al cuidado de mi comunidad\""
        )
    else:
        holon_corr = _normalizar_holon_texto(texto_lower)
        if not holon_corr:
            await update.message.reply_text("No pude entender el holon. Podes repetirlo?")
            return

        candidato, score = _resolver_holon(holon_corr)
        holon_final = (
            candidato if (candidato and score >= 0.85 and candidato != holon_corr)
            else holon_corr
        )
        sesion["temp_holon"]     = holon_final
        sesion["temp_holon_raw"] = holon_corr

        if candidato and candidato != holon_corr and score >= 0.65:
            nivel = "alta" if score >= 0.85 else "posible"
            await update.message.reply_text(
                f"Escuche \"{holon_corr}\" -- quisiste decir \"{candidato}\"? ({nivel} coincidencia)\n\n"
                "Responde \"si\" para confirmar, o escribe el nombre correcto."
            )
        else:
            await update.message.reply_text(
                f"Entendi: \"{holon_final}\"\n\n"
                "Es correcto? Responde \"si\" para continuar, o escribe el nombre correcto."
            )


async def _flujo_registro_voz_1(update, user_id, sesion, embedding):
    """Paso 3: primera muestra de voz dedicada."""
    if embedding is None:
        await update.message.reply_text("No pude procesar el audio. Intenta de nuevo.")
        return

    sesion["temp_emb_1"] = embedding.tolist()
    sesion["state"]      = "registro_voz_2"

    await update.message.reply_text(
        "Primera muestra recibida. OK\n\n"
        "Muestra 2/2 -- Deci en voz alta:\n"
        "\"En mi holon compartimos el trabajo y el cuidado\""
    )


async def _flujo_registro_voz_2(update, user_id, sesion, embedding):
    """Paso 4: segunda muestra. Promedia ambas y guarda el perfil."""
    if embedding is None:
        await update.message.reply_text("No pude procesar el audio. Intenta de nuevo.")
        return

    emb_1  = sesion.get("temp_emb_1")
    nombre = sesion.get("temp_nombre", "Miembro")
    holon  = sesion.get("temp_holon", DEFAULT_HOLON)

    if not emb_1:
        sesion["state"] = "idle"
        await update.message.reply_text("Algo salio mal. Enviame un audio de voz para empezar de nuevo.")
        return

    embedding_final = voice_auth.promediar_embeddings([emb_1, embedding.tolist()])
    logger.info("Registro | %s: pitch promedio del centroide = %.1f Hz",
                nombre, embedding_final[voice_auth.PITCH_MEAN_IDX])

    await update.message.reply_text("Guardando tu perfil de voz...")

    ok = await _db_guardar_perfil(user_id, nombre, holon, embedding_final)

    if not ok:
        await update.message.reply_text(
            "Hubo un error al guardar tu perfil. Intenta registrarte de nuevo."
        )
        sesion["state"] = "idle"
        return

    sesion["member_name"] = nombre
    sesion["holon_id"]    = holon
    sesion["state"]       = "esperando_tarea"
    sesion["tenzo_token"] = await asyncio.to_thread(tenzo_auth)
    sesion.pop("temp_emb_1",     None)
    sesion.pop("temp_nombre",    None)
    sesion.pop("temp_holon",     None)
    sesion.pop("temp_holon_raw", None)
    sesion.pop("temp_embedding", None)

    await update.message.reply_text(
        f"Listo, {nombre}! Tu voz quedo registrada en {holon}\n"
        "Registre 2 muestras para mayor precision. Los audios fueron descartados.\n\n"
        "Contame tu primera tarea. Que hiciste, cuantas horas y de que tipo?"
    )


# ── Descripcion de tarea ──────────────────────────────────────────────────────

def _es_descripcion_tarea(texto: str) -> bool:
    """
    Valida que el texto describe una tarea de cuidado comunitario real.
    Filtra introducciones, saludos y texto sin accion concreta.
    """
    texto_lower = texto.lower().strip()
    palabras    = texto_lower.split()

    if len(palabras) < 4:
        return False

    INTRO = ["soy ", "me llamo ", "hola ", "buenos ", "buenas ", "mi nombre"]
    if any(texto_lower.startswith(p) for p in INTRO):
        return False

    VERBOS_ACCION = [
        "hice", "hicimos", "realice", "cocin", "limpie",
        "cuide", "cuidamos", "prepare", "ayude",
        "ensene", "repare", "arme", "sembre",
        "pode", "recogi", "organice",
        "acompane", "trabaje", "participe",
        "fue", "estuve", "pase", "dedique",
        "cocinamos", "limpiamos", "preparamos", "ayudamos",
    ]
    TIEMPO_KW = ["hora", "horas", "minuto", "minutos", "media hora", "rato"]
    CATEGORIA_KW = [
        "nino", "nina", "nene", "bebe", "cocin", "comida", "almuerzo", "cena",
        "limpi", "barr", "orden", "taller", "clase", "ensene", "aprendiz",
        "reparar", "arreglar", "construi", "pintar", "manteni",
        "jardin", "planta", "huerta", "siembra", "poda",
        "salud", "medic", "botiquin", "primeros auxilios",
    ]

    tiene_verbo     = any(v in texto_lower for v in VERBOS_ACCION)
    tiene_tiempo    = any(t in texto_lower for t in TIEMPO_KW)
    tiene_categoria = any(k in texto_lower for k in CATEGORIA_KW)

    return tiene_verbo or tiene_tiempo or tiene_categoria


def _parsear_tarea(texto: str) -> dict:
    """Parseo basico de texto transcripto para extraer datos de la tarea."""
    import re

    texto_lower = texto.lower()

    duracion = 1.0
    match_horas = re.search(r"(\d+(?:\.\d+)?)\s*hora", texto_lower)
    match_media = re.search(r"media hora|30 minutos", texto_lower)
    if match_horas:
        duracion = float(match_horas.group(1))
    elif match_media:
        duracion = 0.5

    CATEGORIAS = {
        "cuidado_ninos":     ["nino", "nina", "nene", "bebe", "cuidado", "guarderia"],
        "cocina_comunal":    ["cocin", "comida", "almuerzo", "cena", "desayuno"],
        "limpieza_espacios": ["limpi", "barr", "orden", "aseo"],
        "taller_educativo":  ["taller", "clase", "ensene", "aprend", "educa"],
        "mantenimiento":     ["reparar", "arreglar", "manteni", "construi", "pintar"],
        "jardineria":        ["jardin", "planta", "huerta", "siembra", "poda"],
        "salud_comunitaria": ["salud", "medic", "primeros auxilios", "botiquin"],
    }

    categoria = "cuidado_ninos"
    for cat, palabras in CATEGORIAS.items():
        if any(p in texto_lower for p in palabras):
            categoria = cat
            break

    titulo = texto[:60].strip()
    if len(texto) > 60:
        titulo += "..."

    return {"titulo": titulo, "categoria": categoria, "duracion_horas": duracion}


# ── Flujo de tarea ────────────────────────────────────────────────────────────

async def _flujo_tarea(update, user_id, sesion, texto):
    """Procesa una propuesta de tarea usando el Tenzo Agent."""
    if not texto:
        await update.message.reply_text("No pude entender el audio. Podes repetirlo?")
        return

    if not _es_descripcion_tarea(texto):
        await update.message.reply_text(
            "No pude identificar una tarea de cuidado en ese audio.\n\n"
            "Contame que hiciste, cuanto tiempo y de que tipo fue.\n\n"
            "Algunos ejemplos:\n"
            "\"Estuve dos horas cocinando para la reunion del holon\"\n"
            "\"Cuide a los nenes por una hora y media\"\n"
            "\"Hice media hora de poda en el jardin\""
        )
        return

    tarea_data = _parsear_tarea(texto)

    await update.message.reply_text(
        f"Entendi: {texto}\n\nConsultando al Tenzo..."
    )

    token = sesion.get("tenzo_token") or await asyncio.to_thread(tenzo_auth)
    if not token:
        await update.message.reply_text("Error conectando con el Tenzo. Intenta mas tarde.")
        return

    resultado = await asyncio.to_thread(
        tenzo_evaluar,
        token,
        tarea_data["titulo"],
        texto,
        tarea_data["categoria"],
        tarea_data["duracion_horas"],
        sesion["holon_id"],
    )

    if not resultado:
        await update.message.reply_text("Error evaluando la tarea. Intenta de nuevo.")
        return

    sesion["state"] = "autenticado"

    if resultado["aprobada"]:
        hoca  = resultado["recompensa_hoca"]
        tags  = ", ".join(resultado.get("clasificacion", []))
        razon = resultado.get("razonamiento", "")
        await update.message.reply_text(
            f"Tarea aprobada\n\n"
            f"Recompensa: {hoca} HoCa\n"
            f"Tipo: {tags}\n\n"
            f"{razon}\n\n"
            "Tenes otra tarea para reportar?"
        )
    else:
        razon = resultado.get("razonamiento", "")
        await update.message.reply_text(
            f"Tarea no aprobada.\n\n{razon}\n\n"
            "Queres intentar con otra tarea?"
        )


# ── Handler de texto ──────────────────────────────────────────────────────────

async def manejar_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para mensajes de texto."""
    user_id = update.effective_user.id
    sesion  = get_sesion(user_id)
    texto   = update.message.text.strip()

    if sesion["state"] == "registro_nombre":
        await _flujo_registro_nombre(update, user_id, sesion, texto)
        return

    if sesion["state"] == "registro_holon":
        await _flujo_registro_holon(update, user_id, sesion, texto)
        return

    if sesion["state"] == "confirmar_holon":
        await _flujo_confirmar_holon(update, user_id, sesion, texto)
        return

    if sesion["state"] in ("registro_voz_1", "registro_voz_2"):
        muestra = "1" if sesion["state"] == "registro_voz_1" else "2"
        await update.message.reply_text(
            f"Para la muestra {muestra}/2 necesito un audio de voz, no texto.\n"
            "Mandame un mensaje de voz."
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

    sesion["state"] = "esperando_tarea"
    await update.message.reply_text(
        f"Hola {sesion['member_name']} Contame la tarea que queres reportar."
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN no configurado")

    logger.info("HoFi Bot iniciando...")

    if WEBHOOK_URL:
        webhook_path = f"/{TELEGRAM_TOKEN}"
        is_placeholder = "placeholder" in WEBHOOK_URL

        if is_placeholder:
            # Deploy inicial: servidor HTTP minimo para pasar el health check de Cloud Run.
            # NO inicializar DB aqui -- el socket de Cloud SQL puede no estar listo
            # y bloquearia el arranque indefinidamente.
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
                while True:
                    await asyncio.sleep(3600)

            asyncio.run(_run_health_server())
            return

        # Modo webhook real
        # init_db es rapido en modo mock; en PostgreSQL puede bloquearse si el socket
        # no esta listo, pero con connect_timeout=10 falla rapido y el bot arranca igual.
        try:
            db.init_db()
        except Exception as e:
            logger.warning("DB init fallida, continuando en modo degradado: %s", str(e))

        app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        app.add_handler(CommandHandler("start",  cmd_start))
        app.add_handler(CommandHandler("estado", cmd_estado))
        app.add_handler(CommandHandler("tarea",  cmd_tarea))
        app.add_handler(MessageHandler(filters.VOICE, manejar_voz))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_texto))

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
        # Modo polling (desarrollo local)
        try:
            db.init_db()
        except Exception as e:
            logger.warning("DB init fallida, continuando en modo degradado: %s", str(e))

        app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        app.add_handler(CommandHandler("start",  cmd_start))
        app.add_handler(CommandHandler("estado", cmd_estado))
        app.add_handler(CommandHandler("tarea",  cmd_tarea))
        app.add_handler(MessageHandler(filters.VOICE, manejar_voz))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_texto))
        logger.info("Bot modo POLLING (local)")
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
