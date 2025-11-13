import asyncio
import sys
import os

# FIX для Windows - psycopg requires SelectorEventLoop
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import init_db_pool, close_db_pool, get_db_connection


async def run_migration():
    """Run the employee_ratings migration"""

    print("🔄 Running employee_ratings migration...")
    await init_db_pool()

    try:
        # Read migration file
        migration_path = os.path.join(os.path.dirname(__file__), 'migrations', 'add_employee_ratings.sql')
        with open(migration_path, 'r', encoding='utf-8') as f:
            migration_sql = f.read()

        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Execute migration
                await cur.execute(migration_sql)
                print("✅ Migration completed successfully!")

                # Verify table was created
                await cur.execute("""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_name = 'employee_ratings'
                    ORDER BY ordinal_position
                """)
                columns = await cur.fetchall()

                print("\n📋 Table structure:")
                for col_name, col_type in columns:
                    print(f"   - {col_name}: {col_type}")

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        raise
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(run_migration())
