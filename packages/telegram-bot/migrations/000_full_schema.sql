-- ═══════════════════════════════════════════════════════════════════════════
-- HoFi Protocol — Schema completo consolidado para fresh deploy
-- Fecha: 2026-05-14
--
-- Equivale a: init_db() del bot + migraciones 002 + 003 + 004 + 005.
-- Aplicable contra una DB vacía en un solo paso. Idempotente (IF NOT EXISTS
-- en todas las creaciones, ON CONFLICT en los seeds).
--
-- Aplicación en Neon:
--   psql 'postgresql://<user>:<pass>@<endpoint>.neon.tech/hofi?sslmode=require'
--   \i 000_full_schema.sql
--
-- Verificaciones al final del archivo (\dt + counts esperados).
-- ═══════════════════════════════════════════════════════════════════════════

BEGIN;

-- ─── voice_profiles ─────────────────────────────────────────────────────────
-- Embeddings de voz indexados por person_id canónico (lower ASCII, sin tildes).
CREATE TABLE IF NOT EXISTS voice_profiles (
    id                SERIAL       PRIMARY KEY,
    telegram_user_id  BIGINT       NOT NULL,
    member_name       VARCHAR(100) NOT NULL,
    holon_id          VARCHAR(50)  NOT NULL,
    voice_embedding   FLOAT[]      NOT NULL,
    created_at        TIMESTAMP    DEFAULT NOW(),
    person_id         VARCHAR(100)
);

CREATE UNIQUE INDEX IF NOT EXISTS voice_profiles_person_id_key
    ON voice_profiles (person_id)
    WHERE person_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_voice_profiles_telegram
    ON voice_profiles (telegram_user_id);

-- ─── member_identities ──────────────────────────────────────────────────────
-- Bridge multi-canal (telegram_id, email, X handle, etc.) → person_id canónico.
-- UNIQUE (identity_type, identity_value, person_id) permite que UN mismo
-- telegram_id mapee a varios person_ids (familia compartiendo teléfono).
-- La voz desambigua en runtime. Migración 002 ya está incorporada.
CREATE TABLE IF NOT EXISTS member_identities (
    id              SERIAL       PRIMARY KEY,
    person_id       VARCHAR(100) NOT NULL,
    holon_id        VARCHAR(50)  NOT NULL,
    identity_type   VARCHAR(30)  NOT NULL,
    identity_value  VARCHAR(200) NOT NULL,
    display_name    VARCHAR(100),
    created_at      TIMESTAMP    DEFAULT NOW(),
    CONSTRAINT member_identities_bridge_uk
        UNIQUE (identity_type, identity_value, person_id)
);

CREATE INDEX IF NOT EXISTS idx_member_identities_lookup
    ON member_identities (identity_type, identity_value);

-- ─── task_sessions ──────────────────────────────────────────────────────────
-- Estado conversacional del bot (state machine de la carga de tareas).
CREATE TABLE IF NOT EXISTS task_sessions (
    id                SERIAL       PRIMARY KEY,
    telegram_user_id  BIGINT       NOT NULL,
    member_name       VARCHAR(100),
    holon_id          VARCHAR(50),
    state             VARCHAR(50)  DEFAULT 'idle',
    context           JSONB        DEFAULT '{}',
    updated_at        TIMESTAMP    DEFAULT NOW()
);

-- ─── tasks ──────────────────────────────────────────────────────────────────
-- Tareas de cuidado evaluadas por Tenzo. Columnas reconstruidas a partir del
-- INSERT en tenzo_agent.py::_guardar_tarea_y_verificar_sbt + columnas que
-- agrega migración 004 (approval_state, anti-dup constraint).
--
-- Convención de aprobada / approval_state:
--   aprobada = TRUE  ∧ approval_state='auto_approved'      → Tenzo aprobó directo
--   aprobada IS NULL ∧ approval_state='pending_community'  → escalada a votos
--   aprobada = FALSE ∧ approval_state='community_rejected' → rechazada
--                      approval_state='community_approved' → quorum positivo
--                      approval_state='minted'             → HoCa on-chain
CREATE TABLE IF NOT EXISTS tasks (
    id                  SERIAL       PRIMARY KEY,
    persona_id          VARCHAR(100) NOT NULL,
    holon_id            VARCHAR(50)  NOT NULL,
    descripcion         TEXT         NOT NULL,
    categoria           VARCHAR(100),
    recompensa_hoca     NUMERIC(12, 2) DEFAULT 0,
    aprobada            BOOLEAN,                    -- TRUE | NULL | FALSE (ver convención)
    horas               NUMERIC(6, 2)  DEFAULT 0,
    tenzo_score         NUMERIC(4, 3)  DEFAULT 0,   -- confianza 0..1
    carbono_kg          NUMERIC(8, 3)  DEFAULT 0,
    gnh_score           NUMERIC(4, 3)  DEFAULT 0,
    gnh_generosidad     NUMERIC(4, 3)  DEFAULT 0,
    gnh_apoyo_social    NUMERIC(4, 3)  DEFAULT 0,
    gnh_calidad_vida    NUMERIC(4, 3)  DEFAULT 0,
    sbt_inscripta       BOOLEAN        NOT NULL DEFAULT FALSE,
    approval_state      VARCHAR(32)    NOT NULL DEFAULT 'auto_approved',
    -- TIMESTAMP (sin tz) y no TIMESTAMPTZ: el índice parcial idx_tasks_dedup usa
    -- (created_at::date), y ese cast solo es IMMUTABLE sobre timestamp sin tz.
    -- Coincide con el tipo que tenía la tabla original en Cloud SQL.
    created_at          TIMESTAMP      NOT NULL DEFAULT NOW(),
    CONSTRAINT tasks_approval_state_check CHECK (approval_state IN (
        'pending_community',
        'community_approved',
        'community_rejected',
        'auto_approved',
        'minted'
    ))
);

CREATE INDEX IF NOT EXISTS idx_tasks_persona
    ON tasks (persona_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_tasks_holon
    ON tasks (holon_id, created_at DESC);

-- Índice parcial: queries de "tareas pendientes en este holón" (de migración 004)
CREATE INDEX IF NOT EXISTS idx_tasks_pending
    ON tasks (holon_id, approval_state)
    WHERE approval_state = 'pending_community';

-- Red anti-duplicación: misma persona no puede registrar misma descripción
-- en el mismo holón el mismo día MIENTRAS la primera siga viva (de migración 004)
CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_dedup
    ON tasks (persona_id, holon_id, descripcion, (created_at::date))
    WHERE approval_state IN ('pending_community', 'auto_approved');

-- ─── sbt_pending ────────────────────────────────────────────────────────────
-- Acumulador por (persona, holón) para flush diferido al SBT on-chain.
-- FK a tasks(id): borrar tareas requiere limpiar referencias acá primero.
CREATE TABLE IF NOT EXISTS sbt_pending (
    persona_id      VARCHAR(100)   NOT NULL,
    holon_id        VARCHAR(50)    NOT NULL,
    horas_acum      NUMERIC(8, 2)  NOT NULL DEFAULT 0,
    hoca_acum       NUMERIC(12, 2) NOT NULL DEFAULT 0,
    carbono_acum    NUMERIC(10, 3) NOT NULL DEFAULT 0,
    gnh_acum        NUMERIC(8, 3)  NOT NULL DEFAULT 0,
    tasks_acum      INTEGER        NOT NULL DEFAULT 0,
    ultima_tarea_id INTEGER        REFERENCES tasks(id) ON DELETE SET NULL,
    updated_at      TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    PRIMARY KEY (persona_id, holon_id)
);

-- ─── task_catalog ───────────────────────────────────────────────────────────
-- Catálogo de tareas aceptadas por holón con sus rangos de HoCa y duración.
-- Consultado por tenzo_agent.py::obtener_catalogo().
CREATE TABLE IF NOT EXISTS task_catalog (
    id                SERIAL        PRIMARY KEY,
    holon_id          VARCHAR(50)   NOT NULL,
    nombre            VARCHAR(200)  NOT NULL,
    categoria         VARCHAR(100)  NOT NULL,
    hoca_min          INTEGER       NOT NULL CHECK (hoca_min >= 0),
    hoca_max          INTEGER       NOT NULL CHECK (hoca_max >= hoca_min),
    duracion_max_min  INTEGER       NOT NULL CHECK (duracion_max_min > 0),
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    CONSTRAINT task_catalog_holon_nombre_uk UNIQUE (holon_id, nombre)
);

CREATE INDEX IF NOT EXISTS idx_task_catalog_holon
    ON task_catalog (holon_id);

-- ─── holon_rules ────────────────────────────────────────────────────────────
-- Config por holón (quorum requerido, spirit). Migración 004.
CREATE TABLE IF NOT EXISTS holon_rules (
    holon_id            VARCHAR(100) PRIMARY KEY,
    required_approvals  INT          NOT NULL DEFAULT 2 CHECK (required_approvals > 0),
    spirit              TEXT,
    updated_at          TIMESTAMPTZ  DEFAULT NOW()
);

-- ─── task_approvals ─────────────────────────────────────────────────────────
-- Bitácora de votos del community approval. Migración 004.
CREATE TABLE IF NOT EXISTS task_approvals (
    id                BIGSERIAL    PRIMARY KEY,
    task_id           INTEGER      NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    voter_persona_id  VARCHAR(100) NOT NULL,
    voter_holon_id    VARCHAR(100) NOT NULL,
    vote              VARCHAR(16)  NOT NULL CHECK (vote IN ('approve', 'reject')),
    voted_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT task_approvals_voter_uk UNIQUE (task_id, voter_persona_id)
);

CREATE INDEX IF NOT EXISTS idx_task_approvals_voter
    ON task_approvals (voter_holon_id, voter_persona_id);

-- ─── users ──────────────────────────────────────────────────────────────────
-- Credenciales email/password (migración 005). person_id UNIQUE = bridge 1:1
-- con voice_profiles.person_id → cuenta unificada voz + email.
CREATE TABLE IF NOT EXISTS users (
    id              BIGSERIAL    PRIMARY KEY,
    email           VARCHAR(255) NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    member_name     VARCHAR(100) NOT NULL,
    person_id       VARCHAR(100) NOT NULL,
    holon_id        VARCHAR(50)  NOT NULL,
    role            VARCHAR(20)  NOT NULL DEFAULT 'member'
                    CHECK (role IN ('member', 'guardian')),
    email_verified  BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_login_at   TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_uk
    ON users (LOWER(email));

CREATE UNIQUE INDEX IF NOT EXISTS users_person_id_uk
    ON users (person_id);

CREATE INDEX IF NOT EXISTS idx_users_holon
    ON users (holon_id);

-- ═══════════════════════════════════════════════════════════════════════════
-- SEEDS — Configuración inicial mínima para que el sistema arranque funcional
-- ═══════════════════════════════════════════════════════════════════════════

-- 1) holon_rules: dos holones activos
INSERT INTO holon_rules (holon_id, required_approvals, spirit) VALUES
    ('familia-mourino', 2, 'Cuidado regenerativo entre familia y vecinos.'),
    ('archi-brazo',     3, 'Trabajo de cuidado profesional en red.')
ON CONFLICT (holon_id) DO NOTHING;

-- 2) task_catalog: el catálogo base mock que usa el Tenzo (12 entradas).
--    Coincide con MOCK_CATALOGO en tenzo_agent.py. Pueden agregarse más
--    desde el frontend admin a futuro.
INSERT INTO task_catalog (holon_id, nombre, categoria, hoca_min, hoca_max, duracion_max_min) VALUES
    ('familia-mourino', 'Poda de jardín',             'cuidado_ecologico',  40,  120, 240),
    ('familia-mourino', 'Cuidado de niños',           'cuidado_humano',     60,  150, 240),
    ('familia-mourino', 'Cocina comunitaria',         'cocina_comunitaria', 40,  100, 240),
    ('familia-mourino', 'Mantenimiento espacio',      'mantenimiento',      30,   90, 480),
    ('familia-mourino', 'Compostaje',                 'cuidado_ecologico',  20,   60, 120),
    ('familia-mourino', 'Cuidado de animales',        'cuidado_animal',     30,   80, 180),
    ('familia-mourino', 'Limpieza espacios comunes',  'mantenimiento',      25,   70, 180),
    ('familia-mourino', 'Lavado de platos',           'cocina_comunitaria', 10,   30,  45),
    ('familia-mourino', 'Riego y huerta',             'cuidado_ecologico',  20,   60, 120),
    ('familia-mourino', 'Taller educativo',           'educacion',          60,  160, 120),
    ('familia-mourino', 'Cuidado de personas mayores','cuidado_humano',     80,  180, 240),
    ('familia-mourino', 'Reparación y construcción',  'mantenimiento',      50,  150, 480)
ON CONFLICT (holon_id, nombre) DO NOTHING;

COMMIT;

-- ═══════════════════════════════════════════════════════════════════════════
-- VERIFICACIONES POST-APLICACIÓN
-- ═══════════════════════════════════════════════════════════════════════════
\dt

SELECT 'voice_profiles' AS tabla, COUNT(*) AS filas FROM voice_profiles
UNION ALL SELECT 'member_identities', COUNT(*) FROM member_identities
UNION ALL SELECT 'task_sessions',     COUNT(*) FROM task_sessions
UNION ALL SELECT 'tasks',             COUNT(*) FROM tasks
UNION ALL SELECT 'sbt_pending',       COUNT(*) FROM sbt_pending
UNION ALL SELECT 'task_catalog',      COUNT(*) FROM task_catalog
UNION ALL SELECT 'holon_rules',       COUNT(*) FROM holon_rules
UNION ALL SELECT 'task_approvals',    COUNT(*) FROM task_approvals
UNION ALL SELECT 'users',             COUNT(*) FROM users
ORDER BY tabla;

-- Esperado:
--   holon_rules:    2   (seeds)
--   task_catalog:  12   (seeds)
--   resto:          0   (data fresh)
