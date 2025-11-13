"""
Script to update competency weights from HR Excel file

Usage:
    # List all competencies in database
    python update_weights_from_excel.py --list

    # Update from Excel
    python update_weights_from_excel.py competencies.xlsx

    # Update with specialization filter
    python update_weights_from_excel.py competencies.xlsx --specialization "Data Analyst"

Excel format:
    Column A: competency_name (must match database exactly)
    Column B: weight (any positive number, will be normalized)
"""

import pandas as pd
import asyncio
import sys
import os

# Add parent directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database_v2 import init_db_pool, close_db_pool, get_db_connection


async def list_competencies(specialization_filter: str = None):
    """
    List all competencies in the database with their current weights
    """

    print("📊 Listing all competencies in database...\n")

    await init_db_pool()

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                if specialization_filter:
                    await cur.execute("""
                        SELECT c.id, c.name, c.weight, s.name as spec_name
                        FROM competencies c
                        JOIN specializations s ON c.specialization_id = s.id
                        WHERE s.name = %s
                        ORDER BY s.name, c.name
                    """, (specialization_filter,))
                else:
                    await cur.execute("""
                        SELECT c.id, c.name, c.weight, s.name as spec_name
                        FROM competencies c
                        JOIN specializations s ON c.specialization_id = s.id
                        ORDER BY s.name, c.name
                    """)

                rows = await cur.fetchall()

                if not rows:
                    print("❌ No competencies found in database")
                    if specialization_filter:
                        print(f"   (Filter: specialization = '{specialization_filter}')")
                    return

                print(f"Found {len(rows)} competencies:\n")

                current_spec = None
                for row in rows:
                    comp_id, comp_name, weight, spec_name = row

                    if spec_name != current_spec:
                        print(f"\n📁 Specialization: {spec_name}")
                        current_spec = spec_name

                    print(f"   • {comp_name} (weight: {weight:.4f})")

                print("\n" + "="*60)
                print("💡 Use these exact names in your Excel file!")
                print("="*60)

    finally:
        await close_db_pool()


async def update_weights_from_excel(excel_file: str, specialization_filter: str = None):
    """
    Update competency weights from Excel file

    Excel columns:
    - competency_name: Name of competency (must match database exactly)
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

    updated = 0
    not_found = []

    try:
        # First, get all competencies from database to show what's available
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                if specialization_filter:
                    await cur.execute("""
                        SELECT c.name
                        FROM competencies c
                        JOIN specializations s ON c.specialization_id = s.id
                        WHERE s.name = %s
                    """, (specialization_filter,))
                else:
                    await cur.execute("SELECT name FROM competencies")

                db_competencies = [row[0] for row in await cur.fetchall()]

        print(f"📋 Database has {len(db_competencies)} competencies\n")

        # Now update
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                for _, row in df.iterrows():
                    comp_name = str(row['competency_name']).strip()
                    weight = float(row['normalized_weight'])

                    # Update competency
                    if specialization_filter:
                        await cur.execute("""
                            UPDATE competencies c
                            SET weight = %s
                            FROM specializations s
                            WHERE c.specialization_id = s.id
                            AND c.name = %s
                            AND s.name = %s
                        """, (weight, comp_name, specialization_filter))
                    else:
                        await cur.execute("""
                            UPDATE competencies
                            SET weight = %s
                            WHERE name = %s
                        """, (weight, comp_name))

                    if cur.rowcount > 0:
                        print(f"✅ Updated: {comp_name} → weight {weight:.4f}")
                        updated += 1
                    else:
                        not_found.append(comp_name)

        # Summary
        print(f"\n{'='*60}")
        print(f"📊 Summary:")
        print(f"   ✅ Updated: {updated}")
        print(f"   ❌ Not found: {len(not_found)}")

        if not_found:
            print(f"\n⚠️  These competencies were NOT found in database:")
            for name in not_found:
                print(f"   • {name}")

            print(f"\n💡 To see exact competency names in database, run:")
            print(f"   python update_weights_from_excel.py --list")
            if specialization_filter:
                print(f"   python update_weights_from_excel.py --list --specialization \"{specialization_filter}\"")

        print("="*60)

    finally:
        await close_db_pool()


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  List competencies:")
        print("    python update_weights_from_excel.py --list")
        print("    python update_weights_from_excel.py --list --specialization \"Data Analyst\"")
        print("")
        print("  Update from Excel:")
        print("    python update_weights_from_excel.py competencies.xlsx")
        print("    python update_weights_from_excel.py competencies.xlsx --specialization \"Data Analyst\"")
        print("\nExcel format:")
        print("  Column A: competency_name (must match database exactly)")
        print("  Column B: weight (any positive number)")
        return

    # Parse arguments
    args = sys.argv[1:]
    specialization = None
    excel_file = None
    list_mode = False

    i = 0
    while i < len(args):
        if args[i] == '--list':
            list_mode = True
        elif args[i] == '--specialization' and i + 1 < len(args):
            specialization = args[i + 1]
            i += 1
        elif not args[i].startswith('--'):
            excel_file = args[i]
        i += 1

    # Fix for Windows
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    if list_mode:
        # List mode
        asyncio.run(list_competencies(specialization))
    else:
        # Update mode
        if not excel_file:
            print("❌ Please provide Excel file")
            print("Usage: python update_weights_from_excel.py competencies.xlsx")
            return

        if not os.path.exists(excel_file):
            print(f"❌ File not found: {excel_file}")
            return

        asyncio.run(update_weights_from_excel(excel_file, specialization))


if __name__ == "__main__":
    main()
