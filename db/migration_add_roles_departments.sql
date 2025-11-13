-- ==========================================
-- MIGRATION: Add Roles and Departments
-- ==========================================

-- 1. Create departments table
CREATE TABLE IF NOT EXISTS departments (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 2. Add role and department to users table
ALTER TABLE users
ADD COLUMN IF NOT EXISTS role VARCHAR(50) DEFAULT 'employee',
ADD COLUMN IF NOT EXISTS department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL;

-- 3. Add index for performance
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_department ON users(department_id);

-- 4. Seed default departments
INSERT INTO departments (name, description) VALUES
    ('Backend Development', 'Backend разработчики'),
    ('Frontend Development', 'Frontend разработчики'),
    ('Mobile Development', 'Mobile разработчики'),
    ('Data Science', 'Data Scientists и аналитики'),
    ('QA', 'Quality Assurance'),
    ('DevOps', 'DevOps инженеры'),
    ('HR', 'Human Resources'),
    ('Management', 'Менеджмент')
ON CONFLICT (name) DO NOTHING;

-- 5. Update existing users to have default values (if any exist)
UPDATE users SET role = 'employee' WHERE role IS NULL;
UPDATE users SET department_id = 1 WHERE department_id IS NULL;

-- ==========================================
-- CONSTRAINTS
-- ==========================================
-- Valid roles: employee, hr, manager
ALTER TABLE users ADD CONSTRAINT check_user_role
CHECK (role IN ('employee', 'hr', 'manager'));

COMMENT ON TABLE departments IS 'Departments/отделы организации';
COMMENT ON COLUMN users.role IS 'User role: employee, hr, or manager';
COMMENT ON COLUMN users.department_id IS 'Department the user belongs to';
