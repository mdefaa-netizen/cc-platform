-- Migration 001: Add user profile links for Role-Based Access Control (RBAC)
-- Date: 2026-05-14
-- Purpose: Link users table rows to either a hosts row or a facilitators row,
--          so a logged-in facilitator/host knows which profile they own.
-- Refs: Phase 6.1 of RBAC plan.

-- Step 1: Add two nullable Foreign Key columns to users.
-- ON DELETE SET NULL: if the linked host or facilitator is deleted,
-- the user row stays but the link becomes NULL (no orphan IDs).
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS linked_host_id INTEGER
    REFERENCES hosts(host_id) ON DELETE SET NULL;

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS linked_facilitator_id INTEGER
    REFERENCES facilitators(facilitator_id) ON DELETE SET NULL;

-- Step 2: Add a CHECK constraint to enforce exclusivity.
-- A user row can have:
--   - linked_host_id set AND linked_facilitator_id NULL  (a host)
--   - linked_host_id NULL AND linked_facilitator_id set  (a facilitator)
--   - both NULL                                          (coordinator, nhh_staff, cdfa_staff)
-- A user row CANNOT have both columns set at the same time.
ALTER TABLE users
  ADD CONSTRAINT users_link_exclusive
  CHECK (
    NOT (linked_host_id IS NOT NULL AND linked_facilitator_id IS NOT NULL)
  );

-- Step 3: Add indexes for join performance.
-- Queries like "find the user row for this facilitator" need to scan by
-- linked_facilitator_id, so indexes here are worth the small write cost.
CREATE INDEX IF NOT EXISTS idx_users_linked_host_id
  ON users(linked_host_id)
  WHERE linked_host_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_users_linked_facilitator_id
  ON users(linked_facilitator_id)
  WHERE linked_facilitator_id IS NOT NULL;

-- Step 4: Verification queries (run these manually in Supabase SQL Editor
--         after applying the migration; do NOT run as part of the migration).
-- SELECT column_name, data_type, is_nullable
--   FROM information_schema.columns
--   WHERE table_name = 'users'
--     AND column_name IN ('linked_host_id', 'linked_facilitator_id');
--
-- SELECT constraint_name, constraint_type
--   FROM information_schema.table_constraints
--   WHERE table_name = 'users'
--     AND constraint_name = 'users_link_exclusive';
--
-- SELECT indexname FROM pg_indexes
--   WHERE tablename = 'users'
--     AND indexname IN ('idx_users_linked_host_id', 'idx_users_linked_facilitator_id');
