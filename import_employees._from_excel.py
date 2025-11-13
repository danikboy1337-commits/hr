#!/usr/bin/env python3
"""
Import employee data from Excel file to database
Matches the exact schema: name, tab_number, department_id, role
"""

import sys
import asyncio
import pandas as pd
sys.path.append('.')

from db.database import init_db_pool, close_db_pool, get_db_connection

async def import_employees_from_excel(excel_file_path: str):
    """Import employee data from Excel file"""

    print("=" * 70)
    print("📊 IMPORTING EMPLOYEE DATA FROM EXCEL")
    print("=" * 70)

    # Initialize database pool
    print("\n🔌 Initializing database connection pool...")
    await init_db_pool()

    try:
        # Read Excel file
        print(f"\n📖 Reading Excel file: {excel_file_path}")

        try:
            df = pd.read_excel(excel_file_path)
        except Exception as e:
            print(f"❌ Failed to read Excel file: {e}")
            print("\nMake sure you have openpyxl installed:")
            print("  pip install openpyxl pandas")
            return False

        print(f"✅ Found {len(df)} rows in Excel file")
        print(f"📋 Columns found: {list(df.columns)}")

        # Validate required columns
        required_columns = ['name', 'tab_number', 'department_id', 'role']
        missing_columns = [col for col in required_columns if col not in df.columns]

        if missing_columns:
            print(f"\n❌ Error: Missing required columns: {missing_columns}")
            print(f"\nExpected columns: {required_columns}")
            print(f"Found columns: {list(df.columns)}")
            return False

        # Connect to database
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:

                # First, ensure the 4 departments exist
                print("\n📦 Setting up departments...")

                departments = [
                    (1, 'Halyk Super App'),
                    (2, 'Onlinebank'),
                    (3, 'OCDS'),
                    (4, 'AI')
                ]

                for dept_id, dept_name in departments:
                    await cur.execute(
                        """INSERT INTO departments (id, name, description)
                           VALUES (%s, %s, %s)
                           ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name""",
                        (dept_id, dept_name, f'{dept_name} department')
                    )

                await conn.commit()
                print(f"✅ Departments configured: {[d[1] for d in departments]}")

                # Now import employees
                print("\n👥 Importing employees...")
                print("   (Auto-fixing Excel format: padding tab_numbers with leading zeros)")
                print("   Examples: 62704 → 00062704, 238 → 00000238\n")

                imported_count = 0
                updated_count = 0
                skipped_count = 0
                errors = []
                conversions_shown = 0

                for idx, row in df.iterrows():
                    try:
                        # Get required fields
                        tab_number_raw = str(row['tab_number']).strip()
                        name = str(row['name']).strip()
                        department_id = int(row['department_id'])
                        role = str(row['role']).strip().lower()

                        # Validate data
                        if not tab_number_raw or tab_number_raw.lower() in ['nan', 'none', '']:
                            errors.append(f"Row {idx+2}: Missing tab_number")
                            skipped_count += 1
                            continue

                        # Fix Excel issue: pad tab_number with leading zeros to 8 digits
                        # Examples: "62704" -> "00062704", "238" -> "00000238"
                        try:
                            # Remove any non-digit characters and convert to int then back to string
                            tab_number_clean = ''.join(filter(str.isdigit, tab_number_raw))
                            if tab_number_clean:
                                # Pad with leading zeros to make it 8 digits
                                tab_number = tab_number_clean.zfill(8)

                                # Show first few conversions as examples
                                if tab_number_raw != tab_number and conversions_shown < 3:
                                    print(f"   📝 Converting: {tab_number_raw} → {tab_number}")
                                    conversions_shown += 1
                            else:
                                errors.append(f"Row {idx+2}: Invalid tab_number '{tab_number_raw}' (no digits found)")
                                skipped_count += 1
                                continue
                        except Exception as e:
                            errors.append(f"Row {idx+2}: Failed to process tab_number '{tab_number_raw}': {e}")
                            skipped_count += 1
                            continue

                        if not name or name.lower() in ['nan', 'none', '']:
                            errors.append(f"Row {idx+2}: Missing name for {tab_number}")
                            skipped_count += 1
                            continue

                        # Validate department_id
                        if department_id not in [1, 2, 3, 4]:
                            errors.append(f"Row {idx+2}: Invalid department_id {department_id} for {tab_number} (must be 1-4)")
                            skipped_count += 1
                            continue

                        # Validate role
                        if role not in ['employee', 'hr', 'manager']:
                            errors.append(f"Row {idx+2}: Invalid role '{role}' for {tab_number}, defaulting to 'employee'")
                            role = 'employee'

                        # Check if user exists
                        await cur.execute(
                            "SELECT id FROM users WHERE tab_number = %s",
                            (tab_number,)
                        )
                        existing_user = await cur.fetchone()

                        if existing_user:
                            # Update existing user
                            await cur.execute(
                                """UPDATE users
                                   SET name = %s, role = %s, department_id = %s
                                   WHERE tab_number = %s""",
                                (name, role, department_id, tab_number)
                            )
                            updated_count += 1
                        else:
                            # Insert new user
                            await cur.execute(
                                """INSERT INTO users (name, tab_number, company, role, department_id)
                                   VALUES (%s, %s, %s, %s, %s)""",
                                (name, tab_number, 'Halyk Bank', role, department_id)
                            )
                            imported_count += 1

                        if (imported_count + updated_count) % 10 == 0:
                            print(f"   Processed {imported_count + updated_count} employees...")

                    except Exception as e:
                        errors.append(f"Row {idx+2}: Error processing {tab_number if 'tab_number' in locals() else 'unknown'}: {e}")
                        skipped_count += 1
                        continue

                await conn.commit()

                print(f"\n✅ Import complete!")
                print(f"   📥 New employees imported: {imported_count}")
                print(f"   🔄 Existing employees updated: {updated_count}")
                print(f"   ⏭️  Rows skipped: {skipped_count}")

                if errors:
                    print(f"\n⚠️  Errors encountered:")
                    for error in errors[:10]:  # Show first 10 errors
                        print(f"   - {error}")
                    if len(errors) > 10:
                        print(f"   ... and {len(errors) - 10} more errors")

                # Show summary
                await cur.execute("SELECT COUNT(*) FROM users")
                total_users = (await cur.fetchone())[0]

                await cur.execute("""
                    SELECT d.name, COUNT(u.id)
                    FROM departments d
                    LEFT JOIN users u ON d.id = u.department_id
                    GROUP BY d.id, d.name
                    ORDER BY d.id
                """)
                dept_summary = await cur.fetchall()

                print(f"\n📊 Database Summary:")
                print(f"   Total users: {total_users}")
                print(f"\n   Users by department:")
                for dept_name, count in dept_summary:
                    print(f"   - {dept_name}: {count} employees")

                # Role distribution
                await cur.execute("""
                    SELECT role, COUNT(*)
                    FROM users
                    GROUP BY role
                    ORDER BY role
                """)
                role_summary = await cur.fetchall()

                print(f"\n   Users by role:")
                for role_name, count in role_summary:
                    print(f"   - {role_name}: {count} employees")

    except Exception as e:
        print(f"\n❌ Import failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Close database pool
        print("\n🔌 Closing database connection pool...")
        await close_db_pool()

    print("\n" + "=" * 70)
    print("✅ IMPORT COMPLETE")
    print("=" * 70)
    print("\nYou can now:")
    print("  1. Run the application: python main.py")
    print("  2. Employees can log in with their tab_number and AD password")
    print("  3. Their role and department will be automatically loaded")
    print("\n")

    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python import_employees.py <excel_file_path>")
        print("\nExample:")
        print("  python import_employees.py employees.xlsx")
        print("  python import_employees.py /path/to/employees.xlsx")
        print("\nExpected Excel columns:")
        print("  - name: Employee full name")
        print("  - tab_number: Employee ID (format: 00012345)")
        print("  - department_id: Department ID (1=Halyk Super App, 2=Onlinebank, 3=OCDS, 4=AI)")
        print("  - role: Role (employee, hr, or manager)")
        sys.exit(1)

    excel_file = sys.argv[1]

    try:
        result = asyncio.run(import_employees_from_excel(excel_file))
        sys.exit(0 if result else 1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)