"""
Script to update competency weights from HR Excel file

Usage:
    python update_weights_from_excel.py competencies.xlsx

Excel format:
    Column A: competency_name
    Column B: weight (0.0 to 1.0)
"""

import pandas as pd
import asyncio
import sys
import os

# Add parent directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database_v2 import init_db_pool, close_db_pool, get_db_connection

async def update_weights_from_excel(excel_file: str):
    """
    Update competency weights from Excel file

    Excel columns:
    - competency_name: Name of competency (must match database)
    - weight: Weight value (0.0 to 1.0)
    """

    print(f"📁 Reading {excel_file}...")
    df = pd.read_excel(excel_file)

    # Validate columns
    required_cols = ['competency_name', 'weight']
    if not all(col in df.columns for col in required_cols):
        print(f"❌ Excel must have columns: {required_cols}")
        return

    # Normalize weights to sum to 1.0
    total_weight = df['weight'].sum()
    df['normalized_weight'] = df['weight'] / total_weight

    print(f"\n📊 Found {len(df)} competencies")
    print(f"Total weight: {total_weight} → normalized to 1.0\n")

    # Initialize database
    await init_db_pool()

    updated = 0
    not_found = 0

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                for _, row in df.iterrows():
                    comp_name = row['competency_name']
                    weight = row['normalized_weight']

                    # Update competency
                    await cur.execute("""
                        UPDATE competencies
                        SET weight = %s
                        WHERE name = %s
                    """, (weight, comp_name))

                    if cur.rowcount > 0:
                        print(f"✅ Updated: {comp_name} → weight {weight:.4f}")
                        updated += 1
                    else:
                        print(f"⚠️  Not found: {comp_name}")
                        not_found += 1

        print(f"\n📊 Summary:")
        print(f"   Updated: {updated}")
        print(f"   Not found: {not_found}")

    finally:
        await close_db_pool()

def main():
    if len(sys.argv) < 2:
        print("Usage: python update_weights_from_excel.py competencies.xlsx")
        print("\nExcel format:")
        print("  Column A: competency_name")
        print("  Column B: weight (0.0 to 1.0)")
        return

    excel_file = sys.argv[1]

    if not os.path.exists(excel_file):
        print(f"❌ File not found: {excel_file}")
        return

    # Fix for Windows
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(update_weights_from_excel(excel_file))

if __name__ == "__main__":
    main()
