"""
HoFi — Capa de base de datos para el Bot de Telegram
Maneja voice_profiles y sesiones de usuario.

NOTA IMPORTANTE sobre el mock de familia compartida:
  Toda la familia Valdés usa el mismo telegram_user_id (2012212775).
  El mock NO puede clave por telegram_user_id solo, porque overwritería
  el perfil anterior. Se usa clave compuesta: f"{user_id}_{nombre_norm}"
  Ejemplo: "2012212775_doco", "2012212775_luna", "2012212775_gaya"
"""

import os
import logging
import json
from typing import Optional

logger = logging.getLogger("HoFiDB")

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "hofi_db")
DB_USER = os.getenv("DB_USER", "tenzo_user")
DB_PASS = os.getenv("DB_PASS", "")
DB_MOCK = os.getenv("DB_MOCK", "true").lower() == "true"

# ── Persistencia del mock ─────────────────────────────────────────────────────
_MOCK_DB_FILE  = os.path.join(os.path.dirname(__file__), "mock_profiles.json")
_GCS_BUCKET    = os.getenv("GCS_BUCKET", "")
_GCS_BLOB_NAME = os.getenv("GCS_BLOB_NAME", "mock_profiles.json")

# Clave compuesta: "telegram_user_id_nombre_normalizado"
# Permite múltiples perfiles por cuenta de Telegram (familia compartida)
_MOCK_PROFILES: dict[str, dict] = {}


def _mock_key(telegram_user_id: int, member_name: str) -> str:
    """Genera clave compuesta 'userid_nombre' para el mock."""
    nombre_norm = member_name.lower().replace(" ", "_")
    return f"{telegram_user_id}_{nombre_norm}"


def _gcs_descargar():
    try:
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(_GCS_BUCKET)
        blob   = bucket.blob(_GCS_BLOB_NAME)
        if blob.exists():
            blob.download_to_filename(_MOCK_DB_FILE)
            logger.info("DB mock | descargado desde gs://%s/%s", _GCS_BUCKET, _GCS_BLOB_NAME)
        else:
            logger.info("DB mock | blob GCS no existe aún, empezando vacío")
    except Exception as e:
        logger.warning("DB mock | no se pudo descargar desde GCS: %s", str(e))


def _gcs_subir():
    try:
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(_GCS_BUCKET)
        blob   = bucket.blob(_GCS_BLOB_NAME)
        blob.upload_from_filename(_MOCK_DB_FILE, content_type="application/json")
        logger.info("DB mock | subido a gs://%s/%s", _GCS_BUCKET, _GCS_BLOB_NAME)
    except Exception as e:
        logger.warning("DB mock | no se pudo subir a GCS: %s", str(e))


def _mock_cargar():
    """Carga perfiles desde JSON con migración de claves viejas (int → compuesta)."""
    global _MOCK_PROFILES
    if _GCS_BUCKET:
        _gcs_descargar()
    if not os.path.exists(_MOCK_DB_FILE):
        _MOCK_PROFILES = {}
        return
    try:
        with open(_MOCK_DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        _MOCK_PROFILES = {}
        for k, v in data.items():
            # Migración automática: claves int (formato viejo, 1 perfil por user)
            # → clave compuesta (formato nuevo, múltiples por user)
            try:
                int(k)  # lanza ValueError si ya es compuesta ("2012212775_doco")
                new_key = _mock_key(v["telegram_user_id"], v["member_name"])
                _MOCK_PROFILES[new_key] = v
                logger.info("DB mock | migrado perfil %s → clave '%s'", v["member_name"], new_key)
            except ValueError:
                _MOCK_PROFILES[k] = v  # ya tiene formato compuesto

        logger.info("DB mock | cargados %d perfiles", len(_MOCK_PROFILES))
    except Exception as e:
        logger.error("DB mock | error cargando perfiles: %s", str(e))
        _MOCK_PROFILES = {}


def _mock_guardar():
    """Persiste todos los perfiles en JSON (y GCS si está configurado)."""
    try:
        with open(_MOCK_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(_MOCK_PROFILES, f, ensure_ascii=False, indent=2)
        if _GCS_BUCKET:
            _gcs_subir()
    except Exception as e:
        logger.error("DB mock | error guardando perfiles: %s", str(e))


def _get_conn():
    import psycopg2
    # Cloud SQL (Cloud Run): socket Unix
    # Local: host TCP
    if DB_HOST.startswith("/"):
        return psycopg2.connect(
            host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASS
        )
    return psycopg2.connect(
        host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASS,
        connect_timeout=10
    )


def init_db():
    """Inicializa la DB: carga el mock o verifica conexión PostgreSQL."""
    if DB_MOCK:
        _mock_cargar()
        logger.info("DB | modo mock — perfiles en %s", _MOCK_DB_FILE)
        return

    sql = """
    CREATE TABLE IF NOT EXISTS voice_profiles (
        id                SERIAL PRIMARY KEY,
        telegram_user_id  BIGINT NOT NULL,
        member_name       VARCHAR(100) NOT NULL,
        holon_id          VARCHAR(50) NOT NULL,
        voice_embedding   FLOAT[] NOT NULL,
        created_at        TIMESTAMP DEFAULT NOW(),
        UNIQUE(telegram_user_id, member_name)
    );

    CREATE TABLE IF NOT EXISTS task_sessions (
        id                SERIAL PRIMARY KEY,
        telegram_user_id  BIGINT NOT NULL,
        member_name       VARCHAR(100),
        holon_id          VARCHAR(50),
        state             VARCHAR(50) DEFAULT 'idle',
        context           JSONB DEFAULT '{}',
        updated_at        TIMESTAMP DEFAULT NOW()
    );
    """
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        conn.close()
        logger.info("DB | tablas inicializadas OK")
    except Exception as e:
        logger.error("DB | error al inicializar tablas: %s", str(e))
        raise


# ── voice_profiles ────────────────────────────────────────────────────────────

def guardar_perfil(telegram_user_id: int, member_name: str, holon_id: str, embedding):
    """
    Guarda o actualiza el perfil de voz.
    En mock: clave compuesta 'user_id_nombre' para soportar familia compartida.
    En PostgreSQL: UNIQUE(telegram_user_id, member_name).
    """
    # Convertir ndarray → list[float] para JSON
    if hasattr(embedding, "tolist"):
        embedding_lista = embedding.tolist()
    else:
        embedding_lista = [float(x) for x in embedding]

    if DB_MOCK:
        key = _mock_key(telegram_user_id, member_name)
        _MOCK_PROFILES[key] = {
            "telegram_user_id": telegram_user_id,
            "member_name": member_name,
            "holon_id": holon_id,
            "voice_embedding": embedding_lista,
        }
        _mock_guardar()
        logger.info("DB mock | guardado: %s (%s) — clave '%s'", member_name, holon_id, key)
        logger.info("DB mock | total perfiles en memoria: %d", len(_MOCK_PROFILES))
        return

    sql = """
    INSERT INTO voice_profiles (telegram_user_id, member_name, holon_id, voice_embedding)
    VALUES (%s, %s, %s, %s)
    ON CONFLICT (telegram_user_id, member_name)
    DO UPDATE SET holon_id        = EXCLUDED.holon_id,
                  voice_embedding = EXCLUDED.voice_embedding,
                  created_at      = NOW()
    """
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(sql, (telegram_user_id, member_name, holon_id, embedding_lista))
        conn.commit()
        conn.close()
        logger.info("DB | perfil guardado: %s (%s)", member_name, holon_id)
    except Exception as e:
        logger.error("DB | error guardando perfil: %s", str(e))
        raise


def obtener_perfiles_holon(holon_id: str) -> list[dict]:
    """Obtiene todos los perfiles de un holón."""
    if DB_MOCK:
        return [p for p in _MOCK_PROFILES.values() if p["holon_id"] == holon_id]

    sql = """
    SELECT telegram_user_id, member_name, holon_id, voice_embedding
    FROM voice_profiles WHERE holon_id = %s
    """
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(sql, (holon_id,))
            rows = cur.fetchall()
        conn.close()
        return [
            {"telegram_user_id": r[0], "member_name": r[1],
             "holon_id": r[2], "voice_embedding": list(r[3])}
            for r in rows
        ]
    except Exception as e:
        logger.error("DB | error obteniendo perfiles de holón: %s", str(e))
        return []


def obtener_todos_perfiles() -> list[dict]:
    """Obtiene todos los perfiles (para autenticación cross-holón)."""
    if DB_MOCK:
        perfiles = list(_MOCK_PROFILES.values())
        logger.info("DB mock | obtener_todos_perfiles: %d perfiles disponibles", len(perfiles))
        return perfiles

    sql = "SELECT telegram_user_id, member_name, holon_id, voice_embedding FROM voice_profiles"
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
        conn.close()
        return [
            {"telegram_user_id": r[0], "member_name": r[1],
             "holon_id": r[2], "voice_embedding": list(r[3])}
            for r in rows
        ]
    except Exception as e:
        logger.error("DB | error obteniendo todos los perfiles: %s", str(e))
        return []


def perfil_existe(telegram_user_id: int) -> bool:
    """Verifica si existe al menos un perfil para este telegram_user_id."""
    if DB_MOCK:
        prefix = f"{telegram_user_id}_"
        return any(k.startswith(prefix) for k in _MOCK_PROFILES)

    sql = "SELECT 1 FROM voice_profiles WHERE telegram_user_id = %s LIMIT 1"
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(sql, (telegram_user_id,))
            result = cur.fetchone()
        conn.close()
        return result is not None
    except Exception as e:
        logger.error("DB | error verificando perfil: %s", str(e))
        return False
