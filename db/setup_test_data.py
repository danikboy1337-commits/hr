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


async def check_and_setup_test_data():
    """Comprehensive script to check database and create all test data"""

    print("=" * 60)
    print("🔍 CHECKING DATABASE AND CREATING TEST DATA")
    print("=" * 60)

    await init_db_pool()

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # ============================================
                # STEP 1: Check existing users
                # ============================================
                print("\n📊 STEP 1: Checking existing users...")
                await cur.execute("SELECT COUNT(*), COUNT(CASE WHEN role='employee' THEN 1 END) FROM users")
                user_counts = await cur.fetchone()
                total_users = user_counts[0]
                employee_count = user_counts[1]

                print(f"   Total users: {total_users}")
                print(f"   Employees: {employee_count}")

                # ============================================
                # STEP 2: Create test users if needed
                # ============================================
                if employee_count < 5:
                    print("\n⚠️  Not enough employees. Creating test users...")

                    test_users = [
                        # HR Users
                        ("HR", "Manager", "+77001111111", "Халык банк", "HR Manager", "hr", 7),
                        ("HR", "Specialist", "+77001111112", "Халык банк", "HR Specialist", "hr", 7),
                        # Managers
                        ("Бекенд", "Руководитель", "+77002222221", "Халык банк", "Backend Team Lead", "manager", 1),
                        ("Фронтенд", "Руководитель", "+77002222222", "Халык банк", "Frontend Team Lead", "manager", 2),
                        ("Мобайл", "Руководитель", "+77002222223", "Халык банк", "Mobile Team Lead", "manager", 3),
                        # Employees
                        ("Алексей", "Иванов", "+77003333331", "Халык банк", "Python Developer", "employee", 1),
                        ("Дмитрий", "Петров", "+77003333332", "Халык банк", "Java Developer", "employee", 1),
                        ("Сергей", "Сидоров", "+77003333333", "Халык банк", "React Developer", "employee", 2),
                        ("Анна", "Смирнова", "+77003333334", "Халык банк", "Vue Developer", "employee", 2),
                        ("Мария", "Козлова", "+77003333335", "Халык банк", "iOS Developer", "employee", 3),
                        ("Елена", "Новикова", "+77003333336", "Халык банк", "Android Developer", "employee", 3),
                        ("Игорь", "Морозов", "+77003333337", "Халык банк", "Data Scientist", "employee", 4),
                        ("Ольга", "Волкова", "+77003333338", "Халык банк", "ML Engineer", "employee", 4),
                        ("Павел", "Соколов", "+77003333339", "Халык банк", "DevOps Engineer", "employee", 5),
                        ("Наталья", "Лебедева", "+77003333340", "Халык банк", "QA Engineer", "employee", 6),
                        ("Виктор", "Козлов", "+77003333341", "Халык банк", "Business Analyst", "employee", 8),
                    ]

                    for name, surname, phone, company, job_title, role, dept_id in test_users:
                        try:
                            await cur.execute("""
                                INSERT INTO users (name, surname, phone, company, job_title, role, department_id)
                                VALUES (%s, %s, %s, %s, %s, %s, %s)
                                ON CONFLICT (phone) DO NOTHING
                            """, (name, surname, phone, company, job_title, role, dept_id))
                            print(f"   ✓ Created: {name} {surname} ({role})")
                        except Exception as e:
                            print(f"   ⚠️  Skipped {name} {surname}: {e}")

                    await conn.commit()
                    print(f"   ✅ Test users created!")

                # ============================================
                # STEP 3: Check test results
                # ============================================
                print("\n📊 STEP 3: Checking existing test results...")
                await cur.execute("SELECT COUNT(*) FROM user_specialization_tests WHERE completed_at IS NOT NULL")
                completed_tests = (await cur.fetchone())[0]
                print(f"   Completed tests: {completed_tests}")

                # ============================================
                # STEP 4: Check specializations and topics
                # ============================================
                print("\n📊 STEP 4: Checking specializations and topics...")
                await cur.execute("SELECT COUNT(*) FROM specializations")
                spec_count = (await cur.fetchone())[0]
                await cur.execute("SELECT COUNT(*) FROM topics")
                topic_count = (await cur.fetchone())[0]
                await cur.execute("SELECT COUNT(*) FROM questions")
                question_count = (await cur.fetchone())[0]

                print(f"   Specializations: {spec_count}")
                print(f"   Topics: {topic_count}")
                print(f"   Questions: {question_count}")

                if spec_count == 0 or topic_count == 0:
                    print("\n❌ ERROR: No specializations or topics found!")
                    print("   Please import your test data first!")
                    return

                # ============================================
                # STEP 5: Create test results if needed
                # ============================================
                if completed_tests < 10:
                    print("\n⚠️  Not enough test results. Creating sample tests...")

                    # Get employees
                    await cur.execute("""
                        SELECT id, name, surname, department_id
                        FROM users
                        WHERE role = 'employee'
                        ORDER BY id
                    """)
                    employees = await cur.fetchall()

                    if not employees:
                        print("   ❌ No employees found!")
                        return

                    print(f"   Found {len(employees)} employees")

                    # Get specializations
                    await cur.execute("SELECT id, name FROM specializations ORDER BY id")
                    specializations = await cur.fetchall()
                    print(f"   Found {len(specializations)} specializations")

                    tests_created = 0

                    for emp_id, emp_name, emp_surname, dept_id in employees:
                        # Each employee takes 2-3 tests
                        num_tests = random.randint(2, min(3, len(specializations)))
                        selected_specs = random.sample(specializations, num_tests)

                        for spec_id, spec_name in selected_specs:
                            # Get topics for this specialization through competencies
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
                                print(f"      ⚠️  No topics for {spec_name}, skipping...")
                                continue

                            # Random performance level
                            performance_roll = random.random()
                            if performance_roll < 0.20:  # 20% Senior
                                score_percentage = random.uniform(0.70, 0.95)
                            elif performance_roll < 0.55:  # 35% Middle
                                score_percentage = random.uniform(0.40, 0.66)
                            else:  # 45% Junior
                                score_percentage = random.uniform(0.15, 0.33)

                            max_score = 24
                            score = int(max_score * score_percentage)

                            # Random timestamps
                            started_at = datetime.now() - timedelta(
                                days=random.randint(1, 60),
                                hours=random.randint(0, 23)
                            )
                            completed_at = started_at + timedelta(minutes=random.randint(20, 50))

                            # Create test record (skip if already exists)
                            await cur.execute("""
                                INSERT INTO user_specialization_tests
                                (user_id, specialization_id, score, max_score, started_at, completed_at)
                                VALUES (%s, %s, %s, %s, %s, %s)
                                ON CONFLICT (user_id, specialization_id) DO NOTHING
                                RETURNING id
                            """, (emp_id, spec_id, score, max_score, started_at, completed_at))
                            result = await cur.fetchone()

                            # Skip if test already existed
                            if not result:
                                print(f"      ⊘ {emp_name} {emp_surname}: {spec_name} - already exists, skipping")
                                continue

                            test_id = result[0]

                            # Insert topics
                            for idx, (topic_id, competency_id) in enumerate(topics, 1):
                                await cur.execute("""
                                    INSERT INTO user_test_topics
                                    (user_test_id, topic_id, competency_id, topic_order)
                                    VALUES (%s, %s, %s, %s)
                                """, (test_id, topic_id, competency_id, idx))

                            # Get questions for each topic
                            all_questions = []
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
                                all_questions.extend(topic_questions)

                            # Limit to 24 questions
                            all_questions = all_questions[:24]

                            # Answer questions
                            correct_indices = set(random.sample(range(len(all_questions)), score))

                            for idx, (question_id, correct_answer) in enumerate(all_questions):
                                is_correct = idx in correct_indices
                                user_answer = correct_answer if is_correct else random.choice(
                                    [i for i in range(1, 5) if i != correct_answer]
                                )

                                await cur.execute("""
                                    INSERT INTO test_answers
                                    (user_test_id, question_id, user_answer, is_correct)
                                    VALUES (%s, %s, %s, %s)
                                """, (test_id, question_id, user_answer, is_correct))

                            tests_created += 1
                            level = 'Senior' if score_percentage >= 0.67 else 'Middle' if score_percentage >= 0.34 else 'Junior'
                            print(f"      ✓ {emp_name} {emp_surname}: {spec_name} - {score}/{max_score} ({int(score_percentage*100)}%) [{level}]")

                    await conn.commit()
                    print(f"\n   ✅ Created {tests_created} test results!")

                # ============================================
                # STEP 6: Verify final data
                # ============================================
                print("\n📊 STEP 6: Final verification...")

                await cur.execute("SELECT COUNT(*) FROM users WHERE role='employee'")
                final_employees = (await cur.fetchone())[0]

                await cur.execute("SELECT COUNT(*) FROM user_specialization_tests WHERE completed_at IS NOT NULL")
                final_tests = (await cur.fetchone())[0]

                await cur.execute("""
                    SELECT
                        CASE
                            WHEN (score::float / max_score::float * 100) >= 67 THEN 'Senior'
                            WHEN (score::float / max_score::float * 100) >= 34 THEN 'Middle'
                            ELSE 'Junior'
                        END as level,
                        COUNT(*) as count
                    FROM user_specialization_tests
                    WHERE completed_at IS NOT NULL
                    GROUP BY level
                """)
                level_stats = await cur.fetchall()

                print(f"   ✓ Employees: {final_employees}")
                print(f"   ✓ Completed tests: {final_tests}")
                print(f"   ✓ Level breakdown:")
                for level, count in level_stats:
                    print(f"      - {level}: {count}")

                print("\n" + "=" * 60)
                print("✅ SETUP COMPLETE!")
                print("=" * 60)
                print("\nYou can now:")
                print("  1. Visit /hr/results to see all test results")
                print("  2. Login as manager to see department results")
                print("  3. Check statistics on both panels")
                print("\nHR Panel: http://localhost:8000/hr")
                print("Password: halyk2024")
                print("=" * 60)

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(check_and_setup_test_data())
