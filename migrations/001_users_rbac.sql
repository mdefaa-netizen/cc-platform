-- 001_users_rbac.sql
-- Role-Based Access Control schema for CC Platform (Supabase / Postgres).
--
-- This migration:
--   1. Drops the existing username-based `users` table (wipe and reseed).
--   2. Creates the new email-based `users` table.
--   3. Adds `owner_user_id` FK to the `events` table.
--   4. Seeds one bootstrap Coordinator (mdefaa@gmail.com).
--
-- Run order: apply this once against your Supabase project.
-- The bootstrap password must be supplied by the calling code
-- (utils/auth.py::ensure_bootstrap_coordinator); this SQL leaves the
-- password_hash as a placeholder you MUST NOT use in production.

BEGIN;

-- 1. Drop the old users table (username-based). CASCADE drops any FKs.
DROP TABLE IF EXISTS users CASCADE;

-- 2. Create the new users table.
CREATE TABLE users (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email            TEXT UNIQUE NOT NULL,
    password_hash    TEXT NOT NULL,
    role             TEXT NOT NULL CHECK (role IN (
                        'coordinator',
                        'facilitator',
                        'host',
                        'cdfa_staff',
                        'nhh_staff'
                    )),
    full_name        TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active        BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX idx_users_email  ON users (email);
CREATE INDEX idx_users_role   ON users (role);
CREATE INDEX idx_users_active ON users (is_active);

-- 3. Add owner_user_id to events. NULL = unassigned (legacy rows stay NULL
--    until a Coordinator assigns them).
ALTER TABLE events
    ADD COLUMN IF NOT EXISTS owner_user_id UUID
    REFERENCES users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_events_owner_user_id ON events (owner_user_id);

-- 4. Bootstrap coordinator placeholder row.
--    The Python code (utils/auth.py::ensure_bootstrap_coordinator) will
--    replace this on first run with a real bcrypt hash. We INSERT a
--    deliberately-invalid hash so logins fail until Python runs.
INSERT INTO users (email, password_hash, role, full_name, is_active)
VALUES (
    'mdefaa@gmail.com',
    '$2b$12$INVALID_PLACEHOLDER_REPLACED_BY_BOOTSTRAP_CODE______________',
    'coordinator',
    'Bootstrap Coordinator',
    TRUE
)
ON CONFLICT (email) DO NOTHING;

COMMIT;
