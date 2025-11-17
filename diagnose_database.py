"""
Diagnostic script to check database state
"""
import asyncio
import sys
from db.database_v2 import init_db_pool, close_db_pool, get_db_connection

async def diagnose():
    await init_db_pool()

    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            print("="*80)
            print("DATABASE DIAGNOSTIC REPORT")
            print("="*80)

            # 1. Specializations
            print("\n1️⃣ SPECIALIZATIONS:")
            await cur.execute("SELECT id, name FROM specializations ORDER BY id")
            specs = await cur.fetchall()
            for spec_id, name in specs:
                print(f"   ID {spec_id}: {name}")

            # 2. For each specialization, show competencies
            for spec_id, spec_name in specs:
                print(f"\n2️⃣ COMPETENCIES for '{spec_name}' (ID {spec_id}):")
                await cur.execute("""
                    SELECT id, name, weight
                    FROM competencies
                    WHERE specialization_id = %s
                    ORDER BY id
                """, (spec_id,))
                comps = await cur.fetchall()

                if not comps:
                    print(f"   ❌ NO COMPETENCIES FOUND!")
                else:
                    for comp_id, comp_name, weight in comps:
                        # Count topics for this competency
                        await cur.execute("SELECT COUNT(*) FROM topics WHERE competency_id = %s", (comp_id,))
                        topic_count = (await cur.fetchone())[0]

                        # Count questions for this competency
                        await cur.execute("""
                            SELECT COUNT(*) FROM questions q
                            JOIN topics t ON t.id = q.topic_id
                            WHERE t.competency_id = %s
                        """, (comp_id,))
                        question_count = (await cur.fetchone())[0]

                        print(f"   ID {comp_id}: {comp_name}")
                        print(f"      Weight: {weight}")
                        print(f"      Topics: {topic_count}")
                        print(f"      Questions: {question_count}")

            # 3. Question levels distribution
            print(f"\n3️⃣ QUESTION LEVELS DISTRIBUTION:")
            await cur.execute("""
                SELECT level, COUNT(*)
                FROM questions
                GROUP BY level
                ORDER BY level
            """)
            levels = await cur.fetchall()
            for level, count in levels:
                print(f"   {level}: {count} questions")

            # 4. Topics with complete triplets
            print(f"\n4️⃣ TOPICS WITH COMPLETE TRIPLETS (junior + middle + senior):")
            await cur.execute("""
                SELECT c.name, COUNT(DISTINCT t.id)
                FROM topics t
                JOIN competencies c ON c.id = t.competency_id
                WHERE EXISTS (SELECT 1 FROM questions WHERE topic_id = t.id AND LOWER(level) = 'junior')
                AND EXISTS (SELECT 1 FROM questions WHERE topic_id = t.id AND LOWER(level) = 'middle')
                AND EXISTS (SELECT 1 FROM questions WHERE topic_id = t.id AND LOWER(level) = 'senior')
                GROUP BY c.name
                ORDER BY c.name
            """)
            triplets = await cur.fetchall()

            total_triplets = 0
            if not triplets:
                print(f"   ❌ NO TOPICS WITH COMPLETE TRIPLETS!")
            else:
                for comp_name, count in triplets:
                    print(f"   {comp_name}: {count} complete triplets")
                    total_triplets += count
                print(f"\n   TOTAL: {total_triplets} topics with complete triplets")

            print("\n" + "="*80)
            print("DIAGNOSIS:")
            print("="*80)
            if not comps:
                print("❌ NO COMPETENCIES: Run load_questions_v2.py to load questions")
            elif total_triplets == 0:
                print("❌ NO COMPLETE TRIPLETS: Check if questions have all 3 levels")
            elif total_triplets < 20:
                print(f"⚠️  ONLY {total_triplets} COMPLETE TRIPLETS: Need at least 20 for a full test")
            else:
                print(f"✅ Database looks good! {total_triplets} complete triplets available")
            print("="*80)

    await close_db_pool()

if __name__ == "__main__":
    asyncio.run(diagnose())
