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

import voice_auth  # canonical_person_id — voice_auth no importa db (sin ciclo)

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
    # connect_timeout aplica en ambos casos para evitar bloqueo indefinido al arrancar
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
        person_id         VARCHAR(100)
    );

    CREATE UNIQUE INDEX IF NOT EXISTS voice_profiles_person_id_key
        ON voice_profiles (person_id) WHERE person_id IS NOT NULL;

    CREATE INDEX IF NOT EXISTS idx_voice_profiles_telegram
        ON voice_profiles (telegram_user_id);

    CREATE TABLE IF NOT EXISTS member_identities (
        id              SERIAL PRIMARY KEY,
        person_id       VARCHAR(100) NOT NULL,
        holon_id        VARCHAR(50)  NOT NULL,
        identity_type   VARCHAR(30)  NOT NULL,
        identity_value  VARCHAR(200) NOT NULL,
        display_name    VARCHAR(100),
        created_at      TIMESTAMP DEFAULT NOW(),
        UNIQUE(identity_type, identity_value)
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
        logger.error("DB | error al inicializar tablas: %s — continuando en modo degradado", str(e))
        # No relanzar: el bot puede arrancar sin DB y usar GCS como fallback


# ── voice_profiles ────────────────────────────────────────────────────────────

def guardar_perfil(telegram_user_id: int, member_name: str, holon_id: str, embedding):
    """
    Guarda o actualiza el perfil de voz.

    En mock: clave compuesta 'user_id_nombre' para soportar familia compartida.

    En PostgreSQL (identity bridge):
      1) Intenta registrar la identidad telegram_id -> person_id en member_identities.
         El member_name actúa como person_id canónico. Si el telegram_id ya estaba
         asociado a otro person_id (ej: otro miembro de la familia ya usó este
         teléfono), se respeta el mapping existente — la voz se guarda de todas
         formas bajo el member_name que se dijo en el audio.
      2) Upsert voice_profiles por person_id (UNIQUE parcial WHERE person_id IS NOT NULL).

    La identidad REAL es la voz (embedding) — el telegram_id es solo el canal.
    Una persona tiene un único embedding válido, indexado por person_id.
    """
    # Convertir ndarray → list[float] para JSON / PostgreSQL
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

    # person_id canónico = nombre normalizado (lower, sin tildes/ñ, sin puntuación).
    # Así "¡Doco!" → "doco", "Mouriño" → "mourino", "Luna Ramirez" → "luna".
    # El member_name se preserva legible (display); el person_id es la clave
    # estable de identity bridge — inmune a lo que Whisper agregue al ASR.
    # Fallback: si la normalización queda vacía, usar el member_name como está
    # (nunca guardar person_id vacío porque el UNIQUE parcial lo rechazaría
    # y rompería el upsert).
    person_id = voice_auth.canonical_person_id(member_name) or member_name

    sql_identity = """
        INSERT INTO member_identities
            (person_id, holon_id, identity_type, identity_value, display_name)
        VALUES (%s, %s, 'telegram_id', %s, %s)
        ON CONFLICT (identity_type, identity_value) DO NOTHING
    """
    sql_voice = """
        INSERT INTO voice_profiles
            (person_id, telegram_user_id, member_name, holon_id, voice_embedding)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (person_id) WHERE person_id IS NOT NULL
        DO UPDATE SET
            telegram_user_id = EXCLUDED.telegram_user_id,
            member_name      = EXCLUDED.member_name,
            holon_id         = EXCLUDED.holon_id,
            voice_embedding  = EXCLUDED.voice_embedding,
            created_at       = NOW()
    """

    conn = None
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            # 1) Intentar registrar la identidad telegram_id -> person_id.
            #    Si el telegram_id ya estaba asociado a otro person_id, no lo
            #    pisamos: la voz sigue guardándose bajo el member_name dicho.
            cur.execute(
                sql_identity,
                (person_id, holon_id, str(telegram_user_id), member_name),
            )

            # 2) Upsert voice_profiles por person_id.
            cur.execute(
                sql_voice,
                (person_id, telegram_user_id, member_name, holon_id, embedding_lista),
            )
        conn.commit()
        logger.info(
            "DB | perfil guardado: person_id=%s name=%s holon=%s tg=%s",
            person_id, member_name, holon_id, telegram_user_id,
        )
    except Exception as e:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        logger.error("DB | error guardando perfil: %s", str(e))
        raise
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


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

# ── Identity Bridge ───────────────────────────────────────────────────────────

def resolve_person_id(telegram_user_id: int) -> tuple[str, str]:
    """
    Resuelve el telegram_user_id al person_id canonico y holon_id
    usando member_identities. Fallback: (str(id), 'familia-valdes').
    """
    if DB_MOCK:
        prefix = f"{telegram_user_id}_"
        for k, v in _MOCK_PROFILES.items():
            if k.startswith(prefix):
                return v["member_name"], v["holon_id"]
        return str(telegram_user_id), "familia-valdes"

    sql = """
        SELECT person_id, holon_id FROM member_identities
        WHERE identity_type = 'telegram_id' AND identity_value = %s LIMIT 1
    """
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(sql, (str(telegram_user_id),))
            row = cur.fetchone()
        conn.close()
        if row:
            return row[0], row[1]
    except Exception as e:
        logger.error("DB | error en resolve_person_id: %s", str(e))
    return str(telegram_user_id), "familia-valdes"


def get_balance_y_metricas(person_id: str, holon_id: str) -> dict:
    """Balance de HoCa y metricas de impacto del miembro desde tasks."""
    if DB_MOCK:
        return {"balance": 0, "co2_total": 0.0, "gnh_score": 0.0, "horas_total": 0.0, "tareas": 0}

    sql = """
        SELECT
            COALESCE(SUM(recompensa_hoca), 0)                  AS balance,
            COALESCE(SUM(COALESCE(carbono_kg, recompensa_hoca / 40.0)), 0) AS co2_total,
            COALESCE(AVG(COALESCE(gnh_score, tenzo_score)), 0) AS gnh_score,
            COALESCE(SUM(COALESCE(horas, recompensa_hoca / 80.0)), 0)      AS horas_total,
            COUNT(*)                                           AS tareas
        FROM tasks WHERE holon_id = %s AND persona_id = %s AND aprobada = true
    """
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(sql, (holon_id, person_id))
            row = cur.fetchone()
        conn.close()
        if row:
            return {"balance": round(float(row[0])), "co2_total": round(float(row[1]),1),
                    "gnh_score": round(float(row[2]),2), "horas_total": round(float(row[3]),1),
                    "tareas": int(row[4])}
    except Exception as e:
        logger.error("DB | error en get_balance_y_metricas: %s", str(e))
    return {"balance": 0, "co2_total": 0.0, "gnh_score": 0.0, "horas_total": 0.0, "tareas": 0}


def register_identity(person_id: str, holon_id: str,
                      identity_type: str, identity_value: str,
                      display_name: str = None) -> bool:
    """Registra una identidad nueva en member_identities."""
    if DB_MOCK:
        return True
    sql = """
        INSERT INTO member_identities
            (person_id, holon_id, identity_type, identity_value, display_name)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (identity_type, identity_value) DO UPDATE
            SET person_id = EXCLUDED.person_id, holon_id = EXCLUDED.holon_id,
                display_name = EXCLUDED.display_name
    """
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(sql, (person_id, holon_id, identity_type,
                              identity_value, display_name or person_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error("DB | error en register_identity: %s", str(e))
        return False
