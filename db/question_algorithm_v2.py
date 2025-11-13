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
from typing import List, Dict, Any


def calculate_theme_distribution(competencies: List[Dict[str, Any]], total_themes: int = 20) -> Dict[int, int]:
    """
    Calculate how many themes to select from each competency based on weight

    Args:
        competencies: List of dicts with 'id' and 'weight' keys
        total_themes: Total themes needed (default 20)

    Returns:
        Dict mapping competency_id -> number of themes to select

    Example:
        competencies = [
            {'id': 1, 'weight': 90.0},
            {'id': 2, 'weight': 70.0},
            {'id': 3, 'weight': 40.0}
        ]
        Result: {1: 9, 2: 7, 3: 4}  # Total = 20
    """

    if not competencies:
        return {}

    # Sort by weight (descending)
    sorted_comps = sorted(competencies, key=lambda x: x['weight'], reverse=True)

    # Calculate total weight
    total_weight = sum(comp['weight'] for comp in sorted_comps)

    if total_weight == 0:
        # If no weights, distribute equally
        themes_per_comp = total_themes // len(sorted_comps)
        remainder = total_themes % len(sorted_comps)
        distribution = {}
        for i, comp in enumerate(sorted_comps):
            distribution[comp['id']] = themes_per_comp + (1 if i < remainder else 0)
        return distribution

    # Calculate proportional distribution
    distribution = {}
    allocated = 0

    for i, comp in enumerate(sorted_comps):
        if i == len(sorted_comps) - 1:
            # Last competency gets remaining themes
            distribution[comp['id']] = total_themes - allocated
        else:
            # Calculate proportional share
            proportion = comp['weight'] / total_weight
            num_themes = int(round(total_themes * proportion))
            distribution[comp['id']] = num_themes
            allocated += num_themes

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
        # 1. Get competencies with weights
        await cur.execute("""
            SELECT id, name, weight
            FROM hr_test.competencies
            WHERE specialization_id = %s
            ORDER BY weight DESC
        """, (specialization_id,))

        competencies = []
        for row in await cur.fetchall():
            competencies.append({
                'id': row[0],
                'name': row[1],
                'weight': float(row[2])
            })

        if not competencies:
            raise Exception(f"No competencies found for specialization_id={specialization_id}")

        print(f"📊 Found {len(competencies)} competencies")
        for comp in competencies:
            print(f"   - {comp['name']}: weight {comp['weight']}")

        # 2. Calculate theme distribution
        theme_distribution = calculate_theme_distribution(competencies, total_themes=20)

        print(f"\n📈 Theme distribution:")
        for comp_id, num_themes in theme_distribution.items():
            comp_name = next(c['name'] for c in competencies if c['id'] == comp_id)
            print(f"   - {comp_name}: {num_themes} themes")

        # 3. Select random themes from each competency
        selected_themes = []

        for comp in competencies:
            comp_id = comp['id']
            num_themes_needed = theme_distribution.get(comp_id, 0)

            if num_themes_needed == 0:
                continue

            # Get all topics (themes) for this competency
            await cur.execute("""
                SELECT id, name
                FROM hr_test.topics
                WHERE competency_id = %s
            """, (comp_id,))

            available_themes = await cur.fetchall()

            if len(available_themes) < num_themes_needed:
                print(f"⚠️  Warning: Competency {comp['name']} has only {len(available_themes)} themes, needed {num_themes_needed}")
                num_themes_needed = len(available_themes)

            # Randomly select themes
            chosen_themes = random.sample(available_themes, num_themes_needed)

            for theme_id, theme_name in chosen_themes:
                selected_themes.append({
                    'competency_id': comp_id,
                    'topic_id': theme_id,
                    'topic_name': theme_name
                })

        print(f"\n✅ Selected {len(selected_themes)} themes")

        # 4. For each theme, get 3 questions (junior, middle, senior)
        question_order = 1
        questions_to_insert = []

        for theme in selected_themes:
            topic_id = theme['topic_id']
            comp_id = theme['competency_id']

            # Get 1 question from each level
            for level in ['junior', 'middle', 'senior']:
                await cur.execute("""
                    SELECT id, question_text
                    FROM hr_test.questions
                    WHERE topic_id = %s AND level = %s
                    ORDER BY RANDOM()
                    LIMIT 1
                """, (topic_id, level))

                question = await cur.fetchone()

                if not question:
                    print(f"⚠️  Warning: No {level} question found for topic {topic_id}")
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
                INSERT INTO hr_test.user_questions
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
