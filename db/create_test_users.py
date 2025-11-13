import asyncio
import sys
import os

# FIX для Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import init_db_pool, close_db_pool, get_db_connection
from auth import create_access_token


async def create_test_users():
    """Create sample test users across all roles and departments"""

    print("🚀 Creating test users...")
    await init_db_pool()

    # Sample users data
    test_users = [
        # HR Users
        {
            "name": "HR",
            "surname": "Manager",
            "phone": "+77001111111",
            "company": "Халык банк",
            "job_title": "HR Manager",
            "role": "hr",
            "department_id": 7  # HR department
        },
        {
            "name": "HR",
            "surname": "Specialist",
            "phone": "+77001111112",
            "company": "Халык банк",
            "job_title": "HR Specialist",
            "role": "hr",
            "department_id": 7
        },

        # Backend Development Managers
        {
            "name": "Бекенд",
            "surname": "Руководитель",
            "phone": "+77002222221",
            "company": "Халык банк",
            "job_title": "Backend Team Lead",
            "role": "manager",
            "department_id": 1  # Backend Development
        },

        # Frontend Development Manager
        {
            "name": "Фронтенд",
            "surname": "Руководитель",
            "phone": "+77002222222",
            "company": "Халык банк",
            "job_title": "Frontend Team Lead",
            "role": "manager",
            "department_id": 2  # Frontend Development
        },

        # Mobile Development Manager
        {
            "name": "Мобайл",
            "surname": "Руководитель",
            "phone": "+77002222223",
            "company": "Халык банк",
            "job_title": "Mobile Team Lead",
            "role": "manager",
            "department_id": 3  # Mobile Development
        },

        # Data Science Manager
        {
            "name": "Дата",
            "surname": "Руководитель",
            "phone": "+77002222224",
            "company": "Халык банк",
            "job_title": "Data Science Lead",
            "role": "manager",
            "department_id": 4  # Data Science
        },

        # Backend Employees
        {
            "name": "Алексей",
            "surname": "Иванов",
            "phone": "+77003333331",
            "company": "Халык банк",
            "job_title": "Python Developer",
            "role": "employee",
            "department_id": 1  # Backend Development
        },
        {
            "name": "Дмитрий",
            "surname": "Петров",
            "phone": "+77003333332",
            "company": "Халык банк",
            "job_title": "Java Developer",
            "role": "employee",
            "department_id": 1
        },
        {
            "name": "Сергей",
            "surname": "Сидоров",
            "phone": "+77003333333",
            "company": "Халык банк",
            "job_title": "Go Developer",
            "role": "employee",
            "department_id": 1
        },

        # Frontend Employees
        {
            "name": "Анна",
            "surname": "Смирнова",
            "phone": "+77003333334",
            "company": "Халык банк",
            "job_title": "React Developer",
            "role": "employee",
            "department_id": 2  # Frontend Development
        },
        {
            "name": "Мария",
            "surname": "Козлова",
            "phone": "+77003333335",
            "company": "Халык банк",
            "job_title": "Angular Developer",
            "role": "employee",
            "department_id": 2
        },

        # Mobile Employees
        {
            "name": "Иван",
            "surname": "Морозов",
            "phone": "+77003333336",
            "company": "Халык банк",
            "job_title": "iOS Developer",
            "role": "employee",
            "department_id": 3  # Mobile Development
        },
        {
            "name": "Павел",
            "surname": "Новиков",
            "phone": "+77003333337",
            "company": "Халык банк",
            "job_title": "Android Developer",
            "role": "employee",
            "department_id": 3
        },

        # Data Science Employees
        {
            "name": "Елена",
            "surname": "Волкова",
            "phone": "+77003333338",
            "company": "Халык банк",
            "job_title": "Data Scientist",
            "role": "employee",
            "department_id": 4  # Data Science
        },
        {
            "name": "Ольга",
            "surname": "Соколова",
            "phone": "+77003333339",
            "company": "Халык банк",
            "job_title": "Data Analyst",
            "role": "employee",
            "department_id": 4
        },

        # QA Employees
        {
            "name": "Андрей",
            "surname": "Лебедев",
            "phone": "+77003333340",
            "company": "Халык банк",
            "job_title": "QA Engineer",
            "role": "employee",
            "department_id": 5  # QA
        },

        # DevOps Employees
        {
            "name": "Николай",
            "surname": "Егоров",
            "phone": "+77003333341",
            "company": "Халык банк",
            "job_title": "DevOps Engineer",
            "role": "employee",
            "department_id": 6  # DevOps
        }
    ]

    created_count = 0
    skipped_count = 0

    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            for user_data in test_users:
                try:
                    # Check if user already exists
                    await cur.execute(
                        "SELECT id FROM users WHERE phone = %s",
                        (user_data["phone"],)
                    )
                    existing = await cur.fetchone()

                    if existing:
                        print(f"⚪ Skipped: {user_data['name']} {user_data['surname']} (phone already exists)")
                        skipped_count += 1
                        continue

                    # Create user
                    await cur.execute(
                        """INSERT INTO users (name, surname, phone, company, job_title, role, department_id)
                           VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                        (
                            user_data["name"],
                            user_data["surname"],
                            user_data["phone"],
                            user_data["company"],
                            user_data["job_title"],
                            user_data["role"],
                            user_data["department_id"]
                        )
                    )
                    user_id = (await cur.fetchone())[0]

                    # Get department name
                    await cur.execute("SELECT name FROM departments WHERE id = %s", (user_data["department_id"],))
                    dept_name = (await cur.fetchone())[0]

                    role_emoji = "👔" if user_data["role"] == "hr" else "👨‍💼" if user_data["role"] == "manager" else "👨‍💻"

                    print(f"✅ Created: {role_emoji} {user_data['name']} {user_data['surname']} - {user_data['role']} @ {dept_name}")
                    print(f"   Phone: {user_data['phone']}")
                    created_count += 1

                except Exception as e:
                    print(f"❌ Error creating {user_data['name']} {user_data['surname']}: {e}")

    await close_db_pool()

    print(f"\n{'='*60}")
    print(f"📊 SUMMARY")
    print(f"{'='*60}")
    print(f"✅ Created: {created_count} users")
    print(f"⚪ Skipped: {skipped_count} users (already exist)")
    print(f"📱 Total: {len(test_users)} users processed")
    print(f"{'='*60}")

    print("\n📋 TEST CREDENTIALS:")
    print("=" * 60)
    print("\n🔐 HR Users (can view ALL departments):")
    print("   Phone: +77001111111 (HR Manager)")
    print("   Phone: +77001111112 (HR Specialist)")

    print("\n👨‍💼 Managers (can view ONLY their department):")
    print("   Phone: +77002222221 (Backend Team Lead)")
    print("   Phone: +77002222222 (Frontend Team Lead)")
    print("   Phone: +77002222223 (Mobile Team Lead)")
    print("   Phone: +77002222224 (Data Science Lead)")

    print("\n👨‍💻 Employees (by department):")
    print("   Backend Development:")
    print("      +77003333331 - Алексей Иванов (Python)")
    print("      +77003333332 - Дмитрий Петров (Java)")
    print("      +77003333333 - Сергей Сидоров (Go)")
    print("   Frontend Development:")
    print("      +77003333334 - Анна Смирнова (React)")
    print("      +77003333335 - Мария Козлова (Angular)")
    print("   Mobile Development:")
    print("      +77003333336 - Иван Морозов (iOS)")
    print("      +77003333337 - Павел Новиков (Android)")
    print("   Data Science:")
    print("      +77003333338 - Елена Волкова (Data Scientist)")
    print("      +77003333339 - Ольга Соколова (Data Analyst)")
    print("   QA:")
    print("      +77003333340 - Андрей Лебедев")
    print("   DevOps:")
    print("      +77003333341 - Николай Егоров")

    print("\n" + "=" * 60)
    print("💡 To login, use any phone number above")
    print("=" * 60)


async def main():
    await create_test_users()


if __name__ == "__main__":
    asyncio.run(main())
