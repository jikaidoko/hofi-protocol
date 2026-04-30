# Deploy target: Cloud Run hofi-v2-2026
"""
HoFi - Agente Tenzo · v1.1.0
Cambios respecto a v1.0.0:
  - 3 dimensiones de impacto: horas_validadas, carbono_kg, gnh (en prompt y respuesta)
  - _guardar_tarea_y_verificar_sbt(): persistencia diferida + umbral SBT_UMBRAL_TAREAS
  - _flush_sbt(): stub para update_reputation() en HolonSBT ISC (TODO on-chain)
Cambios respecto a v0.9.0:
  - task_parser.py: extracción estructurada antes de evaluar (duración real, categoría, topes)
  - Prompt Gemini refactorizado: recibe datos estructurados, devuelve confianza 0-1
  - Pipeline de 3 capas: Gemini → GenLayer ISC → apelación activa / avalista humano
  - evaluar_tarea ahora es async (requiere uvicorn con loop de eventos)
  - TareaRequest acepta descripcion_libre además del formato estructurado
"""

import os
import json
import time
import logging
import secrets
import asyncio
import tempfile
import requests
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Request, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from pydantic import BaseModel, Field
from typing import Optional
import bcrypt
import jwt as pyjwt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s"
)
logger = logging.getLogger("TenzoAgent")

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="HoFi Tenzo Agent API", version="1.1.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001",
                   "https://*.vercel.app", "*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"]    = "nosniff"
    response.headers["X-Frame-Options"]           = "DENY"
    response.headers["X-XSS-Protection"]          = "1; mode=block"
    response.headers["Referrer-Policy"]           = "strict-origin-when-cross-origin"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    ct = response.headers.get("content-type", "")
    if "application/json" in ct and "charset" not in ct:
        response.headers["content-type"] = "application/json; charset=utf-8"
    return response

# ── Configuración ────────────────────────────────────────────────────────────
API_KEY             = os.getenv("GEMINI_API_KEY", "")
MODEL_NAME          = os.getenv("MODEL_NAME", "gemini-2.5-flash")
DB_MOCK             = os.getenv("DB_MOCK", "true").lower() == "true"
DB_HOST             = os.getenv("DB_HOST", "localhost")
DB_NAME             = os.getenv("DB_NAME", "hofi")
DB_USER             = os.getenv("DB_USER", "postgres")
DB_PASS             = os.getenv("DB_PASS", "")
PORT                = int(os.getenv("PORT", "8080"))
JWT_SECRET_KEY      = os.getenv("JWT_SECRET_KEY", "")
JWT_EXPIRE_MINUTES  = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "").strip()
ADMIN_USERNAME      = os.getenv("ADMIN_USERNAME", "tenzo-admin").strip()
DEMO_API_KEY        = os.getenv("DEMO_API_KEY", "").strip()
ON_CHAIN            = os.getenv("ON_CHAIN", "false").lower() == "true"

# Umbrales del pipeline (configurables por env)
CONFIANZA_DIRECTA   = float(os.getenv("CONFIANZA_APROBACION_DIRECTA", "0.85"))
CERTEZA_MIN_APELAR  = float(os.getenv("CERTEZA_MIN_APELAR", "0.55"))
CERTEZA_MAX_APELAR  = float(os.getenv("CERTEZA_MAX_APELAR", "0.75"))
SBT_UMBRAL_TAREAS   = int(os.getenv("SBT_UMBRAL_TAREAS", "5"))
# Cantidad de tareas aprobadas acumuladas antes de hacer flush al SBT on-chain.

@app.on_event("startup")
async def validate_config():
    if not JWT_SECRET_KEY or len(JWT_SECRET_KEY) < 32:
        raise RuntimeError("JWT_SECRET_KEY inválida o muy corta")
    if not ADMIN_PASSWORD_HASH:
        raise RuntimeError("ADMIN_PASSWORD_HASH no configurada")
    logger.info("Auth | username='%s' hash_len=%d demo_key_set=%s",
                ADMIN_USERNAME, len(ADMIN_PASSWORD_HASH), bool(DEMO_API_KEY))
    if ON_CHAIN:
        logger.info("Modo ON_CHAIN activado — conectando al bridge...")
        from onchain_bridge import get_bridge
        bridge = get_bridge()
        if bridge:
            logger.info("Bridge on-chain OK | stats: %s", bridge.get_stats())
        else:
            logger.warning("ON_CHAIN=true pero bridge no disponible")
    logger.info(
        "Tenzo v1.1.0 listo | on_chain=%s db_mock=%s confianza_directa=%.2f "
        "certeza_apelar=[%.2f–%.2f] sbt_umbral=%d",
        ON_CHAIN, DB_MOCK, CONFIANZA_DIRECTA, CERTEZA_MIN_APELAR, CERTEZA_MAX_APELAR,
        SBT_UMBRAL_TAREAS
    )

# ── Whisper (transcripción de voz a texto) ───────────────────────────────────
# Lazy-load: el modelo se carga la primera vez que llega un audio. Mismo patrón
# que packages/telegram-bot/bot.py (faster-whisper base, CPU, int8 quantized).

_faster_whisper_model = None

def _get_whisper_model():
    """Carga faster-whisper una sola vez y la reutiliza (evita reload por request)."""
    global _faster_whisper_model
    if _faster_whisper_model is None:
        from faster_whisper import WhisperModel
        logger.info("Cargando faster-whisper base (CPU, int8)...")
        _faster_whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
        logger.info("faster-whisper listo.")
    return _faster_whisper_model


def _transcribir_audio(audio_path: str) -> tuple[str, float]:
    """
    Transcribe audio (webm/oga/wav/mp3) a texto en español.
    Devuelve (texto, language_probability). Si falla, ('', 0.0).
    """
    try:
        model = _get_whisper_model()
        segments, info = model.transcribe(audio_path, language="es")
        texto = " ".join(seg.text for seg in segments).strip()
        prob = float(getattr(info, "language_probability", 0.0) or 0.0)
        logger.info(
            "Transcripción (lang=%s, prob=%.2f): '%s'",
            getattr(info, "language", "?"), prob, texto[:80]
        )
        return texto, prob
    except Exception as e:
        logger.error("Error transcribiendo audio: %s — %s", type(e).__name__, str(e))
        return "", 0.0


# ── JWT ──────────────────────────────────────────────────────────────────────
security = HTTPBearer()

def crear_token(username: str) -> str:
    expira = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    return pyjwt.encode(
        {"sub": username, "exp": expira,
         "iat": datetime.now(timezone.utc), "jti": secrets.token_hex(16)},
        JWT_SECRET_KEY, algorithm="HS256"
    )

def verificar_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    try:
        payload = pyjwt.decode(
            credentials.credentials, JWT_SECRET_KEY, algorithms=["HS256"]
        )
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="Token inválido")
        return username
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")

def verificar_password(plain: str, hashed: str) -> bool:
    plain_clean = (plain or "").strip()
    demo_clean  = (DEMO_API_KEY or "").strip()
    if demo_clean and plain_clean == demo_clean:
        logger.info("Auth | método=demo_key OK")
        return True
    try:
        result = bcrypt.checkpw(plain_clean.encode("utf-8"), hashed.encode("utf-8"))
        logger.info("Auth | método=bcrypt resultado=%s", result)
        return result
    except Exception as e:
        logger.error("Auth | bcrypt error: %s", str(e))
        return False

# ── Modelos ──────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3,  max_length=50)
    password: str = Field(..., min_length=8,  max_length=128)

class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    expires_in:   int

class TareaRequest(BaseModel):
    """
    Acepta dos formatos:
    1. descripcion_libre: texto natural del bot ("Podé el jardín 2 horas")
    2. Formato estructurado legacy (titulo + categoria + duracion_horas)
    Si viene descripcion_libre, el parser la procesa. Si no, usa el formato legacy.
    """
    descripcion_libre:   Optional[str]   = Field(default=None, max_length=1000)
    titulo:              Optional[str]   = Field(default=None, max_length=200)
    descripcion:         Optional[str]   = Field(default=None, max_length=1000)
    categoria:           Optional[str]   = Field(default=None, max_length=100)
    duracion_horas:      Optional[float] = Field(default=None, gt=0, le=24)
    holon_id:            Optional[str]   = Field(default="holon-demo", max_length=100)
    persona_id:          Optional[str]   = Field(default=None, max_length=100)
    persona_nombre:      Optional[str]   = Field(default="miembro", max_length=100)
    recompensa_esperada: Optional[float] = Field(default=None, ge=0, le=100000)
    executor_address:    Optional[str]   = Field(default=None, max_length=42)

class MemberRequest(BaseModel):
    address:  str = Field(..., min_length=42, max_length=42)
    holon_id: str = Field(..., min_length=1,  max_length=100)
    role:     str = Field(default="member",   max_length=50)

# ── Histórico mock ───────────────────────────────────────────────────────────
MOCK_HISTORICO = [
    {"categoria": "cuidado_humano",     "duracion_horas": 2.0, "recompensa_hoca": 200,
     "descripcion": "Cuidado de niños", "fecha": "2026-03-26", "aprobada": True},
    {"categoria": "cocina_comunitaria", "duracion_horas": 1.5, "recompensa_hoca": 120,
     "descripcion": "Cocina comunal",   "fecha": "2026-03-25", "aprobada": True},
    {"categoria": "mantenimiento",      "duracion_horas": 1.0, "recompensa_hoca": 80,
     "descripcion": "Limpieza",         "fecha": "2026-03-24", "aprobada": True},
    {"categoria": "educacion",          "duracion_horas": 2.0, "recompensa_hoca": 180,
     "descripcion": "Taller",           "fecha": "2026-03-23", "aprobada": True},
    {"categoria": "mantenimiento",      "duracion_horas": 3.0, "recompensa_hoca": 240,
     "descripcion": "Mantenimiento",    "fecha": "2026-03-22", "aprobada": True},
    {"categoria": "cuidado_ecologico",  "duracion_horas": 2.0, "recompensa_hoca": 160,
     "descripcion": "Jardinería",       "fecha": "2026-03-21", "aprobada": True},
    {"categoria": "cuidado_humano",     "duracion_horas": 1.5, "recompensa_hoca": 150,
     "descripcion": "Salud comunitaria","fecha": "2026-03-20", "aprobada": True},
]

MOCK_CATALOGO = [
    {"nombre": "Poda de jardín",          "categoria": "cuidado_ecologico",  "hoca_min": 40,  "hoca_max": 120, "duracion_max_min": 240},
    {"nombre": "Cuidado de niños",        "categoria": "cuidado_humano",     "hoca_min": 60,  "hoca_max": 150, "duracion_max_min": 240},
    {"nombre": "Cocina comunitaria",      "categoria": "cocina_comunitaria", "hoca_min": 40,  "hoca_max": 100, "duracion_max_min": 240},
    {"nombre": "Mantenimiento espacio",   "categoria": "mantenimiento",      "hoca_min": 30,  "hoca_max": 90,  "duracion_max_min": 480},
    {"nombre": "Compostaje",              "categoria": "cuidado_ecologico",  "hoca_min": 20,  "hoca_max": 60,  "duracion_max_min": 120},
    {"nombre": "Cuidado de animales",     "categoria": "cuidado_animal",     "hoca_min": 30,  "hoca_max": 80,  "duracion_max_min": 180},
    {"nombre": "Limpieza espacios comunes","categoria": "mantenimiento",     "hoca_min": 25,  "hoca_max": 70,  "duracion_max_min": 180},
    {"nombre": "Lavado de platos",        "categoria": "cocina_comunitaria", "hoca_min": 10,  "hoca_max": 30,  "duracion_max_min": 45},
    {"nombre": "Riego y huerta",          "categoria": "cuidado_ecologico",  "hoca_min": 20,  "hoca_max": 60,  "duracion_max_min": 120},
    {"nombre": "Taller educativo",        "categoria": "educacion",          "hoca_min": 60,  "hoca_max": 160, "duracion_max_min": 120},
    {"nombre": "Cuidado de personas mayores","categoria": "cuidado_humano",  "hoca_min": 80,  "hoca_max": 180, "duracion_max_min": 240},
    {"nombre": "Reparación y construcción","categoria": "mantenimiento",     "hoca_min": 50,  "hoca_max": 150, "duracion_max_min": 480},
]

def obtener_catalogo(holon_id: str) -> list[dict]:
    if DB_MOCK:
        return MOCK_CATALOGO
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        conn = psycopg2.connect(host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASS)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT nombre, categoria, hoca_min, hoca_max, duracion_max_min "
                "FROM task_catalog WHERE holon_id = %s", (holon_id,)
            )
            rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows] if rows else MOCK_CATALOGO
    except Exception as e:
        logger.warning("DB catalogo error, usando mock: %s", type(e).__name__)
        return MOCK_CATALOGO

def obtener_historial_persona(persona_id: str, limit: int = 10) -> list[dict]:
    if DB_MOCK or not persona_id:
        return MOCK_HISTORICO[:limit]
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        conn = psycopg2.connect(host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASS)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT descripcion, categoria, recompensa_hoca AS hoca, "
                "created_at::date::text AS fecha, aprobada "
                "FROM tasks WHERE persona_id = %s ORDER BY created_at DESC LIMIT %s",
                (persona_id, limit)
            )
            rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows] if rows else MOCK_HISTORICO[:limit]
    except Exception as e:
        logger.warning("DB historial error, usando mock: %s", type(e).__name__)
        return MOCK_HISTORICO[:limit]

# ── Prompt Gemini ─────────────────────────────────────────────────────────────
def construir_prompt_evaluacion(
    tarea_struct,          # TareaEstructurada (de task_parser)
    catalogo: list[dict],
    historial: list[dict],
    nombre_holon: str,
    recompensa_esperada: Optional[float] = None,
) -> str:
    """
    v1.1.0: agrega evaluación de tres dimensiones de impacto:
      - horas_validadas: valida si las horas declaradas son creíbles
      - carbono_kg: CO₂ equivalente evitado o capturado (estimación)
      - gnh: impacto en bienestar (generosidad, apoyo_social, calidad_de_vida)
    """
    catalogo_str = "\n".join(
        f"- {t['nombre']} ({t['categoria']}) "
        f"[{t['hoca_min']}–{t['hoca_max']} HoCa, max {t['duracion_max_min']} min/día]"
        for t in catalogo
    )
    historial_str = "\n".join(
        f"- {h.get('descripcion','?')} → {h.get('hoca', h.get('recompensa_hoca',0))} HoCa ({h.get('fecha','')})"
        for h in historial[-8:]
    ) or "Sin historial previo."

    from task_parser import tarea_a_prompt_context
    contexto_tarea = tarea_a_prompt_context(tarea_struct)

    instruccion_recompensa = (
        "Calcula la recompensa justa en HoCa basada en el catálogo e historial."
        if recompensa_esperada is None
        else f"El usuario espera {recompensa_esperada} HoCa. Evalúa si es justo."
    )

    return f"""Eres el Tenzo, el agente evaluador del holón "{nombre_holon}".
Tu rol es reconocer el trabajo de cuidado comunitario, asignarle una recompensa en HoCa
y estimar su impacto en tres dimensiones: horas reales, huella de carbono y bienestar (GNH).
Eres justo, preciso y consistente. No eres generoso por defecto — eres equitativo.

## CATÁLOGO APROBADO POR ESTE HOLÓN
{catalogo_str}

## HISTORIAL RECIENTE DE ESTA PERSONA
{historial_str}

## TAREA A EVALUAR (procesada por el parser)
{contexto_tarea}
Descripción original: "{tarea_struct.descripcion_original}"

## INSTRUCCIÓN
{instruccion_recompensa}

## CRITERIOS DE RECHAZO INMEDIATO
Responde con "aprobada": false si el input:
- Es una presentación personal ("Soy X", "Me llamo X", "Hola")
- No contiene descripción de una acción real realizada
- Es incoherente, una pregunta, o claramente no relacionado con cuidado comunitario
- La duración declarada es físicamente imposible para esa actividad
  (ej: "lavé los platos 3 horas" — nadie lava platos 3 horas)

## CRITERIOS DE CÁLCULO DE HOCA
- Usa la duración normalizada indicada por el parser (respeta el tope del catálogo)
- Interpola dentro del rango HoCa del catálogo según duración y calidad descripta
- Sé más escéptico si hay advertencias del parser
- Considera el historial: si la persona ya reportó 3 tareas hoy, baja la confianza

## CRITERIOS PARA LAS TRES DIMENSIONES DE IMPACTO

### 1. horas_validadas
Estima las horas reales dedicadas a la tarea según la descripción.
Si la duración declarada es inverosímil, ajusta hacia abajo con criterio.

### 2. carbono_kg (CO₂ equivalente evitado o capturado)
Estima el impacto ambiental positivo de la tarea. Ejemplos de referencia:
- Plantar 1 árbol nativo: ~25 kg CO₂ en ciclo de vida estimado
- Huerta/compostaje 1 hora: ~2–5 kg CO₂ evitado (residuos + transporte)
- Cuidado en casa evitando internación: ~3–8 kg CO₂ por infraestructura evitada
- Cocina comunitaria 1 hora: ~1–3 kg CO₂ (economía de escala vs cocinas individuales)
- Tareas sin impacto ambiental directo (ej: taller educativo): 0.5–1 kg CO₂
- Nunca asignes 0 a tareas de cuidado — siempre hay algún impacto positivo.
- Usa valores conservadores. No exageres.

### 3. gnh (Índice de Felicidad Nacional Bruta — tres sub-dimensiones)
Puntúa de 0.0 a 1.0 cada dimensión:
- generosidad: ¿la tarea implica dar sin esperar retorno directo?
- apoyo_social: ¿fortalece vínculos, redes de cuidado o comunidad?
- calidad_de_vida: ¿mejora directamente el bienestar de otras personas?
El gnh_score es el promedio de las tres.

## FORMATO DE RESPUESTA (JSON estricto, sin texto adicional)
{{
  "aprobada": true/false,
  "confianza": 0.0–1.0,
  "recompensa_hoca": <número entero, 0 si no aprobada>,
  "categoria": "<categoria>",
  "match_catalogo": "<nombre exacto de la tarea del catálogo que matchea, o 'sin_match'>",
  "duracion_usada_min": <entero>,
  "horas_validadas": <float, horas reales estimadas>,
  "carbono_kg": <float, CO₂ eq evitado/capturado, siempre >= 0>,
  "gnh": {{
    "generosidad": <float 0.0–1.0>,
    "apoyo_social": <float 0.0–1.0>,
    "calidad_de_vida": <float 0.0–1.0>,
    "score": <float 0.0–1.0, promedio de las tres>
  }},
  "razonamiento": "<explicación breve en español, máx 2 oraciones>",
  "alerta": null
}}

Reglas de confianza:
- 0.9–1.0: match exacto en catálogo, duración plausible, sin advertencias
- 0.7–0.9: match aproximado o duración razonable
- 0.5–0.7: válida pero ambigua (activar GenLayer)
- < 0.5: rechazar directamente

Responde SOLO con el JSON. Sin explicaciones adicionales.
""".strip()

# ── Llamada a Gemini ──────────────────────────────────────────────────────────
def llamar_gemini(prompt: str, _reintentos: int = 3) -> dict:
    import time as _time
    if not API_KEY:
        raise ValueError("GEMINI_API_KEY no configurada")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{MODEL_NAME}:generateContent"
    )
    resp = None
    for intento in range(_reintentos):
        resp = requests.post(
            url,
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "temperature": 0.2,
                },
            },
            headers={"Content-Type": "application/json", "x-goog-api-key": API_KEY},
            timeout=30,
        )
        if resp.status_code in (429, 503) and intento < _reintentos - 1:
            espera = 10 * (2 ** intento)
            logger.warning("Gemini %d reintentando en %ds (%d/%d)",
                           resp.status_code, espera, intento+1, _reintentos)
            _time.sleep(espera)
            continue
        resp.raise_for_status()
        break
    data = json.loads(resp.content.decode("utf-8"))
    texto = data["candidates"][0]["content"]["parts"][0]["text"]
    texto = texto.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(texto)

# ── Persistencia DB y flush SBT ──────────────────────────────────────────────
async def _guardar_tarea_y_verificar_sbt(tarea: TareaRequest, resultado: dict) -> None:
    """
    Guarda la tarea aprobada en DB con las tres dimensiones de impacto.
    Acumula en sbt_pending y verifica si se alcanzó el umbral para
    hacer flush al SBT on-chain (escritura diferida).
    """
    if DB_MOCK:
        logger.info("DB_MOCK=true → tarea no persistida en DB")
        return

    try:
        import psycopg2
        conn = psycopg2.connect(
            host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASS
        )
        gnh = resultado.get("gnh", {})

        with conn.cursor() as cur:
            # 1. Insertar tarea con todas las dimensiones
            cur.execute("""
                INSERT INTO tasks (
                    persona_id, holon_id, descripcion, categoria,
                    recompensa_hoca, aprobada,
                    horas, tenzo_score,
                    carbono_kg,
                    gnh_score, gnh_generosidad, gnh_apoyo_social, gnh_calidad_vida,
                    sbt_inscripta
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s,
                    %s, %s, %s, %s,
                    false
                ) RETURNING id
            """, (
                tarea.persona_id,
                tarea.holon_id or "familia-valdes",
                tarea.descripcion_libre or tarea.titulo or "",
                resultado.get("categoria", "default"),
                resultado.get("recompensa_hoca", 0),
                True,
                resultado.get("horas_validadas", 0.0),
                resultado.get("confianza", 0.0),
                resultado.get("carbono_kg", 0.0),
                gnh.get("score", 0.0),
                gnh.get("generosidad", 0.0),
                gnh.get("apoyo_social", 0.0),
                gnh.get("calidad_de_vida", 0.0),
            ))
            task_id = cur.fetchone()[0]

            # 2. Acumular en sbt_pending (upsert)
            cur.execute("""
                INSERT INTO sbt_pending (
                    persona_id, holon_id,
                    horas_acum, hoca_acum, carbono_acum, gnh_acum,
                    tasks_acum, ultima_tarea_id
                ) VALUES (%s, %s, %s, %s, %s, %s, 1, %s)
                ON CONFLICT (persona_id, holon_id) DO UPDATE SET
                    horas_acum      = sbt_pending.horas_acum     + EXCLUDED.horas_acum,
                    hoca_acum       = sbt_pending.hoca_acum      + EXCLUDED.hoca_acum,
                    carbono_acum    = sbt_pending.carbono_acum   + EXCLUDED.carbono_acum,
                    gnh_acum        = sbt_pending.gnh_acum       + EXCLUDED.gnh_acum,
                    tasks_acum      = sbt_pending.tasks_acum     + 1,
                    ultima_tarea_id = EXCLUDED.ultima_tarea_id
                RETURNING tasks_acum, hoca_acum, carbono_acum, gnh_acum, horas_acum
            """, (
                tarea.persona_id,
                tarea.holon_id or "familia-valdes",
                resultado.get("horas_validadas", 0.0),
                resultado.get("recompensa_hoca", 0),
                resultado.get("carbono_kg", 0.0),
                gnh.get("score", 0.0),
                task_id,
            ))
            pending = cur.fetchone()
            tasks_acum, hoca_acum, carbono_acum, gnh_acum, horas_acum = pending

            conn.commit()

        logger.info(
            "DB | tarea #%d guardada | pending: %d tareas / %.1f HoCa / %.2f kg CO₂",
            task_id, tasks_acum, hoca_acum, carbono_acum
        )

        # 3. Verificar umbral para flush al SBT
        if tasks_acum >= SBT_UMBRAL_TAREAS:
            logger.info(
                "SBT | umbral alcanzado (%d tareas) para %s en %s → iniciando flush",
                tasks_acum, tarea.persona_id, tarea.holon_id
            )
            await _flush_sbt(
                persona_id=tarea.persona_id,
                holon_id=tarea.holon_id or "familia-valdes",
                horas_acum=horas_acum,
                hoca_acum=hoca_acum,
                carbono_acum=carbono_acum,
                gnh_acum=gnh_acum,
                tasks_acum=tasks_acum,
                tenzo_score=resultado.get("confianza", 0.0),
            )
            # Resetear sbt_pending
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE sbt_pending SET
                        horas_acum=0, hoca_acum=0, carbono_acum=0,
                        gnh_acum=0, tasks_acum=0
                    WHERE persona_id=%s AND holon_id=%s
                """, (tarea.persona_id, tarea.holon_id))
                cur.execute("""
                    UPDATE tasks SET sbt_inscripta=true
                    WHERE persona_id=%s AND holon_id=%s AND sbt_inscripta=false
                """, (tarea.persona_id, tarea.holon_id))
                conn.commit()

        conn.close()

    except Exception as e:
        logger.error("DB | error guardando tarea: %s → %s", type(e).__name__, str(e))


async def _flush_sbt(
    persona_id: str,
    holon_id: str,
    horas_acum: float,
    hoca_acum: float,
    carbono_acum: float,
    gnh_acum: float,
    tasks_acum: int,
    tenzo_score: float,
) -> None:
    """
    Llama a update_reputation() en el HolonSBT ISC de GenLayer.
    Solo se ejecuta cuando se alcanza el umbral de tareas acumuladas.
    Por ahora loguea — la integración real con genlayer_bridge se agrega
    cuando HolonChain termine el bootstrap.
    """
    logger.info(
        "SBT flush | persona=%s holon=%s | horas=%.1f hoca=%.1f co2=%.2f gnh=%.3f tasks=%d",
        persona_id, holon_id, horas_acum, hoca_acum, carbono_acum, gnh_acum, tasks_acum
    )
    # TODO: cuando ON_CHAIN=true y HolonChain esté lista:
    # from genlayer_bridge import llamar_update_reputation
    # await llamar_update_reputation(
    #     member_address = <wallet del persona_id>,
    #     holon_id       = holon_id,
    #     category       = "cuidado",       # categoría dominante acumulada
    #     hours          = horas_acum,
    #     hoca_earned    = hoca_acum,
    #     tenzo_score    = tenzo_score,
    # )


# ── Pipeline de evaluación ────────────────────────────────────────────────────
async def pipeline_evaluacion(tarea: TareaRequest) -> dict:
    """
    Flujo completo:
      1. Parser → extracción estructurada
      2. Gemini → evaluación con confianza
      3. Si confianza alta + match → aprobación directa
      4. Si no → GenLayer ISC → posible apelación activa del Tenzo
    """
    from task_parser import parsear_tarea

    # Determinar texto a parsear
    texto_input = (
        tarea.descripcion_libre
        or (f"{tarea.titulo}. {tarea.descripcion or ''}" if tarea.titulo else None)
        or ""
    ).strip()

    if not texto_input:
        return {
            "aprobada": False, "recompensa_hoca": 0, "confianza": 0.0,
            "categoria": "default", "match_catalogo": "sin_match",
            "razonamiento": "No se proporcionó descripción de la tarea.",
            "alerta": None, "escalada_humana": False, "pipeline": [],
        }

    # Capa 1: parser estructurado
    tarea_struct = parsear_tarea(texto_input)

    # Cargar catálogo e historial
    holon_id_norm = (tarea.holon_id or "familia-valdes").replace("familia-valdez", "familia-valdes")
    catalogo = obtener_catalogo(holon_id_norm)
    historial = obtener_historial_persona(tarea.persona_id or "", limit=10)

    # Capa 2: Gemini
    prompt = construir_prompt_evaluacion(
        tarea_struct, catalogo, historial,
        nombre_holon=tarea.holon_id or "holón",
        recompensa_esperada=tarea.recompensa_esperada,
    )
    gemini = llamar_gemini(prompt)

    confianza        = float(gemini.get("confianza", 0.0))
    aprobada_gemini  = bool(gemini.get("aprobada", False))
    match_catalogo   = gemini.get("match_catalogo", "sin_match")
    hoca             = int(gemini.get("recompensa_hoca", 0))

    pipeline = [{
        "capa": "gemini",
        "aprobada": aprobada_gemini,
        "confianza": confianza,
        "hoca": hoca,
        "match": match_catalogo,
        "advertencias": tarea_struct.advertencias,
    }]

    # Rechazo directo de Gemini (no-tarea evidente con alta certeza)
    if not aprobada_gemini and confianza >= 0.8:
        return _respuesta(gemini, escalada=False, pipeline=pipeline,
                          advertencias=tarea_struct.advertencias)

    # Aprobación directa: alta confianza + match en catálogo
    if aprobada_gemini and confianza >= CONFIANZA_DIRECTA and match_catalogo != "sin_match":
        logger.info("Aprobación directa | confianza=%.2f match=%s", confianza, match_catalogo)
        resultado = _respuesta(gemini, escalada=False, pipeline=pipeline,
                               advertencias=tarea_struct.advertencias)
        await _guardar_tarea_y_verificar_sbt(tarea, resultado)
        return resultado

    # Capa 3: GenLayer ISC con apelación activa del Tenzo
    logger.info("Escalando a GenLayer | confianza=%.2f match=%s", confianza, match_catalogo)
    from genlayer_bridge import consultar_oracle
    oracle = await consultar_oracle(
        tarea_data={
            "actividad":    tarea_struct.actividad,
            "duracion_min": tarea_struct.duracion_normalizada_min,
            "categoria":    tarea_struct.categoria,
            "descripcion_original": texto_input,
            "holon_id": holon_id_norm,
        },
        catalogo_holon=catalogo,
        historial_persona=historial,
        certeza_gemini=confianza,   # ← determina si el Tenzo apela o no
    )
    pipeline.append({
        "capa":           "genlayer",
        "aprobada":       oracle.aprobada,
        "confianza":      oracle.confianza,
        "hoca":           oracle.hoca_sugerido,
        "apelacion":      oracle.apelacion_usada,
        "escalada_humana": oracle.escalada_humana,
        "pasos_isc":      oracle.pipeline_pasos,
    })

    if oracle.aprobada is True:
        gemini["recompensa_hoca"] = oracle.hoca_sugerido
        gemini["razonamiento"]    = oracle.razon
        gemini["aprobada"]        = True
        resultado = _respuesta(gemini, escalada=False, pipeline=pipeline,
                               advertencias=tarea_struct.advertencias)
        await _guardar_tarea_y_verificar_sbt(tarea, resultado)
        return resultado

    if oracle.aprobada is False:
        gemini["aprobada"]     = False
        gemini["razonamiento"] = oracle.razon
        return _respuesta(gemini, escalada=False, pipeline=pipeline,
                          advertencias=tarea_struct.advertencias)

    # oracle.aprobada is None → escalar a avalista humano
    return _respuesta(
        gemini, escalada=True, pipeline=pipeline,
        advertencias=tarea_struct.advertencias,
        razon_escalada=oracle.razon,
        hoca_sugerido=oracle.hoca_sugerido,
    )


def _construir_narracion(pipeline: list, escalada: bool) -> list[str]:
    """
    Genera una lista de mensajes en voz del Tenzo que narran
    las decisiones tomadas durante la evaluacion.
    Se envian al usuario entre la espera y el veredicto final.
    """
    pasos = []

    for paso in pipeline:
        capa = paso.get("capa", "")

        if capa == "gemini":
            confianza   = paso.get("confianza", 0.0)
            match       = paso.get("match", "sin_match")
            hoca        = paso.get("hoca", 0)
            aprobada_g  = paso.get("aprobada", False)

            if match != "sin_match":
                pasos.append(
                    f"Encontre coincidencia en el catalogo del holon: {match.replace('_', ' ')}."
                )
            else:
                pasos.append(
                    "No encontre una coincidencia exacta en el catalogo del holon. Analice con criterios generales de cuidado."
                )

            nivel = (
                "alta"   if confianza >= 0.75 else
                "media"  if confianza >= 0.55 else
                "baja"
            )
            pasos.append(
                f"Mi confianza inicial fue del {confianza:.0%} ({nivel}). "
                f"Tarea {'reconocida' if aprobada_g else 'cuestionada'} en primera instancia."
            )

            if hoca > 0:
                pasos.append(f"Recompensa estimada: {hoca} HoCa.")

        elif capa == "genlayer":
            aprobada_isc  = paso.get("aprobada")
            apelacion     = paso.get("apelacion", False)
            escalada_hum  = paso.get("escalada_humana", False)
            nodos         = (paso.get("pasos_isc") or [{}])
            # extraer nodos_total del primer paso de pipeline del ISC si existe
            total = 5

            if not escalada_hum:
                pasos.append(
                    f"Derive la decision al consejo de {total} validadores independientes en GenLayer."
                )
                if apelacion:
                    pasos.append(
                        "El consejo rechazo inicialmente. Presente evidencia adicional: "
                        "historial limpio de la persona y coincidencias del catalogo del holon."
                    )
                    if aprobada_isc is True:
                        pasos.append("Tras la apelacion, el consejo aprobo la tarea.")
                    else:
                        pasos.append("La apelacion no cambio el resultado del consejo.")
                else:
                    if aprobada_isc is True:
                        pasos.append("El consejo alcanzo consenso: tarea aprobada.")
                    else:
                        pasos.append("El consejo rechazo la tarea. Acepto la decision.")
            else:
                pasos.append(
                    "Hay tension entre mi evaluacion y la del consejo. "
                    "Escale la decision a los avalistas del holon para que voten."
                )

    return pasos


def _respuesta(
    gemini: dict,
    escalada: bool,
    pipeline: list,
    advertencias: list,
    razon_escalada: str = "",
    hoca_sugerido: int = 0,
) -> dict:
    """v1.1.0: incluye horas_validadas, carbono_kg y gnh en la respuesta."""
    gnh = gemini.get("gnh", {})
    return {
        "aprobada":        gemini.get("aprobada", False) if not escalada else None,
        "recompensa_hoca": float(hoca_sugerido or gemini.get("recompensa_hoca", 0)),
        "confianza":       float(gemini.get("confianza", 0.0)),
        "categoria":       gemini.get("categoria", "default"),
        "match_catalogo":  gemini.get("match_catalogo", "sin_match"),
        "razonamiento":    razon_escalada or gemini.get("razonamiento", ""),
        "alerta":          gemini.get("alerta"),
        "escalada_humana": escalada,
        "advertencias":    [a for a in advertencias if a],
        "pipeline":        pipeline,
        "narracion":       _construir_narracion(pipeline, escalada),
        # ── Nuevas dimensiones de impacto v1.1.0 ─────────────────────────────
        "horas_validadas": float(gemini.get("horas_validadas", 0.0)),
        "carbono_kg":      float(gemini.get("carbono_kg", 0.0)),
        "gnh": {
            "generosidad":     float(gnh.get("generosidad", 0.0)),
            "apoyo_social":    float(gnh.get("apoyo_social", 0.0)),
            "calidad_de_vida": float(gnh.get("calidad_de_vida", 0.0)),
            "score":           float(gnh.get("score", 0.0)),
        },
    }

# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return JSONResponse(content={
        "status":    "ok",
        "version":   "1.1.0",
        "db_mock":   DB_MOCK,
        "model":     MODEL_NAME,
        "on_chain":  ON_CHAIN,
        "pipeline":  {
            "confianza_directa":  CONFIANZA_DIRECTA,
            "certeza_min_apelar": CERTEZA_MIN_APELAR,
            "certeza_max_apelar": CERTEZA_MAX_APELAR,
        },
        "contracts": {
            "hoca_token":    "0xe06eAf03992d9B3D2BCAC219D0838b34A4dBEA75",
            "brazo_token":   "0xA16DF94634E2Dd09Bf311Ec0d88EDe41f3F88E91",
            "network":       "HolonChain (chainId 73621)",
        },
    }, media_type="application/json; charset=utf-8")


@app.post("/auth/token", response_model=TokenResponse)
@limiter.limit("5/minute")
def obtener_token(request: Request, login: LoginRequest):
    logger.info("Auth | intento para username='%s'", login.username[:20])
    username_ok = login.username.strip() == ADMIN_USERNAME
    password_ok = verificar_password(login.password, ADMIN_PASSWORD_HASH)
    if not username_ok or not password_ok:
        logger.warning("Auth | FALLIDO username_ok=%s password_ok=%s",
                       username_ok, password_ok)
        raise HTTPException(
            status_code=401, detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"}
        )
    token = crear_token(login.username.strip())
    logger.info("Auth | OK — token emitido para '%s'", login.username.strip())
    return TokenResponse(
        access_token=token, token_type="bearer",
        expires_in=JWT_EXPIRE_MINUTES * 60
    )


@app.post("/evaluar")
@limiter.limit("10/minute")
async def evaluar_tarea(
    request: Request,
    tarea: TareaRequest,
    username: str = Depends(verificar_token),
):
    if not API_KEY:
        return JSONResponse(status_code=400,
            content={"error": "Service not configured", "code": "CONFIG_ERROR"})

    logger.info(
        "Evaluar | user=%s holon=%s persona=%s input='%s'",
        username,
        tarea.holon_id,
        tarea.persona_id or "anon",
        (tarea.descripcion_libre or tarea.titulo or "")[:60],
    )

    try:
        resultado = await pipeline_evaluacion(tarea)
    except requests.exceptions.Timeout:
        return JSONResponse(status_code=503,
            content={"error": "Service temporarily unavailable", "code": "TIMEOUT"})
    except Exception as e:
        logger.error("Evaluar | error: %s — %s", type(e).__name__, str(e))
        return JSONResponse(status_code=500,
            content={"error": "Internal server error", "code": "INTERNAL_ERROR"})

    # On-chain bridge (solo si aprobada definitivamente y hay address)
    if ON_CHAIN and resultado.get("aprobada") is True and tarea.executor_address:
        try:
            from onchain_bridge import get_bridge
            bridge = get_bridge()
            if bridge:
                tx = bridge.approve_task_onchain(
                    executor=tarea.executor_address,
                    holon_id=tarea.holon_id or "holon-demo",
                    categoria=resultado.get("categoria", "default"),
                    duracion_horas=(
                        tarea.duracion_horas
                        or resultado.get("pipeline", [{}])[-1].get("hoca", 0) / 80
                    ),
                    recompensa_hoca=resultado.get("recompensa_hoca", 0),
                    razonamiento=resultado.get("razonamiento", ""),
                )
                resultado["on_chain"] = tx
                logger.info("Evaluar | minted on-chain: %s", tx.get("tx_hash"))
        except Exception as e:
            logger.error("Evaluar | bridge error: %s", str(e))
            resultado["on_chain"] = {"error": "Bridge unavailable", "detail": str(e)}

    return JSONResponse(
        content=resultado,
        media_type="application/json; charset=utf-8"
    )


@app.post("/evaluar-voz")
@limiter.limit("10/minute")
async def evaluar_tarea_voz(
    request: Request,
    audio: UploadFile = File(...),
    holon_id: str = Form("holon-demo"),
    member_name: Optional[str] = Form(None),
    persona_id: Optional[str] = Form(None),
    executor_address: Optional[str] = Form(None),
    username: str = Depends(verificar_token),
):
    """
    Variante voz de /evaluar: acepta multipart/form-data con campo `audio`
    (webm grabado por MediaRecorder en el browser). Transcribe con faster-whisper,
    arma una TareaRequest con descripcion_libre=texto y reusa pipeline_evaluacion().
    """
    if not API_KEY:
        return JSONResponse(status_code=400,
            content={"error": "Service not configured", "code": "CONFIG_ERROR"})

    # ── Validar audio ─────────────────────────────────────────────────────────
    if not audio or not audio.filename:
        return JSONResponse(status_code=400,
            content={"error": "Se requiere campo 'audio'", "code": "MISSING_AUDIO"})

    # Guardar a archivo temporal para que faster-whisper lo lea (necesita ffmpeg).
    # webm → ffmpeg lo decodifica al vuelo. Sufijo igual al del upload para que
    # ffmpeg infiera el formato si Whisper depende de la extensión.
    suffix = ".webm"
    fname = (audio.filename or "").lower()
    for ext in (".webm", ".oga", ".ogg", ".wav", ".mp3", ".m4a"):
        if fname.endswith(ext):
            suffix = ext
            break

    tmp_path: Optional[str] = None
    try:
        contenido = await audio.read()
        if not contenido or len(contenido) < 100:
            return JSONResponse(status_code=400,
                content={"error": "Audio vacío o demasiado corto", "code": "EMPTY_AUDIO"})

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(contenido)
            tmp_path = tmp.name

        logger.info(
            "EvaluarVoz | user=%s holon=%s member=%s bytes=%d suffix=%s",
            username, holon_id, member_name or persona_id or "anon",
            len(contenido), suffix,
        )

        # ── Transcribir ───────────────────────────────────────────────────────
        # Whisper es CPU-bound; lo ejecutamos en threadpool para no bloquear el loop.
        texto, prob = await asyncio.to_thread(_transcribir_audio, tmp_path)

        if not texto:
            return JSONResponse(status_code=422, content={
                "error": "No se pudo transcribir el audio",
                "code": "TRANSCRIPTION_FAILED",
                "language_probability": prob,
            })

        # ── Pipeline normal ───────────────────────────────────────────────────
        tarea = TareaRequest(
            descripcion_libre=texto,
            holon_id=holon_id or "holon-demo",
            persona_id=persona_id,
            persona_nombre=member_name or "miembro",
            executor_address=executor_address,
        )

        try:
            resultado = await pipeline_evaluacion(tarea)
        except requests.exceptions.Timeout:
            return JSONResponse(status_code=503,
                content={"error": "Service temporarily unavailable", "code": "TIMEOUT"})
        except Exception as e:
            logger.error("EvaluarVoz | pipeline error: %s — %s", type(e).__name__, str(e))
            return JSONResponse(status_code=500,
                content={"error": "Internal server error", "code": "INTERNAL_ERROR"})

        # On-chain bridge (mismo flujo que /evaluar)
        if ON_CHAIN and resultado.get("aprobada") is True and executor_address:
            try:
                from onchain_bridge import get_bridge
                bridge = get_bridge()
                if bridge:
                    tx = bridge.approve_task_onchain(
                        executor=executor_address,
                        holon_id=holon_id or "holon-demo",
                        categoria=resultado.get("categoria", "default"),
                        duracion_horas=(
                            resultado.get("pipeline", [{}])[-1].get("hoca", 0) / 80
                        ),
                        recompensa_hoca=resultado.get("recompensa_hoca", 0),
                        razonamiento=resultado.get("razonamiento", ""),
                    )
                    resultado["on_chain"] = tx
                    logger.info("EvaluarVoz | minted on-chain: %s", tx.get("tx_hash"))
            except Exception as e:
                logger.error("EvaluarVoz | bridge error: %s", str(e))
                resultado["on_chain"] = {"error": "Bridge unavailable", "detail": str(e)}

        # Adjuntar transcripción al resultado para que la UI pueda mostrarla.
        resultado["transcripcion"] = texto
        resultado["language_probability"] = prob

        return JSONResponse(
            content=resultado,
            media_type="application/json; charset=utf-8",
        )
    finally:
        # Limpieza del archivo temporal (incluso ante excepciones).
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


@app.post("/member/register")
@limiter.limit("10/minute")
def register_member(
    request: Request,
    member: MemberRequest,
    username: str = Depends(verificar_token),
):
    if not ON_CHAIN:
        return JSONResponse(content={
            "status":  "off_chain_only",
            "message": "ON_CHAIN=false — SBT registration requires on-chain mode",
            "member":  member.model_dump(),
        })
    try:
        from onchain_bridge import get_bridge
        bridge = get_bridge()
        if not bridge:
            raise HTTPException(status_code=503, detail="On-chain bridge unavailable")
        tx_hash = bridge.issue_sbt(member.address, member.holon_id, member.role)
        return JSONResponse(content={
            "status":   "issued",
            "tx_hash":  tx_hash,
            "explorer": f"http://104.154.138.51:9650/ext/bc/czfN9bkKgPqpJ5SxegkDCRSSWuSPGDveAB6nLwtSPyWybRwHD/rpc/tx/{tx_hash}",
            "member":   member.model_dump(),
        })
    except Exception as e:
        logger.error("Register | SBT error: %s", str(e))
        raise HTTPException(status_code=500, detail="SBT issuance failed")


@app.get("/protocol/stats")
def protocol_stats(username: str = Depends(verificar_token)):
    if not ON_CHAIN:
        return JSONResponse(content={
            "on_chain": False,
            "message":  "Enable ON_CHAIN=true to see live blockchain stats",
            "contracts": {
                "task_registry": "0xd9B253E6E1b494a7f2030f9961101fC99d3fD038",
                "network":       "Ethereum Sepolia",
            },
        })
    try:
        from onchain_bridge import get_bridge
        bridge = get_bridge()
        if not bridge:
            raise HTTPException(status_code=503, detail="Bridge unavailable")
        stats = bridge.get_stats()
        return JSONResponse(content={"on_chain": True, **stats})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/debug-auth")
def debug_auth():
    return JSONResponse(content={
        "version":          "1.0.0",
        "admin_username":   ADMIN_USERNAME,
        "hash_len":         len(ADMIN_PASSWORD_HASH),
        "hash_prefix":      ADMIN_PASSWORD_HASH[:7] if ADMIN_PASSWORD_HASH else "",
        "demo_key_set":     bool(DEMO_API_KEY),
        "demo_key_len":     len(DEMO_API_KEY),
        "jwt_secret_set":   bool(JWT_SECRET_KEY),
        "on_chain":         ON_CHAIN,
        "db_mock":          DB_MOCK,
        "pipeline_thresholds": {
            "confianza_directa":  CONFIANZA_DIRECTA,
            "certeza_min_apelar": CERTEZA_MIN_APELAR,
            "certeza_max_apelar": CERTEZA_MAX_APELAR,
        },
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("tenzo_agent:app", host="0.0.0.0", port=PORT, reload=False)
