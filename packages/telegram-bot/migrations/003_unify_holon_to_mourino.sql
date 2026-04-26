-- ── Migración 003: Unificar holon_id a "familia-mourino" canónico ────────────
-- Fecha: 2026-04-26
--
-- CONTEXTO
-- Hasta hoy convivían dos variantes del mismo holón:
--   - "familia-valdes"   (legacy, pre-rebrand familia)
--   - "familia-mouriño"  (con tilde, escrito por bot post-registro de Pablo)
-- y queríamos defaultear todo el sistema a un único id canónico.
--
-- DECISIÓN
-- Canónico = "familia-mourino"  (lowercase ASCII puro, sin acento ni guión bajo).
-- Display  = "Familia Mouriño"  (se aplica en UI vía helper, no se persiste).
--
-- IMPACTO EN DB (snapshot 2026-04-26 14:00 UTC)
--   tasks:             14 filas en familia-valdes              → familia-mourino
--   member_identities:  2 en familia-valdes + 1 en mouriño     → familia-mourino
--   voice_profiles:     1 en familia-mouriño                   → familia-mourino
--   task_catalog:      22 filas en familia-valdes              → familia-mourino
--   sbt_pending:        — (sin filas hoy, pero default de schema futuro)
--   task_sessions:      — (sin filas hoy, pero default de schema futuro)
-- View v_reputacion_persona NO requiere migración (deriva de tablas base).
-- Total: 40 filas movidas.
--
-- POST-MIGRACIÓN: actualizar defaults en el código:
--   - packages/frontend/src/app/page.tsx (líneas 82, 90)
--   - packages/frontend/src/components/hofi/voice-connect-modal.tsx (línea 35)
--   - packages/frontend/src/lib/server/db.ts (función normalizeHolonId)
--   - packages/frontend/src/app/api/care/register/route.ts (default fallback)
-- ─────────────────────────────────────────────────────────────────────────────

BEGIN;

-- 1. tasks
UPDATE tasks
   SET holon_id = 'familia-mourino'
 WHERE holon_id IN ('familia-valdes', 'familia-mouriño');

-- 2. member_identities (bridge multi-identidad introducido en migración 002)
UPDATE member_identities
   SET holon_id = 'familia-mourino'
 WHERE holon_id IN ('familia-valdes', 'familia-mouriño');

-- 3. voice_profiles
UPDATE voice_profiles
   SET holon_id = 'familia-mourino'
 WHERE holon_id IN ('familia-valdes', 'familia-mouriño');

-- 4. task_catalog (catálogo de tareas reconocidas por el holón)
UPDATE task_catalog
   SET holon_id = 'familia-mourino'
 WHERE holon_id IN ('familia-valdes', 'familia-mouriño');

-- 5. sbt_pending (tareas pendientes de minteo on-chain)
UPDATE sbt_pending
   SET holon_id = 'familia-mourino'
 WHERE holon_id IN ('familia-valdes', 'familia-mouriño');

-- 6. task_sessions (sesiones de captura de voz)
UPDATE task_sessions
   SET holon_id = 'familia-mourino'
 WHERE holon_id IN ('familia-valdes', 'familia-mouriño');

-- ── Verificación post-update ────────────────────────────────────────────────
-- Después del COMMIT, las queries deben mostrar SOLO familia-mourino.
SELECT 'tasks'             AS tabla, holon_id, COUNT(*) AS rows FROM tasks             GROUP BY holon_id
UNION ALL
SELECT 'member_identities' AS tabla, holon_id, COUNT(*) AS rows FROM member_identities GROUP BY holon_id
UNION ALL
SELECT 'voice_profiles'    AS tabla, holon_id, COUNT(*) AS rows FROM voice_profiles    GROUP BY holon_id
UNION ALL
SELECT 'task_catalog'      AS tabla, holon_id, COUNT(*) AS rows FROM task_catalog      GROUP BY holon_id
UNION ALL
SELECT 'sbt_pending'       AS tabla, holon_id, COUNT(*) AS rows FROM sbt_pending       GROUP BY holon_id
UNION ALL
SELECT 'task_sessions'     AS tabla, holon_id, COUNT(*) AS rows FROM task_sessions     GROUP BY holon_id
ORDER BY tabla, holon_id;

COMMIT;
