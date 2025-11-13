-- Add time limit tracking to tests
-- Tests will have 40 minutes time limit

ALTER TABLE hr.user_specialization_tests
ADD COLUMN IF NOT EXISTS time_limit_minutes INTEGER DEFAULT 40,
ADD COLUMN IF NOT EXISTS time_started_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS time_expired BOOLEAN DEFAULT FALSE;

-- Update existing tests to have time_started_at = started_at
UPDATE hr.user_specialization_tests
SET time_started_at = started_at
WHERE time_started_at IS NULL AND started_at IS NOT NULL;
