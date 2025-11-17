"""
Question Selection Algorithm for HR Testing Platform V2

This module implements the probabilistic weighted distribution algorithm
for selecting test questions. Each test consists of 20 triplets (60 questions total).

Key Concept:
- Each topic (theme) belongs to ONE level only (junior OR middle OR senior)
- A triplet consists of 3 questions from the SAME competency but DIFFERENT levels
- Questions are selected from different topics within the same competency
"""

import random
import math
from typing import List, Dict, Any


def calculate_theme_distribution(competencies: List[Dict[str, Any]], total_themes: int = 20) -> Dict[int, int]:
    """
    Calculate how many triplets (themes) to assign to each competency based on weights.

    Uses the probabilistic weighted distribution algorithm:
    1. cnt = weight * total_themes (normalized)
    2. int = floor(cnt)
    3. top = total_themes - sum(int)
    4. diff = cnt - int
    5. prob = random(0, diff)
    6. Sort by prob descending
    7. gen = 1 for top N, 0 for rest
    8. k = gen + int

    Args:
        competencies: List of competency dicts with 'id' and 'weight'
        total_themes: Total number of triplets to distribute (default 20)

    Returns:
        Dict mapping competency_id to number of triplets
    """

    if not competencies:
        return {}

    # Normalize weights to sum to 1.0
    total_weight = sum(comp['weight'] for comp in competencies)

    if total_weight == 0:
        # Equal distribution if no weights
        equal_share = total_themes // len(competencies)
        return {comp['id']: equal_share for comp in competencies}

    # Step 1: Calculate cnt for each competency
    working = []
    for comp in competencies:
        normalized_weight = comp['weight'] / total_weight
        cnt = normalized_weight * total_themes
        int_part = math.floor(cnt)
        diff = cnt - int_part

        working.append({
            'id': comp['id'],
            'cnt': cnt,
            'int': int_part,
            'diff': diff
        })

    # Step 3: Calculate top (remaining themes to distribute)
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
    if total != total_themes:
        print(f"⚠️  Distribution warning: {total} != {total_themes}, adjusting...")
        # Adjust if needed
        diff = total_themes - total
        if diff > 0:
            # Add to highest weighted competency
            max_comp = max(distribution.keys(), key=lambda x: distribution[x])
            distribution[max_comp] += diff
        elif diff < 0:
            # Remove from lowest weighted competency
            min_comp = min(distribution.keys(), key=lambda x: distribution[x])
            distribution[min_comp] = max(0, distribution[min_comp] + diff)

    return distribution


async def generate_test_themes_v2(user_id: int, test_session_id: int, specialization_id: int, conn):
    """
    Generate 20 triplets for a test (60 questions total)

    NEW ALGORITHM (based on JSON structure):
    1. Get competencies for specialization (with weights)
    2. Calculate triplet distribution by weight (how many triplets per competency)
    3. For each competency with N triplets:
       - Get N junior questions (from junior-level topics)
       - Get N middle questions (from middle-level topics)
       - Get N senior questions (from senior-level topics)
    4. Combine into triplets and store in user_questions table

    Key Understanding:
    - Each topic (theme) belongs to ONE level only (junior OR middle OR senior)
    - A triplet = 1 junior + 1 middle + 1 senior from the SAME competency
    - These come from DIFFERENT topics but the SAME competency

    Args:
        user_id: User ID
        test_session_id: Test session ID
        specialization_id: Specialization ID
        conn: Database connection

    Returns:
        Number of questions generated (should be 60)
    """

    async with conn.cursor() as cur:
        # DEBUG: Check database state
        print(f"\n{'='*60}")
        print(f"🔍 Question Algorithm V2 - CORRECTED")
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
        print(f"   Found {len(rows)} competencies")

        competencies = []
        for row in rows:
            competencies.append({
                'id': row[0],
                'name': row[1],
                'weight': float(row[2])
            })

        if not competencies:
            await cur.execute("SELECT id, name FROM specializations ORDER BY id")
            specs = await cur.fetchall()
            print(f"\n❌ ERROR: No competencies found for specialization_id={specialization_id}")
            print(f"Available specializations:")
            for spec_id, spec_name in specs:
                print(f"  - ID {spec_id}: {spec_name}")
            raise Exception(f"No competencies found for specialization_id={specialization_id}")

        print(f"\n📊 Found {len(competencies)} competencies:")
        for comp in competencies:
            print(f"   - {comp['name']} (weight: {comp['weight']:.4f})")

        # 2. Calculate triplet distribution
        print(f"\n2️⃣ Calculating triplet distribution for 20 triplets...")
        triplet_distribution = calculate_theme_distribution(competencies, total_themes=20)

        print(f"\n📈 Triplet distribution:")
        total_assigned = 0
        for comp_id, num_triplets in triplet_distribution.items():
            comp_name = next(c['name'] for c in competencies if c['id'] == comp_id)
            print(f"   - {comp_name}: {num_triplets} triplets ({num_triplets * 3} questions)")
            total_assigned += num_triplets
        print(f"   TOTAL: {total_assigned} triplets = {total_assigned * 3} questions")

        # 3. For each competency, get questions by level
        print(f"\n3️⃣ Selecting questions for each competency...")
        questions_to_insert = []
        question_order = 1

        for comp in competencies:
            comp_id = comp['id']
            num_triplets = triplet_distribution.get(comp_id, 0)

            if num_triplets == 0:
                continue

            print(f"\n   Processing '{comp['name']}' (ID: {comp_id}):")
            print(f"     Need: {num_triplets} triplets")

            # Check available questions per level for this competency
            level_questions = {}
            for level in ['junior', 'middle', 'senior']:
                await cur.execute("""
                    SELECT q.id, q.question_text, t.id as topic_id
                    FROM questions q
                    JOIN topics t ON t.id = q.topic_id
                    WHERE t.competency_id = %s AND LOWER(q.level) = %s
                    ORDER BY RANDOM()
                """, (comp_id, level))

                questions = await cur.fetchall()
                level_questions[level] = questions
                print(f"     {level.upper()} questions available: {len(questions)}")

            # Check if we have enough questions
            min_available = min(len(level_questions[level]) for level in ['junior', 'middle', 'senior'])

            if min_available == 0:
                print(f"     ❌ Missing questions for some levels! Skipping this competency.")
                continue

            if min_available < num_triplets:
                print(f"     ⚠️  Only {min_available} triplets possible (needed {num_triplets})")
                num_triplets = min_available

            # Select questions for each triplet
            for i in range(num_triplets):
                for level in ['junior', 'middle', 'senior']:
                    if i < len(level_questions[level]):
                        q_id, q_text, topic_id = level_questions[level][i]

                        questions_to_insert.append((
                            user_id,
                            test_session_id,
                            specialization_id,
                            comp_id,
                            topic_id,
                            q_id,
                            question_order,
                            q_text  # Still encrypted
                        ))
                        question_order += 1

            print(f"     ✅ Selected {num_triplets} triplets")

        # 4. Batch insert questions
        print(f"\n4️⃣ Inserting questions into database...")
        if questions_to_insert:
            await cur.executemany("""
                INSERT INTO user_questions
                (user_id, test_session_id, specialization_id, competency_id, topic_id,
                 question_id, question_order, question_text)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, questions_to_insert)

            print(f"   ✅ Inserted {len(questions_to_insert)} questions")
        else:
            print(f"   ❌ No questions to insert!")

        print(f"\n{'='*60}")
        print(f"✅ RESULT: Generated {len(questions_to_insert)} questions (target: 60)")
        print(f"{'='*60}")

        return len(questions_to_insert)


# =====================================================
# HELPER FUNCTIONS FOR TESTING
# =====================================================

def test_theme_distribution():
    """Test theme distribution calculation"""

    # Test case 1: 3 competencies
    competencies = [
        {'id': 1, 'weight': 0.45, 'name': 'SQL Skills'},
        {'id': 2, 'weight': 0.35, 'name': 'Python'},
        {'id': 3, 'weight': 0.20, 'name': 'Statistics'}
    ]

    distribution = calculate_theme_distribution(competencies, 20)
    print("Test case 1 (3 competencies):")
    for comp in competencies:
        print(f"  {comp['name']} (weight {comp['weight']}): {distribution[comp['id']]} triplets")
    print(f"  Total: {sum(distribution.values())}")

    # Test case 2: 5 competencies (equal weights)
    competencies = [
        {'id': 1, 'weight': 0.20},
        {'id': 2, 'weight': 0.20},
        {'id': 3, 'weight': 0.20},
        {'id': 4, 'weight': 0.20},
        {'id': 5, 'weight': 0.20}
    ]

    distribution = calculate_theme_distribution(competencies, 20)
    print("\nTest case 2 (5 equal competencies):")
    for comp in competencies:
        print(f"  Comp {comp['id']} (weight {comp['weight']}): {distribution[comp['id']]} triplets")
    print(f"  Total: {sum(distribution.values())}")


if __name__ == "__main__":
    test_theme_distribution()
