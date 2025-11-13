import asyncio
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import init_db_pool, close_db_pool, get_db_connection

async def diagnose_manager_department():
    """Diagnose manager department filtering issues"""

    print("🔍 DIAGNOSING MANAGER DEPARTMENT FILTERING")
    print("=" * 80)

    await init_db_pool()

    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            # 1. Check all managers
            print("\n📊 MANAGERS IN DATABASE:")
            print("-" * 80)
            await cur.execute("""
                SELECT u.id, u.name, u.surname, u.phone, u.role, u.department_id, d.name as dept_name
                FROM users u
                LEFT JOIN departments d ON u.department_id = d.id
                WHERE u.role = 'manager'
                ORDER BY u.id
            """)
            managers = await cur.fetchall()

            if not managers:
                print("❌ NO MANAGERS FOUND!")
            else:
                for mgr in managers:
                    print(f"ID: {mgr[0]} | {mgr[1]} {mgr[2]} | Phone: {mgr[3]} | Dept ID: {mgr[5]} | Dept: {mgr[6] or 'NULL'}")

            # 2. Check employees in each manager's department
            print("\n\n👥 EMPLOYEES BY DEPARTMENT:")
            print("-" * 80)

            for mgr in managers:
                dept_id = mgr[5]
                dept_name = mgr[6]

                print(f"\n🏢 Department: {dept_name} (ID: {dept_id})")
                print(f"   Manager: {mgr[1]} {mgr[2]}")

                # Get employees in this department
                await cur.execute("""
                    SELECT id, name, surname, phone, role
                    FROM users
                    WHERE department_id = %s AND role != 'manager'
                    ORDER BY id
                """, (dept_id,))
                employees = await cur.fetchall()

                if not employees:
                    print(f"   ❌ NO EMPLOYEES in department {dept_id}")
                else:
                    print(f"   ✅ Found {len(employees)} employees:")
                    for emp in employees:
                        print(f"      - {emp[1]} {emp[2]} (ID: {emp[0]}, Phone: {emp[3]}, Role: {emp[4]})")

                # 3. Check test results for this department
                await cur.execute("""
                    SELECT
                        u.id,
                        u.name,
                        u.surname,
                        s.name as specialization,
                        ust.score,
                        ust.max_score,
                        ust.completed_at
                    FROM user_specialization_tests ust
                    JOIN users u ON ust.user_id = u.id
                    JOIN specializations s ON ust.specialization_id = s.id
                    WHERE u.department_id = %s AND ust.completed_at IS NOT NULL
                    ORDER BY ust.completed_at DESC
                """, (dept_id,))
                test_results = await cur.fetchall()

                if not test_results:
                    print(f"   ❌ NO TEST RESULTS for department {dept_id}")
                else:
                    print(f"   ✅ Found {len(test_results)} completed tests:")
                    for result in test_results:
                        percentage = (result[4] / result[5] * 100) if result[5] > 0 else 0
                        print(f"      - {result[1]} {result[2]}: {result[3]} - {percentage:.1f}% ({result[4]}/{result[5]})")

            # 4. Check ALL completed tests to see what data exists
            print("\n\n📋 ALL COMPLETED TESTS:")
            print("-" * 80)
            await cur.execute("""
                SELECT
                    u.id,
                    u.name,
                    u.surname,
                    u.department_id,
                    d.name as dept_name,
                    s.name as specialization,
                    ust.score,
                    ust.max_score,
                    ust.completed_at
                FROM user_specialization_tests ust
                JOIN users u ON ust.user_id = u.id
                LEFT JOIN departments d ON u.department_id = d.id
                JOIN specializations s ON ust.specialization_id = s.id
                WHERE ust.completed_at IS NOT NULL
                ORDER BY u.department_id, ust.completed_at DESC
            """)
            all_tests = await cur.fetchall()

            if not all_tests:
                print("❌ NO COMPLETED TESTS FOUND IN DATABASE!")
            else:
                print(f"✅ Found {len(all_tests)} total completed tests:\n")
                current_dept = None
                for test in all_tests:
                    if test[3] != current_dept:
                        current_dept = test[3]
                        print(f"\n🏢 Department: {test[4] or 'NULL'} (ID: {test[3] or 'NULL'})")

                    percentage = (test[6] / test[7] * 100) if test[7] > 0 else 0
                    print(f"   - User {test[0]}: {test[1]} {test[2]} - {test[5]} - {percentage:.1f}% ({test[6]}/{test[7]})")

            # 5. Test the actual manager query
            print("\n\n🔍 TESTING MANAGER API QUERY:")
            print("-" * 80)

            for mgr in managers:
                dept_id = mgr[5]
                print(f"\nManager: {mgr[1]} {mgr[2]} (Department {dept_id})")

                # This is the exact query from the API
                query = """
                    SELECT
                        ust.id as test_id,
                        u.id as user_id,
                        u.name,
                        u.surname,
                        u.phone,
                        u.company,
                        u.job_title,
                        s.name as specialization,
                        p.name as profile,
                        ust.score,
                        ust.max_score,
                        ROUND((ust.score::numeric / ust.max_score::numeric * 100), 2) as percentage,
                        CASE
                            WHEN (ust.score::numeric / ust.max_score::numeric * 100) >= 67 THEN 'Senior'
                            WHEN (ust.score::numeric / ust.max_score::numeric * 100) >= 34 THEN 'Middle'
                            ELSE 'Junior'
                        END as level,
                        ust.started_at,
                        ust.completed_at,
                        EXTRACT(EPOCH FROM (ust.completed_at - ust.started_at)) as duration_seconds
                    FROM user_specialization_tests ust
                    JOIN users u ON ust.user_id = u.id
                    JOIN specializations s ON ust.specialization_id = s.id
                    JOIN profiles p ON s.profile_id = p.id
                    WHERE ust.completed_at IS NOT NULL
                    AND u.department_id = $1
                    ORDER BY ust.completed_at DESC
                """

                await cur.execute(query, (dept_id,))
                results = await cur.fetchall()

                if not results:
                    print(f"   ❌ Query returned 0 results for department {dept_id}")
                else:
                    print(f"   ✅ Query returned {len(results)} results:")
                    for row in results:
                        print(f"      - {row[2]} {row[3]}: {row[7]} - {row[11]}%")

    await close_db_pool()
    print("\n" + "=" * 80)

if __name__ == "__main__":
    asyncio.run(diagnose_manager_department())
