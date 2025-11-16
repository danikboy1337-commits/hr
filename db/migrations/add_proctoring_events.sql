-- Migration: Add AI Proctoring Support
-- Run this on existing hr_test databases to enable proctoring

SET search_path TO hr_test, public;

-- 1. Add proctoring columns to user_test_time table
ALTER TABLE user_test_time
    ADD COLUMN IF NOT EXISTS proctoring_enabled BOOLEAN DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS suspicious_events_count INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS proctoring_risk_level VARCHAR(20) DEFAULT 'low';

-- Add check constraint for risk level (if not exists)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.check_constraints
        WHERE constraint_name = 'user_test_time_proctoring_risk_level_check'
    ) THEN
        ALTER TABLE user_test_time
            ADD CONSTRAINT user_test_time_proctoring_risk_level_check
            CHECK (proctoring_risk_level IN ('low', 'medium', 'high'));
    END IF;
END $$;

-- 2. Create proctoring_events table
CREATE TABLE IF NOT EXISTS proctoring_events (
    id SERIAL PRIMARY KEY,
    user_test_id INTEGER NOT NULL REFERENCES user_test_time(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_type VARCHAR(100) NOT NULL, -- e.g., 'face_not_detected', 'multiple_faces', 'tab_switch'
    severity VARCHAR(20) DEFAULT 'medium' CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    details JSONB, -- Additional event details
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Create indexes for proctoring_events
CREATE INDEX IF NOT EXISTS idx_proctoring_events_test ON proctoring_events(user_test_id);
CREATE INDEX IF NOT EXISTS idx_proctoring_events_user ON proctoring_events(user_id);
CREATE INDEX IF NOT EXISTS idx_proctoring_events_type ON proctoring_events(event_type);
CREATE INDEX IF NOT EXISTS idx_proctoring_events_severity ON proctoring_events(severity);

-- 4. Verify migration
DO $$
DECLARE
    col_count INTEGER;
    table_exists BOOLEAN;
BEGIN
    -- Check if columns were added
    SELECT COUNT(*) INTO col_count
    FROM information_schema.columns
    WHERE table_schema = 'hr_test'
    AND table_name = 'user_test_time'
    AND column_name IN ('proctoring_enabled', 'suspicious_events_count', 'proctoring_risk_level');

    -- Check if table was created
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'hr_test' AND table_name = 'proctoring_events'
    ) INTO table_exists;

    IF col_count = 3 AND table_exists THEN
        RAISE NOTICE 'Migration successful: Proctoring support enabled';
        RAISE NOTICE '  - Added 3 columns to user_test_time';
        RAISE NOTICE '  - Created proctoring_events table';
    ELSE
        RAISE WARNING 'Migration incomplete: col_count=%, table_exists=%', col_count, table_exists;
    END IF;
END $$;
