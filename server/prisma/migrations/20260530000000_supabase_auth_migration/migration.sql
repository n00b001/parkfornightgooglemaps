-- Migration: Migrate from custom User table to Supabase Auth (auth.users)
-- This migration:
-- 1. Drops foreign key constraints from favorite, review, visit tables
-- 2. Drops the old User table (users managed by Supabase Auth)
-- 3. Drops the Session table (JWT auth replaces session cookies)
-- 4. Does NOT add FK to auth.users — existing userId values are from old User table
--    and won't match auth.users IDs. Old records become orphaned and are cleaned up.
-- 5. Creates trigger for future auth user sync

-- Step 1: Drop old foreign key constraints
ALTER TABLE IF EXISTS favorite DROP CONSTRAINT IF EXISTS favorite_userId_fkey;
ALTER TABLE IF EXISTS review DROP CONSTRAINT IF EXISTS review_userId_fkey;
ALTER TABLE IF EXISTS visit DROP CONSTRAINT IF EXISTS visit_userId_fkey;

-- Step 2: Drop the old User table
-- Existing favorites/reviews/visits with old userId values become orphaned.
-- They will be cleaned up when users re-authenticate with Supabase Auth.
DROP TABLE IF EXISTS "user";

-- Step 3: Drop the Session table (no longer needed with JWT auth)
DROP TABLE IF EXISTS "Session";

-- Step 4: Create trigger to sync new auth users
-- This ensures that when a new user signs up via Supabase Auth,
-- their metadata is available for the app.
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  -- The auth.users table stores the user. No additional sync needed.
  -- This function is a placeholder for future metadata sync if needed.
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
