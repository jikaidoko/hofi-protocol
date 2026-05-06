-- ── Migración 004 — ROLLBACK ────────────────────────────────────────────────
-- Fecha: 2026-05-06
--
-- CONTEXTO
-- Revierte la migración 004_community_approval.sql.
-- NO toca la columna `tasks.aprobada` original — esa se mantiene intacta
-- durante toda la 004, así que el rollback restaura el schema pre-PR #4.
--
-- ⚠️ ATENCIÓN — pérdida de datos posibles:
-- Si en producción ya hay votos registrados en `task_approvals` o reglas
-- por holón en `holon_rules`, este rollback BORRA esa información.
-- Antes de correr, exportar a CSV si hace falta auditoría.
--
-- ⚠️ ATENCIÓN — tareas en estado community_approved/minted:
-- Si hay tareas con approval_state IN ('community_approved', 'minted'),
-- esos estados desaparecen al droppear la columna. La columna `aprobada`
-- todavía las marca como TRUE (única señal que sobrevive). Si el rollback
-- se hace después de mintear, la marca de "ya minteada" se pierde y el
-- sistema podría re-mintear. Solo correr si el sistema está OFFLINE.
--
-- APLICACIÓN
--   gcloud sql connect hofi-db --user=hofi_user --database=hofi
--   \i 004_community_approval_down.sql
-- ─────────────────────────────────────────────────────────────────────────────

BEGIN;

-- 1) Borrar índices parciales de tasks (no requieren lock pesado)
DROP INDEX IF EXISTS idx_tasks_pending;
DROP INDEX IF EXISTS idx_tasks_dedup;

-- 2) Borrar tabla de votos (FK CASCADE en task_id ya estaba; al droppear la
--    tabla entera se va sola junto con idx_task_approvals_voter).
DROP TABLE IF EXISTS task_approvals;

-- 3) Borrar tabla de reglas por holón.
DROP TABLE IF EXISTS holon_rules;

-- 4) Quitar la columna approval_state de tasks. CHECK constraint cae con
--    el ALTER ... DROP COLUMN.
LOCK TABLE tasks IN ACCESS EXCLUSIVE MODE;

ALTER TABLE tasks
    DROP CONSTRAINT IF EXISTS tasks_approval_state_check;

ALTER TABLE tasks
    DROP COLUMN IF EXISTS approval_state;

COMMIT;

-- ── Verificación post-rollback ───────────────────────────────────────────────
-- Estas queries deben confirmar que el schema está como antes de la 004.

-- Confirma que approval_state ya no existe.
SELECT column_name
  FROM information_schema.columns
 WHERE table_name = 'tasks'
   AND column_name = 'approval_state';
-- (debe devolver 0 filas)

-- Confirma que las dos tablas de soporte ya no existen.
SELECT table_name
  FROM information_schema.tables
 WHERE table_schema = 'public'
   AND table_name IN ('holon_rules', 'task_approvals');
-- (debe devolver 0 filas)

-- Confirma que los índices parciales ya no existen.
SELECT indexname
  FROM pg_indexes
 WHERE tablename = 'tasks'
   AND indexname IN ('idx_tasks_pending', 'idx_tasks_dedup');
-- (debe devolver 0 filas)

-- Confirma que la columna `aprobada` original sigue intacta.
SELECT COALESCE(aprobada::text, 'NULL') AS aprobada, COUNT(*) AS rows
  FROM tasks
 GROUP BY aprobada
 ORDER BY 1;
