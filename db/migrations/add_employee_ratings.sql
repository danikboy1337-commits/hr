-- Migration to add employee_ratings table
-- This table stores manager ratings for employees (1-10 scale)
-- Only accessible by managers (for their department) and HR (all departments)
-- NOTE: This is superseded by update_manager_evaluations_competency_based.sql

CREATE TABLE IF NOT EXISTS hr.employee_ratings (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES hr.users(id) ON DELETE CASCADE,
    manager_id INTEGER NOT NULL REFERENCES hr.users(id) ON DELETE CASCADE,
    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 10),
    comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(employee_id, manager_id)  -- Each manager can rate each employee only once (but can update)
);

-- Index for faster queries
CREATE INDEX IF NOT EXISTS idx_employee_ratings_employee ON hr.employee_ratings(employee_id);
CREATE INDEX IF NOT EXISTS idx_employee_ratings_manager ON hr.employee_ratings(manager_id);

-- Trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION hr.update_employee_ratings_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER employee_ratings_updated_at
    BEFORE UPDATE ON hr.employee_ratings
    FOR EACH ROW
    EXECUTE FUNCTION hr.update_employee_ratings_updated_at();
