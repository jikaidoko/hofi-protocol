# Deploy: 2026-03-24
"""
HoFi - Agente Tenzo · v0.9.0
Reset limpio con todo el aprendizaje de v0.8.0.
Fix crítico: verificar_password ahora completa el chequeo bcrypt.
"""

import os
import json
import logging
import secrets
import requests
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Request, HTTPException, Depends
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
app = FastAPI(title="HoFi Tenzo Agent API", version="0.9.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "https://*.vercel.app", "*"],
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

# ── Configuración ───────────────────────────────────────────────────────────
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
    logger.info("Tenzo v0.9.0 listo | on_chain=%s db_mock=%s", ON_CHAIN, DB_MOCK)

# ── JWT ─────────────────────────────────────────────────────────────────────
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
        payload = pyjwt.decode(credentials.credentials, JWT_SECRET_KEY, algorithms=["HS256"])
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="Token inválido")
        return username
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")

def verificar_password(plain: str, hashed: str) -> bool:
    """
    Verifica la password contra:
    1. DEMO_API_KEY (comparación directa, para demo/hackathon)
    2. bcrypt hash almacenado en Secret Manager
    """
    plain_clean = (plain or "").strip()

    # Vía 1: DEMO_API_KEY
    demo_clean = (DEMO_API_KEY or "").strip()
    if demo_clean and plain_clean == demo_clean:
        logger.info("Auth | método=demo_key OK")
        return True

    # Vía 2: bcrypt
    try:
        result = bcrypt.checkpw(plain_clean.encode("utf-8"), hashed.encode("utf-8"))
        logger.info("Auth | método=bcrypt resultado=%s", result)
        return result
    except Exception as e:
        logger.error("Auth | bcrypt error: %s", str(e))
        return False

# ── Modelos ─────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=128)

class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    expires_in:   int

class TareaRequest(BaseModel):
    titulo:              str   = Field(..., min_length=1, max_length=200)
    descripcion:         str   = Field(..., min_length=1, max_length=1000)
    categoria:           str   = Field(..., min_length=1, max_length=100)
    duracion_horas:      float = Field(..., gt=0, le=24)
    holon_id:            Optional[str]   = Field(default="holon-demo", max_length=100)
    recompensa_esperada: Optional[float] = Field(default=None, ge=0, le=100000)
    executor_address:    Optional[str]   = Field(default=None, max_length=42)

class MemberRequest(BaseModel):
    address:  str = Field(..., min_length=42, max_length=42)
    holon_id: str = Field(..., min_length=1, max_length=100)
    role:     str = Field(default="member", max_length=50)

# ── Histórico mock ──────────────────────────────────────────────────────────
MOCK_HISTORICO = [
    {"categoria": "cuidado_ninos",     "duracion_horas": 2.0, "recompensa_hoca": 200},
    {"categoria": "cocina_comunal",    "duracion_horas": 1.5, "recompensa_hoca": 120},
    {"categoria": "limpieza_espacios", "duracion_horas": 1.0, "recompensa_hoca":  80},
    {"categoria": "taller_educativo",  "duracion_horas": 2.0, "recompensa_hoca": 180},
    {"categoria": "mantenimiento",     "duracion_horas": 3.0, "recompensa_hoca": 240},
    {"categoria": "jardineria",        "duracion_horas": 2.0, "recompensa_hoca": 160},
    {"categoria": "salud_comunitaria", "duracion_horas": 1.5, "recompensa_hoca": 150},
]

def obtener_contexto_historico(categoria: str) -> str:
    if DB_MOCK:
        ejemplos = [t for t in MOCK_HISTORICO if t["categoria"] == categoria]
        return json.dumps(ejemplos or MOCK_HISTORICO[:3], ensure_ascii=False, indent=2)
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        conn = psycopg2.connect(host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASS)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT categoria, duracion_horas, recompensa_hoca "
                "FROM historical_tasks WHERE categoria = %s "
                "ORDER BY created_at DESC LIMIT 5", (categoria,)
            )
            rows = cur.fetchall()
            if not rows:
                cur.execute(
                    "SELECT categoria, duracion_horas, recompensa_hoca "
                    "FROM historical_tasks LIMIT 3"
                )
                rows = cur.fetchall()
        conn.close()
        return json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("DB error, usando mock: %s", type(e).__name__)
        return json.dumps(MOCK_HISTORICO[:3], ensure_ascii=False, indent=2)

def llamar_gemini(prompt: str) -> dict:
    if not API_KEY:
        raise ValueError("GEMINI_API_KEY no configurada")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent"
    resp = requests.post(
        url,
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}
        },
        headers={"Content-Type": "application/json", "x-goog-api-key": API_KEY},
        timeout=30
    )
    resp.raise_for_status()
    data = json.loads(resp.content.decode("utf-8"))
    return json.loads(data["candidates"][0]["content"]["parts"][0]["text"])

def construir_prompt(tarea: TareaRequest, contexto: str) -> str:
    modo = "CALCULATE" if tarea.recompensa_esperada is None else "VALIDATE"
    instruccion = (
        "The user did NOT specify a reward. Calculate the fair HOCA amount based on historical data."
        if modo == "CALCULATE"
        else f"The user expects {tarea.recompensa_esperada} HOCA. Evaluate if this is fair."
    )
    return f"""You are the Tenzo Agent of HoFi Protocol — an AI oracle for care economy justice.
MODE: {modo}
{instruccion}

FIRST — verify this is a legitimate completed care task.
Set "aprobada": false immediately if the input:
- Is a personal introduction or greeting ("I am Luna", "My name is...", "Hello")
- Contains no description of a real action performed (no verbs of work or care)
- Is nonsense, a question, or clearly unrelated to community care work
- Has no plausible time reference or activity for the stated duration

THEN — if it IS a valid task, evaluate and calculate reward based on historical data.

Return ONLY a valid JSON object (no markdown, no extra text):
{{
  "aprobada": true,
  "recompensa_hoca": 160.0,
  "clasificacion": ["cuidado", "comunitaria"],
  "razonamiento": "Brief explanation in Spanish (max 2 sentences)",
  "alerta": null
}}

Valid classifications: "cuidado" (care work), "regenerativa" (ecological), "comunitaria" (community benefit)

TASK: {tarea.titulo} | {tarea.categoria} | {tarea.duracion_horas}h | {tarea.holon_id}
HISTORICAL REFERENCE: {contexto}""".strip()

# ── Endpoints ───────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return JSONResponse(content={
        "status": "ok",
        "version": "0.9.0",
        "db_mock": DB_MOCK,
        "model": MODEL_NAME,
        "on_chain": ON_CHAIN,
        "contracts": {
            "hoca_token":    "0x2a6339b63ec0344619923Dbf8f8B27cC5c9b40dc",
            "holon_sbt":     "0x977E4eac99001aD8fe02D8d7f31E42E3d0Ffb036",
            "task_registry": "0xd9B253E6E1b494a7f2030f9961101fC99d3fD038",
            "network":       "Ethereum Sepolia",
        },
    }, media_type="application/json; charset=utf-8")


@app.post("/auth/token", response_model=TokenResponse)
@limiter.limit("5/minute")
def obtener_token(request: Request, login: LoginRequest):
    logger.info("Auth | intento para username='%s'", login.username[:20])
    username_ok  = login.username.strip() == ADMIN_USERNAME
    password_ok  = verificar_password(login.password, ADMIN_PASSWORD_HASH)
    if not username_ok or not password_ok:
        logger.warning("Auth | FALLIDO username_ok=%s password_ok=%s", username_ok, password_ok)
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"}
        )
    token = crear_token(login.username.strip())
    logger.info("Auth | OK — token emitido para '%s'", login.username.strip())
    return TokenResponse(access_token=token, token_type="bearer", expires_in=JWT_EXPIRE_MINUTES * 60)


@app.post("/evaluar")
@limiter.limit("10/minute")
def evaluar_tarea(request: Request, tarea: TareaRequest, username: str = Depends(verificar_token)):
    if not API_KEY:
        return JSONResponse(status_code=400,
            content={"error": "Service not configured", "code": "CONFIG_ERROR"})

    modo = "calcular" if tarea.recompensa_esperada is None else "validar"
    logger.info("Evaluar | user=%s tarea='%s' cat=%s modo=%s",
                username, tarea.titulo, tarea.categoria, modo)

    try:
        contexto  = obtener_contexto_historico(tarea.categoria)
        resultado = llamar_gemini(construir_prompt(tarea, contexto))
    except requests.exceptions.Timeout:
        return JSONResponse(status_code=503,
            content={"error": "Service temporarily unavailable", "code": "TIMEOUT"})
    except Exception as e:
        logger.error("Evaluar | error: %s — %s", type(e).__name__, str(e))
        return JSONResponse(status_code=500,
            content={"error": "Internal server error", "code": "INTERNAL_ERROR"})

    response_data = {
        "modo":            modo,
        "aprobada":        resultado.get("aprobada", False),
        "recompensa_hoca": float(resultado.get("recompensa_hoca", 0)),
        "clasificacion":   resultado.get("clasificacion", []),
        "razonamiento":    resultado.get("razonamiento", ""),
        "alerta":          resultado.get("alerta"),
        "on_chain":        None,
    }

    if ON_CHAIN and resultado.get("aprobada") and tarea.executor_address:
        try:
            from onchain_bridge import get_bridge
            bridge = get_bridge()
            if bridge:
                tx = bridge.approve_task_onchain(
                    executor=tarea.executor_address,
                    holon_id=tarea.holon_id or "holon-demo",
                    categoria=tarea.categoria,
                    duracion_horas=tarea.duracion_horas,
                    recompensa_hoca=float(resultado.get("recompensa_hoca", 0)),
                    razonamiento=resultado.get("razonamiento", ""),
                )
                response_data["on_chain"] = tx
                logger.info("Evaluar | minted on-chain: %s", tx.get("tx_hash"))
        except Exception as e:
            logger.error("Evaluar | bridge error: %s", str(e))
            response_data["on_chain"] = {"error": "Bridge unavailable", "detail": str(e)}

    return JSONResponse(content=response_data, media_type="application/json; charset=utf-8")


@app.post("/member/register")
@limiter.limit("10/minute")
def register_member(request: Request, member: MemberRequest, username: str = Depends(verificar_token)):
    if not ON_CHAIN:
        return JSONResponse(content={
            "status": "off_chain_only",
            "message": "ON_CHAIN=false — SBT registration requires on-chain mode",
            "member": member.model_dump(),
        })
    try:
        from onchain_bridge import get_bridge
        bridge = get_bridge()
        if not bridge:
            raise HTTPException(status_code=503, detail="On-chain bridge unavailable")
        tx_hash = bridge.issue_sbt(member.address, member.holon_id, member.role)
        return JSONResponse(content={
            "status": "issued",
            "tx_hash": tx_hash,
            "explorer": f"https://sepolia.etherscan.io/tx/{tx_hash}",
            "member": member.model_dump(),
        })
    except Exception as e:
        logger.error("Register | SBT error: %s", str(e))
        raise HTTPException(status_code=500, detail="SBT issuance failed")


@app.get("/protocol/stats")
def protocol_stats(username: str = Depends(verificar_token)):
    if not ON_CHAIN:
        return JSONResponse(content={
            "on_chain": False,
            "message": "Enable ON_CHAIN=true to see live blockchain stats",
            "contracts": {
                "task_registry": "0xd9B253E6E1b494a7f2030f9961101fC99d3fD038",
                "network": "Ethereum Sepolia",
            }
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
    """Endpoint temporal para verificar qué valores tiene el servidor en runtime."""
    return JSONResponse(content={
        "version":          "0.9.0",
        "admin_username":   ADMIN_USERNAME,
        "hash_len":         len(ADMIN_PASSWORD_HASH),
        "hash_prefix":      ADMIN_PASSWORD_HASH[:7] if ADMIN_PASSWORD_HASH else "",
        "demo_key_set":     bool(DEMO_API_KEY),
        "demo_key_len":     len(DEMO_API_KEY),
        "jwt_secret_set":   bool(JWT_SECRET_KEY),
        "on_chain":         ON_CHAIN,
        "db_mock":          DB_MOCK,
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("tenzo_agent:app", host="0.0.0.0", port=PORT, reload=False)
