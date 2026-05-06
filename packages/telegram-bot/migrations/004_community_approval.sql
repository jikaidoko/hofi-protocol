-- ── Migración 004: Community Approval (PR #4) ──────────────────────────────
-- Fecha: 2026-05-06
--
-- CONTEXTO
-- Hasta ahora la columna `tasks.aprobada` codificaba tres estados implícitos:
--   - aprobada = true  → tarea aprobada por Tenzo (capa 2 Gemini), persistida
--                        por el Tenzo Agent (single source).
--   - aprobada = NULL  → tarea ambigua, escalada a humano. Persistida por el
--                        frontend con `aprobada=NULL` (pending review).
--   - aprobada = false → tarea rechazada (no debería persistirse, pero se
--                        contempla por compatibilidad histórica).
--
-- Con PR #19 (voice-register-modal) la UX ya distingue los tres veredictos.
-- Lo que falta — y resuelve esta migración — es darle al estado "pendiente"
-- un mecanismo de **aprobación comunitaria con quorum**, en vez de quedar
-- congelado esperando a un humano.
--
-- DECISIÓN
-- Se introduce una columna explícita `approval_state` (VARCHAR enum-like) y
-- dos tablas de soporte:
--
--   `holon_rules`        — config por holón: quorum requerido y spirit guía.
--                          Default familia-mourino = 2, archi-brazo = 3.
--   `task_approvals`     — bitácora de votos. UNIQUE (task_id, voter)
--                          previene doble-voto del mismo miembro.
--
-- Reglas de negocio enforced en código (no en DB porque dependen de joins):
--   - El submitter NO puede votar su propia tarea.
--   - Solo personas listadas en member_identities del mismo holon pueden votar.
--   - Cuando se alcanza quorum, approval_state pasa a 'community_approved'
--     y queda lista para `/tasks/{id}/activate-reward` (mintea HoCa on-chain).
--
-- IMPACTO EN DB (snapshot pre-migración)
--   tasks: ~20 filas — todas se backfillean según `aprobada`:
--     true  → 'auto_approved'         (Tenzo/Gemini directo)
--     NULL  → 'pending_community'     (escaladas vía PR #19)
--     false → 'community_rejected'    (legacy, no debería haber)
--   holon_rules: 2 filas seed (familia-mourino, archi-brazo).
--   task_approvals: 0 filas, schema listo.
--
-- ANTI-DUPLICACIÓN (red de seguridad a nivel DB)
-- Antes del PR #19 había doble persistencia frontend+Tenzo. PR #19 lo arregló
-- a nivel código pero no a nivel DB. Esta migración agrega un UNIQUE INDEX
-- parcial sobre (persona_id, holon_id, descripcion, created_at::date) que
-- evita que la misma persona registre la misma tarea dos veces el mismo día.
-- Solo aplica a estados activos (pending_community, auto_approved). Una tarea
-- rechazada no bloquea un re-intento posterior.
--
-- POST-MIGRACIÓN: actualizar código en orden:
--   1. Tenzo: pipeline_evaluacion guarda pending con approval_state.
--   2. Tenzo: nuevos endpoints GET /holons/{id}/tasks/pending,
--             GET /holons/{id}/rules,
--             POST /tasks/{id}/approve,
--             POST /tasks/{id}/activate-reward.
--   3. Frontend: dejar de persistir pending desde /api/care/voice y
--             /api/care/register (ahora lo hace el Tenzo).
--   4. Frontend: community-approval-modal.tsx reemplaza mocks por fetch real.
--
-- APLICACIÓN
--   gcloud sql connect hofi-db --user=hofi_user --database=hofi
--   \i 004_community_approval.sql
--
-- REVERSIÓN: ver `004_community_approval_down.sql` (separado).
-- ─────────────────────────────────────────────────────────────────────────────

BEGIN;

-- LOCK explícito para que ninguna escritura concurrente del Tenzo o del bot
-- vea estados inconsistentes durante el ALTER + backfill. Tabla pequeña (~20
-- filas), el lock libera en ms.
LOCK TABLE tasks IN ACCESS EXCLUSIVE MODE;

-- 1) tasks.approval_state (preserve-data)
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS approval_state VARCHAR(32);

UPDATE tasks
   SET approval_state = CASE
       WHEN aprobada = TRUE  THEN 'auto_approved'
       WHEN aprobada IS NULL THEN 'pending_community'
       WHEN aprobada = FALSE THEN 'community_rejected'
   END
 WHERE approval_state IS NULL;

-- Una vez backfilleado, lo dejamos NOT NULL con default sano para inserts
-- futuros del Tenzo cuando aprueba directamente (capa 2 Gemini).
ALTER TABLE tasks
    ALTER COLUMN approval_state SET DEFAULT 'auto_approved';
ALTER TABLE tasks
    ALTER COLUMN approval_state SET NOT NULL;

-- CHECK enum-like: previene typos a nivel DB. Estados válidos:
--   pending_community   — escalada, esperando votos del holón
--   community_approved  — alcanzó quorum, lista para mintear
--   community_rejected  — quorum negativo o rechazada explícitamente
--   auto_approved       — aprobada directo por Tenzo (Gemini score alto)
--   minted              — HoCa ya transferida on-chain (post activate-reward)
--
-- ALTER TABLE ADD CONSTRAINT no soporta IF NOT EXISTS hasta PG 16, así que
-- envolvemos en DO $$ para que la migración sea idempotente (poder re-correr
-- sin error si una corrida previa falló a la mitad).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM pg_constraint
         WHERE conname = 'tasks_approval_state_check'
           AND conrelid = 'tasks'::regclass
    ) THEN
        ALTER TABLE tasks
            ADD CONSTRAINT tasks_approval_state_check
            CHECK (approval_state IN (
                'pending_community',
                'community_approved',
                'community_rejected',
                'auto_approved',
                'minted'
            ));
    END IF;
END $$;

-- 2) holon_rules
-- ─────────────────────────────────────────────────────────────────────────────
-- Config por holón. Una fila por holón. Si un holón no tiene fila, el código
-- aplica el default (required_approvals=2) — es el mismo default de la tabla.
CREATE TABLE IF NOT EXISTS holon_rules (
    holon_id            VARCHAR(100) PRIMARY KEY,
    required_approvals  INT          NOT NULL DEFAULT 2 CHECK (required_approvals > 0),
    spirit              TEXT,
    updated_at          TIMESTAMPTZ  DEFAULT NOW()
);

-- Seeds de los dos holones activos. ON CONFLICT DO NOTHING por idempotencia
-- (si la migración se corre dos veces, no pisa configuraciones manuales).
INSERT INTO holon_rules (holon_id, required_approvals, spirit) VALUES
    ('familia-mourino', 2, 'Cuidado regenerativo entre familia y vecinos.'),
    ('archi-brazo',     3, 'Trabajo de cuidado profesional en red.')
ON CONFLICT (holon_id) DO NOTHING;

-- 3) task_approvals
-- ─────────────────────────────────────────────────────────────────────────────
-- Bitácora de votos. Un voter solo puede votar una vez por task_id (UNIQUE).
-- voter_holon_id se redunda intencionalmente para auditar y filtrar más rápido
-- sin joinear member_identities. Validación de membership y de ≠ submitter
-- vive en el código del Tenzo (POST /tasks/{id}/approve).
--
-- ⚠️ task_id usa INTEGER (no BIGINT) para alinearse con `tasks.id SERIAL`,
-- consistente con el resto del schema (voice_profiles, member_identities,
-- task_sessions). Si en algún momento tasks.id pasa a BIGSERIAL, hay que
-- migrar este FK también.
CREATE TABLE IF NOT EXISTS task_approvals (
    id                BIGSERIAL    PRIMARY KEY,
    task_id           INTEGER      NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    voter_persona_id  VARCHAR(100) NOT NULL,
    voter_holon_id    VARCHAR(100) NOT NULL,
    vote              VARCHAR(16)  NOT NULL CHECK (vote IN ('approve', 'reject')),
    voted_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT task_approvals_voter_uk UNIQUE (task_id, voter_persona_id)
);

-- Índice secundario para queries del tipo "¿este voter ya votó alguna tarea
-- en este holón?" — útil para mostrar UI de "ya votaste" en el frontend.
CREATE INDEX IF NOT EXISTS idx_task_approvals_voter
    ON task_approvals (voter_holon_id, voter_persona_id);

-- 4) Índice parcial para queries de "tareas pendientes en este holón"
-- ─────────────────────────────────────────────────────────────────────────────
-- GET /holons/{id}/tasks/pending escanea solo pending_community. El índice
-- parcial es ~10x más chico que uno full y refleja el caso de uso real.
CREATE INDEX IF NOT EXISTS idx_tasks_pending
    ON tasks (holon_id, approval_state)
    WHERE approval_state = 'pending_community';

-- 5) Índice parcial UNIQUE anti-duplicación
-- ─────────────────────────────────────────────────────────────────────────────
-- Red de seguridad por si vuelve a aparecer doble persistencia (frontend +
-- Tenzo) tras un refactor. Una persona NO puede registrar la misma descripción
-- en el mismo holón dos veces el mismo día, MIENTRAS la primera siga viva
-- (pending o auto_approved). Si la primera fue rechazada, el re-intento es
-- válido (el WHERE filtra los rejected/minted, así que no bloquean).
CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_dedup
    ON tasks (persona_id, holon_id, descripcion, (created_at::date))
    WHERE approval_state IN ('pending_community', 'auto_approved');

COMMIT;

-- ── Verificación post-migración ──────────────────────────────────────────────
-- Después del COMMIT, las queries de abajo deben mostrar:
--   1. Distribución de tasks.approval_state coherente con tasks.aprobada.
--   2. Las dos filas seed de holon_rules.
--   3. task_approvals vacía (0 filas).
--   4. Los dos índices parciales creados.

SELECT 'tasks.approval_state' AS check, approval_state, COUNT(*) AS rows
  FROM tasks
 GROUP BY approval_state
UNION ALL
SELECT 'tasks.aprobada (legacy mirror)', COALESCE(aprobada::text, 'NULL'), COUNT(*)
  FROM tasks
 GROUP BY aprobada
 ORDER BY 1, 2;

SELECT holon_id, required_approvals, spirit FROM holon_rules ORDER BY holon_id;

SELECT 'task_approvals' AS tabla, COUNT(*) AS rows FROM task_approvals;

SELECT indexname, indexdef
  FROM pg_indexes
 WHERE tablename = 'tasks'
   AND indexname IN ('idx_tasks_pending', 'idx_tasks_dedup')
 ORDER BY indexname;

-- ── Detección de duplicados pre-existentes (informativo) ─────────────────────
-- Si la migración del UNIQUE PARTIAL falla, esta query muestra qué filas
-- existentes violan la constraint. Útil para limpiar antes de re-correrla.
-- (La incluyo como comentario porque solo se necesita en caso de error.)
--
-- SELECT persona_id, holon_id, descripcion, created_at::date AS dia, COUNT(*) AS dup
--   FROM tasks
--  WHERE approval_state IN ('pending_community', 'auto_approved')
--  GROUP BY 1, 2, 3, 4
-- HAVING COUNT(*) > 1
--  ORDER BY dup DESC, dia DESC;
