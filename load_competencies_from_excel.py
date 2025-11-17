"""
Script to load competencies from Excel into database

This script CREATES new competencies (use update_weights_from_excel.py to update existing ones)

Usage:
    python load_competencies_from_excel.py competencies.xlsx --specialization "Data Analyst"

Excel format:
    Column A: competency_name
    Column B: weight (any positive number, will be normalized)
"""

import pandas as pd
import asyncio
import sys
import os

# Add parent directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database_v2 import init_db_pool, close_db_pool, get_db_connection


async def load_competencies_from_excel(excel_file: str, specialization_name: str):
    """
    Load competencies from Excel file into database

    Excel columns:
    - competency_name: Name of competency
    - weight: Weight value (any positive number, will be normalized)
    """

    print(f"📁 Reading {excel_file}...")
    df = pd.read_excel(excel_file)

    # Validate columns
    required_cols = ['competency_name', 'weight']
    if not all(col in df.columns for col in required_cols):
        print(f"❌ Excel must have columns: {required_cols}")
        print(f"   Found columns: {list(df.columns)}")
        return

    # Remove any rows with NaN
    df = df.dropna(subset=['competency_name', 'weight'])

    # Normalize weights to sum to 1.0
    total_weight = df['weight'].sum()
    df['normalized_weight'] = df['weight'] / total_weight

    print(f"\n📊 Found {len(df)} competencies in Excel")
    print(f"Total weight: {total_weight} → normalized to 1.0\n")

    # Initialize database
    await init_db_pool()

    inserted = 0
    already_exist = []
    errors = []

    try:
        # First, check if specialization exists
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT id FROM specializations WHERE name = %s",
                    (specialization_name,)
                )
                row = await cur.fetchone()

                if not row:
                    print(f"❌ Specialization '{specialization_name}' not found in database")
                    print("\n💡 Available specializations:")

                    await cur.execute("SELECT name FROM specializations ORDER BY name")
                    specs = await cur.fetchall()

                    if specs:
                        for spec in specs:
                            print(f"   • {spec[0]}")
                    else:
                        print("   (No specializations found - load questions first using load_questions_v2.py)")

                    return

                specialization_id = row[0]
                print(f"✅ Found specialization: {specialization_name} (ID: {specialization_id})\n")

        # Now insert competencies
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                for _, row in df.iterrows():
                    comp_name = str(row['competency_name']).strip()
                    weight = float(row['normalized_weight'])

                    try:
                        # Check if already exists
                        await cur.execute("""
                            SELECT id FROM competencies
                            WHERE specialization_id = %s AND name = %s
                        """, (specialization_id, comp_name))

                        existing = await cur.fetchone()

                        if existing:
                            already_exist.append(comp_name)
                            print(f"⚠️  Already exists: {comp_name}")
                        else:
                            # Insert new competency
                            await cur.execute("""
                                INSERT INTO competencies (specialization_id, name, weight)
                                VALUES (%s, %s, %s)
                            """, (specialization_id, comp_name, weight))

                            print(f"✅ Inserted: {comp_name} (weight: {weight:.4f})")
                            inserted += 1

                    except Exception as e:
                        errors.append(f"{comp_name}: {str(e)}")
                        print(f"❌ Error with {comp_name}: {e}")

        # Summary
        print(f"\n{'='*60}")
        print(f"📊 Summary:")
        print(f"   ✅ Inserted: {inserted}")
        print(f"   ⚠️  Already existed: {len(already_exist)}")
        print(f"   ❌ Errors: {len(errors)}")

        if already_exist:
            print(f"\n💡 Use update_weights_from_excel.py to update existing competencies")

        print("="*60)

    finally:
        await close_db_pool()


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python load_competencies_from_excel.py competencies.xlsx --specialization \"Data Analyst\"")
        print("\nExcel format:")
        print("  Column A: competency_name")
        print("  Column B: weight (any positive number)")
        print("\nNote: Specialization must already exist in database (created by load_questions_v2.py)")
        return

    # Parse arguments
    args = sys.argv[1:]
    specialization = None
    excel_file = None

    i = 0
    while i < len(args):
        if args[i] == '--specialization' and i + 1 < len(args):
            specialization = args[i + 1]
            i += 1
        elif not args[i].startswith('--'):
            excel_file = args[i]
        i += 1

    if not excel_file:
        print("❌ Please provide Excel file")
        print("Usage: python load_competencies_from_excel.py competencies.xlsx --specialization \"Data Analyst\"")
        return

    if not specialization:
        print("❌ Please provide --specialization")
        print("Usage: python load_competencies_from_excel.py competencies.xlsx --specialization \"Data Analyst\"")
        return

    if not os.path.exists(excel_file):
        print(f"❌ File not found: {excel_file}")
        return

    # Fix for Windows
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(load_competencies_from_excel(excel_file, specialization))


if __name__ == "__main__":
    main()
