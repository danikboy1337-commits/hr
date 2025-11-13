# Migration Plan: V1 → V2 (LDAP + New Question Structure)

## Overview
This document outlines the migration from phone-based authentication to LDAP + tab_number, and from the old question structure to the new encrypted JSON format.

---

## Key Changes

### 1. Authentication
- **OLD**: Phone number (`+77001234567`)
- **NEW**: Tab number (`00061221`) via LDAP

### 2. Database Schema
- **OLD**: Schema `hr`, phone-based users
- **NEW**: Schema `hr_test`, tab_number-based users

### 3. Question Structure
**OLD** (Questions.json):
```
Profile → Specialization → Competency → Topic → Questions (3 per topic)
- 4 competencies × 4 topics × 3 levels = 48 questions
- Test selects 8 random topics = 24 questions
```

**NEW** (Data_Analyst_encrypted_questions.json):
```
Profile → Specialization → Levels → Themes → Questions
- Levels: junior (43 themes) + middle (42) + senior (43) = 128 themes
- Questions are encrypted
- Multiple questions per theme
```

### 4. Question Algorithm
- **OLD**: Select 8 topics by competency importance, 3 questions per topic (J/M/S)
- **NEW**: Select questions across all 3 levels in order (junior → middle → senior)

---

## Database Schema V2

### Core Tables
1. `users` - **tab_number** (not phone), department_id, specialization_id
2. `departments` - 4 departments (Halyk Super App, OnlineBank, OCDS, AI)
3. `profiles` - Test categories
4. `specializations` - Skill areas
5. `competencies` - Core skills (with weight)
6. `topics` - Knowledge areas (formerly "themes")
7. `questions` - All questions (decrypted)
8. `user_questions` - Questions assigned to user's test
9. `user_results` - User answers (0 or 1 for correct)
10. `user_test_time` - Test timing and scoring

---

## Files Created

### 1. `db/init_db_v2.sql`
New database schema for hr_test

**Usage**:
```bash
psql -h 10.23.14.188 -U admin -d cds_hb_main -f db/init_db_v2.sql
```

### 2. `db/load_questions_v2.py`
Loads encrypted JSON files into database

**Usage**:
```bash
# Without decryption (questions stay encrypted)
python db/load_questions_v2.py

# With decryption key
python db/load_questions_v2.py --decrypt-key YOUR_FERNET_KEY
```

---

## Questions to Resolve

### 1. Encryption
- Do you have the Fernet decryption key for the questions?
- Should questions be decrypted before database insertion?
- Or decrypt on-the-fly when serving to frontend?

### 2. Test Algorithm
With 128 themes, how should questions be selected?
- **Option A**: 24 total (8 junior + 8 middle + 8 senior)
- **Option B**: Different count per level based on user's role
- **Option C**: Adaptive (start junior, progress if correct)

### 3. Multiple Specializations
- Only `Data_Analyst_encrypted_questions.json` exists currently
- How many total specializations will you have?
- One JSON file per specialization?

### 4. User Profile Assignment
How is user's specialization determined?
- **Option A**: HR admin assigns manually in database
- **Option B**: User selects during first login
- **Option C**: Automatically from LDAP attribute

### 5. Migration Strategy
- **Clean slate**: New schema, start fresh (lose existing data)?
- **Data migration**: Keep users and test results from V1?

---

## Next Steps (After Questions Resolved)

### Phase 1: Database Setup
- [ ] Run `init_db_v2.sql` to create schema
- [ ] Load questions with `load_questions_v2.py`
- [ ] Verify data integrity

### Phase 2: Code Refactoring
- [ ] Create `main_v2.py` (tab_number instead of phone)
- [ ] Update LDAP authentication
- [ ] Create new question generation algorithm
- [ ] Update API endpoints
- [ ] Remove phone-based logic

### Phase 3: Frontend Updates
- [ ] Update login form (tab_number input)
- [ ] Update test interface
- [ ] Update results display

### Phase 4: Testing
- [ ] Unit tests for question selection
- [ ] Integration tests for API endpoints
- [ ] Load testing with Locust

### Phase 5: Deployment
- [ ] Backup existing database
- [ ] Deploy new schema
- [ ] Update .env variables
- [ ] Restart service

---

## Migration Checklist

### Pre-Migration
- [ ] Backup current database
- [ ] Export existing users (if migrating data)
- [ ] Test new schema on staging server
- [ ] Prepare rollback plan

### Migration
- [ ] Create `hr_test` schema
- [ ] Load departments (4 departments)
- [ ] Load questions from JSON files
- [ ] Migrate users (tab_number from LDAP)
- [ ] Update config.py (schema = hr_test)
- [ ] Deploy new main.py
- [ ] Update nginx/gunicorn config

### Post-Migration
- [ ] Verify LDAP authentication works
- [ ] Test question generation
- [ ] Check user test flow end-to-end
- [ ] Monitor error logs
- [ ] Update documentation

---

## Risk Assessment

### High Risk
1. **Data loss**: If not properly backed up
2. **Authentication failure**: LDAP misconfiguration
3. **Question decryption**: If key is wrong

### Medium Risk
1. **Performance**: New question algorithm may be slower
2. **User confusion**: Different login method (tab_number)

### Low Risk
1. **Frontend updates**: Minimal changes needed
2. **API compatibility**: Endpoints mostly unchanged

---

## Rollback Plan

If migration fails:
1. Keep old `hr` schema intact during migration
2. Test `hr_test` schema separately
3. Switch main.py to point to `hr_test` when ready
4. If issues occur, revert to `hr` schema

---

## Support

For questions or issues during migration:
- Check logs: `/var/log/hr_testing/error.log`
- Test database connection: `psql -h 10.23.14.188 -U admin -d cds_hb_main`
- Verify LDAP: Check `login_history.log`

---

**Status**: ✅ Schema created, ⏳ Awaiting answers to proceed with refactoring
