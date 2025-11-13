#!/usr/bin/env python3
"""
Run database migrations

This script applies SQL migrations to the hr schema in the database.
"""

import asyncio
import os
from pathlib import Path
from db.database import init_db_pool, get_db_connection

async def run_migrations():
    """Run all migration files in order"""

    print("\n" + "=" * 80)
    print("DATABASE MIGRATIONS")
    print("=" * 80 + "\n")

    # Initialize database pool
    await init_db_pool()
    print("✅ Database connection established\n")

    # Get migration files in order
    migrations_dir = Path(__file__).parent / "db" / "migrations"
    migration_files = sorted(migrations_dir.glob("*.sql"))

    if not migration_files:
        print("⚠️  No migration files found in db/migrations/")
        return

    print(f"Found {len(migration_files)} migration file(s):\n")

    success_count = 0
    failed_count = 0

    async with get_db_connection() as conn:
        for migration_file in migration_files:
            print(f"📝 Running: {migration_file.name}")

            try:
                # Read migration file
                with open(migration_file, 'r', encoding='utf-8') as f:
                    sql = f.read()

                # Execute migration
                async with conn.cursor() as cur:
                    await cur.execute(sql)

                print(f"   ✅ SUCCESS\n")
                success_count += 1

            except Exception as e:
                print(f"   ❌ FAILED: {e}\n")
                failed_count += 1
                # Continue with other migrations

    print("=" * 80)
    print(f"MIGRATION SUMMARY:")
    print(f"  ✅ Successful: {success_count}")
    print(f"  ❌ Failed: {failed_count}")
    print("=" * 80 + "\n")

    if failed_count == 0:
        print("🎉 All migrations completed successfully!")
    else:
        print("⚠️  Some migrations failed. Check the errors above.")

if __name__ == "__main__":
    asyncio.run(run_migrations())
