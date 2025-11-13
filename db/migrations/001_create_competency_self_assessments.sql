-- Migration: Create competency_self_assessments table
-- This table stores employee self-ratings for competencies (1-10 scale)
-- Used for collecting self-assessment data before tests

CREATE TABLE IF NOT EXISTS hr.competency_self_assessments (
    id SERIAL PRIMARY KEY,
    user_test_id INTEGER NOT NULL REFERENCES hr.user_specialization_tests(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES hr.users(id) ON DELETE CASCADE,
    competency_id INTEGER NOT NULL REFERENCES hr.competencies(id) ON DELETE CASCADE,
    self_rating INTEGER NOT NULL CHECK (self_rating >= 1 AND self_rating <= 10),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_test_id, competency_id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_comp_self_assess_user_test ON hr.competency_self_assessments(user_test_id);
CREATE INDEX IF NOT EXISTS idx_comp_self_assess_user ON hr.competency_self_assessments(user_id);
CREATE INDEX IF NOT EXISTS idx_comp_self_assess_competency ON hr.competency_self_assessments(competency_id);

-- Auto-update timestamp trigger
CREATE OR REPLACE FUNCTION hr.update_competency_self_assessments_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER competency_self_assessments_updated_at
    BEFORE UPDATE ON hr.competency_self_assessments
    FOR EACH ROW
    EXECUTE FUNCTION hr.update_competency_self_assessments_updated_at();
