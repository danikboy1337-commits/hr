import asyncio
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# FIX для Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from db.database import init_db_pool, close_db_pool, get_db_connection


async def diagnose_hr_results():
    """Diagnose why HR results page shows no statistics"""

    print("=" * 70)
    print("🔍 DIAGNOSING HR RESULTS PAGE")
    print("=" * 70)

    await init_db_pool()

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:

                # ===== TEST 1: Check completed tests =====
                print("\n📊 TEST 1: Checking for completed tests...")
                await cur.execute("""
                    SELECT COUNT(*)
                    FROM user_specialization_tests
                    WHERE completed_at IS NOT NULL
                """)
                completed_count = (await cur.fetchone())[0]

                if completed_count == 0:
                    print(f"   ❌ PROBLEM FOUND: {completed_count} completed tests")
                    print(f"   → This is why HR results page is empty!")
                    print(f"   → Solution: Run 'python db/setup_test_data.py'")
                else:
                    print(f"   ✅ Found {completed_count} completed tests")

                # ===== TEST 2: Simulate /api/hr/results/stats =====
                print("\n📊 TEST 2: Simulating /api/hr/results/stats endpoint...")

                # Overall stats
                await cur.execute("""
                    SELECT
                        COUNT(*) as total_tests,
                        AVG(score::numeric / max_score::numeric * 100) as avg_percentage,
                        MIN(score::numeric / max_score::numeric * 100) as min_percentage,
                        MAX(score::numeric / max_score::numeric * 100) as max_percentage,
                        AVG(EXTRACT(EPOCH FROM (completed_at - started_at)) / 60) as avg_duration_minutes
                    FROM user_specialization_tests
                    WHERE completed_at IS NOT NULL
                """)
                overall = await cur.fetchone()

                if overall and overall[0] > 0:
                    print(f"   ✅ Stats API would return:")
                    print(f"      - Total tests: {overall[0]}")
                    print(f"      - Average percentage: {round(overall[1], 2) if overall[1] else 0}%")
                    print(f"      - Average duration: {round(overall[4], 1) if overall[4] else 0} minutes")
                else:
                    print(f"   ❌ Stats API would return empty data")
                    print(f"      - Total tests: 0")

                # By level
                await cur.execute("""
                    SELECT
                        CASE
                            WHEN (score::numeric / max_score::numeric * 100) >= 67 THEN 'Senior'
                            WHEN (score::numeric / max_score::numeric * 100) >= 34 THEN 'Middle'
                            ELSE 'Junior'
                        END as level,
                        COUNT(*) as count
                    FROM user_specialization_tests
                    WHERE completed_at IS NOT NULL
                    GROUP BY level
                """)
                by_level = await cur.fetchall()

                if by_level:
                    print(f"   ✅ Level breakdown:")
                    for level, count in by_level:
                        print(f"      - {level}: {count}")
                else:
                    print(f"   ❌ No level data")

                # ===== TEST 3: Simulate /api/hr/results =====
                print("\n📊 TEST 3: Simulating /api/hr/results endpoint...")

                await cur.execute("""
                    SELECT
                        ust.id as test_id,
                        u.name,
                        u.surname,
                        s.name as specialization,
                        ust.score,
                        ust.max_score,
                        ROUND((ust.score::numeric / ust.max_score::numeric * 100), 2) as percentage
                    FROM user_specialization_tests ust
                    JOIN users u ON ust.user_id = u.id
                    JOIN specializations s ON ust.specialization_id = s.id
                    JOIN profiles p ON s.profile_id = p.id
                    WHERE ust.completed_at IS NOT NULL
                    ORDER BY ust.completed_at DESC
                    LIMIT 5
                """)
                results = await cur.fetchall()

                if results:
                    print(f"   ✅ Results API would return {len(results)} tests (showing first 5):")
                    for test_id, name, surname, spec, score, max_score, percentage in results:
                        print(f"      - {name} {surname}: {spec} - {score}/{max_score} ({percentage}%)")
                else:
                    print(f"   ❌ Results API would return 0 tests")
                    print(f"      → This is why the results table is empty!")

                # ===== TEST 4: Check users table =====
                print("\n📊 TEST 4: Checking users table...")
                await cur.execute("SELECT COUNT(*) FROM users WHERE role='employee'")
                employee_count = (await cur.fetchone())[0]
                print(f"   Employees in database: {employee_count}")

                # ===== TEST 5: Check specializations =====
                print("\n📊 TEST 5: Checking specializations...")
                await cur.execute("SELECT COUNT(*) FROM specializations")
                spec_count = (await cur.fetchone())[0]
                print(f"   Specializations in database: {spec_count}")

                # ===== FINAL DIAGNOSIS =====
                print("\n" + "=" * 70)
                print("📋 DIAGNOSIS SUMMARY")
                print("=" * 70)

                if completed_count == 0:
                    print("\n❌ ROOT CAUSE: No completed tests in database")
                    print("\n💡 SOLUTION:")
                    print("   1. Run: python db/setup_test_data.py")
                    print("   2. This will create:")
                    print("      - 11 employee users")
                    print("      - 20-30 completed test results")
                    print("      - Realistic scores and dates")
                    print("   3. Refresh HR results page")
                    print("   4. You should see statistics and results!")
                elif completed_count > 0:
                    print("\n✅ Database has completed tests!")
                    print("\n💡 NEXT STEPS:")
                    print("   1. Visit: http://localhost:8000/hr")
                    print("   2. Enter password: 159753")
                    print("   3. Click on 'Результаты тестов'")
                    print("   4. Open browser DevTools (F12)")
                    print("   5. Check Console tab for errors")
                    print("   6. Check Network tab for API calls")
                    print("   7. Look for any red errors")
                    print("\n   If you see errors, share them with me!")

                print("=" * 70)

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(diagnose_hr_results())
