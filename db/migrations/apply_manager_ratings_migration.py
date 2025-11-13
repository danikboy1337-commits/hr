#!/usr/bin/env python3
"""
Apply update_manager_evaluations_competency_based migration
Creates hr.manager_competency_ratings table
"""

import asyncio
from db.database import init_db_pool, get_db_connection

async def apply_migration():
    """Create manager_competency_ratings table"""

    print("\n" + "=" * 80)
    print("MIGRATION: Create Manager Competency Ratings Table")
    print("=" * 80 + "\n")

    await init_db_pool()

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Check if table exists
                await cur.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = 'hr'
                        AND table_name = 'manager_competency_ratings'
                    )
                """)
                exists = (await cur.fetchone())[0]

                if exists:
                    print("✅ Table hr.manager_competency_ratings already exists!")
                    await cur.execute("SELECT COUNT(*) FROM hr.manager_competency_ratings")
                    count = (await cur.fetchone())[0]
                    print(f"   Current row count: {count}")
                    print("\n" + "=" * 80)
                    return

                print("📝 Creating table hr.manager_competency_ratings...")

                await cur.execute("""
                    SET search_path TO hr, public;

                    CREATE TABLE hr.manager_competency_ratings (
                        id SERIAL PRIMARY KEY,
                        employee_id INTEGER NOT NULL,
                        manager_id INTEGER NOT NULL,
                        user_test_id INTEGER NOT NULL,
                        competency_id INTEGER NOT NULL,
                        rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 10),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(user_test_id, competency_id, manager_id)
                    );
                """)
                print("   ✅ Table created")

                # Add foreign keys
                print("\n📝 Adding foreign key constraints...")

                try:
                    await cur.execute("""
                        ALTER TABLE hr.manager_competency_ratings
                        ADD CONSTRAINT fk_manager_comp_ratings_employee
                        FOREIGN KEY (employee_id) REFERENCES hr.users(id) ON DELETE CASCADE;
                    """)
                    print("   ✅ FK: employee_id → hr.users(id)")
                except Exception as e:
                    print(f"   ⚠️  FK employee_id failed: {e}")

                try:
                    await cur.execute("""
                        ALTER TABLE hr.manager_competency_ratings
                        ADD CONSTRAINT fk_manager_comp_ratings_manager
                        FOREIGN KEY (manager_id) REFERENCES hr.users(id) ON DELETE CASCADE;
                    """)
                    print("   ✅ FK: manager_id → hr.users(id)")
                except Exception as e:
                    print(f"   ⚠️  FK manager_id failed: {e}")

                try:
                    await cur.execute("""
                        ALTER TABLE hr.manager_competency_ratings
                        ADD CONSTRAINT fk_manager_comp_ratings_test
                        FOREIGN KEY (user_test_id) REFERENCES hr.user_specialization_tests(id) ON DELETE CASCADE;
                    """)
                    print("   ✅ FK: user_test_id → hr.user_specialization_tests(id)")
                except Exception as e:
                    print(f"   ⚠️  FK user_test_id failed: {e}")

                try:
                    await cur.execute("""
                        ALTER TABLE hr.manager_competency_ratings
                        ADD CONSTRAINT fk_manager_comp_ratings_competency
                        FOREIGN KEY (competency_id) REFERENCES hr.competencies(id) ON DELETE CASCADE;
                    """)
                    print("   ✅ FK: competency_id → hr.competencies(id)")
                except Exception as e:
                    print(f"   ⚠️  FK competency_id failed: {e}")

                # Add indexes
                print("\n📝 Creating indexes...")

                await cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_manager_comp_ratings_employee
                    ON hr.manager_competency_ratings(employee_id);
                """)
                print("   ✅ Index: idx_manager_comp_ratings_employee")

                await cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_manager_comp_ratings_manager
                    ON hr.manager_competency_ratings(manager_id);
                """)
                print("   ✅ Index: idx_manager_comp_ratings_manager")

                await cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_manager_comp_ratings_test
                    ON hr.manager_competency_ratings(user_test_id);
                """)
                print("   ✅ Index: idx_manager_comp_ratings_test")

                await cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_manager_comp_ratings_competency
                    ON hr.manager_competency_ratings(competency_id);
                """)
                print("   ✅ Index: idx_manager_comp_ratings_competency")

                # Create trigger
                print("\n📝 Creating trigger function...")

                await cur.execute("""
                    CREATE OR REPLACE FUNCTION hr.update_manager_competency_ratings_updated_at()
                    RETURNS TRIGGER AS $$
                    BEGIN
                        NEW.updated_at = CURRENT_TIMESTAMP;
                        RETURN NEW;
                    END;
                    $$ LANGUAGE plpgsql;
                """)
                print("   ✅ Function: update_manager_competency_ratings_updated_at()")

                await cur.execute("""
                    DROP TRIGGER IF EXISTS manager_competency_ratings_updated_at
                    ON hr.manager_competency_ratings;

                    CREATE TRIGGER manager_competency_ratings_updated_at
                        BEFORE UPDATE ON hr.manager_competency_ratings
                        FOR EACH ROW
                        EXECUTE FUNCTION hr.update_manager_competency_ratings_updated_at();
                """)
                print("   ✅ Trigger: manager_competency_ratings_updated_at")

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
