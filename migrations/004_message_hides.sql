-- Migration 004: message_hides — per-viewer hide-from-my-view
-- Date: 2026-05-25
-- Purpose: Add the table that backs (a) "🙈 Hide from my view" for hosts and
--          facilitators in the portal, and (b) the bookkeeping the coordinator
--          hard-delete uses to clean up dangling hides. Spans BOTH message
--          systems: the legacy `messages` table (Message-Coordinator flow)
--          and the new `facilitator_conversation_messages` table (Contact
--          Facilitator(s) threads), discriminated by `message_system`.
--
-- Status: HOLD. Do NOT apply automatically. Operator runs this in the
--          Supabase SQL Editor after reviewing the diff. Local SQLite picks
--          the table up automatically via utils.database.init_all() →
--          init_message_hides().
--
-- Strategy: additive, idempotent CREATE TABLE IF NOT EXISTS + CREATE INDEX
--          IF NOT EXISTS. Safe to re-run. Touches no existing table.
--
-- Note on no FK: the `message_id` column intentionally has NO foreign-key
--          constraint, because a single column would otherwise need to FK
--          two different tables (legacy `messages.message_id` vs.
--          `facilitator_conversation_messages.id`). Integrity is enforced
--          in application code: the delete_message and
--          delete_conversation_message helpers always purge corresponding
--          message_hides rows when they hard-delete a message.

CREATE TABLE IF NOT EXISTS message_hides (
    id              SERIAL PRIMARY KEY,
    message_system  TEXT NOT NULL,   -- 'legacy' | 'fac_conv'
    message_id      INTEGER NOT NULL,
    viewer_type     TEXT NOT NULL,   -- 'host' | 'facilitator'
    viewer_id       TEXT NOT NULL,   -- str(host_id) / str(facilitator_id)
    hidden_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(message_system, message_id, viewer_type, viewer_id)
);

CREATE INDEX IF NOT EXISTS idx_message_hides_lookup
    ON message_hides (message_system, viewer_type, viewer_id);

-- ──────────────────────────────────────────────────────────────────────────────
-- Verification queries (run manually in Supabase SQL Editor after applying;
-- do NOT execute as part of the migration itself).
-- ──────────────────────────────────────────────────────────────────────────────
--
-- 1. Confirm the table + columns:
-- SELECT column_name, data_type
--   FROM information_schema.columns
--   WHERE table_schema = 'public' AND table_name = 'message_hides'
--   ORDER BY ordinal_position;
--
-- 2. Confirm the UNIQUE constraint and the lookup index:
-- SELECT conname FROM pg_constraint
--   WHERE conrelid = 'public.message_hides'::regclass AND contype = 'u';
-- SELECT indexname FROM pg_indexes
--   WHERE schemaname='public' AND indexname='idx_message_hides_lookup';
--
-- ──────────────────────────────────────────────────────────────────────────────
-- Apply steps (operator runs these — do NOT run from the app sandbox):
-- ──────────────────────────────────────────────────────────────────────────────
-- 1. Snapshot Supabase: Project → Database → Backups → "Take backup now".
-- 2. Open Supabase SQL Editor against the production project.
-- 3. Paste the contents of THIS file (everything above the verification block)
--    and run it. It is idempotent; re-running is safe.
-- 4. Run verification queries (1) and (2) above.
-- 5. In the app: hosts and facilitators see the "🙈 Hide from my view" button
--    on each of their messages; the coordinator sees "🗑️ Delete permanently"
--    on legacy messages and on Host↔Facilitator thread messages.
