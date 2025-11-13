-- =====================================================
-- HR Testing Platform - Database Schema V2
-- Schema: hr_test (New structure for LDAP migration)
-- =====================================================
-- Changes from V1:
-- 1. Users identified by tab_number (not phone)
-- 2. Questions structure supports encrypted JSON format
-- 3. Simplified user_questions and user_results tables
-- 4. Added profiles and specializations hierarchy
-- =====================================================

-- Drop existing schema if exists (CAUTION: Only for fresh installs!)
-- DROP SCHEMA IF EXISTS hr_test CASCADE;

-- Create schema
CREATE SCHEMA IF NOT EXISTS hr_test;

-- Set search path
SET search_path TO hr_test, public;

-- =====================================================
-- TABLE: departments
-- Four departments: Halyk Super App, OnlineBank, OCDS, AI
-- =====================================================
CREATE TABLE IF NOT EXISTS hr_test.departments (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert the 4 departments
INSERT INTO hr_test.departments (name, description) VALUES
    ('Halyk Super App', 'Mobile application development and maintenance'),
    ('OnlineBank', 'Online banking platform and web services'),
    ('OCDS', 'Open Contracting Data Standard team'),
    ('AI', 'Artificial Intelligence and Machine Learning division')
ON CONFLICT (name) DO NOTHING;

-- =====================================================
-- TABLE: profiles
-- Test categories (e.g., "Backend Developer", "Data Analyst")
-- =====================================================
CREATE TABLE IF NOT EXISTS hr_test.profiles (
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
CREATE TABLE IF NOT EXISTS hr_test.specializations (
    id SERIAL PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES hr_test.profiles(id) ON DELETE CASCADE,
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
CREATE TABLE IF NOT EXISTS hr_test.competencies (
    id SERIAL PRIMARY KEY,
    specialization_id INTEGER NOT NULL REFERENCES hr_test.specializations(id) ON DELETE CASCADE,
    name VARCHAR(500) NOT NULL,
    weight DECIMAL(5,2) DEFAULT 1.0, -- Relative weight/importance (0.0 - 100.0)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- TABLE: topics
-- Specific knowledge areas within competencies
-- (Previously called "themes" in JSON structure)
-- =====================================================
CREATE TABLE IF NOT EXISTS hr_test.topics (
    id SERIAL PRIMARY KEY,
    competency_id INTEGER NOT NULL REFERENCES hr_test.competencies(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- TABLE: questions
-- All questions stored here (decrypted from JSON files)
-- =====================================================
CREATE TABLE IF NOT EXISTS hr_test.questions (
    id SERIAL PRIMARY KEY,
    specialization_id INTEGER NOT NULL REFERENCES hr_test.specializations(id) ON DELETE CASCADE,
    competency_id INTEGER NOT NULL REFERENCES hr_test.competencies(id) ON DELETE CASCADE,
    topic_id INTEGER NOT NULL REFERENCES hr_test.topics(id) ON DELETE CASCADE,
    level VARCHAR(20) NOT NULL CHECK (level IN ('junior', 'middle', 'senior')),
    question_text TEXT NOT NULL,
    var_1 TEXT NOT NULL,
    var_2 TEXT NOT NULL,
    var_3 TEXT NOT NULL,
    var_4 TEXT NOT NULL,
    correct_answer INTEGER NOT NULL CHECK (correct_answer BETWEEN 1 AND 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Indexes for performance
    INDEX idx_questions_specialization (specialization_id),
    INDEX idx_questions_competency (competency_id),
    INDEX idx_questions_topic (topic_id),
    INDEX idx_questions_level (level)
);

-- =====================================================
-- TABLE: users
-- Employee information from LDAP
-- =====================================================
CREATE TABLE IF NOT EXISTS hr_test.users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    tab_number VARCHAR(50) NOT NULL UNIQUE, -- Employee ID from LDAP (e.g., "00061221")
    company VARCHAR(255) DEFAULT 'Halyk Bank',
    role VARCHAR(50) DEFAULT 'employee' CHECK (role IN ('employee', 'hr', 'manager')),
    department_id INTEGER REFERENCES hr_test.departments(id) ON DELETE SET NULL,
    specialization_id INTEGER REFERENCES hr_test.specializations(id) ON DELETE SET NULL, -- Assigned specialization
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Indexes
    INDEX idx_users_tab_number (tab_number),
    INDEX idx_users_department (department_id),
    INDEX idx_users_role (role)
);

-- =====================================================
-- TABLE: user_questions
-- Questions assigned to each user for their test
-- Generated when test starts based on specialization
-- =====================================================
CREATE TABLE IF NOT EXISTS hr_test.user_questions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES hr_test.users(id) ON DELETE CASCADE,
    test_session_id INTEGER, -- Links to user_test_time (added below)
    specialization_id INTEGER NOT NULL REFERENCES hr_test.specializations(id),
    competency_id INTEGER NOT NULL REFERENCES hr_test.competencies(id),
    topic_id INTEGER NOT NULL REFERENCES hr_test.topics(id),
    question_id INTEGER NOT NULL REFERENCES hr_test.questions(id) ON DELETE CASCADE,
    question_order INTEGER NOT NULL, -- Order in test (1-24)
    question_text TEXT NOT NULL, -- Denormalized for performance
    date_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Indexes
    INDEX idx_user_questions_user (user_id),
    INDEX idx_user_questions_session (test_session_id),
    INDEX idx_user_questions_order (user_id, question_order),
    UNIQUE(user_id, test_session_id, question_id) -- Prevent duplicate questions in same test
);

-- =====================================================
-- TABLE: user_results
-- User answers to questions
-- Appended as user answers each question
-- =====================================================
CREATE TABLE IF NOT EXISTS hr_test.user_results (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES hr_test.users(id) ON DELETE CASCADE,
    test_session_id INTEGER, -- Links to user_test_time
    specialization_id INTEGER NOT NULL REFERENCES hr_test.specializations(id),
    competency_id INTEGER NOT NULL REFERENCES hr_test.competencies(id),
    topic_id INTEGER NOT NULL REFERENCES hr_test.topics(id),
    question_id INTEGER NOT NULL REFERENCES hr_test.questions(id) ON DELETE CASCADE,
    question_text TEXT NOT NULL,
    user_answer INTEGER NOT NULL CHECK (user_answer BETWEEN 1 AND 4),
    correct INTEGER NOT NULL CHECK (correct IN (0, 1)), -- 0 = wrong, 1 = correct
    date_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Indexes
    INDEX idx_user_results_user (user_id),
    INDEX idx_user_results_session (test_session_id),
    INDEX idx_user_results_correct (correct),
    UNIQUE(user_id, test_session_id, question_id) -- Prevent answering same question twice
);

-- =====================================================
-- TABLE: user_test_time
-- Test session timing information
-- =====================================================
CREATE TABLE IF NOT EXISTS hr_test.user_test_time (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES hr_test.users(id) ON DELETE CASCADE,
    specialization_id INTEGER NOT NULL REFERENCES hr_test.specializations(id),
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- When test questions were generated
    start_time TIMESTAMP, -- When user started answering
    end_time TIMESTAMP, -- When user finished
    score INTEGER, -- Total correct answers
    max_score INTEGER DEFAULT 24, -- Total questions
    level VARCHAR(20) CHECK (level IN ('junior', 'middle', 'senior')), -- Final assessed level
    completed BOOLEAN DEFAULT FALSE,

    -- Indexes
    INDEX idx_user_test_time_user (user_id),
    INDEX idx_user_test_time_completed (completed),
    INDEX idx_user_test_time_dates (created_date, start_time, end_time)
);

-- Add foreign key to user_questions and user_results
ALTER TABLE hr_test.user_questions
    ADD CONSTRAINT fk_user_questions_session
    FOREIGN KEY (test_session_id)
    REFERENCES hr_test.user_test_time(id)
    ON DELETE CASCADE;

ALTER TABLE hr_test.user_results
    ADD CONSTRAINT fk_user_results_session
    FOREIGN KEY (test_session_id)
    REFERENCES hr_test.user_test_time(id)
    ON DELETE CASCADE;

-- =====================================================
-- OPTIONAL: Self-assessment and manager ratings tables
-- (Keep from V1 if needed)
-- =====================================================
CREATE TABLE IF NOT EXISTS hr_test.competency_self_assessments (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES hr_test.users(id) ON DELETE CASCADE,
    test_session_id INTEGER NOT NULL REFERENCES hr_test.user_test_time(id) ON DELETE CASCADE,
    competency_id INTEGER NOT NULL REFERENCES hr_test.competencies(id) ON DELETE CASCADE,
    self_rating INTEGER NOT NULL CHECK (self_rating BETWEEN 1 AND 10),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(test_session_id, competency_id)
);

CREATE TABLE IF NOT EXISTS hr_test.manager_competency_ratings (
    id SERIAL PRIMARY KEY,
    test_session_id INTEGER NOT NULL REFERENCES hr_test.user_test_time(id) ON DELETE CASCADE,
    competency_id INTEGER NOT NULL REFERENCES hr_test.competencies(id) ON DELETE CASCADE,
    manager_id INTEGER NOT NULL REFERENCES hr_test.users(id) ON DELETE CASCADE,
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 10),
    comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(test_session_id, competency_id, manager_id)
);

-- =====================================================
-- GRANT PERMISSIONS (adjust username as needed)
-- =====================================================
-- GRANT ALL PRIVILEGES ON SCHEMA hr_test TO your_app_user;
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA hr_test TO your_app_user;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA hr_test TO your_app_user;

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
-- 7. users (tab_number, not phone)
-- 8. user_questions
-- 9. user_results
-- 10. user_test_time
-- 11. competency_self_assessments (optional)
-- 12. manager_competency_ratings (optional)
-- =====================================================
