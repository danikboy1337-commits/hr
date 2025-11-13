#!/usr/bin/env python3
"""
Fix HR user test access issue by ensuring proper data exists
"""

import asyncio
from db.database import init_db_pool, close_db_pool, get_db_connection

async def fix_hr_test_access():
    """Fix HR test access by ensuring all required data exists"""
    
    print("\n" + "=" * 80)
    print("🔧 FIXING HR TEST ACCESS")
    print("=" * 80 + "\n")

    await init_db_pool()

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # 1. Ensure HR admin user exists with proper data
                print("1️⃣ Checking HR admin user...")
                await cur.execute("""
                    INSERT INTO hr.users (name, surname, phone, company, job_title, role, department_id)
                    SELECT 'HR', 'Admin', 'hr_admin', 'Halyk Bank', 'HR Administrator', 'hr',
                           (SELECT id FROM hr.departments WHERE name = 'HR' LIMIT 1)
                    WHERE NOT EXISTS (SELECT 1 FROM hr.users WHERE phone = 'hr_admin')
                    RETURNING id
                """)
                result = await cur.fetchone()
                if result:
                    print(f"   ✅ Created HR admin user with ID: {result[0]}")
                else:
                    await cur.execute("SELECT id, name, role FROM hr.users WHERE phone = 'hr_admin'")
                    user_data = await cur.fetchone()
                    print(f"   ✅ HR admin user exists: ID {user_data[0]}, {user_data[1]}, role: {user_data[2]}")

                # 2. Check that we have test data
                print("\n2️⃣ Checking test data availability...")
                
                await cur.execute("SELECT COUNT(*) FROM hr.profiles")
                profiles_count = (await cur.fetchone())[0]
                print(f"   📊 Profiles: {profiles_count}")

                await cur.execute("SELECT COUNT(*) FROM hr.specializations")
                specs_count = (await cur.fetchone())[0]
                print(f"   📊 Specializations: {specs_count}")

                await cur.execute("SELECT COUNT(*) FROM hr.competencies")
                comps_count = (await cur.fetchone())[0]
                print(f"   📊 Competencies: {comps_count}")

                await cur.execute("SELECT COUNT(*) FROM hr.topics")
                topics_count = (await cur.fetchone())[0]
                print(f"   📊 Topics: {topics_count}")

                await cur.execute("SELECT COUNT(*) FROM hr.questions")
                questions_count = (await cur.fetchone())[0]
                print(f"   📊 Questions: {questions_count}")

                if questions_count == 0:
                    print("\n   ⚠️  WARNING: No questions found! This will cause the test to fail.")
                    print("   💡 You need to import test data first.")
                    print("   📄 Run: python import_excel_data.py")

                # 3. Ensure competency_self_assessments table exists
                print("\n3️⃣ Checking competency self-assessments table...")
                await cur.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables 
                        WHERE table_schema = 'hr' AND table_name = 'competency_self_assessments'
                    )
                """)
                table_exists = (await cur.fetchone())[0]

                if not table_exists:
                    print("   📝 Creating competency_self_assessments table...")
                    await cur.execute("""
                        CREATE TABLE hr.competency_self_assessments (
                            id SERIAL PRIMARY KEY,
                            user_test_id INTEGER NOT NULL REFERENCES hr.user_specialization_tests(id) ON DELETE CASCADE,
                            user_id INTEGER NOT NULL REFERENCES hr.users(id) ON DELETE CASCADE,
                            competency_id INTEGER NOT NULL REFERENCES hr.competencies(id) ON DELETE CASCADE,
                            self_rating INTEGER NOT NULL CHECK (self_rating >= 1 AND self_rating <= 10),
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE(user_test_id, competency_id)
                        );
                        
                        CREATE INDEX idx_comp_self_assess_user_test ON hr.competency_self_assessments(user_test_id);
                        CREATE INDEX idx_comp_self_assess_user ON hr.competency_self_assessments(user_id);
                        CREATE INDEX idx_comp_self_assess_competency ON hr.competency_self_assessments(competency_id);
                    """)
                    print("   ✅ Table created successfully!")
                else:
                    print("   ✅ Table already exists")

                # 4. Test a sample specialization selection for HR admin
                print("\n4️⃣ Testing specialization selection for HR admin...")
                await cur.execute("SELECT id FROM hr.users WHERE phone = 'hr_admin'")
                hr_user_id = (await cur.fetchone())[0]

                await cur.execute("SELECT id, name FROM hr.specializations LIMIT 1")
                spec_data = await cur.fetchone()
                if spec_data:
                    spec_id, spec_name = spec_data
                    await cur.execute("""
                        INSERT INTO hr.user_specialization_selections (user_id, specialization_id)
                        VALUES (%s, %s)
                        ON CONFLICT DO NOTHING
                    """, (hr_user_id, spec_id))
                    print(f"   ✅ HR admin can select specialization: {spec_name}")
                else:
                    print("   ⚠️  No specializations found - import test data first")

                await conn.commit()

                print("\n" + "=" * 80)
                print("✅ HR TEST ACCESS FIXED!")
                print("=" * 80)
                
                if questions_count > 0:
                    print("\n🎯 HR admin should now be able to:")
                    print("   • Log in to HR panel (/hr)")
                    print("   • Access test pages (/specializations, /test)")
                    print("   • Take tests like regular users")
                    print("   • Return to HR panel functionality")
                else:
                    print("\n⚠️  NEXT STEP REQUIRED:")
                    print("   Run: python import_excel_data.py")
                    print("   This will import questions needed for tests")

                print("\n")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await close_db_pool()

if __name__ == "__main__":
    asyncio.run(fix_hr_test_access())
