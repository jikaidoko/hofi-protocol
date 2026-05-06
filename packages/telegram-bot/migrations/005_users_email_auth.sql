-- HoFi Protocol — Migración 005: tabla `users` para autenticación email/password
-- Fecha: 2026-05-06
--
-- CONTEXTO
-- Hasta hoy el frontend tenía un /api/auth/login "permisivo": aceptaba cualquier
-- email + password, derivaba el member_name del prefijo del email y firmaba la
-- cookie de sesión sin validar contra ninguna tabla. La autenticación real solo
-- existía por voz (voice_profiles + voice-auth-service).
--
-- Con esta migración creamos la tabla `users` como fuente de verdad para
-- credenciales email/password. Cada usuario tiene un `person_id` canónico
-- (mismo schema que voice_profiles.person_id, lower ASCII puro) — cuando un
-- usuario también tenga perfil de voz, ambas tablas comparten ese person_id
-- y la cuenta queda "unificada": el feed personal, el balance y las tareas
-- son las mismas independientemente del canal de login.
--
-- DECISIÓN
-- - users.person_id es UNIQUE y es la clave de unificación con voice_profiles.
-- - users.email es UNIQUE case-insensitive (índice sobre LOWER(email)).
-- - users.password_hash es bcrypt (mismo formato que ADMIN_PASSWORD_HASH).
-- - role ∈ {'member', 'guardian'} — mismo enum que UserRole en el frontend.
-- - email_verified arranca FALSE; verification flow va en un PR posterior.
--
-- IDEMPOTENCIA
-- IF NOT EXISTS en CREATE TABLE y CREATE INDEX → re-aplicable sin romper.
-- Si la tabla ya existe con otro schema, abortar y rehacer manualmente.
--
-- APLICACIÓN
--   gcloud sql connect hofi-db --user=hofi_user --database=hofi
--   \i 005_users_email_auth.sql
--
-- ROLLBACK (al final del archivo, comentado).
-- ─────────────────────────────────────────────────────────────────────────────

BEGIN;

-- 1) Tabla users
CREATE TABLE IF NOT EXISTS users (
    id              BIGSERIAL    PRIMARY KEY,
    email           VARCHAR(255) NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,        -- bcrypt ($2b$...)
    member_name     VARCHAR(100) NOT NULL,        -- display name legible
    person_id       VARCHAR(100) NOT NULL,        -- canónico (lower ASCII)
    holon_id        VARCHAR(50)  NOT NULL,
    role            VARCHAR(20)  NOT NULL DEFAULT 'member'
                    CHECK (role IN ('member', 'guardian')),
    email_verified  BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_login_at   TIMESTAMPTZ
);

-- 2) UNIQUE case-insensitive sobre email
--    pg no permite UNIQUE directo sobre LOWER(email); usamos índice único
--    funcional. Toda inserción/lookup debe pasar por LOWER(email).
CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_uk
    ON users (LOWER(email));

-- 3) UNIQUE sobre person_id
--    Permite que voice_profiles.person_id y users.person_id coincidan 1:1.
--    Si existe un voice_profile previo con ese person_id, el INSERT en users
--    queda asociado automáticamente (JOIN por person_id).
CREATE UNIQUE INDEX IF NOT EXISTS users_person_id_uk
    ON users (person_id);

-- 4) Lookup por holón (para listar miembros, calcular quorum, etc.)
CREATE INDEX IF NOT EXISTS idx_users_holon
    ON users (holon_id);

-- 5) Trigger opcional: actualizar last_login_at desde la app, no desde DB.
--    Lo manejamos en el endpoint /auth/email/login del Tenzo.

COMMIT;

-- ── Verificación post-migración ─────────────────────────────────────────────
\d users
SELECT COUNT(*) AS users_existentes FROM users;
-- (debería ser 0 después de aplicar; las cuentas las crean los registros)

-- ── ROLLBACK (descomentar si hace falta revertir) ───────────────────────────
-- BEGIN;
-- DROP INDEX IF EXISTS idx_users_holon;
-- DROP INDEX IF EXISTS users_person_id_uk;
-- DROP INDEX IF EXISTS users_email_lower_uk;
-- DROP TABLE IF EXISTS users;
-- COMMIT;
