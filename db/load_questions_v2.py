"""
Load questions from encrypted JSON files into database (Schema V2)

This script:
1. Reads JSON files from specializations/output/final/
2. Decrypts questions (if encryption key provided)
3. Creates profiles, specializations, competencies, topics
4. Inserts all questions into hr_test.questions table

Usage:
    python load_questions_v2.py [--decrypt-key YOUR_KEY]
"""

import asyncio
import sys
import os
import json
from pathlib import Path

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import init_db_pool, close_db_pool, get_db_connection

# Encryption support (optional)
ENCRYPTION_KEY = None
try:
    from cryptography.fernet import Fernet
    ENCRYPTION_AVAILABLE = True
except ImportError:
    print("⚠️  cryptography not installed. Install with: pip install cryptography")
    ENCRYPTION_AVAILABLE = False


def decrypt_text(encrypted_text: str, key: str = None) -> str:
    """Decrypt Fernet-encrypted text"""
    if not ENCRYPTION_AVAILABLE:
        raise Exception("cryptography library not available")

    if not key:
        raise Exception("Encryption key not provided")

    cipher = Fernet(key.encode())
    decrypted = cipher.decrypt(encrypted_text.encode())
    return decrypted.decode()


def load_json_file(file_path: Path) -> dict:
    """Load JSON file"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


async def get_or_create_profile(conn, profile_name: str) -> int:
    """Get or create profile, return ID"""
    async with conn.cursor() as cur:
        # Check if exists
        await cur.execute(
            "SELECT id FROM hr_test.profiles WHERE name = %s",
            (profile_name,)
        )
        row = await cur.fetchone()
        if row:
            return row[0]

        # Create new
        await cur.execute(
            "INSERT INTO hr_test.profiles (name, has_specializations) VALUES (%s, TRUE) RETURNING id",
            (profile_name,)
        )
        row = await cur.fetchone()
        print(f"   ✅ Created profile: {profile_name}")
        return row[0]


async def get_or_create_specialization(conn, profile_id: int, spec_name: str, file_name: str) -> int:
    """Get or create specialization, return ID"""
    async with conn.cursor() as cur:
        # Check if exists
        await cur.execute(
            "SELECT id FROM hr_test.specializations WHERE profile_id = %s AND name = %s",
            (profile_id, spec_name)
        )
        row = await cur.fetchone()
        if row:
            return row[0]

        # Create new
        await cur.execute(
            """INSERT INTO hr_test.specializations (profile_id, name, json_file_name)
               VALUES (%s, %s, %s) RETURNING id""",
            (profile_id, spec_name, file_name)
        )
        row = await cur.fetchone()
        print(f"   ✅ Created specialization: {spec_name}")
        return row[0]


async def get_or_create_competency(conn, specialization_id: int, comp_name: str, weight: float = 1.0) -> int:
    """Get or create competency, return ID"""
    async with conn.cursor() as cur:
        # Check if exists
        await cur.execute(
            "SELECT id FROM hr_test.competencies WHERE specialization_id = %s AND name = %s",
            (specialization_id, comp_name)
        )
        row = await cur.fetchone()
        if row:
            return row[0]

        # Create new
        await cur.execute(
            """INSERT INTO hr_test.competencies (specialization_id, name, weight)
               VALUES (%s, %s, %s) RETURNING id""",
            (specialization_id, comp_name, weight)
        )
        row = await cur.fetchone()
        return row[0]


async def get_or_create_topic(conn, competency_id: int, topic_name: str) -> int:
    """Get or create topic, return ID"""
    async with conn.cursor() as cur:
        # Check if exists
        await cur.execute(
            "SELECT id FROM hr_test.topics WHERE competency_id = %s AND name = %s",
            (competency_id, topic_name)
        )
        row = await cur.fetchone()
        if row:
            return row[0]

        # Create new
        await cur.execute(
            """INSERT INTO hr_test.topics (competency_id, name)
               VALUES (%s, %s) RETURNING id""",
            (competency_id, topic_name)
        )
        row = await cur.fetchone()
        return row[0]


async def insert_question(conn, specialization_id: int, competency_id: int, topic_id: int,
                          level: str, question_data: dict, decrypt_key: str = None):
    """Insert a single question into database"""

    # Decrypt if needed
    if decrypt_key and ENCRYPTION_AVAILABLE:
        try:
            question_text = decrypt_text(question_data['question'], decrypt_key)
            var_1 = decrypt_text(question_data['var_1'], decrypt_key)
            var_2 = decrypt_text(question_data['var_2'], decrypt_key)
            var_3 = decrypt_text(question_data['var_3'], decrypt_key)
            var_4 = decrypt_text(question_data['var_4'], decrypt_key)
        except Exception as e:
            print(f"      ❌ Decryption failed: {e}")
            return False
    else:
        # Use as-is (assume already decrypted or will be handled later)
        question_text = question_data.get('question', '')
        var_1 = question_data.get('var_1', '')
        var_2 = question_data.get('var_2', '')
        var_3 = question_data.get('var_3', '')
        var_4 = question_data.get('var_4', '')

    # Correct answer position
    correct_answer = question_data.get('correct_position', question_data.get('correct_answer', 1))

    async with conn.cursor() as cur:
        await cur.execute("""
            INSERT INTO hr_test.questions
            (specialization_id, competency_id, topic_id, level, question_text, var_1, var_2, var_3, var_4, correct_answer)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (specialization_id, competency_id, topic_id, level, question_text, var_1, var_2, var_3, var_4, correct_answer))

    return True


async def load_questions_from_json(json_file: Path, decrypt_key: str = None):
    """
    Load questions from a JSON file into database

    Expected structure:
    {
      "profile": "Data Analyst",
      "specialization": "Data Analyst",
      "file_name": "Data_Analyst",
      "levels": {
        "junior": {
          "themes": [
            {
              "theme": "...",
              "competency": "...",
              "questions": [...]
            }
          ]
        },
        "middle": {...},
        "senior": {...}
      }
    }
    """

    print(f"\n📁 Loading: {json_file.name}")

    data = load_json_file(json_file)

    profile_name = data.get('profile')
    spec_name = data.get('specialization')
    file_name = data.get('file_name')

    if not all([profile_name, spec_name]):
        print(f"   ❌ Missing profile or specialization in {json_file.name}")
        return

    async with get_db_connection() as conn:
        # Create profile
        profile_id = await get_or_create_profile(conn, profile_name)

        # Create specialization
        spec_id = await get_or_create_specialization(conn, profile_id, spec_name, json_file.name)

        # Process each level (junior, middle, senior)
        levels = data.get('levels', {})

        total_questions = 0
        total_themes = 0

        for level_name, level_data in levels.items():
            themes = level_data.get('themes', [])
            print(f"\n   📊 Level: {level_name.upper()} ({len(themes)} themes)")

            for theme_data in themes:
                theme_name = theme_data.get('theme')
                competency_name = theme_data.get('competency')
                questions = theme_data.get('questions', [])

                if not theme_name or not competency_name:
                    continue

                total_themes += 1

                # Create competency
                comp_id = await get_or_create_competency(conn, spec_id, competency_name)

                # Create topic (theme)
                topic_id = await get_or_create_topic(conn, comp_id, theme_name)

                # Insert questions
                for question_data in questions:
                    success = await insert_question(
                        conn, spec_id, comp_id, topic_id,
                        level_name, question_data, decrypt_key
                    )
                    if success:
                        total_questions += 1

        print(f"\n   ✅ Loaded: {total_questions} questions from {total_themes} themes")


async def main():
    """Main function"""

    # Parse arguments
    decrypt_key = None
    if len(sys.argv) > 2 and sys.argv[1] == '--decrypt-key':
        decrypt_key = sys.argv[2]
        print(f"🔑 Using decryption key: {decrypt_key[:10]}...")

    print("🚀 Starting question loader (Schema V2)...")

    # Initialize database
    await init_db_pool()

    # Find JSON files
    json_dir = Path(__file__).parent.parent / "specializations" / "output" / "final"

    if not json_dir.exists():
        print(f"❌ Directory not found: {json_dir}")
        await close_db_pool()
        return

    json_files = list(json_dir.glob("*.json"))

    if not json_files:
        print(f"❌ No JSON files found in {json_dir}")
        await close_db_pool()
        return

    print(f"📚 Found {len(json_files)} JSON file(s)")

    # Load each file
    for json_file in json_files:
        try:
            await load_questions_from_json(json_file, decrypt_key)
        except Exception as e:
            print(f"❌ Error loading {json_file.name}: {e}")
            import traceback
            traceback.print_exc()

    # Close database
    await close_db_pool()

    print("\n✅ Question loading complete!")


if __name__ == "__main__":
    # Fix for Windows
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())
