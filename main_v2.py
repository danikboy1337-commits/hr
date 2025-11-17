"""
HR Testing Platform V2 - Main Application
LDAP-based authentication with tab_number (instead of phone)
New question structure: 20 triplets = 60 questions per test

Changes from V1:
- Uses hr_test schema (not hr)
- tab_number for user identification (not phone)
- 60 questions per test (20 junior + 20 middle + 20 senior)
- Questions stored encrypted
- Simplified user model (no surname, phone optional)
"""

import sys
import os

# CRITICAL: Enable OpenSSL legacy provider for MD4 support (required for NTLM/LDAP)
os.environ['OPENSSL_CONF'] = os.path.join(os.path.dirname(__file__), 'openssl_legacy.cnf')

from fastapi import FastAPI, Request, HTTPException, Header, Depends, Response, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any

# Monitoring
import psutil
import time
import json
from datetime import datetime, timedelta
from collections import deque

# Fix for Windows asyncio
if sys.platform == 'win32':
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# V2 imports
from db.database_v2 import init_db_pool, close_db_pool, get_db_connection
from db.question_algorithm_v2 import generate_test_themes_v2
import config_v2 as config
from auth_v2 import create_access_token, verify_token

import httpx

print(f"🔧 Config: DB_SCHEMA={config.DB_SCHEMA}, THEMES_PER_TEST={config.THEMES_PER_TEST}, TOTAL_QUESTIONS={config.TOTAL_QUESTIONS}")

# Anthropic Claude AI (OPTIONAL)
try:
    import anthropic
    http_client = httpx.Client(timeout=30.0)
    claude_client = anthropic.Anthropic(
        api_key=config.ANTHROPIC_API_KEY,
        http_client=http_client
    )
    ANTHROPIC_AVAILABLE = True
    print("✅ Anthropic Claude AI client initialized")
except ImportError:
    ANTHROPIC_AVAILABLE = False
    claude_client = None
    print("⚠️  Anthropic not available (using rule-based recommendations)")
except Exception as e:
    ANTHROPIC_AVAILABLE = False
    claude_client = None
    print(f"⚠️  Anthropic initialization failed: {e}")

# LDAP Authentication
try:
    from ldap import authenticate_user as ldap_authenticate_user
    LDAP_AVAILABLE = True
    print("✅ LDAP authentication module loaded successfully")
except ImportError as e:
    LDAP_AVAILABLE = False
    print(f"⚠️  LDAP module not available: {e}")

# =====================================================
# MONITORING
# =====================================================
monitoring_data = {
    "requests": deque(maxlen=10000),
    "active_users": {},
    "start_time": time.time()
}

# =====================================================
# PYDANTIC MODELS
# =====================================================
class LDAPLoginRequest(BaseModel):
    employee_id: str  # Employee tab number (e.g., "00061221") - keeping field name for frontend compatibility
    password: str

class TestStart(BaseModel):
    pass  # specialization_id comes from user record

class SpecializationSelect(BaseModel):
    specialization_id: int

class AnswerSubmit(BaseModel):
    user_test_id: int  # Frontend uses user_test_id
    question_id: int
    user_answer: int  # 1-4

class SelfAssessmentSubmit(BaseModel):
    assessments: List[Dict[str, Any]]  # [{"competency_id": 1, "self_rating": 8}, ...]
    # Note: test_session_id comes from URL path, not request body

class ProctoringEventSubmit(BaseModel):
    user_test_id: int
    event_type: str  # e.g., 'face_not_detected', 'multiple_faces', 'tab_switch'
    severity: str = "medium"  # 'low', 'medium', 'high', 'critical'
    details: Optional[dict] = None

class SQLQuery(BaseModel):
    query: str

# =====================================================
# LIFECYCLE
# =====================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting HR Testing Platform V2...")
    await init_db_pool()
    print("✅ Database pool ready (hr_test schema)")
    yield
    print("🔄 Shutting down...")
    await close_db_pool()

# =====================================================
# FASTAPI APP
# =====================================================
app = FastAPI(
    title="Halyk HR Testing Platform V2",
    description="Система тестирования компетенций (LDAP + 60 questions)",
    lifespan=lifespan
)

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# =====================================================
# MIDDLEWARE - MONITORING
# =====================================================
@app.middleware("http")
async def monitor_requests(request: Request, call_next):
    start_time = time.time()

    # Extract user_id from token
    user_id = None
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "")
        user_data = verify_token(token)
        if user_data:
            user_id = user_data.get("user_id")
            monitoring_data["active_users"][user_id] = datetime.now()

    try:
        response = await call_next(request)
        response_time = (time.time() - start_time) * 1000

        monitoring_data["requests"].append({
            "endpoint": request.url.path,
            "method": request.method,
            "response_time": response_time,
            "timestamp": datetime.now(),
            "user_id": user_id
        })

        return response
    except Exception as e:
        raise

# =====================================================
# DEPENDENCY - AUTH
# =====================================================
async def get_current_user(authorization: Optional[str] = Header(None)):
    """Verify JWT token and return user data"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.replace("Bearer ", "")
    user_data = verify_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user_data

# =====================================================
# DEPENDENCY - HR AUTH
# =====================================================
async def verify_hr_cookie(hr_token: Optional[str] = Cookie(None)):
    """Verify HR cookie"""
    if not hr_token:
        return None

    user_data = verify_token(hr_token)
    if user_data and user_data.get("role") == "hr":
        return user_data
    return None

# =====================================================
# HTML ROUTES - PUBLIC
# =====================================================
@app.get("/", response_class=HTMLResponse)
async def home():
    """Redirect to login"""
    return RedirectResponse(url="/login", status_code=302)

@app.get("/login", response_class=HTMLResponse)
async def login_page():
    """LDAP login page"""
    with open('templates/login.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/panels", response_class=HTMLResponse)
async def panels_page():
    """Panel selection page after login"""
    with open('templates/panels.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/specializations", response_class=HTMLResponse)
async def specializations_page():
    """Specialization selection page"""
    with open('templates/specializations.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/test", response_class=HTMLResponse)
async def test_page():
    """Test taking interface"""
    with open('templates/test.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/results", response_class=HTMLResponse)
async def results_page():
    """Test results page"""
    with open('templates/results.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/health")
async def health():
    """Health check"""
    return {"status": "ok", "service": "hr-testing-v2", "schema": config.DB_SCHEMA}

# =====================================================
# API - PUBLIC CONFIG
# =====================================================
@app.get("/api/config")
async def get_public_config():
    """Return public configuration"""
    return {
        "recaptcha_site_key": config.RECAPTCHA_SITE_KEY,
        "org_name": config.ORG_NAME,
        "org_logo": config.ORG_LOGO,
        "ldap_enabled": config.LDAP_ENABLED,
        "auth_method": "ldap",
        "total_questions": config.TOTAL_QUESTIONS,
        "themes_per_test": config.THEMES_PER_TEST
    }

@app.get("/api/departments")
async def get_departments():
    """Get list of all departments"""
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT id, name, description FROM departments ORDER BY name")
                rows = await cur.fetchall()
                departments = [
                    {"id": row[0], "name": row[1], "description": row[2]}
                    for row in rows
                ]
                return {"status": "success", "departments": departments}
    except Exception as e:
        print(f"Error fetching departments: {e}")
        return {"status": "success", "departments": []}

# =====================================================
# API - AUTHENTICATION
# =====================================================
@app.post("/api/login")
async def ldap_login(login_data: LDAPLoginRequest):
    """
    LDAP authentication endpoint (V2)
    Uses employee_id (tab_number) instead of phone

    Request:
        {
            "employee_id": "00061221",
            "password": "user_password"
        }

    Returns (flat structure for frontend compatibility):
        {
            "status": "success",
            "token": "jwt_token_here",
            "user_id": 1,
            "name": "Danial Aibassov",
            "employee_id": "00061221",
            "tab_number": "00061221",
            "role": "employee",
            "department_id": 3,
            "specialization_id": 1
        }
    """

    if not LDAP_AVAILABLE:
        raise HTTPException(status_code=500, detail="LDAP authentication not available")

    try:
        # Authenticate with LDAP
        ldap_user = ldap_authenticate_user(login_data.employee_id, login_data.password)

        # Get or create user in database
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Check if user exists
                await cur.execute(
                    "SELECT id, name, tab_number, role, department_id, specialization_id FROM users WHERE tab_number = %s",
                    (login_data.employee_id,)
                )
                user_row = await cur.fetchone()

                if user_row:
                    # User exists - update last login
                    user_id, name, tab_number, role, department_id, specialization_id = user_row
                else:
                    # Create new user
                    await cur.execute("""
                        INSERT INTO users (name, tab_number, company, role)
                        VALUES (%s, %s, 'Halyk Bank', 'employee')
                        RETURNING id, name, tab_number, role, department_id, specialization_id
                    """, (ldap_user['name'], login_data.employee_id))

                    user_row = await cur.fetchone()
                    user_id, name, tab_number, role, department_id, specialization_id = user_row
                    print(f"✅ Created new user: {name} ({tab_number})")

        # Create JWT token
        token = create_access_token(
            user_id=user_id,
            tab_number=tab_number,
            role=role,
            department_id=department_id
        )

        # Return format matching frontend expectations (flat structure, not nested)
        return {
            "status": "success",
            "token": token,
            "user_id": user_id,
            "name": name,
            "employee_id": tab_number,  # Frontend uses employee_id
            "tab_number": tab_number,   # Keep for compatibility
            "role": role,
            "department_id": department_id,
            "specialization_id": specialization_id
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Login error: {e}")
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

# =====================================================
# API - PROFILES & SPECIALIZATIONS
# =====================================================
@app.get("/api/profiles")
async def get_profiles():
    """Get all profiles with specializations"""
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT id, name, has_specializations FROM profiles ORDER BY id")
                rows = await cur.fetchall()

        profiles = [{"id": row[0], "name": row[1], "has_specializations": row[2]} for row in rows]
        return {"status": "success", "profiles": profiles}
    except Exception as e:
        print(f"Error fetching profiles: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/profiles/{profile_id}/specializations")
async def get_specializations(profile_id: int):
    """Get specializations for a specific profile"""
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT id, name FROM specializations WHERE profile_id = %s ORDER BY id",
                    (profile_id,)
                )
                rows = await cur.fetchall()

        specializations = [{"id": row[0], "name": row[1]} for row in rows]
        return {"status": "success", "specializations": specializations}
    except Exception as e:
        print(f"Error fetching specializations: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/select-specialization")
async def select_specialization(data: SpecializationSelect, current_user: dict = Depends(get_current_user)):
    """Update user's specialization"""
    user_id = current_user["user_id"]
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Update user's specialization_id
                await cur.execute(
                    "UPDATE users SET specialization_id = %s WHERE id = %s",
                    (data.specialization_id, user_id)
                )
        return {"status": "success"}
    except Exception as e:
        print(f"Error selecting specialization: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================
# API - TEST FLOW
# =====================================================
@app.post("/api/start-test")
async def start_test(user_data: dict = Depends(get_current_user)):
    """
    Start a new test for user (V2)
    Generates 60 questions (20 triplets) based on user's specialization

    Returns:
        {
            "status": "success",
            "test_session_id": 1,
            "total_questions": 60,
            "specialization": "Data Analyst"
        }
    """

    user_id = user_data["user_id"]

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Get user's specialization
                await cur.execute(
                    "SELECT specialization_id FROM users WHERE id = %s",
                    (user_id,)
                )
                row = await cur.fetchone()

                if not row or not row[0]:
                    raise HTTPException(
                        status_code=400,
                        detail="User has no specialization assigned. Contact HR to assign a specialization."
                    )

                specialization_id = row[0]

                # Get specialization name
                await cur.execute(
                    "SELECT name FROM specializations WHERE id = %s",
                    (specialization_id,)
                )
                spec_row = await cur.fetchone()
                specialization_name = spec_row[0] if spec_row else "Unknown"

                # Create test session
                await cur.execute("""
                    INSERT INTO user_test_time
                    (user_id, specialization_id, created_date, max_score, completed)
                    VALUES (%s, %s, %s, %s, FALSE)
                    RETURNING id
                """, (user_id, specialization_id, datetime.now(), config.TOTAL_QUESTIONS))

                test_session_id = (await cur.fetchone())[0]

        # Generate questions using V2 algorithm (20 triplets = 60 questions)
        async with get_db_connection() as conn:
            num_questions = await generate_test_themes_v2(
                user_id, test_session_id, specialization_id, conn
            )

        return {
            "status": "success",
            "user_test_id": test_session_id,  # Frontend expects user_test_id
            "test_session_id": test_session_id,  # Keep for backward compatibility
            "total_questions": num_questions,
            "expected_questions": config.TOTAL_QUESTIONS,
            "specialization": specialization_name
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Start test error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to start test: {str(e)}")

@app.get("/api/test/{user_test_id}/top-competencies")
async def get_top_competencies(user_test_id: int, user_data: dict = Depends(get_current_user)):
    """
    Get top competencies for self-assessment BEFORE test starts (V2)
    Uses weight instead of importance field
    """
    user_id = user_data["user_id"]

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Verify test belongs to user
                await cur.execute(
                    "SELECT user_id, specialization_id FROM user_test_time WHERE id = %s",
                    (user_test_id,)
                )
                test_data = await cur.fetchone()

                if not test_data:
                    raise HTTPException(status_code=404, detail="Test not found")
                if test_data[0] != user_id:
                    raise HTTPException(status_code=403, detail="Access denied")

                specialization_id = test_data[1]

                # Check if self-assessment already submitted
                await cur.execute("""
                    SELECT COUNT(*) FROM competency_self_assessments
                    WHERE test_session_id = %s
                """, (user_test_id,))
                already_submitted = (await cur.fetchone())[0] > 0

                # Get top competencies by weight (highest weight = most important)
                await cur.execute("""
                    SELECT c.id, c.name, c.weight
                    FROM competencies c
                    WHERE c.specialization_id = %s
                    ORDER BY c.weight DESC
                    LIMIT 10
                """, (specialization_id,))

                competencies = []
                for row in await cur.fetchall():
                    competencies.append({
                        "id": row[0],
                        "name": row[1],
                        "importance": int(row[2] * 100) if row[2] else 50  # Convert weight to importance scale (0-100)
                    })

                return {
                    "status": "success",
                    "competencies": competencies,
                    "already_submitted": already_submitted
                }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in top-competencies: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/test/{user_test_id}/self-assessment")
async def submit_self_assessment(
    user_test_id: int,
    data: SelfAssessmentSubmit,
    user_data: dict = Depends(get_current_user)
):
    """Submit self-assessment ratings for competencies (V2)"""
    user_id = user_data["user_id"]

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Verify test belongs to user
                await cur.execute(
                    "SELECT user_id FROM user_test_time WHERE id = %s",
                    (user_test_id,)
                )
                test_data = await cur.fetchone()

                if not test_data:
                    raise HTTPException(status_code=404, detail="Test not found")
                if test_data[0] != user_id:
                    raise HTTPException(status_code=403, detail="Access denied")

                # Insert self-assessments
                for assessment in data.assessments:
                    competency_id = assessment.get("competency_id")
                    self_rating = assessment.get("self_rating")

                    if not competency_id or not self_rating:
                        continue

                    if self_rating < 1 or self_rating > 10:
                        raise HTTPException(status_code=400, detail="Rating must be between 1 and 10")

                    await cur.execute("""
                        INSERT INTO competency_self_assessments
                        (test_session_id, user_id, competency_id, self_rating)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (test_session_id, competency_id)
                        DO UPDATE SET self_rating = EXCLUDED.self_rating
                    """, (user_test_id, user_id, competency_id, self_rating))

                return {"status": "success", "message": "Self-assessment submitted"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error submitting self-assessment: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/test/{test_session_id}/questions")
async def get_test_questions(test_session_id: int, user_data: dict = Depends(get_current_user)):
    """
    Get all questions for a test session (V2)
    Returns 60 questions in order

    Questions are ENCRYPTED - frontend will need to decrypt them

    Returns:
        {
            "status": "success",
            "test_session_id": 1,
            "questions": [
                {
                    "question_id": 123,
                    "question_order": 1,
                    "level": "junior",
                    "question_text": "encrypted_string",
                    "var_1": "encrypted_string",
                    "var_2": "encrypted_string",
                    "var_3": "encrypted_string",
                    "var_4": "encrypted_string",
                    "competency_name": "SQL Skills"
                },
                ...
            ],
            "total": 60
        }
    """

    user_id = user_data["user_id"]

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Verify test belongs to user
                await cur.execute(
                    "SELECT user_id FROM user_test_time WHERE id = %s",
                    (test_session_id,)
                )
                row = await cur.fetchone()

                if not row:
                    raise HTTPException(status_code=404, detail="Test session not found")

                if row[0] != user_id:
                    raise HTTPException(status_code=403, detail="Access denied")

                # Get questions with answer status
                await cur.execute("""
                    SELECT
                        uq.question_id,
                        uq.question_order,
                        q.level,
                        q.question_text,
                        q.var_1,
                        q.var_2,
                        q.var_3,
                        q.var_4,
                        c.name as competency_name,
                        t.name as topic_name,
                        ur.user_answer,
                        ur.is_correct
                    FROM user_questions uq
                    JOIN questions q ON q.id = uq.question_id
                    JOIN competencies c ON c.id = uq.competency_id
                    JOIN topics t ON t.id = uq.topic_id
                    LEFT JOIN user_results ur ON ur.question_id = uq.question_id AND ur.test_session_id = uq.test_session_id
                    WHERE uq.test_session_id = %s
                    ORDER BY uq.question_order
                """, (test_session_id,))

                rows = await cur.fetchall()

                questions = []
                for row in rows:
                    questions.append({
                        "question_id": row[0],
                        "question_order": row[1],
                        "level": row[2],
                        "question_text": row[3],  # Encrypted
                        "options": [row[4], row[5], row[6], row[7]],  # Frontend expects options array
                        "competency_name": row[8],
                        "topic_name": row[9],
                        "is_answered": row[10] is not None,
                        "user_answer": row[10],
                        "is_correct": row[11]
                    })

                # Calculate progress
                answered = sum(1 for q in questions if q["is_answered"])
                correct = sum(1 for q in questions if q["is_correct"])

                # Calculate progress by competency
                competency_stats = {}
                for q in questions:
                    comp_name = q["competency_name"]
                    if comp_name not in competency_stats:
                        competency_stats[comp_name] = {
                            "name": comp_name,
                            "total": 0,
                            "answered": 0,
                            "correct": 0
                        }
                    competency_stats[comp_name]["total"] += 1
                    if q["is_answered"]:
                        competency_stats[comp_name]["answered"] += 1
                    if q["is_correct"]:
                        competency_stats[comp_name]["correct"] += 1

                competencies_list = list(competency_stats.values())

                return {
                    "status": "success",
                    "test_session_id": test_session_id,
                    "questions": questions,
                    "total": len(questions),
                    "time_limit_minutes": 40,  # Default 40 minutes
                    "progress": {
                        "total": {
                            "answered": answered,
                            "total": len(questions),
                            "correct": correct,
                            "percentage": int((answered / len(questions)) * 100) if questions else 0
                        },
                        "competencies": competencies_list
                    }
                }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Get questions error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/submit-answer")
async def submit_answer(answer: AnswerSubmit, user_data: dict = Depends(get_current_user)):
    """
    Submit answer to a question (V2)

    Request:
        {
            "user_test_id": 1,
            "question_id": 123,
            "user_answer": 2
        }

    Returns:
        {
            "status": "success",
            "correct": true,
            "correct_answer": 2
        }
    """

    user_id = user_data["user_id"]

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Verify test belongs to user
                await cur.execute(
                    "SELECT user_id FROM user_test_time WHERE id = %s",
                    (answer.user_test_id,)
                )
                row = await cur.fetchone()

                if not row or row[0] != user_id:
                    raise HTTPException(status_code=403, detail="Access denied")

                # Get question details
                await cur.execute("""
                    SELECT q.correct_answer, uq.specialization_id, uq.competency_id, uq.topic_id, q.question_text
                    FROM user_questions uq
                    JOIN questions q ON q.id = uq.question_id
                    WHERE uq.test_session_id = %s AND uq.question_id = %s
                """, (answer.user_test_id, answer.question_id))

                question_row = await cur.fetchone()

                if not question_row:
                    raise HTTPException(status_code=404, detail="Question not found in this test")

                correct_answer, spec_id, comp_id, topic_id, question_text = question_row
                is_correct = 1 if answer.user_answer == correct_answer else 0

                # Insert result
                await cur.execute("""
                    INSERT INTO user_results
                    (user_id, test_session_id, specialization_id, competency_id, topic_id,
                     question_id, question_text, user_answer, correct, date_created)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, test_session_id, question_id) DO UPDATE
                    SET user_answer = %s, correct = %s
                """, (user_id, answer.user_test_id, spec_id, comp_id, topic_id,
                      answer.question_id, question_text, answer.user_answer, is_correct, datetime.now(),
                      answer.user_answer, is_correct))

                return {
                    "status": "success",
                    "correct": bool(is_correct),
                    "correct_answer": correct_answer
                }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Submit answer error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/complete-test/{test_session_id}")
async def complete_test(test_session_id: int, user_data: dict = Depends(get_current_user)):
    """
    Complete test and calculate score (V2)

    Returns:
        {
            "status": "success",
            "score": 45,
            "max_score": 60,
            "percentage": 75.0,
            "level": "middle",
            "recommendation": "..."
        }
    """

    user_id = user_data["user_id"]

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Verify ownership
                await cur.execute(
                    "SELECT user_id, completed FROM user_test_time WHERE id = %s",
                    (test_session_id,)
                )
                row = await cur.fetchone()

                if not row or row[0] != user_id:
                    raise HTTPException(status_code=403, detail="Access denied")

                if row[1]:  # already completed
                    raise HTTPException(status_code=400, detail="Test already completed")

                # Calculate score
                await cur.execute("""
                    SELECT COUNT(*) as total, SUM(correct) as correct_count
                    FROM user_results
                    WHERE test_session_id = %s
                """, (test_session_id,))

                result_row = await cur.fetchone()
                total_answered, correct_count = result_row

                if total_answered < config.TOTAL_QUESTIONS:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Not all questions answered ({total_answered}/{config.TOTAL_QUESTIONS})"
                    )

                # Determine level
                percentage = (correct_count / config.TOTAL_QUESTIONS) * 100

                if percentage >= 80:
                    level = "senior"
                elif percentage >= 50:
                    level = "middle"
                else:
                    level = "junior"

                # Update test session
                await cur.execute("""
                    UPDATE user_test_time
                    SET end_time = %s, score = %s, level = %s, completed = TRUE
                    WHERE id = %s
                """, (datetime.now(), correct_count, level, test_session_id))

                # Generate recommendation
                recommendation = f"Вы показали {level} уровень ({correct_count}/{config.TOTAL_QUESTIONS} правильных ответов, {percentage:.1f}%)."

                # Get competency statistics
                await cur.execute("""
                    SELECT
                        c.name as competency_name,
                        COUNT(*) as total,
                        SUM(CASE WHEN ur.correct = 1 THEN 1 ELSE 0 END) as correct
                    FROM user_results ur
                    JOIN questions q ON ur.question_id = q.id
                    JOIN competencies c ON q.competency_id = c.id
                    WHERE ur.test_session_id = %s
                    GROUP BY c.id, c.name
                    ORDER BY c.name
                """, (test_session_id,))

                competency_rows = await cur.fetchall()
                competency_stats = []
                for row in competency_rows:
                    competency_stats.append({
                        "name": row[0],
                        "total": row[1],
                        "correct": row[2]
                    })

                return {
                    "status": "success",
                    "score": correct_count,
                    "max_score": config.TOTAL_QUESTIONS,
                    "percentage": percentage,
                    "level": level,
                    "recommendation": recommendation,
                    "competencies": competency_stats
                }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Complete test error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================
# API - RESULTS
# =====================================================
@app.get("/api/results/{test_session_id}")
async def get_results(test_session_id: int, user_data: dict = Depends(get_current_user)):
    """Get test results (V2)"""

    user_id = user_data["user_id"]

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Get test info
                await cur.execute("""
                    SELECT
                        utt.score,
                        utt.max_score,
                        utt.level,
                        utt.end_time,
                        utt.created_date,
                        s.name as specialization_name,
                        u.name as user_name,
                        u.tab_number
                    FROM user_test_time utt
                    JOIN specializations s ON s.id = utt.specialization_id
                    JOIN users u ON u.id = utt.user_id
                    WHERE utt.id = %s
                """, (test_session_id,))

                test_row = await cur.fetchone()

                if not test_row:
                    raise HTTPException(status_code=404, detail="Test not found")

                score, max_score, level, end_time, created_date, spec_name, user_name, tab_number = test_row

                # Get competency breakdown
                await cur.execute("""
                    SELECT
                        c.name as competency_name,
                        COUNT(*) as total,
                        SUM(ur.correct) as correct
                    FROM user_results ur
                    JOIN competencies c ON c.id = ur.competency_id
                    WHERE ur.test_session_id = %s
                    GROUP BY c.name
                    ORDER BY c.name
                """, (test_session_id,))

                competency_rows = await cur.fetchall()

                competencies = []
                for row in competency_rows:
                    competencies.append({
                        "name": row[0],
                        "total": row[1],
                        "correct": row[2],
                        "percentage": (row[2] / row[1] * 100) if row[1] > 0 else 0
                    })

                return {
                    "status": "success",
                    "score": score,
                    "max_score": max_score,
                    "percentage": (score / max_score * 100) if max_score > 0 else 0,
                    "level": level,
                    "specialization": spec_name,
                    "user_name": user_name,
                    "tab_number": tab_number,
                    "completed_at": end_time.isoformat() if end_time else None,
                    "competencies": competencies
                }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Get results error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================
# API - AI PROCTORING
# =====================================================
@app.post("/api/proctoring/event")
async def log_proctoring_event(
    event: ProctoringEventSubmit,
    current_user: dict = Depends(get_current_user)
):
    """Log a proctoring event detected by AI"""
    user_id = current_user["user_id"]

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Verify test belongs to user
                await cur.execute(
                    "SELECT user_id FROM user_test_time WHERE id = %s",
                    (event.user_test_id,)
                )
                test_data = await cur.fetchone()

                if not test_data:
                    raise HTTPException(status_code=404, detail="Test not found")
                if test_data[0] != user_id:
                    raise HTTPException(status_code=403, detail="Access denied")

                # Insert proctoring event
                details_json = None
                if event.details is not None:
                    details_json = json.dumps(event.details)

                await cur.execute("""
                    INSERT INTO proctoring_events
                    (user_test_id, user_id, event_type, severity, details)
                    VALUES (%s, %s, %s, %s, %s::jsonb)
                    RETURNING id
                """, (
                    event.user_test_id,
                    user_id,
                    event.event_type,
                    event.severity,
                    details_json
                ))

                event_id = (await cur.fetchone())[0]

                # Update suspicious event count and calculate risk level based on severity
                # Get current count of high/critical severity events
                await cur.execute("""
                    SELECT
                        COUNT(*) as total_events,
                        COUNT(*) FILTER (WHERE severity IN ('high', 'critical')) as high_severity_count
                    FROM proctoring_events
                    WHERE user_test_id = %s
                """, (event.user_test_id,))

                counts = await cur.fetchone()
                total_events = counts[0] if counts else 0
                high_severity_count = counts[1] if counts else 0

                # Calculate risk level based on thresholds:
                # high/critical events >= 10 → 'high' (CRITICAL)
                # high/critical events >= 5 → 'high'
                # total events >= 15 → 'medium'
                # else → 'low'
                if high_severity_count >= 10:
                    risk_level = 'high'  # CRITICAL
                elif high_severity_count >= 5:
                    risk_level = 'high'
                elif total_events >= 15:
                    risk_level = 'medium'
                else:
                    risk_level = 'low'

                await cur.execute("""
                    UPDATE user_test_time
                    SET suspicious_events_count = %s,
                        proctoring_risk_level = %s
                    WHERE id = %s
                """, (total_events, risk_level, event.user_test_id))

                return {
                    "status": "success",
                    "event_id": event_id,
                    "message": "Proctoring event logged",
                    "risk_level": risk_level,
                    "total_events": total_events,
                    "high_severity_events": high_severity_count
                }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Proctoring event error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/proctoring/events/{user_test_id}")
async def get_proctoring_events(
    user_test_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Get all proctoring events for a test"""
    user_id = current_user["user_id"]

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Verify test belongs to user or user is HR/manager
                await cur.execute(
                    "SELECT user_id FROM user_test_time WHERE id = %s",
                    (user_test_id,)
                )
                test_data = await cur.fetchone()

                if not test_data:
                    raise HTTPException(status_code=404, detail="Test not found")

                # Allow test owner or HR/managers to view
                role = current_user.get("role", "employee")
                if test_data[0] != user_id and role not in ["hr", "manager"]:
                    raise HTTPException(status_code=403, detail="Access denied")

                # Get events
                await cur.execute("""
                    SELECT id, event_type, severity, details, created_at
                    FROM proctoring_events
                    WHERE user_test_id = %s
                    ORDER BY created_at DESC
                """, (user_test_id,))

                rows = await cur.fetchall()
                events = [
                    {
                        "id": row[0],
                        "event_type": row[1],
                        "severity": row[2],
                        "details": row[3],
                        "created_at": row[4].isoformat() if row[4] else None
                    }
                    for row in rows
                ]

                return {
                    "status": "success",
                    "events": events,
                    "count": len(events)
                }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Get proctoring events error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/proctoring/summary/{user_test_id}")
async def get_proctoring_summary(
    user_test_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Get proctoring summary statistics for a test"""
    user_id = current_user["user_id"]

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Verify test belongs to user or user is HR/manager
                await cur.execute(
                    "SELECT user_id, suspicious_events_count, proctoring_risk_level FROM user_test_time WHERE id = %s",
                    (user_test_id,)
                )
                test_data = await cur.fetchone()

                if not test_data:
                    raise HTTPException(status_code=404, detail="Test not found")

                # Allow test owner or HR/managers to view
                role = current_user.get("role", "employee")
                if test_data[0] != user_id and role not in ["hr", "manager"]:
                    raise HTTPException(status_code=403, detail="Access denied")

                # Get event breakdown
                await cur.execute("""
                    SELECT
                        event_type,
                        COUNT(*) as count,
                        severity
                    FROM proctoring_events
                    WHERE user_test_id = %s
                    GROUP BY event_type, severity
                    ORDER BY count DESC
                """, (user_test_id,))

                breakdown_rows = await cur.fetchall()
                breakdown = [
                    {
                        "event_type": row[0],
                        "count": row[1],
                        "severity": row[2]
                    }
                    for row in breakdown_rows
                ]

                return {
                    "status": "success",
                    "total_events": test_data[1] if test_data[1] else 0,
                    "risk_level": test_data[2] if test_data[2] else "low",
                    "breakdown": breakdown
                }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Get proctoring summary error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================
# HR PANEL (Simplified for V2)
# =====================================================
@app.get("/hr", response_class=HTMLResponse)
async def hr_login_page():
    """HR login page"""
    with open('templates/hr_login.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/hr/menu", response_class=HTMLResponse)
async def hr_menu_page():
    """HR menu page"""
    with open('templates/hr_menu.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/hr/results", response_class=HTMLResponse)
async def hr_results_page():
    """HR results page"""
    with open('templates/hr_results.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/hr/ratings", response_class=HTMLResponse)
async def hr_ratings_page():
    """HR ratings page"""
    with open('templates/hr_ratings.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/hr/monitoring", response_class=HTMLResponse)
async def hr_monitoring_page():
    """HR monitoring page"""
    with open('templates/hr_monitoring.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/hr/diagnostic", response_class=HTMLResponse)
async def hr_diagnostic_page():
    """HR diagnostic page"""
    with open('templates/hr_diagnostic.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/manager/menu", response_class=HTMLResponse)
async def manager_menu_page():
    """Manager menu page"""
    with open('templates/manager_menu.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/manager/results", response_class=HTMLResponse)
async def manager_results_page():
    """Manager results page"""
    with open('templates/manager_results.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/manager/ratings", response_class=HTMLResponse)
async def manager_ratings_page():
    """Manager ratings page"""
    with open('templates/manager_ratings.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.post("/api/hr/login")
async def hr_login(password: str, response: Response):
    """HR login (simple password-based)"""
    if password == config.HR_PASSWORD:
        token = create_access_token(
            user_id=0,  # Special HR user
            tab_number="HR_ADMIN",
            role="hr",
            department_id=None
        )
        response.set_cookie(
            key="hr_token",
            value=token,
            httponly=True,
            max_age=86400,  # 24 hours
            samesite="lax"
        )
        return {"status": "success", "message": "Logged in"}
    else:
        raise HTTPException(status_code=401, detail="Incorrect password")

@app.get("/api/hr/results")
async def hr_get_all_results(hr_user: dict = Depends(verify_hr_cookie)):
    """HR: Get all test results"""
    if not hr_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT
                        utt.id,
                        u.name,
                        u.tab_number,
                        u.company,
                        u.role,
                        d.name as department,
                        s.name as specialization,
                        utt.score,
                        utt.max_score,
                        utt.level,
                        utt.start_time,
                        utt.end_time
                    FROM user_test_time utt
                    JOIN users u ON u.id = utt.user_id
                    JOIN specializations s ON s.id = utt.specialization_id
                    LEFT JOIN departments d ON d.id = u.department_id
                    WHERE utt.completed = TRUE
                    ORDER BY utt.end_time DESC
                    LIMIT 100
                """)

                rows = await cur.fetchall()

                results = []
                for row in rows:
                    score = row[7] or 0
                    max_score = row[8] or 1
                    percentage = round((score / max_score) * 100, 1) if max_score > 0 else 0

                    # Calculate duration in minutes
                    duration = 0
                    if row[10] and row[11]:
                        delta = row[11] - row[10]
                        duration = round(delta.total_seconds() / 60, 1)

                    results.append({
                        "test_id": row[0],
                        "name": row[1],
                        "tab_number": row[2],
                        "company": row[3] or "-",
                        "role": row[4] or "-",
                        "department": row[5] or "-",
                        "specialization": row[6],
                        "score": score,
                        "max_score": max_score,
                        "percentage": percentage,
                        "level": row[9].capitalize() if row[9] else "Junior",
                        "completed_at": row[11].isoformat() if row[11] else None,
                        "duration_minutes": duration
                    })

                return {"status": "success", "results": results}

    except Exception as e:
        print(f"HR results error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/hr/results/stats")
async def hr_get_results_stats(hr_user: dict = Depends(verify_hr_cookie)):
    """HR: Get statistical analysis of all results"""
    if not hr_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Overall stats
                await cur.execute("""
                    SELECT
                        COUNT(*) as total_tests,
                        AVG(CASE WHEN max_score > 0 THEN (score::numeric / max_score::numeric * 100) ELSE 0 END) as avg_percentage,
                        AVG(EXTRACT(EPOCH FROM (end_time - start_time)) / 60) as avg_duration_minutes
                    FROM user_test_time
                    WHERE completed = TRUE
                """)
                overall = await cur.fetchone()

                # By specialization
                await cur.execute("""
                    SELECT
                        s.name,
                        COUNT(*) as count,
                        AVG(CASE WHEN utt.max_score > 0 THEN (utt.score::numeric / utt.max_score::numeric * 100) ELSE 0 END) as avg_percentage
                    FROM user_test_time utt
                    JOIN specializations s ON utt.specialization_id = s.id
                    WHERE utt.completed = TRUE
                    GROUP BY s.name
                    ORDER BY count DESC
                """)
                by_spec = await cur.fetchall()

                # By level
                await cur.execute("""
                    SELECT
                        UPPER(level) as level_name,
                        COUNT(*) as count
                    FROM user_test_time
                    WHERE completed = TRUE AND level IS NOT NULL
                    GROUP BY level
                """)
                by_level_rows = await cur.fetchall()

                by_level = {"Senior": 0, "Middle": 0, "Junior": 0}
                for row in by_level_rows:
                    level_key = row[0].capitalize()
                    if level_key in by_level:
                        by_level[level_key] = row[1]

                return {
                    "status": "success",
                    "overall": {
                        "total_tests": overall[0] or 0,
                        "avg_percentage": round(overall[1], 1) if overall[1] else 0,
                        "avg_duration_minutes": round(overall[2], 1) if overall[2] else 0
                    },
                    "by_specialization": [
                        {"name": row[0], "count": row[1], "avg_percentage": round(row[2], 1) if row[2] else 0}
                        for row in by_spec
                    ],
                    "by_level": by_level
                }
    except Exception as e:
        print(f"HR stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/hr/results/{test_id}")
async def hr_get_result_detail(test_id: int, hr_user: dict = Depends(verify_hr_cookie)):
    """HR: Get detailed information about a specific test"""
    if not hr_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Get test info
                await cur.execute("""
                    SELECT
                        utt.id,
                        u.name,
                        u.tab_number,
                        u.company,
                        u.role,
                        d.name as department,
                        s.name as specialization,
                        utt.score,
                        utt.max_score,
                        utt.level,
                        utt.start_time,
                        utt.end_time
                    FROM user_test_time utt
                    JOIN users u ON u.id = utt.user_id
                    JOIN specializations s ON s.id = utt.specialization_id
                    LEFT JOIN departments d ON d.id = u.department_id
                    WHERE utt.id = %s
                """, (test_id,))
                test_info = await cur.fetchone()

                if not test_info:
                    raise HTTPException(status_code=404, detail="Test not found")

                # Get answers by competency
                await cur.execute("""
                    SELECT
                        c.name as competency,
                        q.question_text,
                        q.difficulty,
                        q.option_a, q.option_b, q.option_c, q.option_d,
                        q.correct_answer,
                        ur.selected_answer,
                        ur.correct
                    FROM user_results ur
                    JOIN questions q ON ur.question_id = q.id
                    JOIN competencies c ON q.competency_id = c.id
                    WHERE ur.test_session_id = %s
                    ORDER BY c.name, q.difficulty
                """, (test_id,))
                answers = await cur.fetchall()

                return {
                    "status": "success",
                    "test_info": {
                        "id": test_info[0],
                        "name": test_info[1],
                        "tab_number": test_info[2],
                        "company": test_info[3] or "-",
                        "role": test_info[4] or "-",
                        "department": test_info[5] or "-",
                        "specialization": test_info[6],
                        "score": test_info[7],
                        "max_score": test_info[8],
                        "level": test_info[9],
                        "started_at": test_info[10].isoformat() if test_info[10] else None,
                        "completed_at": test_info[11].isoformat() if test_info[11] else None
                    },
                    "answers": [
                        {
                            "competency": ans[0],
                            "question": ans[1],
                            "level": ans[2],
                            "options": [ans[3], ans[4], ans[5], ans[6]],
                            "correct_answer": ans[7],
                            "user_answer": ans[8],
                            "is_correct": bool(ans[9])
                        } for ans in answers
                    ]
                }
    except HTTPException:
        raise
    except Exception as e:
        print(f"HR result detail error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================
# MANAGER PANEL APIs
# =====================================================
async def get_current_manager(authorization: Optional[str] = Header(None)):
    """Extract manager info from token"""
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    token = authorization.split(' ')[1]
    user_data = verify_token(token)
    if not user_data or user_data.get("role") != "manager":
        raise HTTPException(status_code=403, detail="Доступ только для руководителей")
    if not user_data.get("department_id"):
        raise HTTPException(status_code=400, detail="У руководителя не указан отдел")
    return user_data

@app.get("/api/manager/results")
async def get_manager_results(manager: dict = Depends(get_current_manager)):
    """Get test results for manager's department only"""
    department_id = manager.get("department_id")

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT
                        utt.id,
                        u.name,
                        u.tab_number,
                        s.name as specialization,
                        utt.score,
                        utt.max_score,
                        utt.level,
                        utt.start_time,
                        utt.end_time
                    FROM user_test_time utt
                    JOIN users u ON u.id = utt.user_id
                    JOIN specializations s ON s.id = utt.specialization_id
                    WHERE utt.completed = TRUE AND u.department_id = %s
                    ORDER BY utt.end_time DESC
                    LIMIT 100
                """, (department_id,))

                rows = await cur.fetchall()

                results = []
                for row in rows:
                    score = row[4] or 0
                    max_score = row[5] or 1
                    percentage = round((score / max_score) * 100, 1) if max_score > 0 else 0

                    duration = 0
                    if row[7] and row[8]:
                        delta = row[8] - row[7]
                        duration = round(delta.total_seconds() / 60, 1)

                    results.append({
                        "test_id": row[0],
                        "name": row[1],
                        "tab_number": row[2],
                        "specialization": row[3],
                        "score": score,
                        "max_score": max_score,
                        "percentage": percentage,
                        "level": row[6].capitalize() if row[6] else "Junior",
                        "completed_at": row[8].isoformat() if row[8] else None,
                        "duration_minutes": duration
                    })

                return {"status": "success", "results": results}

    except Exception as e:
        print(f"Manager results error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/manager/results/stats")
async def get_manager_results_stats(manager: dict = Depends(get_current_manager)):
    """Get statistical analysis for manager's department"""
    department_id = manager.get("department_id")

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Overall stats for department
                await cur.execute("""
                    SELECT
                        COUNT(*) as total_tests,
                        AVG(CASE WHEN utt.max_score > 0 THEN (utt.score::numeric / utt.max_score::numeric * 100) ELSE 0 END) as avg_percentage,
                        AVG(EXTRACT(EPOCH FROM (utt.end_time - utt.start_time)) / 60) as avg_duration_minutes
                    FROM user_test_time utt
                    JOIN users u ON utt.user_id = u.id
                    WHERE utt.completed = TRUE AND u.department_id = %s
                """, (department_id,))
                overall = await cur.fetchone()

                # By level
                await cur.execute("""
                    SELECT
                        UPPER(utt.level) as level_name,
                        COUNT(*) as count
                    FROM user_test_time utt
                    JOIN users u ON utt.user_id = u.id
                    WHERE utt.completed = TRUE AND u.department_id = %s AND utt.level IS NOT NULL
                    GROUP BY utt.level
                """, (department_id,))
                by_level_rows = await cur.fetchall()

                by_level = {"Senior": 0, "Middle": 0, "Junior": 0}
                for row in by_level_rows:
                    level_key = row[0].capitalize()
                    if level_key in by_level:
                        by_level[level_key] = row[1]

                return {
                    "status": "success",
                    "overall": {
                        "total_tests": overall[0] or 0,
                        "avg_percentage": round(overall[1], 1) if overall[1] else 0,
                        "avg_duration_minutes": round(overall[2], 1) if overall[2] else 0
                    },
                    "by_level": by_level
                }
    except Exception as e:
        print(f"Manager stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================
# END OF MAIN_V2.PY
# =====================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.APP_HOST, port=config.APP_PORT)
