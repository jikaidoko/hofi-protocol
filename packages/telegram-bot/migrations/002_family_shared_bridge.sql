-- HoFi Protocol — Migración 002
-- Objetivo: permitir que múltiples person_ids compartan un mismo
--           (identity_type, identity_value) en member_identities.
--
-- Caso real: toda la familia Valdés/Mouriño usa un solo teléfono con un
-- único chat_id de Telegram. Con el UNIQUE(identity_type, identity_value)
-- original, cada nuevo miembro que se registraba sobreescribía (via
-- ON CONFLICT DO UPDATE) el mapping del miembro anterior — Luna pisaba a
-- Doco, Gaya pisaba a Luna, etc.
--
-- Fix: la clave única pasa a ser la terna (identity_type, identity_value,
-- person_id). El mismo telegram_id puede mapear a varios person_ids; la
-- identidad REAL (voz) ya desambigua en el momento de autenticar.
--
-- Aplicación:
--   gcloud sql connect hofi-postgres --user=hofi_user --database=hofi
--   \i 002_family_shared_bridge.sql
--
-- Reversión (si hiciera falta): ver bloque ROLLBACK al final.

BEGIN;

-- 1) Drop de la constraint original.
--    pg genera el nombre automáticamente como <tabla>_<cols>_key. En nuestra
--    creación original (db.py init_db) fue member_identities_identity_type_identity_value_key.
--    Usamos un bloque DO para robustez si el nombre difiere por histórico.
DO $$
DECLARE
    cname text;
BEGIN
    SELECT conname
      INTO cname
      FROM pg_constraint
     WHERE conrelid = 'member_identities'::regclass
       AND contype  = 'u'
       AND array_length(conkey, 1) = 2
       AND EXISTS (
           SELECT 1
             FROM unnest(conkey) AS k
             JOIN pg_attribute a ON a.attnum = k AND a.attrelid = 'member_identities'::regclass
            WHERE a.attname IN ('identity_type', 'identity_value')
       )
     LIMIT 1;

    IF cname IS NOT NULL THEN
        EXECUTE format('ALTER TABLE member_identities DROP CONSTRAINT %I', cname);
        RAISE NOTICE 'Dropped constraint %', cname;
    ELSE
        RAISE NOTICE 'No legacy 2-column UNIQUE found; skipping drop';
    END IF;
END $$;

-- 2) Nueva constraint: (identity_type, identity_value, person_id).
--    Permite que el mismo (telegram, 2012212775) mapee a 'doco', 'luna',
--    'gaya' y 'uma' sin conflicto.
ALTER TABLE member_identities
    ADD CONSTRAINT member_identities_bridge_uk
    UNIQUE (identity_type, identity_value, person_id);

-- 3) Índice de búsqueda rápida: lookups "dado este telegram_id, ¿qué
--    person_ids conozco?" — se usa en resolve_person_id y en la auth
--    por voz cuando hay que listar candidatos del chat.
CREATE INDEX IF NOT EXISTS idx_member_identities_lookup
    ON member_identities (identity_type, identity_value);

COMMIT;

-- ── Verificación post-migración ──────────────────────────────────────────────
\d member_identities
SELECT identity_type, identity_value, person_id, display_name
FROM member_identities
WHERE identity_type = 'telegram_id'
ORDER BY identity_value, person_id;

-- ── ROLLBACK (solo si se necesita revertir) ──────────────────────────────────
-- BEGIN;
-- ALTER TABLE member_identities DROP CONSTRAINT member_identities_bridge_uk;
-- DROP INDEX IF EXISTS idx_member_identities_lookup;
-- -- Atención: si antes de revertir hay múltiples filas con el mismo
-- -- (identity_type, identity_value), la constraint original fallaría al
-- -- re-crearse. Habría que consolidar primero (quedarse con 1 sola fila
-- -- por telegram_id) antes del rollback.
-- ALTER TABLE member_identities
--     ADD CONSTRAINT member_identities_identity_type_identity_value_key
--     UNIQUE (identity_type, identity_value);
-- COMMIT;
