-- Migration 003: Contact Facilitator(s) — host↔facilitator threads
-- Date: 2026-05-24
-- Purpose: Add the three tables that back the new "Contact Facilitator(s)"
--          host-portal feature. The host can start a two-way thread with the
--          facilitator(s) of their event; the main coordinator is silently
--          copied as a hidden participant (visible only in the coordinator's
--          read-only view in pages/14_Messages.py).
--
-- Status: HOLD. Do NOT apply automatically. The operator runs this in the
--          Supabase SQL Editor after reviewing the diff. Local SQLite picks
--          the tables up automatically via utils.database.init_all() →
--          init_facilitator_conversations().
--
-- Strategy: additive, idempotent CREATE TABLE IF NOT EXISTS / CREATE INDEX
--          IF NOT EXISTS. Safe to re-run. Touches no existing table; the
--          legacy `messages` flow and its helpers are unchanged.
--
-- Note on participant_id type: TEXT (not INTEGER) so the same column can
--          hold host_id / facilitator_id (integers from their tables) AND
--          the coordinator users.id (UUID under Postgres). Application code
--          str()'s the value before INSERT. Querying by participant_id from
--          Python also passes str(...) to keep the comparison stable.

CREATE TABLE IF NOT EXISTS facilitator_conversations (
    conversation_id SERIAL PRIMARY KEY,
    event_id        INTEGER REFERENCES events(event_id),
    host_id         INTEGER REFERENCES hosts(host_id),
    subject         TEXT,
    status          TEXT DEFAULT 'open',
    created_by_type TEXT,
    created_by_id   INTEGER,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS facilitator_conversation_messages (
    id              SERIAL PRIMARY KEY,
    conversation_id INTEGER REFERENCES facilitator_conversations(conversation_id),
    sender_type     TEXT NOT NULL,
    sender_id       INTEGER,
    sender_name     TEXT,
    body            TEXT NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS facilitator_conversation_participants (
    id               SERIAL PRIMARY KEY,
    conversation_id  INTEGER REFERENCES facilitator_conversations(conversation_id),
    participant_type TEXT NOT NULL,
    participant_id   TEXT,
    is_hidden        INTEGER DEFAULT 0,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_fc_participants_lookup
    ON facilitator_conversation_participants (participant_type, participant_id);

CREATE INDEX IF NOT EXISTS idx_fc_messages_conv
    ON facilitator_conversation_messages (conversation_id, created_at);

-- ──────────────────────────────────────────────────────────────────────────────
-- Verification queries (run manually in Supabase SQL Editor after applying;
-- do NOT execute as part of the migration itself).
-- ──────────────────────────────────────────────────────────────────────────────
--
-- 1. Confirm all three tables exist with the expected columns:
-- SELECT table_name, column_name, data_type
--   FROM information_schema.columns
--   WHERE table_schema = 'public'
--     AND table_name IN (
--       'facilitator_conversations',
--       'facilitator_conversation_messages',
--       'facilitator_conversation_participants'
--     )
--   ORDER BY table_name, ordinal_position;
--
-- 2. Confirm both indexes exist:
-- SELECT indexname FROM pg_indexes
--   WHERE schemaname = 'public'
--     AND indexname IN ('idx_fc_participants_lookup', 'idx_fc_messages_conv');
--
-- ──────────────────────────────────────────────────────────────────────────────
-- Apply steps (operator runs these — do NOT run from the app sandbox):
-- ──────────────────────────────────────────────────────────────────────────────
-- 1. Snapshot Supabase: Project → Database → Backups → "Take backup now".
-- 2. Open Supabase SQL Editor against the production project.
-- 3. Paste the contents of THIS file (everything above the verification block)
--    and run it. It is idempotent; re-running is safe.
-- 4. Run verification queries (1) and (2) above.
-- 5. In the Streamlit app, open the host portal → "Contact Facilitator(s)" tab
--    and test the flow per cc_evidence/contact_facilitator/TESTPLAN.md.
