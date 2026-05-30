-- Migration: Integrate Supabase Auth with existing User table
-- Adds authUserId column and trigger to sync auth.users -> app User table

-- Add authUserId column to existing User table
ALTER TABLE "User" ADD COLUMN IF NOT EXISTS authUserId TEXT UNIQUE;
CREATE INDEX IF NOT EXISTS idx_user_authUserId ON "User"(authUserId);

-- Backfill: match existing users by email to auth.users
-- This runs once during migration to link existing records
UPDATE "User" u
SET authUserId = au.id
FROM auth.users au
WHERE u.email = au.email
  AND u.authUserId IS NULL
  AND au.deleted_at IS NULL;

-- Trigger function: create or update User record on auth sign-in
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public
AS $$
DECLARE
  app_user_id TEXT;
  google_provider_id TEXT;
BEGIN
  -- Try to find existing user by email
  SELECT id INTO app_user_id FROM "User" WHERE email = NEW.email LIMIT 1;

  IF app_user_id IS NOT NULL THEN
    -- Update existing user: set authUserId, update name/avatar if from Google
    UPDATE "User"
    SET
      authUserId = NEW.id,
      updatedAt = NOW()
    WHERE id = app_user_id;
  ELSE
    -- Create new User record
    -- Extract Google provider info if available
    SELECT raw_user_meta_data->>'google_id' INTO google_provider_id FROM auth.users WHERE id = NEW.id;

    INSERT INTO "User" (id, authUserId, email, name, avatar, "googleId", createdAt, updatedAt)
    VALUES (
      gen_random_uuid(),
      NEW.id,
      NEW.email,
      COALESCE(NEW.raw_user_meta_data->>'name', NEW.raw_user_meta_data->>'full_name'),
      COALESCE(NEW.raw_user_meta_data->>'avatar_url', NEW.raw_user_meta_data->>'picture'),
      google_provider_id,
      NOW(),
      NOW()
    );
    GET DIAGNOSTICS app_user_id = ROW_COUNT;
  END IF;

  RETURN NEW;
END;
$$;

-- Create trigger on auth.users
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT OR UPDATE ON auth.users
  FOR EACH ROW
  EXECUTE FUNCTION public.handle_new_user();

-- Drop the Session model (no longer needed with JWT auth)
-- The Session table is used by connect-pg-simple for express-session storage
-- We keep it for now to avoid breaking existing sessions during migration
-- It can be dropped after a grace period
