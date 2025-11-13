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

class AnswerSubmit(BaseModel):
    test_session_id: int
    question_id: int
    user_answer: int  # 1-4

class SelfAssessmentSubmit(BaseModel):
    test_session_id: int
    assessments: List[Dict[str, Any]]  # [{"competency_id": 1, "self_rating": 8}, ...]

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
            "test_session_id": test_session_id,
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

                # Get questions
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
                        t.name as topic_name
                    FROM user_questions uq
                    JOIN questions q ON q.id = uq.question_id
                    JOIN competencies c ON c.id = uq.competency_id
                    JOIN topics t ON t.id = uq.topic_id
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
                        "var_1": row[4],  # Encrypted
                        "var_2": row[5],  # Encrypted
                        "var_3": row[6],  # Encrypted
                        "var_4": row[7],  # Encrypted
                        "competency_name": row[8],
                        "topic_name": row[9]
                    })

                return {
                    "status": "success",
                    "test_session_id": test_session_id,
                    "questions": questions,
                    "total": len(questions),
                    "note": "Questions are encrypted - decrypt on frontend"
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
            "test_session_id": 1,
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
                    (answer.test_session_id,)
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
                """, (answer.test_session_id, answer.question_id))

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
                """, (user_id, answer.test_session_id, spec_id, comp_id, topic_id,
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

                return {
                    "status": "success",
                    "score": correct_count,
                    "max_score": config.TOTAL_QUESTIONS,
                    "percentage": percentage,
                    "level": level,
                    "recommendation": recommendation
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

@app.get("/manager/menu", response_class=HTMLResponse)
async def manager_menu_page():
    """Manager menu page"""
    with open('templates/manager_menu.html', 'r', encoding='utf-8') as f:
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
                        s.name as specialization,
                        utt.score,
                        utt.max_score,
                        utt.level,
                        utt.end_time
                    FROM user_test_time utt
                    JOIN users u ON u.id = utt.user_id
                    JOIN specializations s ON s.id = utt.specialization_id
                    WHERE utt.completed = TRUE
                    ORDER BY utt.end_time DESC
                    LIMIT 100
                """)

                rows = await cur.fetchall()

                results = []
                for row in rows:
                    results.append({
                        "test_session_id": row[0],
                        "user_name": row[1],
                        "tab_number": row[2],
                        "specialization": row[3],
                        "score": row[4],
                        "max_score": row[5],
                        "level": row[6],
                        "completed_at": row[7].isoformat() if row[7] else None
                    })

                return {"status": "success", "results": results}

    except Exception as e:
        print(f"HR results error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================
# END OF MAIN_V2.PY
# =====================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.APP_HOST, port=config.APP_PORT)
