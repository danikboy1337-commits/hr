#!/usr/bin/env python3
"""
Check which migrations have been successfully applied
"""

import asyncio
from db.database import init_db_pool, get_db_connection

async def check_migration_status():
    """Check if migration changes exist in the database"""

    print("\n" + "=" * 80)
    print("CHECKING MIGRATION STATUS")
    print("=" * 80 + "\n")

    await init_db_pool()

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                migrations_status = []

                # 1. Check: competency_self_assessments table (001_create_competency_self_assessments.sql)
                await cur.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = 'hr'
                        AND table_name = 'competency_self_assessments'
                    )
                """)
                has_comp_self_assess = (await cur.fetchone())[0]
                migrations_status.append({
                    'name': '001_create_competency_self_assessments.sql',
                    'check': 'hr.competency_self_assessments table exists',
                    'applied': has_comp_self_assess
                })

                # 2. Check: time_limit_minutes column (add_test_time_limit.sql)
                await cur.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_schema = 'hr'
                        AND table_name = 'user_specialization_tests'
                        AND column_name = 'time_limit_minutes'
                    )
                """)
                has_time_limit = (await cur.fetchone())[0]
                migrations_status.append({
                    'name': 'add_test_time_limit.sql',
                    'check': 'hr.user_specialization_tests.time_limit_minutes column exists',
                    'applied': has_time_limit
                })

                # 3. Check: manager_competency_ratings table (update_manager_evaluations_competency_based.sql)
                await cur.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = 'hr'
                        AND table_name = 'manager_competency_ratings'
                    )
                """)
                has_manager_comp_ratings = (await cur.fetchone())[0]
                migrations_status.append({
                    'name': 'update_manager_evaluations_competency_based.sql',
                    'check': 'hr.manager_competency_ratings table exists',
                    'applied': has_manager_comp_ratings
                })

                # 4. Check: employee_ratings table (add_employee_ratings.sql)
                # NOTE: This gets dropped by update_manager_evaluations_competency_based.sql
                await cur.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = 'hr'
                        AND table_name = 'employee_ratings'
                    )
                """)
                has_employee_ratings = (await cur.fetchone())[0]
                migrations_status.append({
                    'name': 'add_employee_ratings.sql',
                    'check': 'hr.employee_ratings table exists (may be dropped by later migration)',
                    'applied': has_employee_ratings
                })

                # Print results
                print("Migration Status:\n")
                applied_count = 0
                pending_count = 0

                for migration in migrations_status:
                    status = "✅ APPLIED" if migration['applied'] else "❌ PENDING"
                    print(f"{status} - {migration['name']}")
                    print(f"           Check: {migration['check']}\n")
                    if migration['applied']:
                        applied_count += 1
                    else:
                        pending_count += 1

                print("=" * 80)
                print(f"Summary: {applied_count} applied, {pending_count} pending")
                print("=" * 80)

                if pending_count > 0:
                    print("\n⚠️  Some migrations have NOT been applied yet.")
                    print("   Run: python create_missing_table.py")
                    print("   This will create the missing competency_self_assessments table.")
                else:
                    print("\n✅ All migrations have been applied!")

                print("\n")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(check_migration_status())