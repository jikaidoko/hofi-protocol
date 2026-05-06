"""
HoFi — Voice Authentication Service (HTTP)

FastAPI que expone la capa de biometría de voz (voice_auth.py) como endpoints
HTTP, consumibles por el frontend Next.js, el bot de Telegram (en cualquier
contexto que no sea el flujo nativo de PTB) y cualquier otro cliente.

Endpoints:
  POST /voice/authenticate — recibe audio + nombre opcional, retorna sesión
                             equivalente a la del bot si la voz coincide.
  POST /voice/register     — registra o refresca el perfil de voz de un
                             miembro; requiere token admin (DEMO_API_KEY).
  GET  /health             — health check para Cloud Run startup probe.

Reutiliza `voice_auth.py` y `db.py` del paquete `telegram-bot`: el Dockerfile
los copia dentro de este contenedor. Comparte Secret Manager (JWT_SECRET_KEY,
DB_PASS) con el Tenzo Agent y el bot, así los tokens emitidos por el frontend
vía este endpoint son aceptados por Tenzo.
"""

import os
import logging
import tempfile
import time
import unicodedata
from typing import Optional

import jwt  # PyJWT
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import voice_auth
import db


# ── Holon ID canonicalization ────────────────────────────────────────────────
# La migración SQL 003 unificó voice_profiles.holon_id a 'familia-mourino'
# (lowercase ASCII puro). Pero filas legacy o pools cacheados pueden todavía
# contener 'familia-mouriño' (con tilde) o 'familia-valdes/valdez'. Esta
# función normaliza la salida para garantizar que el JSON contract del
# servicio NUNCA expone variantes — siempre devuelve la clave canónica que
# espera el frontend (lib/server/db.ts:normalizeHolonId).
_HOLON_ALIASES = {
    "familia-valdes":  "familia-mourino",
    "familia-valdez":  "familia-mourino",
    "familia-mouriño": "familia-mourino",
}


def _canonical_holon_id(holon_id: Optional[str]) -> str:
    """
    Normaliza holon_id antes de exponerlo al cliente.

      1) Strip + lowercase.
      2) NFD + quita combining marks (tildes).
      3) Aplica alias hardcoded para los IDs legacy conocidos.

    Idempotente: si el holon_id ya está canónico, lo devuelve igual.
    """
    if not holon_id:
        return ""
    s = holon_id.strip().lower()
    # NFD + strip diacríticos (Mouriño → mourino).
    s_nfd = unicodedata.normalize("NFD", s)
    s_ascii = "".join(c for c in s_nfd if not unicodedata.combining(c))
    # Si después del strip quedó un alias conocido, lo mapeamos a canónico.
    return _HOLON_ALIASES.get(s_ascii, s_ascii)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("VoiceAuthAPI")


# ── Configuración ────────────────────────────────────────────────────────────

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "").strip()
JWT_ALGORITHM  = "HS256"
JWT_TTL_SECS   = int(os.getenv("JWT_TTL_SECS", str(60 * 60 * 24 * 7)))  # 7 días

DEMO_API_KEY   = os.getenv("DEMO_API_KEY", "").strip()

# CORS: permitimos orígenes del frontend. Lista coma-separada; default razonable
# para dev + prod en Vercel. En producción setear explícito vía env var.
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,https://hofi.app,https://hofi-protocol.vercel.app",
    ).split(",")
    if o.strip()
]


app = FastAPI(
    title="HoFi Voice Authentication Service",
    description="Biometría de voz compartida entre el bot de Telegram y el frontend.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup():
    """Carga el mock/abre conexión a Cloud SQL."""
    db.init_db()
    if not JWT_SECRET_KEY:
        logger.warning(
            "JWT_SECRET_KEY vacío — los tokens emitidos no serán aceptados por Tenzo."
        )
    logger.info("VoiceAuthAPI | listo (CORS=%s)", CORS_ORIGINS)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sign_session_token(person_id: str, name: str, role: str, holon_id: str) -> str:
    """
    Firma un JWT compatible con el del frontend (@/lib/server/auth) y el de
    Tenzo. El `sub` es el person_id canónico, así Tenzo puede atribuir la
    tarea al SBT sin mapeo adicional.
    """
    if not JWT_SECRET_KEY:
        raise RuntimeError("JWT_SECRET_KEY no configurado")

    now = int(time.time())
    payload = {
        "sub":    person_id,
        "name":   name,
        "role":   role,
        "holon":  holon_id,
        "avatar": (name[:2] or "??").upper(),
        "iat":    now,
        "exp":    now + JWT_TTL_SECS,
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def _require_admin(authorization: Optional[str]) -> None:
    """Registro requiere DEMO_API_KEY (igual que el Tenzo Agent)."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization requerido")
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        raise HTTPException(status_code=401, detail="Formato Bearer requerido")
    token = authorization[len(prefix):].strip()
    if not DEMO_API_KEY or token != DEMO_API_KEY:
        raise HTTPException(status_code=403, detail="DEMO_API_KEY inválido")


async def _write_upload_to_tmp(upload: UploadFile) -> str:
    """
    Persiste el UploadFile a un tmp local para que librosa lo procese.
    Retorna el path. El caller debe remover el archivo al finalizar.
    """
    suffix = os.path.splitext(upload.filename or "voice.webm")[1] or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        data = await upload.read()
        tmp.write(data)
        return tmp.name


# ── Schemas de respuesta ──────────────────────────────────────────────────────

class AuthResponse(BaseModel):
    authenticated: bool
    person_id:     Optional[str] = None
    name:          Optional[str] = None
    role:          Optional[str] = None
    holon_id:      Optional[str] = None
    confidence:    Optional[float] = None
    # Token de sesión consumible por el frontend como cookie httpOnly, o por
    # Tenzo como Bearer. Firma y claims idénticos al del login tradicional.
    session_token: Optional[str] = None
    error:         Optional[str] = None


class RegisterResponse(BaseModel):
    ok:            bool
    person_id:     Optional[str] = None
    holon_id:      Optional[str] = None
    error:         Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/")
@app.get("/health")
def health():
    return {"status": "ok", "service": "voice-auth"}


@app.post("/voice/authenticate", response_model=AuthResponse)
async def voice_authenticate(
    audio: UploadFile = File(..., description="Audio a autenticar (webm/oga/wav)"),
    name: Optional[str] = Form(None, description="Nombre declarado — activa capa 1 de auth"),
):
    """
    Autenticación por voz. Misma lógica que el flujo `_flujo_autenticacion` del
    bot, pero sin la parte conversacional.

      - Si `name` viene: capa 1 (match dirigido por nombre, umbral 0.80).
      - Si no viene: capa 2 (match puro por voz, umbral 0.90).

    Retorna `session_token` firmado con JWT_SECRET_KEY. El frontend puede
    setearlo como cookie httpOnly y usarlo en llamadas subsecuentes.
    """
    audio_path = await _write_upload_to_tmp(audio)
    try:
        embedding = voice_auth.extraer_embedding(audio_path)
        if embedding is None:
            return AuthResponse(authenticated=False, error="No pude procesar el audio")

        perfiles = db.obtener_todos_perfiles()
        if not perfiles:
            return AuthResponse(authenticated=False, error="No hay perfiles registrados")

        resultado = None
        if name:
            resultado = voice_auth.autenticar_por_nombre(name, embedding, perfiles)
        if resultado is None:
            resultado = voice_auth.autenticar(embedding, perfiles)

        if resultado is None:
            return AuthResponse(authenticated=False, error="Voz no reconocida")

        # Derivar person_id canónico del member_name (mismo algoritmo que el
        # bot usa al escribir tasks.persona_id).
        person_id = (
            voice_auth.canonical_person_id(resultado["member_name"])
            or resultado["member_name"]
        )
        # Canonicalizar holon_id ANTES de devolver — defensa contra filas
        # legacy en voice_profiles o pools cacheados pre-migración 003.
        # Sin esto, Pablo veía holonId="familia-mouriño" (con tilde) en JSON.
        holon_id = _canonical_holon_id(resultado["holon_id"])

        # Resolver rol: si hay entrada en member_identities con rol explícito
        # la usamos; por ahora, default a "member" para todos los miembros
        # familiares. Ampliable cuando exista tabla `roles`.
        role = "member"

        try:
            token = _sign_session_token(
                person_id=person_id,
                name=resultado["member_name"],
                role=role,
                holon_id=holon_id,
            )
        except RuntimeError as e:
            logger.error("No se pudo firmar token: %s", e)
            token = None

        return AuthResponse(
            authenticated=True,
            person_id=person_id,
            name=resultado["member_name"],
            role=role,
            holon_id=holon_id,
            confidence=round(float(resultado.get("similitud", 0.0)), 4),
            session_token=token,
        )
    finally:
        try:
            os.remove(audio_path)
        except Exception:
            pass


@app.post("/voice/register", response_model=RegisterResponse)
async def voice_register(
    authorization: Optional[str] = Header(None),
    audio: UploadFile = File(..., description="Muestra única de voz"),
    name:     str  = Form(..., description="Display name del miembro"),
    holon_id: str  = Form(..., description="ID del holón al que pertenece"),
    telegram_user_id: int = Form(
        0,
        description="Telegram user_id si aplica — default 0 para registros vía web"
    ),
):
    """
    Registro/refresco del perfil de voz. Protegido por DEMO_API_KEY porque
    crea identidad en el bridge — no queremos exponerlo anónimamente.

    Si ya existe un perfil con el mismo person_id canónico, se sobreescribe
    (upsert). Si viene un telegram_user_id > 0, se agrega también a la bridge
    member_identities (compatible con familia compartida).
    """
    _require_admin(authorization)

    # Canonicalizar holon_id de entrada — los clientes pueden mandar
    # 'familia-mouriño' o 'familia-valdes' por error; lo persistimos siempre
    # como 'familia-mourino' para no contaminar voice_profiles.
    holon_id = _canonical_holon_id(holon_id)

    audio_path = await _write_upload_to_tmp(audio)
    try:
        embedding = voice_auth.extraer_embedding(audio_path)
        if embedding is None:
            raise HTTPException(status_code=400, detail="No pude procesar el audio")

        # Guardar perfil de voz — db.guardar_perfil() ya:
        #   1) UPSERTea voice_profiles por person_id canónico
        #   2) Inserta en member_identities si hay telegram_user_id > 0
        db.guardar_perfil(telegram_user_id, name, holon_id, embedding)

        person_id = voice_auth.canonical_person_id(name) or name
        return RegisterResponse(ok=True, person_id=person_id, holon_id=holon_id)

    finally:
        try:
            os.remove(audio_path)
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
        log_level="info",
    )
