# HR Testing Platform V2 - LDAP Migration

## 🎯 What Changed?

### Summary
Migrated from phone-based authentication to LDAP with tab_number, and from 24 questions to 60 questions (20 triplets).

| Feature | V1 (Old) | V2 (New) |
|---------|----------|----------|
| **Database Schema** | `hr` | `hr_test` |
| **User ID** | Phone number | Tab number |
| **Authentication** | Phone + manual | LDAP + tab_number |
| **Questions per test** | 24 (8 topics × 3 levels) | 60 (20 topics × 3 levels) |
| **Question selection** | Random by topic | Weight-based by competency |
| **Question storage** | Plain text | Encrypted (Fernet) |
| **User model** | name, surname, phone | name, tab_number |

---

## 📁 File Structure (V2)

```
hr/
├── config_v2.py                # V2 configuration
├── auth_v2.py                  # JWT with tab_number
├── main_v2.py                  # Refactored API (936 lines)
├── db/
│   ├── database_v2.py          # DB pool with hr_test schema
│   ├── init_db_v2.sql          # New database schema
│   ├── load_questions_v2.py    # Load encrypted questions
│   └── question_algorithm_v2.py # 20 triplets algorithm
├── specializations/output/final/
│   └── Data_Analyst_encrypted_questions.json
└── MIGRATION_PLAN_V2.md        # Migration guide
```

---

## 🚀 Quick Start (V2)

### 1. Create Database Schema

```bash
# Connect to PostgreSQL
psql -h 10.23.14.188 -U admin -d cds_hb_main

# Run schema creation
\i db/init_db_v2.sql

# Verify tables created
\dt hr_test.*
```

### 2. Load Questions

```bash
# Questions will be stored ENCRYPTED
python db/load_questions_v2.py
```

Expected output:
```
🚀 Starting question loader (Schema V2)...
📌 Questions will be stored ENCRYPTED (decryption handled later)
📁 Loading: Data_Analyst_encrypted_questions.json
   ✅ Created profile: Data Analyst
   ✅ Created specialization: Data Analyst

   📊 Level: JUNIOR (43 themes)
   📊 Level: MIDDLE (42 themes)
   📊 Level: SENIOR (43 themes)

   ✅ Loaded: 256 questions from 128 themes
```

### 3. Manually Assign User Specializations

```sql
-- Example: Assign "Data Analyst" specialization to user
UPDATE hr_test.users
SET specialization_id = (SELECT id FROM hr_test.specializations WHERE name = 'Data Analyst')
WHERE tab_number = '00061221';
```

### 4. Update Environment Variables

```bash
# .env file
DATABASE_URL="postgresql://user:pass@10.23.14.188:5432/cds_hb_main"
LDAP_ENABLED=True
LDAP_DOMAIN=UNIVERSAL
LDAP_HOST=your-ldap-server
PERMITTED_USERS="00061221:Danial Aibassov:hr:read,write,admin"
JWT_SECRET_KEY="your-strong-secret-key-min-32-chars"
```

### 5. Run Application

```bash
# Development
python main_v2.py

# Production (with Gunicorn)
gunicorn main_v2:app \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000
```

---

## 🔑 API Endpoints (V2)

### Authentication
```bash
# Login with tab_number
POST /api/login
{
  "tab_number": "00061221",
  "password": "user_password"
}

Response:
{
  "status": "success",
  "token": "eyJ0eXAiOiJKV1QiLCJ...",
  "user": {
    "id": 1,
    "name": "Danial Aibassov",
    "tab_number": "00061221",
    "role": "employee",
    "specialization_id": 1
  }
}
```

### Test Flow
```bash
# 1. Start test (generates 60 questions)
POST /api/start-test
Headers: Authorization: Bearer <token>

Response:
{
  "status": "success",
  "test_session_id": 1,
  "total_questions": 60,
  "specialization": "Data Analyst"
}

# 2. Get questions
GET /api/test/1/questions
Headers: Authorization: Bearer <token>

Response:
{
  "status": "success",
  "questions": [
    {
      "question_id": 123,
      "question_order": 1,
      "level": "junior",
      "question_text": "gAAAAABpDXtX...",  // ENCRYPTED
      "var_1": "gAAAAABpDXtX...",
      "var_2": "gAAAAABpDXtX...",
      "var_3": "gAAAAABpDXtX...",
      "var_4": "gAAAAABpDXtX...",
      "competency_name": "SQL Skills"
    }
  ],
  "total": 60
}

# 3. Submit answer
POST /api/submit-answer
{
  "test_session_id": 1,
  "question_id": 123,
  "user_answer": 2
}

Response:
{
  "status": "success",
  "correct": true,
  "correct_answer": 2
}

# 4. Complete test
POST /api/complete-test/1

Response:
{
  "status": "success",
  "score": 45,
  "max_score": 60,
  "percentage": 75.0,
  "level": "middle",
  "recommendation": "..."
}

# 5. View results
GET /api/results/1

Response:
{
  "status": "success",
  "score": 45,
  "max_score": 60,
  "percentage": 75.0,
  "level": "middle",
  "competencies": [
    {
      "name": "SQL Skills",
      "total": 12,
      "correct": 9,
      "percentage": 75.0
    }
  ]
}
```

---

## 🧪 Question Selection Algorithm

### How 60 Questions are Generated

```python
# For specialization "Data Analyst" with 4 competencies:
#
# Competency A (weight: 90) → 9 themes (9×3 = 27 questions)
# Competency B (weight: 70) → 7 themes (7×3 = 21 questions)
# Competency C (weight: 50) → 4 themes (4×3 = 12 questions)
# Total: 20 themes × 3 levels = 60 questions

# Each theme contributes 3 questions:
# - 1 junior question
# - 1 middle question
# - 1 senior question
```

**Algorithm Steps**:
1. Get all competencies for specialization (sorted by weight)
2. Distribute 20 themes proportionally by weight
3. Randomly select themes from each competency
4. For each theme, select 1 question from each level (J/M/S)
5. Result: 60 questions total

See `db/question_algorithm_v2.py` for implementation.

---

## 🔐 Question Encryption

Questions are stored **encrypted** using Fernet (symmetric encryption).

**Current state**: Encrypted in database
**Future**: Decrypt on frontend or create decrypt endpoint

Example encrypted question:
```
"question": "gAAAAABpDXtXwauaZPoVhdLpGOvY9lo8g6W6SonVpsWmXr..."
```

To decrypt later, set in `.env`:
```
QUESTION_ENCRYPTION_KEY="your-fernet-key-here=="
```

---

## 👥 User Management

### How Users Work in V2

1. **LDAP Authentication**: User logs in with tab_number + password
2. **Auto-creation**: If user doesn't exist, created automatically
3. **Specialization Assignment**: HR manually sets `specialization_id`
4. **Role**: Default is `employee`, can be set to `manager` or `hr`

### Assign Specialization to User

```sql
-- 1. View available specializations
SELECT * FROM hr_test.specializations;

-- 2. Assign to user
UPDATE hr_test.users
SET specialization_id = 1  -- Data Analyst
WHERE tab_number = '00061221';

-- 3. Verify
SELECT u.name, u.tab_number, s.name as specialization
FROM hr_test.users u
LEFT JOIN hr_test.specializations s ON s.id = u.specialization_id
WHERE u.tab_number = '00061221';
```

---

## 📊 Database Schema (hr_test)

### Core Tables

1. **users**: User information
   - `id`, `name`, `tab_number` (unique), `role`, `department_id`, `specialization_id`

2. **departments**: 4 departments
   - Halyk Super App, OnlineBank, OCDS, AI

3. **profiles**: Test categories
   - "Data Analyst", "Backend Developer", etc.

4. **specializations**: Skill areas under profiles
   - "Data Analyst", "Python", "C# / .NET", etc.

5. **competencies**: Core skills
   - "SQL Skills", "Python Programming", etc.
   - Has `weight` field (importance)

6. **topics**: Knowledge areas (themes)
   - "Basic SQL queries", "Aggregation functions", etc.

7. **questions**: All questions (encrypted)
   - `level` (junior/middle/senior)
   - `question_text`, `var_1-4` (encrypted)
   - `correct_answer` (1-4)

8. **user_test_time**: Test sessions
   - `user_id`, `test_session_id`, `score`, `level`, `completed`

9. **user_questions**: Questions assigned to user's test
   - Links user → test_session → question

10. **user_results**: User answers
    - `question_id`, `user_answer`, `correct` (0/1)

---

## 🔧 Configuration (config_v2.py)

```python
# Key settings
DB_SCHEMA = "hr_test"
THEMES_PER_TEST = 20
QUESTIONS_PER_TRIPLET = 3
TOTAL_QUESTIONS = 60

# LDAP
LDAP_ENABLED = True
LDAP_DOMAIN = "UNIVERSAL"
LDAP_HOST = "ldap-server"

# JWT
JWT_SECRET_KEY = "your-secret-key"
ACCESS_TOKEN_EXPIRE_DAYS = 7
```

---

## ✅ Testing Checklist

### Database
- [ ] Schema `hr_test` created
- [ ] 4 departments inserted
- [ ] Questions loaded (check count: `SELECT COUNT(*) FROM hr_test.questions;`)
- [ ] Verify encryption: `SELECT question_text FROM hr_test.questions LIMIT 1;`

### Authentication
- [ ] LDAP enabled in `.env`
- [ ] Can login with tab_number
- [ ] JWT token generated
- [ ] User auto-created on first login

### Test Flow
- [ ] Can start test (60 questions generated)
- [ ] Can retrieve questions
- [ ] Can submit answers
- [ ] Can complete test
- [ ] Score calculated correctly

### User Management
- [ ] User has specialization assigned
- [ ] Cannot start test without specialization
- [ ] Tab_number is unique

---

## 🐛 Common Issues

### Issue: "User has no specialization assigned"
**Solution**: Manually assign specialization in database
```sql
UPDATE hr_test.users SET specialization_id = 1 WHERE tab_number = '00061221';
```

### Issue: "Not all questions answered (50/60)"
**Cause**: Missing questions in database
**Solution**: Re-run question loader or check JSON file

### Issue: "Database pool not initialized"
**Cause**: DATABASE_URL incorrect
**Solution**: Verify `.env` has correct connection string

### Issue: LDAP authentication failed
**Cause**: LDAP server unreachable or credentials wrong
**Solution**: Test LDAP separately, check `login_history.log`

---

## 📈 Performance

### Expected Capacity (V2)

- **Concurrent users**: 200+ (with 300 DB connections)
- **Questions per test**: 60 (vs 24 in V1)
- **Database size**: ~10MB per 1000 tests
- **Response time**: <500ms for question generation

### Optimizations

1. **Connection pooling**: 300 max connections (increased from 150)
2. **Batch operations**: All 60 questions inserted in 1-2 queries
3. **Encrypted storage**: Questions stay encrypted (faster than decrypting)

---

## 🚀 Deployment

### Production Deployment Steps

1. **Backup current database**
   ```bash
   pg_dump -h 10.23.14.188 -U admin -d cds_hb_main -n hr > hr_backup.sql
   ```

2. **Create hr_test schema**
   ```bash
   psql -h 10.23.14.188 -U admin -d cds_hb_main -f db/init_db_v2.sql
   ```

3. **Load questions**
   ```bash
   python db/load_questions_v2.py
   ```

4. **Update systemd service**
   ```bash
   # Edit hr-testing.service
   ExecStart=/path/to/venv/bin/gunicorn main_v2:app ...

   sudo systemctl daemon-reload
   sudo systemctl restart hr-testing
   ```

5. **Verify deployment**
   ```bash
   curl http://localhost:8000/health
   # Should return: {"status":"ok","service":"hr-testing-v2","schema":"hr_test"}
   ```

---

## 📞 Support

For issues:
- Check logs: `/var/log/hr_testing/error.log`
- Test database: `psql -h 10.23.14.188 -U admin -d cds_hb_main`
- LDAP logs: `tail -f login_history.log`

---

**Status**: ✅ V2 Complete and Ready for Testing
**Branch**: `refactor/ldap-migration-v2`
**Files**: 9 files changed, 2132 lines added
