#!/usr/bin/env python3
"""
Create the missing hr.competency_self_assessments table
"""

import asyncio
from db.database import init_db_pool, get_db_connection

async def create_missing_table():
    """Create competency_self_assessments table in hr schema"""

    print("\n" + "=" * 80)
    print("CREATING MISSING TABLE: hr.competency_self_assessments")
    print("=" * 80 + "\n")

    await init_db_pool()

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Check if table already exists
                await cur.execute("""
                    SELECT EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = 'hr'
                        AND table_name = 'competency_self_assessments'
                    )
                """)
                exists = (await cur.fetchone())[0]

                if exists:
                    print("✅ Table hr.competency_self_assessments already exists!")

                    # Show row count
                    await cur.execute("SELECT COUNT(*) FROM hr.competency_self_assessments")
                    count = (await cur.fetchone())[0]
                    print(f"   Current row count: {count}")
                    print("\n" + "=" * 80)
                    return

                print("📝 Creating table hr.competency_self_assessments...")

                # Create table with SET search_path to ensure proper schema context
                await cur.execute("""
                    SET search_path TO hr, public;

                    CREATE TABLE hr.competency_self_assessments (
                        id SERIAL PRIMARY KEY,
                        user_test_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        competency_id INTEGER NOT NULL,
                        self_rating INTEGER NOT NULL CHECK (self_rating >= 1 AND self_rating <= 10),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(user_test_id, competency_id)
                    );
                """)

                print("✅ Table created successfully!")

                # Add foreign key constraints separately
                print("\n📝 Adding foreign key constraints...")

                try:
                    await cur.execute("""
                        ALTER TABLE hr.competency_self_assessments
                        ADD CONSTRAINT fk_comp_self_assess_user_test
                        FOREIGN KEY (user_test_id) REFERENCES hr.user_specialization_tests(id) ON DELETE CASCADE;
                    """)
                    print("   ✅ FK: user_test_id → hr.user_specialization_tests(id)")
                except Exception as e:
                    print(f"   ⚠️  FK user_test_id failed: {e}")

                try:
                    await cur.execute("""
                        ALTER TABLE hr.competency_self_assessments
                        ADD CONSTRAINT fk_comp_self_assess_user
                        FOREIGN KEY (user_id) REFERENCES hr.users(id) ON DELETE CASCADE;
                    """)
                    print("   ✅ FK: user_id → hr.users(id)")
                except Exception as e:
                    print(f"   ⚠️  FK user_id failed: {e}")

                try:
                    await cur.execute("""
                        ALTER TABLE hr.competency_self_assessments
                        ADD CONSTRAINT fk_comp_self_assess_competency
                        FOREIGN KEY (competency_id) REFERENCES hr.competencies(id) ON DELETE CASCADE;
                    """)
                    print("   ✅ FK: competency_id → hr.competencies(id)")
                except Exception as e:
                    print(f"   ⚠️  FK competency_id failed: {e}")

                # Add indexes
                print("\n📝 Creating indexes...")

                await cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_comp_self_assess_user_test
                    ON hr.competency_self_assessments(user_test_id);
                """)
                print("   ✅ Index: idx_comp_self_assess_user_test")

                await cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_comp_self_assess_user
                    ON hr.competency_self_assessments(user_id);
                """)
                print("   ✅ Index: idx_comp_self_assess_user")

                await cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_comp_self_assess_competency
                    ON hr.competency_self_assessments(competency_id);
                """)
                print("   ✅ Index: idx_comp_self_assess_competency")

                # Create trigger function if it doesn't exist
                print("\n📝 Creating trigger function...")

                await cur.execute("""
                    CREATE OR REPLACE FUNCTION hr.update_competency_self_assessments_updated_at()
                    RETURNS TRIGGER AS $$
                    BEGIN
                        NEW.updated_at = CURRENT_TIMESTAMP;
                        RETURN NEW;
                    END;
                    $$ LANGUAGE plpgsql;
                """)
                print("   ✅ Function: update_competency_self_assessments_updated_at()")

                await cur.execute("""
                    DROP TRIGGER IF EXISTS competency_self_assessments_updated_at
                    ON hr.competency_self_assessments;

                    CREATE TRIGGER competency_self_assessments_updated_at
                        BEFORE UPDATE ON hr.competency_self_assessments
                        FOR EACH ROW
                        EXECUTE FUNCTION hr.update_competency_self_assessments_updated_at();
                """)
                print("   ✅ Trigger: competency_self_assessments_updated_at")

                print("\n" + "=" * 80)
                print("🎉 Table hr.competency_self_assessments created successfully!")
                print("=" * 80 + "\n")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        print("\n" + "=" * 80)

if __name__ == "__main__":
    asyncio.run(create_missing_table())