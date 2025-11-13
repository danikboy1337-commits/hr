#!/usr/bin/env python3
"""
Apply add_test_time_limit migration
Adds time limit columns to hr.user_specialization_tests table
"""

import asyncio
from db.database import init_db_pool, get_db_connection

async def apply_migration():
    """Add time limit columns to tests table"""

    print("\n" + "=" * 80)
    print("MIGRATION: Add Test Time Limit Columns")
    print("=" * 80 + "\n")

    await init_db_pool()

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Check if columns already exist
                await cur.execute("""
                    SELECT
                        EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_schema = 'hr' AND table_name = 'user_specialization_tests'
                            AND column_name = 'time_limit_minutes'
                        ) as has_time_limit,
                        EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_schema = 'hr' AND table_name = 'user_specialization_tests'
                            AND column_name = 'time_started_at'
                        ) as has_time_started,
                        EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_schema = 'hr' AND table_name = 'user_specialization_tests'
                            AND column_name = 'time_expired'
                        ) as has_time_expired
                """)
                result = await cur.fetchone()
                has_time_limit, has_time_started, has_time_expired = result

                if has_time_limit and has_time_started and has_time_expired:
                    print("✅ All time limit columns already exist!")
                    print("   - time_limit_minutes")
                    print("   - time_started_at")
                    print("   - time_expired")
                    print("\n" + "=" * 80)
                    return

                print("📝 Adding time limit columns to hr.user_specialization_tests...")

                # Add columns
                if not has_time_limit:
                    await cur.execute("""
                        ALTER TABLE hr.user_specialization_tests
                        ADD COLUMN time_limit_minutes INTEGER DEFAULT 40
                    """)
                    print("   ✅ Added: time_limit_minutes (default: 40)")

                if not has_time_started:
                    await cur.execute("""
                        ALTER TABLE hr.user_specialization_tests
                        ADD COLUMN time_started_at TIMESTAMP
                    """)
                    print("   ✅ Added: time_started_at")

                if not has_time_expired:
                    await cur.execute("""
                        ALTER TABLE hr.user_specialization_tests
                        ADD COLUMN time_expired BOOLEAN DEFAULT FALSE
                    """)
                    print("   ✅ Added: time_expired (default: FALSE)")

                # Update existing tests
                print("\n📝 Updating existing tests...")
                await cur.execute("""
                    UPDATE hr.user_specialization_tests
                    SET time_started_at = started_at
                    WHERE time_started_at IS NULL AND started_at IS NOT NULL
                """)
                print("   ✅ Set time_started_at = started_at for existing tests")

                print("\n" + "=" * 80)
                print("🎉 Migration completed successfully!")
                print("=" * 80 + "\n")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        print("\n" + "=" * 80)

if __name__ == "__main__":
    asyncio.run(apply_migration())
