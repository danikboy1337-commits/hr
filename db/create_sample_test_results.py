import asyncio
import sys
import os
import random
from datetime import datetime, timedelta

# FIX для Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import init_db_pool, close_db_pool, get_db_connection


async def create_sample_test_results():
    """Create sample completed test results for demonstration"""

    print("🎯 Creating sample test results...")
    await init_db_pool()

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Get all employees (not HR, not managers)
                await cur.execute("""
                    SELECT id, name, surname, department_id
                    FROM users
                    WHERE role = 'employee'
                    ORDER BY id
                """)
                employees = await cur.fetchall()

                if not employees:
                    print("❌ No employees found. Run create_test_users.py first!")
                    return

                print(f"✓ Found {len(employees)} employees")

                # Get available specializations
                await cur.execute("SELECT id, name FROM specializations ORDER BY id")
                specializations = await cur.fetchall()

                if not specializations:
                    print("❌ No specializations found in database!")
                    return

                print(f"✓ Found {len(specializations)} specializations")

                # Get topics and questions for each specialization
                test_results_created = 0

                for emp_id, emp_name, emp_surname, dept_id in employees:
                    # Each employee takes 1-3 tests
                    num_tests = random.randint(1, min(3, len(specializations)))
                    selected_specs = random.sample(specializations, num_tests)

                    for spec_id, spec_name in selected_specs:
                        # Get topics for this specialization
                        await cur.execute("""
                            SELECT t.id, c.id as competency_id
                            FROM topics t
                            JOIN competencies c ON t.competency_id = c.id
                            WHERE c.specialization_id = %s
                            ORDER BY RANDOM()
                            LIMIT 8
                        """, (spec_id,))
                        topics = await cur.fetchall()

                        if not topics:
                            print(f"  ⚠️  No topics found for {spec_name}, skipping...")
                            continue

                        # Create test
                        started_at = datetime.now() - timedelta(days=random.randint(1, 30),
                                                                  hours=random.randint(0, 23))
                        completed_at = started_at + timedelta(minutes=random.randint(15, 45))

                        # Determine performance level (weighted random)
                        performance_roll = random.random()
                        if performance_roll < 0.15:  # 15% Senior
                            score_percentage = random.uniform(0.67, 0.95)
                        elif performance_roll < 0.50:  # 35% Middle
                            score_percentage = random.uniform(0.34, 0.66)
                        else:  # 50% Junior
                            score_percentage = random.uniform(0.10, 0.33)

                        max_score = 24
                        score = int(max_score * score_percentage)

                        # Insert user_specialization_test
                        await cur.execute("""
                            INSERT INTO user_specialization_tests
                            (user_id, specialization_id, score, max_score, started_at, completed_at)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            RETURNING id
                        """, (emp_id, spec_id, score, max_score, started_at, completed_at))
                        test_id = (await cur.fetchone())[0]

                        # Insert user_test_topics
                        for idx, (topic_id, competency_id) in enumerate(topics, 1):
                            await cur.execute("""
                                INSERT INTO user_test_topics
                                (user_test_id, topic_id, competency_id, topic_order)
                                VALUES (%s, %s, %s, %s)
                            """, (test_id, topic_id, competency_id, idx))

                        # Get questions for each topic (3 questions per topic: Junior, Middle, Senior)
                        questions_to_answer = []
                        for topic_id, _ in topics:
                            await cur.execute("""
                                SELECT id, correct_answer
                                FROM questions
                                WHERE topic_id = %s
                                ORDER BY
                                    CASE level
                                        WHEN 'Junior' THEN 1
                                        WHEN 'Middle' THEN 2
                                        WHEN 'Senior' THEN 3
                                    END,
                                    RANDOM()
                                LIMIT 3
                            """, (topic_id,))
                            topic_questions = await cur.fetchall()
                            questions_to_answer.extend(topic_questions)

                        # Limit to 24 questions total
                        questions_to_answer = questions_to_answer[:24]

                        # Answer questions based on target score
                        correct_needed = score
                        total_questions = len(questions_to_answer)

                        # Randomly determine which questions are correct
                        correct_indices = set(random.sample(range(total_questions), correct_needed))

                        for idx, (question_id, correct_answer) in enumerate(questions_to_answer):
                            is_correct = idx in correct_indices

                            if is_correct:
                                user_answer = correct_answer
                            else:
                                # Pick wrong answer (1-4, but not correct)
                                wrong_answers = [i for i in range(1, 5) if i != correct_answer]
                                user_answer = random.choice(wrong_answers)

                            await cur.execute("""
                                INSERT INTO test_answers
                                (user_test_id, question_id, user_answer, is_correct)
                                VALUES (%s, %s, %s, %s)
                            """, (test_id, question_id, user_answer, is_correct))

                        test_results_created += 1
                        level = 'Senior' if score_percentage >= 0.67 else 'Middle' if score_percentage >= 0.34 else 'Junior'
                        print(f"  ✓ {emp_name} {emp_surname}: {spec_name} - {score}/{max_score} ({int(score_percentage*100)}%) [{level}]")

                await conn.commit()
                print(f"\n✅ Successfully created {test_results_created} sample test results!")
                print(f"\nNow you can:")
                print(f"  1. Login to HR Panel to view all results")
                print(f"  2. Login as a manager to view department-specific results")
                print(f"  3. Check statistics on both panels")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(create_sample_test_results())
