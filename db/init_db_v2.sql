-- =====================================================
-- HR Testing Platform - Database Schema V2 (FIXED)
-- Schema: hr_test (assumed to exist already)
-- =====================================================
-- Changes from V1:
-- 1. Users identified by tab_number (not phone)
-- 2. Questions structure supports encrypted JSON format
-- 3. Simplified user_questions and user_results tables
-- 4. Added profiles and specializations hierarchy
-- =====================================================

-- Set search path (assuming hr_test schema exists)
SET search_path TO hr_test, public;

-- =====================================================
-- TABLE: departments
-- Four departments: Halyk Super App, OnlineBank, OCDS, AI
-- =====================================================
CREATE TABLE IF NOT EXISTS departments (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert the 4 departments
INSERT INTO departments (name, description) VALUES
    ('Halyk Super App', 'Mobile application development and maintenance'),
    ('OnlineBank', 'Online banking platform and web services'),
    ('OCDS', 'Open Contracting Data Standard team'),
    ('AI', 'Artificial Intelligence and Machine Learning division')
ON CONFLICT (name) DO NOTHING;

-- =====================================================
-- TABLE: profiles
-- Test categories (e.g., "Backend Developer", "Data Analyst")
-- =====================================================
CREATE TABLE IF NOT EXISTS profiles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    has_specializations BOOLEAN DEFAULT TRUE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- TABLE: specializations
-- Skill areas under profiles (e.g., "C# / .NET", "Python")
-- =====================================================
CREATE TABLE IF NOT EXISTS specializations (
    id SERIAL PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    json_file_name VARCHAR(255), -- e.g., "Data_Analyst_encrypted_questions.json"
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(profile_id, name)
);

-- =====================================================
-- TABLE: competencies
-- Core skills within specializations
-- =====================================================
CREATE TABLE IF NOT EXISTS competencies (
    id SERIAL PRIMARY KEY,
    specialization_id INTEGER NOT NULL REFERENCES specializations(id) ON DELETE CASCADE,
    name VARCHAR(500) NOT NULL,
    weight DECIMAL(5,2) DEFAULT 1.0, -- Relative weight/importance (0.0 - 100.0)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- TABLE: topics
-- Specific knowledge areas within competencies
-- (Previously called "themes" in JSON structure)
-- =====================================================
CREATE TABLE IF NOT EXISTS topics (
    id SERIAL PRIMARY KEY,
    competency_id INTEGER NOT NULL REFERENCES competencies(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- TABLE: questions
-- All questions stored here (encrypted)
-- =====================================================
CREATE TABLE IF NOT EXISTS questions (
    id SERIAL PRIMARY KEY,
    specialization_id INTEGER NOT NULL REFERENCES specializations(id) ON DELETE CASCADE,
    competency_id INTEGER NOT NULL REFERENCES competencies(id) ON DELETE CASCADE,
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    level VARCHAR(20) NOT NULL CHECK (level IN ('junior', 'middle', 'senior')),
    question_text TEXT NOT NULL,
    var_1 TEXT NOT NULL,
    var_2 TEXT NOT NULL,
    var_3 TEXT NOT NULL,
    var_4 TEXT NOT NULL,
    correct_answer INTEGER NOT NULL CHECK (correct_answer BETWEEN 1 AND 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- TABLE: users
-- Employee information from LDAP
-- =====================================================
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    tab_number VARCHAR(50) NOT NULL UNIQUE, -- Employee ID from LDAP (e.g., "00061221")
    company VARCHAR(255) DEFAULT 'Halyk Bank',
    role VARCHAR(50) DEFAULT 'employee' CHECK (role IN ('employee', 'hr', 'manager')),
    department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL,
    specialization_id INTEGER REFERENCES specializations(id) ON DELETE SET NULL, -- Assigned specialization
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- TABLE: user_test_time
-- Test session timing information
-- (Created BEFORE user_questions/user_results so FK works)
-- =====================================================
CREATE TABLE IF NOT EXISTS user_test_time (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    specialization_id INTEGER NOT NULL REFERENCES specializations(id),
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- When test questions were generated
    start_time TIMESTAMP, -- When user started answering
    end_time TIMESTAMP, -- When user finished
    score INTEGER, -- Total correct answers
    max_score INTEGER DEFAULT 60, -- Total questions (changed from 24 to 60)
    level VARCHAR(20) CHECK (level IN ('junior', 'middle', 'senior')), -- Final assessed level
    completed BOOLEAN DEFAULT FALSE
);

-- =====================================================
-- TABLE: user_questions
-- Questions assigned to each user for their test
-- Generated when test starts based on specialization
-- =====================================================
CREATE TABLE IF NOT EXISTS user_questions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    test_session_id INTEGER REFERENCES user_test_time(id) ON DELETE CASCADE, -- FK added here directly
    specialization_id INTEGER NOT NULL REFERENCES specializations(id),
    competency_id INTEGER NOT NULL REFERENCES competencies(id),
    topic_id INTEGER NOT NULL REFERENCES topics(id),
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    question_order INTEGER NOT NULL, -- Order in test (1-60)
    question_text TEXT NOT NULL, -- Denormalized for performance
    date_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, test_session_id, question_id) -- Prevent duplicate questions in same test
);

-- =====================================================
-- TABLE: user_results
-- User answers to questions
-- Appended as user answers each question
-- =====================================================
CREATE TABLE IF NOT EXISTS user_results (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    test_session_id INTEGER REFERENCES user_test_time(id) ON DELETE CASCADE, -- FK added here directly
    specialization_id INTEGER NOT NULL REFERENCES specializations(id),
    competency_id INTEGER NOT NULL REFERENCES competencies(id),
    topic_id INTEGER NOT NULL REFERENCES topics(id),
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    question_text TEXT NOT NULL,
    user_answer INTEGER NOT NULL CHECK (user_answer BETWEEN 1 AND 4),
    correct INTEGER NOT NULL CHECK (correct IN (0, 1)), -- 0 = wrong, 1 = correct
    date_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, test_session_id, question_id) -- Prevent answering same question twice
);

-- =====================================================
-- OPTIONAL: Self-assessment and manager ratings tables
-- =====================================================
CREATE TABLE IF NOT EXISTS competency_self_assessments (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    test_session_id INTEGER NOT NULL REFERENCES user_test_time(id) ON DELETE CASCADE,
    competency_id INTEGER NOT NULL REFERENCES competencies(id) ON DELETE CASCADE,
    self_rating INTEGER NOT NULL CHECK (self_rating BETWEEN 1 AND 10),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(test_session_id, competency_id)
);

CREATE TABLE IF NOT EXISTS manager_competency_ratings (
    id SERIAL PRIMARY KEY,
    test_session_id INTEGER NOT NULL REFERENCES user_test_time(id) ON DELETE CASCADE,
    competency_id INTEGER NOT NULL REFERENCES competencies(id) ON DELETE CASCADE,
    manager_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 10),
    comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(test_session_id, competency_id, manager_id)
);

-- =====================================================
-- INDEXES (Created separately, not inline)
-- =====================================================

-- questions table indexes
CREATE INDEX IF NOT EXISTS idx_questions_specialization ON questions(specialization_id);
CREATE INDEX IF NOT EXISTS idx_questions_competency ON questions(competency_id);
CREATE INDEX IF NOT EXISTS idx_questions_topic ON questions(topic_id);
CREATE INDEX IF NOT EXISTS idx_questions_level ON questions(level);

-- users table indexes
CREATE INDEX IF NOT EXISTS idx_users_tab_number ON users(tab_number);
CREATE INDEX IF NOT EXISTS idx_users_department ON users(department_id);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

-- user_questions table indexes
CREATE INDEX IF NOT EXISTS idx_user_questions_user ON user_questions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_questions_session ON user_questions(test_session_id);
CREATE INDEX IF NOT EXISTS idx_user_questions_order ON user_questions(user_id, question_order);

-- user_results table indexes
CREATE INDEX IF NOT EXISTS idx_user_results_user ON user_results(user_id);
CREATE INDEX IF NOT EXISTS idx_user_results_session ON user_results(test_session_id);
CREATE INDEX IF NOT EXISTS idx_user_results_correct ON user_results(correct);

-- user_test_time table indexes
CREATE INDEX IF NOT EXISTS idx_user_test_time_user ON user_test_time(user_id);
CREATE INDEX IF NOT EXISTS idx_user_test_time_completed ON user_test_time(completed);
CREATE INDEX IF NOT EXISTS idx_user_test_time_dates ON user_test_time(created_date, start_time, end_time);

-- =====================================================
-- SUMMARY
-- =====================================================
-- Tables created:
-- 1. departments (4 rows)
-- 2. profiles
-- 3. specializations
-- 4. competencies
-- 5. topics
-- 6. questions
-- 7. users (with tab_number)
-- 8. user_test_time
-- 9. user_questions
-- 10. user_results
-- 11. competency_self_assessments (optional)
-- 12. manager_competency_ratings (optional)
--
-- All indexes created separately for compatibility
-- =====================================================
