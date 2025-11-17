# Question Algorithm - Complete Explanation

## Quick Summary

**When**: Runs every time a user starts a test
**Where**: `db/question_algorithm_v2.py` line 117
**Input**: User's specialization_id
**Output**: 60 questions (20 themes × 3 levels)

---

## Flow Diagram

```
User Starts Test
    ↓
main_v2.py: POST /api/start-test (line 576)
    ↓
Create test session in user_test_time table
    ↓
question_algorithm_v2.py: generate_test_themes_v2()
    ↓
1. Query database:
   SELECT id, name, weight FROM competencies WHERE specialization_id = X
    ↓
2. Calculate distribution:
   calculate_theme_distribution(competencies, total_themes=20)
    ↓
3. For each competency:
   - Select N random themes
   - For each theme: get 1 junior + 1 middle + 1 senior question
    ↓
4. Insert 60 questions into user_questions table
    ↓
Return test_session_id
    ↓
Frontend displays 60 questions
```

---

## Algorithm Steps (Your Probabilistic Distribution)

### Input Example:
```python
competencies = [
    {'id': 1, 'name': 'SQL Skills', 'weight': 0.47},
    {'id': 2, 'name': 'Python', 'weight': 0.33},
    {'id': 3, 'name': 'Statistics', 'weight': 0.20}
]
total_themes = 20
```

### Step 1: Calculate `cnt = weight * total_themes`
```python
# Normalized (weights already sum to 1.0)
Comp 1: 0.47 * 20 = 9.4
Comp 2: 0.33 * 20 = 6.6
Comp 3: 0.20 * 20 = 4.0
```

### Step 2: Get integer part `int = floor(cnt)`
```python
Comp 1: floor(9.4) = 9
Comp 2: floor(6.6) = 6
Comp 3: floor(4.0) = 4
```

### Step 3: Calculate remaining `top = total_themes - sum(int)`
```python
sum(int) = 9 + 6 + 4 = 19
top = 20 - 19 = 1  # Need to distribute 1 more theme
```

### Step 4: Calculate fractional parts `diff = cnt - int`
```python
Comp 1: 9.4 - 9 = 0.4
Comp 2: 6.6 - 6 = 0.6
Comp 3: 4.0 - 4 = 0.0
```

### Step 5: Generate random probability `prob = random(0, diff)`
```python
Comp 1: random(0, 0.4) = 0.23
Comp 2: random(0, 0.6) = 0.51  ← Highest!
Comp 3: random(0, 0.0) = 0.00
```

### Step 6: Sort by `prob` (descending)
```python
Sorted order: [Comp 2, Comp 1, Comp 3]
```

### Step 7: Assign extra themes `gen = 1 for top N`
```python
top = 1, so give +1 to top 1 competency

Comp 1: gen = 0
Comp 2: gen = 1  ← Gets the extra theme
Comp 3: gen = 0
```

### Step 8: Final count `k = gen + int`
```python
Comp 1: 0 + 9 = 9 themes
Comp 2: 1 + 6 = 7 themes
Comp 3: 0 + 4 = 4 themes

Total: 9 + 7 + 4 = 20 themes ✓
```

---

## Database Structure

### Competencies Table:
```sql
CREATE TABLE competencies (
    id SERIAL PRIMARY KEY,
    specialization_id INTEGER,
    name VARCHAR(500),
    weight DECIMAL(5,2)  -- THIS IS WHAT THE ALGORITHM USES
);

-- Example data:
INSERT INTO competencies (specialization_id, name, weight) VALUES
    (1, 'SQL Skills', 0.45),
    (1, 'Python Programming', 0.35),
    (1, 'Statistical Analysis', 0.20);
```

### How Algorithm Reads It:
```python
async with conn.cursor() as cur:
    await cur.execute("""
        SELECT id, name, weight
        FROM competencies
        WHERE specialization_id = %s
        ORDER BY weight DESC
    """, (specialization_id,))

    competencies = []
    for row in await cur.fetchall():
        competencies.append({
            'id': row[0],
            'name': row[1],
            'weight': float(row[2])  # Uses this weight
        })
```

---

## When HR Sends Excel File

### Step 1: HR Creates Excel
```
File: competencies.xlsx

| competency_name        | weight |
|------------------------|--------|
| SQL Skills             | 45     |
| Python Programming     | 35     |
| Statistical Analysis   | 20     |
```

### Step 2: You Run Script
```bash
python update_weights_from_excel.py competencies.xlsx
```

### Step 3: Script Updates Database
```python
# Script does:
1. Reads Excel
2. Normalizes weights (45+35+20=100 → 0.45, 0.35, 0.20)
3. Updates database:
   UPDATE competencies SET weight = 0.45 WHERE name = 'SQL Skills'
   UPDATE competencies SET weight = 0.35 WHERE name = 'Python Programming'
   UPDATE competencies SET weight = 0.20 WHERE name = 'Statistical Analysis'
```

### Step 4: Algorithm Automatically Uses New Weights
Next time a user starts a test:
- Algorithm queries database
- Gets updated weights
- Distributes themes accordingly

**No code changes needed!**

---

## Theme Selection (After Distribution)

After calculating how many themes each competency should have:

```python
# Example: Comp 1 needs 9 themes

# 1. Get all topics for this competency
await cur.execute("""
    SELECT id, name FROM topics WHERE competency_id = 1
""")
# Returns: 43 topics (from JSON file)

# 2. Randomly select 9 topics
chosen_topics = random.sample(available_topics, 9)

# 3. For each topic, get 3 questions:
for topic_id in chosen_topics:
    # Get 1 junior question
    SELECT * FROM questions WHERE topic_id = X AND level = 'junior' ORDER BY RANDOM() LIMIT 1

    # Get 1 middle question
    SELECT * FROM questions WHERE topic_id = X AND level = 'middle' ORDER BY RANDOM() LIMIT 1

    # Get 1 senior question
    SELECT * FROM questions WHERE topic_id = X AND level = 'senior' ORDER BY RANDOM() LIMIT 1
```

Result: 9 themes × 3 questions = 27 questions from Comp 1

---

## Final Result

| Competency | Weight | Themes | Questions |
|------------|--------|--------|-----------|
| SQL Skills | 0.45   | 9      | 27        |
| Python     | 0.35   | 7      | 21        |
| Statistics | 0.20   | 4      | 12        |
| **Total**  | 1.00   | **20** | **60**    |

---

## Files Involved

1. **`db/question_algorithm_v2.py`**
   - `calculate_theme_distribution()` - Your probabilistic algorithm
   - `generate_test_themes_v2()` - Main function (called when test starts)

2. **`main_v2.py`** (line 576)
   - `POST /api/start-test` - Triggers algorithm

3. **`db/database_v2.py`**
   - Database connection (reads competencies table)

4. **`update_weights_from_excel.py`** (NEW!)
   - Updates weights from HR Excel file

5. **Database**:
   - `competencies` table - Stores weights
   - `topics` table - Themes for each competency
   - `questions` table - 60 questions (J/M/S per topic)
   - `user_questions` table - 60 questions assigned to user

---

## Testing the Algorithm

```bash
# Test with sample data
python db/question_algorithm_v2.py

# Output:
# Test case 1:
#   Core Skill (weight 90.0): 9 themes
#   Important Skill (weight 70.0): 7 themes
#   Basic Skill (weight 40.0): 4 themes
#   Total: 20 ✓
```

---

## Key Points

✅ Runs **every time** a user starts a test
✅ Weights stored in **database** (not hardcoded)
✅ HR can update weights via **Excel file**
✅ Algorithm **automatically uses** new weights
✅ Produces exactly **20 themes = 60 questions**
✅ **Probabilistic** distribution for fairness

---

## Questions?

- **Q: Can weights be changed while system is running?**
  A: Yes! Update database, no restart needed.

- **Q: Do weights have to sum to 1.0?**
  A: No, algorithm normalizes them automatically.

- **Q: What if a competency has fewer topics than needed?**
  A: Algorithm uses all available topics from that competency.

- **Q: Is theme selection random?**
  A: Yes, themes are randomly selected from each competency.

- **Q: Are questions random?**
  A: Yes, 1 random question per level per theme.
