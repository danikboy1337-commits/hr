"""
Question Generation Algorithm V2
For LDAP migration with encrypted questions

Requirements:
- 60 questions total = 20 triplets (20 themes)
- Each triplet = 1 theme with 3 questions (junior, middle, senior)
- Selection based on competency weight
- Questions stay encrypted in database

Algorithm:
1. Get all competencies for user's specialization (with weights)
2. Sort competencies by weight (descending)
3. Distribute 20 themes proportionally by weight
4. Randomly select themes from each competency
5. For each theme, get 3 questions (1 junior, 1 middle, 1 senior)
"""

import random
import math
from typing import List, Dict, Any


def calculate_theme_distribution(competencies: List[Dict[str, Any]], total_themes: int = 20) -> Dict[int, int]:
    """
    Calculate how many themes to select from each competency based on weight
    Uses the probabilistic weighted distribution algorithm from question_algorithm.py

    Algorithm:
    1. cnt = weight * total_themes (normalized)
    2. int = floor(cnt)
    3. top = total_themes - sum(int)
    4. diff = cnt - int
    5. prob = random(0, diff)
    6. Sort by prob descending, give +1 to top N competencies
    7. k = gen + int (final count)

    Args:
        competencies: List of dicts with 'id' and 'weight' keys
        total_themes: Total themes needed (default 20)

    Returns:
        Dict mapping competency_id -> number of themes to select

    Example:
        competencies = [
            {'id': 1, 'weight': 0.45},  # 45%
            {'id': 2, 'weight': 0.35},  # 35%
            {'id': 3, 'weight': 0.20}   # 20%
        ]
        Result: {1: 9, 2: 7, 3: 4}  # Total = 20
    """

    if not competencies:
        return {}

    # Normalize weights to sum to 1.0 (if not already)
    total_weight = sum(comp['weight'] for comp in competencies)
    if total_weight == 0:
        # Equal distribution if no weights
        themes_per_comp = total_themes // len(competencies)
        remainder = total_themes % len(competencies)
        distribution = {}
        for i, comp in enumerate(competencies):
            distribution[comp['id']] = themes_per_comp + (1 if i < remainder else 0)
        return distribution

    # Create working list with calculations
    working = []
    for comp in competencies:
        normalized_weight = comp['weight'] / total_weight

        # Step 1: cnt = weight * total_themes
        cnt = normalized_weight * total_themes

        # Step 2: int = floor(cnt)
        int_part = math.floor(cnt)

        # Step 4: diff = cnt - int
        diff = cnt - int_part

        working.append({
            'id': comp['id'],
            'weight': comp['weight'],
            'cnt': cnt,
            'int': int_part,
            'diff': diff
        })

    # Step 3: top = total_themes - sum(int)
    sum_int = sum(item['int'] for item in working)
    top = total_themes - sum_int

    # Step 5: prob = random(0, diff)
    for item in working:
        item['prob'] = random.uniform(0, item['diff'])

    # Step 6: Sort by prob descending
    working.sort(key=lambda x: x['prob'], reverse=True)

    # Step 7: gen = 1 for top N, 0 for rest
    for i, item in enumerate(working):
        item['gen'] = 1 if i < top else 0

    # Step 8: k = gen + int (final count)
    distribution = {}
    for item in working:
        distribution[item['id']] = item['gen'] + item['int']

    # Verify total
    total = sum(distribution.values())
    assert total == total_themes, f"Distribution error: {total} != {total_themes}"

    return distribution


async def generate_test_themes_v2(user_id: int, test_session_id: int, specialization_id: int, conn):
    """
    Generate 20 themes for a test (60 questions total)

    Algorithm:
    1. Get competencies for specialization (with weights)
    2. Calculate theme distribution by weight
    3. Select random themes from each competency
    4. For each theme, select 3 questions (junior, middle, senior)
    5. Store in user_questions table

    Args:
        user_id: User ID
        test_session_id: Test session ID
        specialization_id: Specialization ID
        conn: Database connection
    """

    async with conn.cursor() as cur:
        # DEBUG: Check database state
        print(f"\n{'='*60}")
        print(f"🔍 DEBUG: Question Algorithm V2")
        print(f"{'='*60}")
        print(f"Specialization ID: {specialization_id}")
        print(f"User ID: {user_id}")
        print(f"Test Session ID: {test_session_id}")

        # Check total data in database
        await cur.execute("SELECT COUNT(*) FROM competencies")
        total_comps = (await cur.fetchone())[0]
        await cur.execute("SELECT COUNT(*) FROM topics")
        total_topics = (await cur.fetchone())[0]
        await cur.execute("SELECT COUNT(*) FROM questions")
        total_questions = (await cur.fetchone())[0]

        print(f"\nDatabase totals:")
        print(f"  - Competencies: {total_comps}")
        print(f"  - Topics: {total_topics}")
        print(f"  - Questions: {total_questions}")

        # 1. Get competencies with weights
        print(f"\n1️⃣ Fetching competencies for specialization_id={specialization_id}...")
        await cur.execute("""
            SELECT id, name, weight
            FROM competencies
            WHERE specialization_id = %s
            ORDER BY weight DESC
        """, (specialization_id,))

        rows = await cur.fetchall()
        print(f"   Query returned {len(rows)} rows")

        competencies = []
        for row in rows:
            competencies.append({
                'id': row[0],
                'name': row[1],
                'weight': float(row[2])
            })

        if not competencies:
            # Check what specializations exist
            await cur.execute("SELECT id, name FROM specializations ORDER BY id")
            specs = await cur.fetchall()
            print(f"\n❌ ERROR: No competencies found for specialization_id={specialization_id}")
            print(f"Available specializations in database:")
            for spec_id, spec_name in specs:
                print(f"  - ID {spec_id}: {spec_name}")

            raise Exception(f"No competencies found for specialization_id={specialization_id}")

        print(f"\n📊 Found {len(competencies)} competencies:")
        for comp in competencies:
            print(f"   - ID {comp['id']}: {comp['name']} (weight: {comp['weight']})")

        # 2. Calculate theme distribution
        print(f"\n2️⃣ Calculating theme distribution for 20 themes...")
        theme_distribution = calculate_theme_distribution(competencies, total_themes=20)

        print(f"\n📈 Theme distribution:")
        total_assigned = 0
        for comp_id, num_themes in theme_distribution.items():
            comp_name = next(c['name'] for c in competencies if c['id'] == comp_id)
            print(f"   - {comp_name}: {num_themes} themes")
            total_assigned += num_themes
        print(f"   TOTAL: {total_assigned} themes assigned")

        # 3. Select topics that have ALL 3 levels of questions (complete triplets)
        print(f"\n3️⃣ Selecting topics with complete triplets (junior + middle + senior)...")
        selected_themes = []

        for comp in competencies:
            comp_id = comp['id']
            num_themes_needed = theme_distribution.get(comp_id, 0)

            print(f"\n   Processing competency '{comp['name']}' (ID: {comp_id}):")
            print(f"     Need: {num_themes_needed} themes")

            if num_themes_needed == 0:
                print(f"     ⏭️  Skipping (0 themes needed)")
                continue

            # First, check what levels exist for this competency
            await cur.execute("""
                SELECT DISTINCT q.level, COUNT(*)
                FROM questions q
                JOIN topics t ON t.id = q.topic_id
                WHERE t.competency_id = %s
                GROUP BY q.level
            """, (comp_id,))
            level_counts = await cur.fetchall()
            print(f"     Levels available: {level_counts}")

            # Check how many topics exist for this competency (without level filter)
            await cur.execute("""
                SELECT COUNT(*) FROM topics WHERE competency_id = %s
            """, (comp_id,))
            total_topics_count = (await cur.fetchone())[0]
            print(f"     Total topics for this competency: {total_topics_count}")

            # Get topics that have questions for ALL 3 levels (complete triplets)
            # Using LOWER() to make case-insensitive
            print(f"     Searching for topics with all 3 levels (junior, middle, senior)...")
            await cur.execute("""
                SELECT DISTINCT t.id, t.name
                FROM topics t
                WHERE t.competency_id = %s
                AND EXISTS (SELECT 1 FROM questions WHERE topic_id = t.id AND LOWER(level) = 'junior')
                AND EXISTS (SELECT 1 FROM questions WHERE topic_id = t.id AND LOWER(level) = 'middle')
                AND EXISTS (SELECT 1 FROM questions WHERE topic_id = t.id AND LOWER(level) = 'senior')
            """, (comp_id,))

            available_themes = await cur.fetchall()
            print(f"     Found {len(available_themes)} topics with complete triplets")

            if len(available_themes) == 0:
                print(f"     ❌ No topics with all 3 levels!")
                continue

            if len(available_themes) < num_themes_needed:
                print(f"     ⚠️  Only {len(available_themes)} complete triplets, needed {num_themes_needed}")
                num_themes_needed = len(available_themes)

            # Randomly select themes
            chosen_themes = random.sample(available_themes, num_themes_needed)
            print(f"     ✅ Selected {len(chosen_themes)} themes")

            for theme_id, theme_name in chosen_themes:
                selected_themes.append({
                    'competency_id': comp_id,
                    'topic_id': theme_id,
                    'topic_name': theme_name
                })

        print(f"\n✅ Selected {len(selected_themes)} themes (all have complete triplets)")

        # 4. For each theme, get 3 questions (junior, middle, senior)
        question_order = 1
        questions_to_insert = []

        for theme in selected_themes:
            topic_id = theme['topic_id']
            comp_id = theme['competency_id']

            # Get 1 question from each level (case-insensitive)
            for level in ['junior', 'middle', 'senior']:
                await cur.execute("""
                    SELECT id, question_text
                    FROM questions
                    WHERE topic_id = %s AND LOWER(level) = %s
                    ORDER BY RANDOM()
                    LIMIT 1
                """, (topic_id, level))

                question = await cur.fetchone()

                if not question:
                    # This should never happen since we pre-filtered for complete triplets
                    print(f"⚠️  ERROR: No {level} question found for topic {topic_id} (should not happen!)")
                    continue

                question_id, question_text = question

                questions_to_insert.append((
                    user_id,
                    test_session_id,
                    specialization_id,
                    comp_id,
                    topic_id,
                    question_id,
                    question_order,
                    question_text  # Still encrypted
                ))

                question_order += 1

        # 5. Batch insert questions
        if questions_to_insert:
            await cur.executemany("""
                INSERT INTO user_questions
                (user_id, test_session_id, specialization_id, competency_id, topic_id,
                 question_id, question_order, question_text)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, questions_to_insert)

        print(f"✅ Generated {len(questions_to_insert)} questions (target: 60)")

        return len(questions_to_insert)


# =====================================================
# HELPER FUNCTIONS FOR TESTING
# =====================================================

def test_theme_distribution():
    """Test theme distribution calculation"""

    # Test case 1: 3 competencies
    competencies = [
        {'id': 1, 'weight': 90.0, 'name': 'Core Skill'},
        {'id': 2, 'weight': 70.0, 'name': 'Important Skill'},
        {'id': 3, 'weight': 40.0, 'name': 'Basic Skill'}
    ]

    distribution = calculate_theme_distribution(competencies, 20)
    print("Test case 1:")
    for comp in competencies:
        print(f"  {comp['name']} (weight {comp['weight']}): {distribution[comp['id']]} themes")
    print(f"  Total: {sum(distribution.values())}")

    # Test case 2: 4 competencies
    competencies = [
        {'id': 1, 'weight': 85.0},
        {'id': 2, 'weight': 75.0},
        {'id': 3, 'weight': 65.0},
        {'id': 4, 'weight': 55.0}
    ]

    distribution = calculate_theme_distribution(competencies, 20)
    print("\nTest case 2:")
    for comp in competencies:
        print(f"  Comp {comp['id']} (weight {comp['weight']}): {distribution[comp['id']]} themes")
    print(f"  Total: {sum(distribution.values())}")


if __name__ == "__main__":
    test_theme_distribution()
