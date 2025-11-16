from fastapi import FastAPI, Request, HTTPException, Header, Depends, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from contextlib import asynccontextmanager
from typing import Optional
import sys
import os
import json

# Мониторинг
import psutil
import time
import statistics
from datetime import datetime, timedelta
from collections import deque

# Fix для Windows asyncio
if sys.platform == 'win32':
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from db.database import init_db_pool, close_db_pool, get_db_connection
from db.utils import generate_test_topics, get_test_progress
import config

import anthropic
import httpx

print(f"RECAPTCHA_SECRET_KEY: {config.RECAPTCHA_SECRET_KEY}")

# Инициализируем Claude client
http_client = httpx.Client(timeout=30.0)
claude_client = anthropic.Anthropic(
    api_key=config.ANTHROPIC_API_KEY,
    http_client=http_client
)

from auth import create_access_token, verify_token


# =====================================================
# ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ДЛЯ МОНИТОРИНГА
# =====================================================
monitoring_data = {
    "requests": deque(maxlen=10000),
    "active_users": {},
    "start_time": time.time()
}

# =====================================================
# PYDANTIC MODELS
# =====================================================
class UserRegister(BaseModel):
    name: str
    surname: str
    phone: Optional[str] = None
    company: Optional[str] = None
    job_title: Optional[str] = None

class SpecializationSelect(BaseModel):
    specialization_id: int

class TestStart(BaseModel):
    specialization_id: int

class AnswerSubmit(BaseModel):
    user_test_id: int
    question_id: int
    user_answer: int

class SelfAssessmentSubmit(BaseModel):
    assessments: list[dict]  # [{"competency_id": 1, "self_rating": 8}, ...]

class LoginRequest(BaseModel):
    phone: str

class SQLQuery(BaseModel):
    query: str

# =====================================================
# LIFECYCLE
# =====================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting application...")
    await init_db_pool()
    print("✅ Database pool ready")
    yield
    print("🔄 Shutting down...")
    await close_db_pool()

# =====================================================
# FASTAPI APP
# =====================================================
app = FastAPI(
    title="Halyk HR Forum",
    description="Система тестирования компетенций",
    lifespan=lifespan
)

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# =====================================================
# MIDDLEWARE - МОНИТОРИНГ
# =====================================================
@app.middleware("http")
async def monitor_requests(request: Request, call_next):
    start_time = time.time()
    
    # Извлекаем user_id из токена
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
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.replace("Bearer ", "")
    user_data = verify_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user_data

# =====================================================
# AI РЕКОМЕНДАЦИИ
# =====================================================
async def generate_ai_recommendation(user_test_id: int):
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT ut.score, ut.max_score, s.name, u.name, u.surname
                    FROM user_specialization_tests ut
                    JOIN specializations s ON s.id = ut.specialization_id
                    JOIN users u ON u.id = ut.user_id
                    WHERE ut.id = %s
                """, (user_test_id,))
                
                test_data = await cur.fetchone()
                if not test_data:
                    return None
                
                score, max_score, specialization, name, surname = test_data
                percentage = (score / max_score) * 100
                
                if percentage >= 80:
                    level = "Senior"
                elif percentage >= 50:
                    level = "Middle"
                else:
                    level = "Junior"
                
                recommendation = f"Рекомендация: {name}, вы показали {level} уровень в области \"{specialization}\" ({score}/{max_score} баллов). Продолжайте развиваться в выбранном направлении и обращайте внимание на практические навыки."
                
                await cur.execute(
                    "INSERT INTO ai_recommendations (user_test_id, recommendation_text) VALUES (%s, %s)",
                    (user_test_id, recommendation)
                )
                
                return recommendation
    except Exception as e:
        print(f"Ошибка генерации рекомендации: {e}")
        return "Рекомендация будет доступна позже."

# =====================================================
# API - PUBLIC CONFIG
# =====================================================
@app.get("/api/config")
async def get_public_config():
    """Return public configuration like reCAPTCHA site key"""
    return {
        "recaptcha_site_key": config.RECAPTCHA_SITE_KEY,
        "org_name": config.ORG_NAME,
        "org_logo": config.ORG_LOGO
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

@app.get("/api/debug/me")
async def debug_current_user(authorization: Optional[str] = Header(None)):
    """Debug endpoint to check current user's token data"""
    if not authorization or not authorization.startswith('Bearer '):
        return {
            "status": "error",
            "message": "No authorization header found",
            "help": "Include 'Authorization: Bearer <token>' header"
        }

    token = authorization.split(' ')[1]
    user_data = verify_token(token)

    if not user_data:
        return {
            "status": "error",
            "message": "Invalid or expired token"
        }

    # Get full user info from database
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT u.id, u.name, u.surname, u.phone, u.company, u.job_title,
                           u.role, u.department_id, d.name as department_name
                    FROM users u
                    LEFT JOIN departments d ON u.department_id = d.id
                    WHERE u.id = %s
                """, (user_data.get("user_id"),))
                user_row = await cur.fetchone()

                if not user_row:
                    return {
                        "status": "error",
                        "message": "User not found in database"
                    }

                return {
                    "status": "success",
                    "token_data": user_data,
                    "database_data": {
                        "id": user_row[0],
                        "name": user_row[1],
                        "surname": user_row[2],
                        "phone": user_row[3],
                        "company": user_row[4],
                        "job_title": user_row[5],
                        "role": user_row[6],
                        "department_id": user_row[7],
                        "department_name": user_row[8]
                    },
                    "permissions": {
                        "can_access_test_panel": True,
                        "can_access_hr_panel": user_row[6] == "hr",
                        "can_access_manager_panel": user_row[6] == "manager"
                    }
                }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Database error: {str(e)}"
        }

@app.get("/api/admin/users")
async def get_all_users(
    role: Optional[str] = None,
    department_id: Optional[int] = None
):
    """Admin endpoint to get all users (use with caution in production)"""
    try:
        query = """
            SELECT u.id, u.name, u.surname, u.phone, u.company, u.job_title,
                   u.role, u.department_id, d.name as department_name, u.registered_at,
                   COUNT(DISTINCT ust.id) as completed_tests
            FROM users u
            LEFT JOIN departments d ON u.department_id = d.id
            LEFT JOIN user_specialization_tests ust ON u.id = ust.user_id AND ust.completed_at IS NOT NULL
        """

        params = []
        conditions = []
        param_count = 1

        if role:
            conditions.append(f"u.role = ${param_count}")
            params.append(role)
            param_count += 1

        if department_id:
            conditions.append(f"u.department_id = ${param_count}")
            params.append(department_id)
            param_count += 1

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += """
            GROUP BY u.id, u.name, u.surname, u.phone, u.company, u.job_title,
                     u.role, u.department_id, d.name, u.registered_at
            ORDER BY u.registered_at DESC
        """

        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, tuple(params))
                rows = await cur.fetchall()

                users = []
                for row in rows:
                    users.append({
                        "id": row[0],
                        "name": row[1],
                        "surname": row[2],
                        "phone": row[3],
                        "company": row[4],
                        "job_title": row[5],
                        "role": row[6],
                        "department_id": row[7],
                        "department_name": row[8],
                        "registered_at": row[9].isoformat() if row[9] else None,
                        "completed_tests": row[10]
                    })

                # Get statistics
                await cur.execute("""
                    SELECT
                        COUNT(*) as total,
                        COUNT(CASE WHEN role = 'employee' THEN 1 END) as employees,
                        COUNT(CASE WHEN role = 'hr' THEN 1 END) as hr,
                        COUNT(CASE WHEN role = 'manager' THEN 1 END) as managers
                    FROM users
                """)
                stats = await cur.fetchone()

                return {
                    "status": "success",
                    "users": users,
                    "stats": {
                        "total": stats[0],
                        "employees": stats[1],
                        "hr": stats[2],
                        "managers": stats[3]
                    }
                }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================
# HTML ROUTES - PUBLIC
# =====================================================
@app.get("/", response_class=HTMLResponse)
async def home():
    with open('templates/index.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/panels", response_class=HTMLResponse)
async def panels_page():
    """Panel selection page after login/registration"""
    with open('templates/panels.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/specializations", response_class=HTMLResponse)
async def specializations_page():
    with open('templates/specializations.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/test", response_class=HTMLResponse)
async def test_page():
    with open('templates/test.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/results", response_class=HTMLResponse)
async def results_page():
    with open('templates/results.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/health")
async def health():
    return {"status": "ok", "service": "halyk-hr-forum"}

# =====================================================
# HTML ROUTES - HR PANEL
# =====================================================
# ===== ДОБАВЬ/ЗАМЕНИ ЭТИ ЧАСТИ В main.py =====

from fastapi import Cookie
from fastapi.responses import RedirectResponse

# =====================================================
# DEPENDENCY - HR AUTH (НОВОЕ!)
# =====================================================
async def verify_hr_cookie(hr_token: Optional[str] = Cookie(None)):
    """Проверяет HR токен из cookie"""
    if not hr_token:
        return None
    
    # Проверяем токен
    user_data = verify_token(hr_token)
    if user_data and user_data.get("phone") == "hr_admin":
        return user_data
    return None

# =====================================================
# HTML ROUTES - HR PANEL (ОБНОВЛЕННЫЕ!)
# =====================================================
@app.get("/hr", response_class=HTMLResponse)
async def hr_login_page():
    """Страница логина HR"""
    with open('templates/hr_login.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/hr/menu", response_class=HTMLResponse)
async def hr_menu_page(hr_user: dict = Depends(verify_hr_cookie)):
    """HR меню - защищено"""
    if not hr_user:
        return RedirectResponse(url="/hr", status_code=303)

    with open('templates/hr_menu.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/hr/dashboard", response_class=HTMLResponse)
async def hr_dashboard_page(hr_user: dict = Depends(verify_hr_cookie)):
    """HR дашборд - защищено"""
    if not hr_user:
        return RedirectResponse(url="/hr", status_code=303)

    with open('templates/dashboard.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/hr/database", response_class=HTMLResponse)
async def hr_database_page(hr_user: dict = Depends(verify_hr_cookie)):
    """HR база данных - защищено"""
    if not hr_user:
        return RedirectResponse(url="/hr", status_code=303)

    with open('templates/hr_panel.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/hr/monitoring", response_class=HTMLResponse)
async def hr_monitoring_page(hr_user: dict = Depends(verify_hr_cookie)):
    """HR мониторинг - защищено"""
    if not hr_user:
        return RedirectResponse(url="/hr", status_code=303)

    with open('templates/hr_monitoring.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/hr/results", response_class=HTMLResponse)
async def hr_results_page(hr_user: dict = Depends(verify_hr_cookie)):
    """HR результаты тестов - защищено"""
    if not hr_user:
        return RedirectResponse(url="/hr", status_code=303)

    with open('templates/hr_results.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/hr/ratings", response_class=HTMLResponse)
async def hr_ratings_page(hr_user: dict = Depends(verify_hr_cookie)):
    """HR ratings page - protected"""
    if not hr_user:
        return RedirectResponse(url="/hr", status_code=303)

    with open('templates/hr_ratings.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

@app.get("/hr/diagnostic", response_class=HTMLResponse)
async def hr_diagnostic_page():
    """HR diagnostic tool"""
    with open('templates/hr_diagnostic.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

# =====================================================
# HTML ROUTES - MANAGER PANEL
# =====================================================
async def verify_manager_token(authorization: Optional[str] = Header(None)):
    """Verify manager has valid token"""
    if not authorization or not authorization.startswith('Bearer '):
        return None
    token = authorization.split(' ')[1]
    user_data = verify_token(token)
    if user_data and user_data.get("role") == "manager":
        return user_data
    return None

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
    """Manager employee ratings page"""
    with open('templates/manager_ratings.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

# =====================================================
# HTML ROUTES - ADMIN TOOLS
# =====================================================
@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    """Admin tool for viewing all users"""
    with open('templates/admin.html', 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())

# =====================================================
# API - АУТЕНТИФИКАЦИЯ ПОЛЬЗОВАТЕЛЕЙ
# =====================================================
@app.post("/api/login")
async def login(request: LoginRequest):
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT id, name, surname, role, department_id FROM users WHERE phone = %s",
                    (request.phone,)
                )
                user = await cur.fetchone()

                if user:
                    token = create_access_token(
                        user_id=user[0],
                        phone=request.phone,
                        role=user[3] or "employee",
                        department_id=user[4]
                    )
                    return {
                        "status": "found",
                        "user_id": user[0],
                        "name": user[1],
                        "surname": user[2],
                        "role": user[3] or "employee",
                        "department_id": user[4],
                        "token": token
                    }
                else:
                    return {"status": "not_found"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class UserRegister(BaseModel):
    name: str
    surname: str
    phone: Optional[str] = None
    company: Optional[str] = None
    job_title: Optional[str] = None
    role: str = "employee"  # employee, hr, manager
    department_id: Optional[int] = None
    recaptcha_token: str

@app.post("/api/register")
async def register_user(request: Request, user: UserRegister):
    # Проверка капчи
    async with httpx.AsyncClient() as client:
        recaptcha_response = await client.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data={
                "secret": config.RECAPTCHA_SECRET_KEY,
                "response": user.recaptcha_token,
                "remoteip": request.client.host
            }
        )

        recaptcha_result = recaptcha_response.json()

        if not recaptcha_result.get("success"):
            raise HTTPException(status_code=400, detail="Капча не пройдена")

    # Validate role
    if user.role not in ['employee', 'hr', 'manager']:
        raise HTTPException(status_code=400, detail="Неверная роль")

    # Обычная регистрация
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT id FROM users WHERE phone = %s", (user.phone,))
                if await cur.fetchone():
                    raise HTTPException(status_code=400, detail="Телефон уже зарегистрирован")

                await cur.execute(
                    """INSERT INTO users (name, surname, phone, company, job_title, role, department_id)
                       VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                    (user.name, user.surname, user.phone, user.company, user.job_title, user.role, user.department_id)
                )
                user_id = (await cur.fetchone())[0]

        token = create_access_token(
            user_id=user_id,
            phone=user.phone,
            role=user.role,
            department_id=user.department_id
        )
        return {"status": "success", "user_id": user_id, "token": token, "role": user.role}

    except HTTPException:
        raise
    except Exception as e:
        print(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail="Ошибка регистрации")

# =====================================================
# API - PROFILES & SPECIALIZATIONS
# =====================================================
@app.get("/api/profiles")
async def get_profiles():
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT id, name, has_specializations FROM profiles ORDER BY id")
                rows = await cur.fetchall()
        
        profiles = [{"id": row[0], "name": row[1], "has_specializations": row[2]} for row in rows]
        return {"status": "success", "profiles": profiles}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/profiles/{profile_id}/specializations")
async def get_specializations(profile_id: int):
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
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================
# API - ТЕСТИРОВАНИЕ (ЗАЩИЩЕННЫЕ)
# =====================================================
@app.post("/api/select-specialization")
async def select_specialization(data: SpecializationSelect, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO user_specialization_selections (user_id, specialization_id) VALUES (%s, %s) ON CONFLICT DO NOTHING RETURNING id",
                    (user_id, data.specialization_id)
                )
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/my-specializations")
async def get_my_specializations(current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT s.id, s.name, p.name, ut.id, ut.score, ut.max_score, ut.completed_at, ut.started_at
                    FROM user_specialization_selections uss
                    JOIN specializations s ON s.id = uss.specialization_id
                    JOIN profiles p ON p.id = s.profile_id
                    LEFT JOIN user_specialization_tests ut ON ut.specialization_id = s.id AND ut.user_id = %s
                    WHERE uss.user_id = %s
                    ORDER BY uss.selected_at DESC
                """, (user_id, user_id))
                rows = await cur.fetchall()
        
        specializations = []
        for row in rows:
            status = "not_started"
            if row[7]:
                status = "completed" if row[6] else "in_progress"
            
            specializations.append({
                "id": row[0], "name": row[1], "profile_name": row[2],
                "user_test_id": row[3], "score": row[4], "max_score": row[5], "status": status
            })
        
        return {"status": "success", "specializations": specializations}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/start-test")
async def start_test(data: TestStart, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT id FROM user_specialization_tests WHERE user_id = %s AND specialization_id = %s",
                    (user_id, data.specialization_id)
                )
                existing = await cur.fetchone()
                
                if existing:
                    user_test_id = existing[0]
                else:
                    await cur.execute(
                        "INSERT INTO user_specialization_tests (user_id, specialization_id, max_score) VALUES (%s, %s, 24) RETURNING id",
                        (user_id, data.specialization_id)
                    )
                    user_test_id = (await cur.fetchone())[0]
                    await generate_test_topics(user_test_id, data.specialization_id)
        
        return {"status": "success", "user_test_id": user_test_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/test/{user_test_id}/questions")
async def get_test_questions(user_test_id: int, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT user_id FROM user_specialization_tests WHERE id = %s", (user_test_id,))
                test_data = await cur.fetchone()
                
                if not test_data or test_data[0] != user_id:
                    raise HTTPException(status_code=403, detail="Access denied")
                
                await cur.execute("""
                    SELECT c.id, c.name, q.id, q.level, q.question_text, q.var_1, q.var_2, q.var_3, q.var_4,
                           t.name, utt.topic_order, ta.user_answer, ta.is_correct
                    FROM user_test_topics utt
                    JOIN topics t ON t.id = utt.topic_id
                    JOIN competencies c ON c.id = utt.competency_id
                    JOIN questions q ON q.topic_id = t.id
                    LEFT JOIN test_answers ta ON ta.question_id = q.id AND ta.user_test_id = utt.user_test_id
                    WHERE utt.user_test_id = %s
                    ORDER BY utt.topic_order, CASE q.level WHEN 'Junior' THEN 1 WHEN 'Middle' THEN 2 WHEN 'Senior' THEN 3 END
                """, (user_test_id,))
                rows = await cur.fetchall()
        
        competencies_dict = {}
        all_questions = []
        
        for row in rows:
            comp_id = row[0]
            if comp_id not in competencies_dict:
                competencies_dict[comp_id] = {"id": comp_id, "name": row[1], "questions": []}
            
            question = {
                "question_id": row[2], "level": row[3], "question_text": row[4],
                "options": [row[5], row[6], row[7], row[8]], "topic_name": row[9],
                "is_answered": row[11] is not None, "user_answer": row[11], "is_correct": row[12]
            }
            
            competencies_dict[comp_id]["questions"].append(question)
            all_questions.append(question)
        
        progress = await get_test_progress(user_test_id)
        
        return {
            "status": "success",
            "questions": all_questions,
            "competencies": list(competencies_dict.values()),
            "progress": progress,
            "time_limit_minutes": config.TEST_TIME_LIMIT_MINUTES
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/submit-answer")
async def submit_answer(data: AnswerSubmit, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT user_id, current_question_number FROM user_specialization_tests WHERE id = %s",
                    (data.user_test_id,)
                )
                test_user = await cur.fetchone()
                
                if not test_user or test_user[0] != user_id:
                    raise HTTPException(status_code=403, detail="Access denied")
                
                await cur.execute("SELECT correct_answer FROM questions WHERE id = %s", (data.question_id,))
                correct_answer = (await cur.fetchone())[0]
                is_correct = (data.user_answer == correct_answer)
                
                await cur.execute(
                    "INSERT INTO test_answers (user_test_id, question_id, user_answer, is_correct) VALUES (%s, %s, %s, %s) ON CONFLICT (user_test_id, question_id) DO NOTHING",
                    (data.user_test_id, data.question_id, data.user_answer, is_correct)
                )
                
                await cur.execute(
                    "UPDATE user_specialization_tests SET current_question_number = %s WHERE id = %s",
                    (test_user[1] + 1, data.user_test_id)
                )
        
        return {"status": "success", "is_correct": is_correct}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/complete-test/{user_test_id}")
async def complete_test(user_test_id: int, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT user_id, completed_at, score FROM user_specialization_tests WHERE id = %s",
                    (user_test_id,)
                )
                test_data = await cur.fetchone()
                
                if not test_data:
                    raise HTTPException(status_code=404, detail="Test not found")
                if test_data[0] != user_id:
                    raise HTTPException(status_code=403, detail="Access denied")
                
                if test_data[1] is not None:
                    await cur.execute(
                        "SELECT recommendation_text FROM ai_recommendations WHERE user_test_id = %s",
                        (user_test_id,)
                    )
                    rec_row = await cur.fetchone()
                    recommendation = rec_row[0] if rec_row else None
                    
                    score = test_data[2]
                    percentage = (score / 24) * 100
                    level = "Senior" if percentage >= 80 else "Middle" if percentage >= 50 else "Junior"
                    
                    return {
                        "status": "already_completed",
                        "score": score, "max_score": 24, "level": level,
                        "recommendation": recommendation
                    }
                
                await cur.execute(
                    "SELECT COUNT(*) FROM test_answers WHERE user_test_id = %s AND is_correct = true",
                    (user_test_id,)
                )
                score = (await cur.fetchone())[0]
                
                await cur.execute(
                    "UPDATE user_specialization_tests SET score = %s, completed_at = NOW() WHERE id = %s",
                    (score, user_test_id)
                )
        
        recommendation = await generate_ai_recommendation(user_test_id)
        percentage = (score / 24) * 100
        level = "Senior" if percentage >= 80 else "Middle" if percentage >= 50 else "Junior"
        
        return {
            "status": "success",
            "score": score, "max_score": 24, "level": level,
            "recommendation": recommendation
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/test/{user_test_id}/top-competencies")
async def get_top_competencies(user_test_id: int, current_user: dict = Depends(get_current_user)):
    """Get top CORE competencies for self-assessment BEFORE test starts"""
    user_id = current_user["user_id"]
    print(f"🔍 Loading competencies for test {user_test_id}, user {user_id}")
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Verify test belongs to user
                await cur.execute(
                    "SELECT user_id, specialization_id FROM user_specialization_tests WHERE id = %s",
                    (user_test_id,)
                )
                test_data = await cur.fetchone()
                print(f"  Test data: {test_data}")

                if not test_data:
                    raise HTTPException(status_code=404, detail="Test not found")
                if test_data[0] != user_id:
                    raise HTTPException(status_code=403, detail="Access denied")

                specialization_id = test_data[1]
                print(f"  Specialization ID: {specialization_id}")

                # Check if self-assessment already submitted
                await cur.execute("""
                    SELECT COUNT(*) FROM competency_self_assessments
                    WHERE user_test_id = %s
                """, (user_test_id,))
                already_submitted = (await cur.fetchone())[0] > 0
                print(f"  Self-assessment already submitted: {already_submitted}")

                # Get top CORE competencies for this specialization (importance >= 70)
                await cur.execute("""
                    SELECT c.id, c.name, c.importance
                    FROM competencies c
                    WHERE c.specialization_id = %s
                    AND c.importance >= 70
                    ORDER BY c.importance DESC
                    LIMIT 10
                """, (specialization_id,))

                competencies = []
                for row in await cur.fetchall():
                    competencies.append({
                        "id": row[0],
                        "name": row[1],
                        "importance": row[2]
                    })

                print(f"  ✅ Found {len(competencies)} competencies, already_submitted: {already_submitted}")
                return {
                    "status": "success",
                    "competencies": competencies,
                    "already_submitted": already_submitted
                }
    except HTTPException:
        raise
    except Exception as e:
        print(f"  ❌ ERROR in top-competencies: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)}")

@app.post("/api/test/{user_test_id}/self-assessment")
async def submit_self_assessment(
    user_test_id: int,
    data: SelfAssessmentSubmit,
    current_user: dict = Depends(get_current_user)
):
    """Submit self-assessment ratings for competencies"""
    user_id = current_user["user_id"]
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Verify test belongs to user
                await cur.execute(
                    "SELECT user_id FROM user_specialization_tests WHERE id = %s",
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
                        (user_test_id, user_id, competency_id, self_rating)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (user_test_id, competency_id)
                        DO UPDATE SET self_rating = EXCLUDED.self_rating
                    """, (user_test_id, user_id, competency_id, self_rating))

                await conn.commit()

                return {
                    "status": "success",
                    "message": "Self-assessment submitted successfully"
                }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/results/{user_test_id}")
async def get_results(user_test_id: int, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT ut.user_id, ut.score, ut.max_score, ut.completed_at, s.name, ar.recommendation_text
                    FROM user_specialization_tests ut
                    JOIN specializations s ON s.id = ut.specialization_id
                    LEFT JOIN ai_recommendations ar ON ar.user_test_id = ut.id
                    WHERE ut.id = %s
                """, (user_test_id,))
                row = await cur.fetchone()
                
                if not row:
                    raise HTTPException(status_code=404, detail="Test not found")
                if row[0] != user_id:
                    raise HTTPException(status_code=403, detail="Access denied")
                
                score, max_score = row[1], row[2]
                percentage = (score / max_score) * 100
                level = "Senior" if percentage >= 80 else "Middle" if percentage >= 50 else "Junior"
        
        return {
            "status": "success",
            "score": score, "max_score": max_score, "level": level,
            "specialization_name": row[4], "recommendation": row[5]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================
# API - AI PROCTORING
# =====================================================
class ProctoringEventSubmit(BaseModel):
    user_test_id: int
    event_type: str
    severity: str = "medium"
    details: Optional[dict] = None

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
                    "SELECT user_id FROM user_specialization_tests WHERE id = %s",
                    (event.user_test_id,)
                )
                test_data = await cur.fetchone()

                if not test_data:
                    raise HTTPException(status_code=404, detail="Test not found")
                if test_data[0] != user_id:
                    raise HTTPException(status_code=403, detail="Access denied")

                # Insert proctoring event
                # Convert details dict to JSON string for JSONB column
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

                return {
                    "status": "success",
                    "event_id": event_id,
                    "message": "Proctoring event logged"
                }
    except HTTPException:
        raise
    except Exception as e:
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
                # Verify test belongs to user
                await cur.execute(
                    "SELECT user_id FROM user_specialization_tests WHERE id = %s",
                    (user_test_id,)
                )
                test_data = await cur.fetchone()

                if not test_data:
                    raise HTTPException(status_code=404, detail="Test not found")
                if test_data[0] != user_id:
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
                # Verify test belongs to user
                await cur.execute(
                    "SELECT user_id, suspicious_events_count, proctoring_risk_level FROM user_specialization_tests WHERE id = %s",
                    (user_test_id,)
                )
                test_data = await cur.fetchone()

                if not test_data:
                    raise HTTPException(status_code=404, detail="Test not found")
                if test_data[0] != user_id:
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
                    "total_events": test_data[1],
                    "risk_level": test_data[2],
                    "breakdown": breakdown
                }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================
# API - ДАШБОРД
# =====================================================
@app.get("/api/dashboard/stats")
async def get_dashboard_stats():
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT COUNT(DISTINCT id) FROM users")
                total_users = (await cur.fetchone())[0]
                
                await cur.execute("SELECT COUNT(DISTINCT user_id) FROM user_specialization_tests WHERE completed_at IS NOT NULL")
                completed_users = (await cur.fetchone())[0]
                
                await cur.execute("""
                    SELECT COUNT(DISTINCT ut.user_id)
                    FROM user_specialization_tests ut
                    WHERE ut.completed_at IS NULL
                    AND EXISTS (SELECT 1 FROM test_answers ta WHERE ta.user_test_id = ut.id GROUP BY ta.user_test_id HAVING COUNT(*) >= 10)
                    AND NOT EXISTS (SELECT 1 FROM user_specialization_tests ut2 WHERE ut2.user_id = ut.user_id AND ut2.completed_at IS NOT NULL)
                """)
                in_progress = (await cur.fetchone())[0]
                
                await cur.execute("""
                    SELECT 
                        CASE WHEN (score::numeric / max_score * 100) >= 80 THEN 'Senior'
                             WHEN (score::numeric / max_score * 100) >= 50 THEN 'Middle'
                             ELSE 'Junior' END as level,
                        COUNT(*) as count
                    FROM user_specialization_tests
                    WHERE completed_at IS NOT NULL
                    GROUP BY level
                """)
                levels_data = await cur.fetchall()
                levels = {row[0]: row[1] for row in levels_data}
                
                await cur.execute("""
                    SELECT u.name, u.surname, ut.score, ut.max_score, s.name
                    FROM user_specialization_tests ut
                    JOIN users u ON u.id = ut.user_id
                    JOIN specializations s ON s.id = ut.specialization_id
                    WHERE ut.completed_at IS NOT NULL
                    ORDER BY ut.score DESC, ut.completed_at ASC
                    LIMIT 20
                """)
                top_results_data = await cur.fetchall()
                top_results = [
                    {"name": f"{row[0]} {row[1]}", "score": row[2], "max_score": row[3], "specialization": row[4]}
                    for row in top_results_data
                ]
                
                await cur.execute("""
                    SELECT s.name, COUNT(ut.id) as test_count
                    FROM specializations s
                    LEFT JOIN user_specialization_tests ut ON ut.specialization_id = s.id AND ut.completed_at IS NOT NULL
                    GROUP BY s.id, s.name
                    ORDER BY test_count DESC
                """)
                specializations_data = await cur.fetchall()
                top_specializations = [{"name": row[0], "count": row[1]} for row in specializations_data]
                
                return {
                    "users": {"total": total_users, "completed": completed_users, "in_progress": in_progress},
                    "levels": {"Senior": levels.get("Senior", 0), "Middle": levels.get("Middle", 0), "Junior": levels.get("Junior", 0)},
                    "top_results": top_results,
                    "top_specializations": top_specializations
                }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================
# API - HR PANEL
# =====================================================

# =====================================================
# API - HR LOGIN (ОБНОВЛЕННЫЙ!)
# =====================================================
@app.post("/api/hr/login")
async def hr_login(request: Request, password: str, response: Response):
    """Вход в HR панель - устанавливает cookie"""
    if password == config.HR_PASSWORD:
        token = create_access_token(user_id=0, phone="hr_admin")
        
        # Устанавливаем httpOnly cookie (защита от XSS)
        response.set_cookie(
            key="hr_token",
            value=token,
            httponly=True,  # Нельзя прочитать через JavaScript
            secure=True,    # Только через HTTPS
            samesite="lax", # Защита от CSRF
            max_age=86400   # 24 часа
        )
        
        return {"status": "success"}
    else:
        raise HTTPException(status_code=401, detail="Неверный пароль")

@app.post("/api/hr/logout")
async def hr_logout(response: Response):
    """Выход из HR панели - удаляет cookie"""
    response.delete_cookie(key="hr_token")
    return {"status": "success"}

@app.get("/api/hr/tables")
async def get_hr_tables():
    tables = [
        "users", "profiles", "specializations", "competencies", "topics", "questions",
        "user_specialization_selections", "user_specialization_tests", "user_test_topics",
        "test_answers", "ai_recommendations"
    ]
    
    result = {}
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                for table in tables:
                    await cur.execute(f"SELECT * FROM {table} LIMIT 5")
                    rows = await cur.fetchall()
                    
                    await cur.execute(f"""
                        SELECT column_name FROM information_schema.columns 
                        WHERE table_name = '{table}' ORDER BY ordinal_position
                    """)
                    columns = [row[0] for row in await cur.fetchall()]
                    result[table] = {"columns": columns, "rows": rows}
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/hr/sql")
async def execute_hr_sql(data: SQLQuery):
    query = data.query.lower().strip()
    if not query.startswith("select"):
        raise HTTPException(status_code=400, detail="Только SELECT запросы разрешены")
    
    forbidden = ["insert", "update", "delete", "drop", "create", "alter", "truncate"]
    if any(word in query for word in forbidden):
        raise HTTPException(status_code=400, detail="Запрещённые команды обнаружены")
    
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(data.query)
                rows = await cur.fetchall()
                columns = [desc[0] for desc in cur.description] if cur.description else []
                return {"columns": columns, "rows": rows, "count": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ошибка SQL: {str(e)}")

# =====================================================
# API - HR RESULTS MANAGEMENT
# =====================================================
@app.get("/api/hr/results")
async def get_hr_results(
    specialization_id: Optional[int] = None,
    specialization: Optional[str] = None,
    level: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    search: Optional[str] = None
):
    """Get all test results with optional filtering"""
    try:
        query = """
            SELECT
                ust.id as test_id,
                u.id as user_id,
                u.name,
                u.surname,
                u.phone,
                u.company,
                u.job_title,
                s.name as specialization,
                p.name as profile,
                ust.score,
                ust.max_score,
                CASE
                    WHEN ust.max_score > 0 THEN ROUND((ust.score::numeric / ust.max_score::numeric * 100), 2)
                    ELSE 0
                END as percentage,
                CASE
                    WHEN ust.max_score > 0 AND (ust.score::numeric / ust.max_score::numeric * 100) >= 67 THEN 'Senior'
                    WHEN ust.max_score > 0 AND (ust.score::numeric / ust.max_score::numeric * 100) >= 34 THEN 'Middle'
                    ELSE 'Junior'
                END as level,
                ust.started_at,
                ust.completed_at,
                EXTRACT(EPOCH FROM (ust.completed_at - ust.started_at)) as duration_seconds,
                (
                    SELECT json_agg(json_build_object(
                        'competency_id', csa.competency_id,
                        'competency_name', c.name,
                        'self_rating', csa.self_rating,
                        'importance', c.importance
                    ) ORDER BY c.importance DESC)
                    FROM competency_self_assessments csa
                    JOIN competencies c ON csa.competency_id = c.id
                    WHERE csa.user_test_id = ust.id
                ) as self_assessments,
                (
                    SELECT AVG(mcr.rating)
                    FROM manager_competency_ratings mcr
                    WHERE mcr.user_test_id = ust.id
                ) as avg_manager_rating,
                (
                    SELECT AVG(csa.self_rating)
                    FROM competency_self_assessments csa
                    WHERE csa.user_test_id = ust.id
                ) as avg_self_rating
            FROM user_specialization_tests ust
            JOIN users u ON ust.user_id = u.id
            JOIN specializations s ON ust.specialization_id = s.id
            JOIN profiles p ON s.profile_id = p.id
            WHERE ust.completed_at IS NOT NULL
        """

        params = []

        if specialization_id:
            query += " AND ust.specialization_id = %s"
            params.append(specialization_id)
        elif specialization:
            query += " AND s.name = %s"
            params.append(specialization)

        if level:
            if level == 'Senior':
                query += " AND (ust.score::numeric / ust.max_score::numeric * 100) >= 67"
            elif level == 'Middle':
                query += " AND (ust.score::numeric / ust.max_score::numeric * 100) >= 34 AND (ust.score::numeric / ust.max_score::numeric * 100) < 67"
            elif level == 'Junior':
                query += " AND (ust.score::numeric / ust.max_score::numeric * 100) < 34"

        if date_from:
            query += " AND ust.completed_at >= %s"
            params.append(date_from)

        if date_to:
            query += " AND ust.completed_at <= %s"
            params.append(date_to)

        if search:
            search_param = f"%{search}%"
            query += " AND (LOWER(u.name) LIKE LOWER(%s) OR LOWER(u.surname) LIKE LOWER(%s) OR LOWER(u.phone) LIKE LOWER(%s))"
            params.extend([search_param, search_param, search_param])

        query += " ORDER BY ust.completed_at DESC"

        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, tuple(params))
                rows = await cur.fetchall()
                columns = [desc[0] for desc in cur.description]

                results = []
                for row in rows:
                    result = dict(zip(columns, row))
                    # Convert duration to minutes
                    if result['duration_seconds']:
                        result['duration_minutes'] = round(result['duration_seconds'] / 60, 1)

                    # Calculate weighted score using the formula:
                    # weighted_score = ((test_score * TEST_WEIGHT) + (mgr_rating * MANAGER_WEIGHT) + (self_rtg * SELF_WEIGHT)) / (max_score + 10 + 10) * 100
                    # Where: max_score = max test score, 10 = max manager rating, 10 = max self-assessment rating
                    # Weights are configurable via .env file

                    test_score = result.get('score') or 0
                    max_score = result.get('max_score') or 24  # Default to 24 if not available
                    manager_rating = result.get('avg_manager_rating') or 0
                    self_rating = result.get('avg_self_rating') or 0

                    # Handle None/NULL values safely
                    test_score = float(test_score) if test_score is not None else 0
                    max_score = float(max_score) if max_score is not None and max_score > 0 else 24
                    mgr_rating = float(manager_rating) if manager_rating is not None else 0
                    self_rtg = float(self_rating) if self_rating is not None else 0

                    # Apply the weighted formula using configurable weights
                    weighted_score = (
                        (test_score * config.TEST_WEIGHT) +
                        (mgr_rating * config.MANAGER_WEIGHT) +
                        (self_rtg * config.SELF_WEIGHT)
                    ) / (max_score + 10 + 10) * 100

                    result['weighted_score'] = round(weighted_score, 2)

                    results.append(result)

                return {"status": "success", "results": results, "count": len(results)}
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"ERROR in /api/hr/results: {error_details}")
        raise HTTPException(status_code=500, detail=f"{str(e)} | {error_details}")

@app.get("/api/hr/results/stats")
async def get_hr_results_stats():
    """Get statistical analysis of all results"""
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Overall stats
                await cur.execute("""
                    SELECT
                        COUNT(*) as total_tests,
                        AVG(score::numeric / max_score::numeric * 100) as avg_percentage,
                        MIN(score::numeric / max_score::numeric * 100) as min_percentage,
                        MAX(score::numeric / max_score::numeric * 100) as max_percentage,
                        AVG(EXTRACT(EPOCH FROM (completed_at - started_at)) / 60) as avg_duration_minutes
                    FROM user_specialization_tests
                    WHERE completed_at IS NOT NULL
                """)
                overall = await cur.fetchone()

                # By specialization
                await cur.execute("""
                    SELECT
                        s.name,
                        COUNT(*) as count,
                        AVG(ust.score::numeric / ust.max_score::numeric * 100) as avg_percentage
                    FROM user_specialization_tests ust
                    JOIN specializations s ON ust.specialization_id = s.id
                    WHERE ust.completed_at IS NOT NULL
                    GROUP BY s.name
                    ORDER BY count DESC
                """)
                by_spec = await cur.fetchall()

                # By level
                await cur.execute("""
                    SELECT
                        CASE
                            WHEN (score::numeric / max_score::numeric * 100) >= 67 THEN 'Senior'
                            WHEN (score::numeric / max_score::numeric * 100) >= 34 THEN 'Middle'
                            ELSE 'Junior'
                        END as level,
                        COUNT(*) as count
                    FROM user_specialization_tests
                    WHERE completed_at IS NOT NULL
                    GROUP BY level
                """)
                by_level = await cur.fetchall()

                return {
                    "status": "success",
                    "overall": {
                        "total_tests": overall[0],
                        "avg_percentage": round(overall[1], 2) if overall[1] else 0,
                        "min_percentage": round(overall[2], 2) if overall[2] else 0,
                        "max_percentage": round(overall[3], 2) if overall[3] else 0,
                        "avg_duration_minutes": round(overall[4], 1) if overall[4] else 0
                    },
                    "by_specialization": [
                        {"name": row[0], "count": row[1], "avg_percentage": round(row[2], 2)}
                        for row in by_spec
                    ],
                    "by_level": {row[0]: row[1] for row in by_level}
                }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/hr/results/{test_id}")
async def get_hr_result_detail(test_id: int):
    """Get detailed information about a specific test"""
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Get test info
                await cur.execute("""
                    SELECT
                        ust.id,
                        u.name,
                        u.surname,
                        u.phone,
                        u.company,
                        u.job_title,
                        s.name as specialization,
                        p.name as profile,
                        ust.score,
                        ust.max_score,
                        ust.started_at,
                        ust.completed_at
                    FROM user_specialization_tests ust
                    JOIN users u ON ust.user_id = u.id
                    JOIN specializations s ON ust.specialization_id = s.id
                    JOIN profiles p ON s.profile_id = p.id
                    WHERE ust.id = %s
                """, (test_id,))
                test_info = await cur.fetchone()

                if not test_info:
                    raise HTTPException(status_code=404, detail="Test not found")

                # Get answers by competency
                await cur.execute("""
                    SELECT
                        c.name as competency,
                        t.name as topic,
                        q.question_text,
                        q.level,
                        q.var_1, q.var_2, q.var_3, q.var_4,
                        q.correct_answer,
                        ta.user_answer,
                        ta.is_correct
                    FROM test_answers ta
                    JOIN questions q ON ta.question_id = q.id
                    JOIN topics t ON q.topic_id = t.id
                    JOIN competencies c ON t.competency_id = c.id
                    WHERE ta.user_test_id = %s
                    ORDER BY c.id, t.id, q.level
                """, (test_id,))
                answers = await cur.fetchall()

                # Get AI recommendation
                await cur.execute("""
                    SELECT recommendation_text, created_at
                    FROM ai_recommendations
                    WHERE user_test_id = %s
                """, (test_id,))
                ai_rec = await cur.fetchone()

                return {
                    "status": "success",
                    "test_info": {
                        "id": test_info[0],
                        "name": test_info[1],
                        "surname": test_info[2],
                        "phone": test_info[3],
                        "company": test_info[4],
                        "job_title": test_info[5],
                        "specialization": test_info[6],
                        "profile": test_info[7],
                        "score": test_info[8],
                        "max_score": test_info[9],
                        "started_at": test_info[10],
                        "completed_at": test_info[11]
                    },
                    "answers": [
                        {
                            "competency": ans[0],
                            "topic": ans[1],
                            "question": ans[2],
                            "level": ans[3],
                            "options": [ans[4], ans[5], ans[6], ans[7]],
                            "correct_answer": ans[8],
                            "user_answer": ans[9],
                            "is_correct": ans[10]
                        } for ans in answers
                    ],
                    "ai_recommendation": {
                        "text": ai_rec[0] if ai_rec else None,
                        "created_at": ai_rec[1] if ai_rec else None
                    }
                }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# API - MANAGER RESULTS (Department-filtered)
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
async def get_manager_results(
    manager: dict = Depends(get_current_manager),
    specialization_id: Optional[int] = None,
    specialization: Optional[str] = None,
    level: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    search: Optional[str] = None
):
    """Get test results for manager's department only"""
    department_id = manager.get("department_id")
    manager_id = manager.get("user_id")

    try:
        # Use configurable weights from .env file
        query = f"""
            SELECT
                ust.id as test_id,
                u.id as user_id,
                u.name,
                u.surname,
                u.phone,
                u.company,
                u.job_title,
                s.name as specialization,
                p.name as profile,
                ust.score,
                ust.max_score,
                ROUND((ust.score::numeric / ust.max_score::numeric * 100), 2) as percentage,
                CASE
                    WHEN (ust.score::numeric / ust.max_score::numeric * 100) >= 67 THEN 'Senior'
                    WHEN (ust.score::numeric / ust.max_score::numeric * 100) >= 34 THEN 'Middle'
                    ELSE 'Junior'
                END as level,
                ust.started_at,
                ust.completed_at,
                EXTRACT(EPOCH FROM (ust.completed_at - ust.started_at)) as duration_seconds,
                (
                    SELECT json_agg(json_build_object(
                        'competency_id', csa.competency_id,
                        'competency_name', c.name,
                        'self_rating', csa.self_rating,
                        'importance', c.importance
                    ) ORDER BY c.importance DESC)
                    FROM competency_self_assessments csa
                    JOIN competencies c ON csa.competency_id = c.id
                    WHERE csa.user_test_id = ust.id
                ) as self_assessments,
                (
                    SELECT AVG(mcr.rating)
                    FROM manager_competency_ratings mcr
                    WHERE mcr.user_test_id = ust.id AND mcr.manager_id = %s
                ) as avg_manager_rating,
                (
                    SELECT AVG(csa.self_rating)
                    FROM competency_self_assessments csa
                    WHERE csa.user_test_id = ust.id
                ) as avg_self_rating,
                ROUND(
                    ((ust.score * {config.TEST_WEIGHT}) +
                     COALESCE((
                        SELECT AVG(mcr.rating) * {config.MANAGER_WEIGHT}
                        FROM manager_competency_ratings mcr
                        WHERE mcr.user_test_id = ust.id AND mcr.manager_id = %s
                    ), 0) +
                     COALESCE((
                        SELECT AVG(csa.self_rating) * {config.SELF_WEIGHT}
                        FROM competency_self_assessments csa
                        WHERE csa.user_test_id = ust.id
                    ), 0))
                    / (ust.max_score + 10 + 10) * 100,
                    2
                ) as weighted_score
            FROM user_specialization_tests ust
            JOIN users u ON ust.user_id = u.id
            JOIN specializations s ON ust.specialization_id = s.id
            JOIN profiles p ON s.profile_id = p.id
            WHERE ust.completed_at IS NOT NULL
            AND u.department_id = %s
        """

        params = [manager_id, manager_id, department_id]

        if specialization_id:
            query += " AND ust.specialization_id = %s"
            params.append(specialization_id)
        elif specialization:
            query += " AND s.name = %s"
            params.append(specialization)

        if level:
            if level == 'Senior':
                query += " AND (ust.score::numeric / ust.max_score::numeric * 100) >= 67"
            elif level == 'Middle':
                query += " AND (ust.score::numeric / ust.max_score::numeric * 100) >= 34 AND (ust.score::numeric / ust.max_score::numeric * 100) < 67"
            elif level == 'Junior':
                query += " AND (ust.score::numeric / ust.max_score::numeric * 100) < 34"

        if date_from:
            query += " AND ust.completed_at >= %s"
            params.append(date_from)

        if date_to:
            query += " AND ust.completed_at <= %s"
            params.append(date_to)

        if search:
            query += " AND (LOWER(u.name) LIKE LOWER(%s) OR LOWER(u.surname) LIKE LOWER(%s) OR LOWER(u.phone) LIKE LOWER(%s))"
            search_param = f"%{search}%"
            params.extend([search_param, search_param, search_param])

        query += " ORDER BY ust.completed_at DESC"

        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, tuple(params))
                rows = await cur.fetchall()

                if not rows:
                    return {"status": "success", "results": [], "count": 0}

                columns = [desc[0] for desc in cur.description]

                results = []
                for row in rows:
                    result = dict(zip(columns, row))
                    if result['duration_seconds']:
                        result['duration_minutes'] = round(result['duration_seconds'] / 60, 1)
                    results.append(result)

                return {"status": "success", "results": results, "count": len(results)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/manager/results/stats")
async def get_manager_results_stats(manager: dict = Depends(get_current_manager)):
    """Get statistical analysis for manager's department only"""
    department_id = manager.get("department_id")

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Overall stats for department
                await cur.execute("""
                    SELECT
                        COUNT(*) as total_tests,
                        AVG(ust.score::numeric / ust.max_score::numeric * 100) as avg_percentage,
                        MIN(ust.score::numeric / ust.max_score::numeric * 100) as min_percentage,
                        MAX(ust.score::numeric / ust.max_score::numeric * 100) as max_percentage,
                        AVG(EXTRACT(EPOCH FROM (ust.completed_at - ust.started_at)) / 60) as avg_duration_minutes
                    FROM user_specialization_tests ust
                    JOIN users u ON ust.user_id = u.id
                    WHERE ust.completed_at IS NOT NULL
                    AND u.department_id = %s
                """, (department_id,))
                overall = await cur.fetchone()

                # By specialization (department only)
                await cur.execute("""
                    SELECT
                        s.name,
                        COUNT(*) as count,
                        AVG(ust.score::numeric / ust.max_score::numeric * 100) as avg_percentage
                    FROM user_specialization_tests ust
                    JOIN users u ON ust.user_id = u.id
                    JOIN specializations s ON ust.specialization_id = s.id
                    WHERE ust.completed_at IS NOT NULL
                    AND u.department_id = %s
                    GROUP BY s.name
                    ORDER BY count DESC
                """, (department_id,))
                by_spec = await cur.fetchall()

                # By level (department only)
                await cur.execute("""
                    SELECT
                        CASE
                            WHEN (ust.score::numeric / ust.max_score::numeric * 100) >= 67 THEN 'Senior'
                            WHEN (ust.score::numeric / ust.max_score::numeric * 100) >= 34 THEN 'Middle'
                            ELSE 'Junior'
                        END as level,
                        COUNT(*) as count
                    FROM user_specialization_tests ust
                    JOIN users u ON ust.user_id = u.id
                    WHERE ust.completed_at IS NOT NULL
                    AND u.department_id = %s
                    GROUP BY level
                """, (department_id,))
                by_level = await cur.fetchall()

                return {
                    "status": "success",
                    "overall": {
                        "total_tests": overall[0],
                        "avg_percentage": round(overall[1], 2) if overall[1] else 0,
                        "min_percentage": round(overall[2], 2) if overall[2] else 0,
                        "max_percentage": round(overall[3], 2) if overall[3] else 0,
                        "avg_duration_minutes": round(overall[4], 1) if overall[4] else 0
                    },
                    "by_specialization": [
                        {"name": row[0], "count": row[1], "avg_percentage": round(row[2], 2)}
                        for row in by_spec
                    ],
                    "by_level": {row[0]: row[1] for row in by_level}
                }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/manager/results/{test_id}")
async def get_manager_result_detail(test_id: int, manager: dict = Depends(get_current_manager)):
    """Get detailed information about a specific test (department check)"""
    department_id = manager.get("department_id")

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Get test info with department check
                await cur.execute("""
                    SELECT
                        ust.id,
                        u.name,
                        u.surname,
                        u.phone,
                        u.company,
                        u.job_title,
                        s.name as specialization,
                        p.name as profile,
                        ust.score,
                        ust.max_score,
                        ust.started_at,
                        ust.completed_at,
                        u.department_id
                    FROM user_specialization_tests ust
                    JOIN users u ON ust.user_id = u.id
                    JOIN specializations s ON ust.specialization_id = s.id
                    JOIN profiles p ON s.profile_id = p.id
                    WHERE ust.id = %s
                """, (test_id,))
                test_info = await cur.fetchone()

                if not test_info:
                    raise HTTPException(status_code=404, detail="Test not found")

                # Check department access
                if test_info[12] != department_id:
                    raise HTTPException(status_code=403, detail="Нет доступа к результатам из другого отдела")

                # Get answers
                await cur.execute("""
                    SELECT
                        c.name as competency,
                        t.name as topic,
                        q.question_text,
                        q.level,
                        q.var_1, q.var_2, q.var_3, q.var_4,
                        q.correct_answer,
                        ta.user_answer,
                        ta.is_correct
                    FROM test_answers ta
                    JOIN questions q ON ta.question_id = q.id
                    JOIN topics t ON q.topic_id = t.id
                    JOIN competencies c ON t.competency_id = c.id
                    WHERE ta.user_test_id = %s
                    ORDER BY c.id, t.id, q.level
                """, (test_id,))
                answers = await cur.fetchall()

                # Get AI recommendation
                await cur.execute("""
                    SELECT recommendation_text, created_at
                    FROM ai_recommendations
                    WHERE user_test_id = %s
                """, (test_id,))
                ai_rec = await cur.fetchone()

                return {
                    "status": "success",
                    "test_info": {
                        "id": test_info[0],
                        "name": test_info[1],
                        "surname": test_info[2],
                        "phone": test_info[3],
                        "company": test_info[4],
                        "job_title": test_info[5],
                        "specialization": test_info[6],
                        "profile": test_info[7],
                        "score": test_info[8],
                        "max_score": test_info[9],
                        "started_at": test_info[10],
                        "completed_at": test_info[11]
                    },
                    "answers": [
                        {
                            "competency": ans[0],
                            "topic": ans[1],
                            "question": ans[2],
                            "level": ans[3],
                            "options": [ans[4], ans[5], ans[6], ans[7]],
                            "correct_answer": ans[8],
                            "user_answer": ans[9],
                            "is_correct": ans[10]
                        } for ans in answers
                    ],
                    "ai_recommendation": {
                        "text": ai_rec[0] if ai_rec else None,
                        "created_at": ai_rec[1] if ai_rec else None
                    }
                }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================
# API - EMPLOYEE RATINGS (Manager & HR access)
# =====================================================

class EmployeeRatingSubmit(BaseModel):
    employee_id: int
    rating: int
    comment: Optional[str] = None

class CompetencyRatingSubmit(BaseModel):
    user_test_id: int
    competency_ratings: dict  # {competency_id: rating}

@app.get("/api/manager/employees")
async def get_manager_employees(manager: dict = Depends(get_current_manager)):
    """Get list of employees in manager's department"""
    department_id = manager.get("department_id")
    manager_id = manager.get("user_id")

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT
                        u.id,
                        u.name,
                        u.surname,
                        u.phone,
                        u.job_title,
                        u.company,
                        d.name as department_name
                    FROM users u
                    LEFT JOIN departments d ON u.department_id = d.id
                    WHERE u.department_id = %s
                    AND u.role = 'employee'
                    AND u.id != %s
                    ORDER BY u.surname, u.name
                """, (department_id, manager_id))
                employees = await cur.fetchall()

                return {
                    "status": "success",
                    "employees": [
                        {
                            "id": emp[0],
                            "name": emp[1],
                            "surname": emp[2],
                            "phone": emp[3],
                            "job_title": emp[4],
                            "company": emp[5],
                            "department": emp[6]
                        } for emp in employees
                    ]
                }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/manager/ratings")
async def get_manager_ratings(manager: dict = Depends(get_current_manager)):
    """DEPRECATED: Old API - Use /api/manager/employee-tests instead

    Returns empty data for backward compatibility"""
    return {
        "status": "success",
        "ratings": [],
        "message": "This API is deprecated. Use competency-based ratings instead."
    }

@app.post("/api/manager/rating")
async def submit_employee_rating(data: EmployeeRatingSubmit, manager: dict = Depends(get_current_manager)):
    """DEPRECATED: Old API - Use /api/manager/competency-ratings instead

    Returns success for backward compatibility but doesn't save data"""
    raise HTTPException(
        status_code=410,
        detail="This API is deprecated. Please use the new competency-based rating system at /api/manager/competency-ratings"
    )

# =====================================================
# API - COMPETENCY-BASED RATINGS (New HR Requirements)
# =====================================================

@app.get("/api/manager/employee-tests/{employee_id}")
async def get_employee_completed_tests(employee_id: int, manager: dict = Depends(get_current_manager)):
    """Get completed tests for an employee to rate by competency"""
    department_id = manager.get("department_id")
    manager_id = manager.get("user_id")

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Verify employee is in manager's department
                await cur.execute("""
                    SELECT department_id FROM users WHERE id = %s
                """, (employee_id,))
                emp = await cur.fetchone()

                if not emp or emp[0] != department_id:
                    raise HTTPException(status_code=403, detail="Employee not in your department")

                # Get all tests with competencies and self-assessments (including incomplete)
                await cur.execute("""
                    SELECT
                        ust.id as test_id,
                        s.name as specialization,
                        p.name as profile,
                        ust.completed_at,
                        ust.score,
                        ust.max_score,
                        c.id as competency_id,
                        c.name as competency_name,
                        csa.self_rating,
                        mcr.rating as manager_rating
                    FROM user_specialization_tests ust
                    JOIN specializations s ON s.id = ust.specialization_id
                    JOIN profiles p ON p.id = s.profile_id
                    JOIN competencies c ON c.specialization_id = ust.specialization_id
                    LEFT JOIN competency_self_assessments csa ON csa.user_test_id = ust.id AND csa.competency_id = c.id
                    LEFT JOIN manager_competency_ratings mcr ON mcr.user_test_id = ust.id AND mcr.competency_id = c.id AND mcr.manager_id = %s
                    WHERE ust.user_id = %s
                    ORDER BY ust.started_at DESC, c.name
                """, (manager_id, employee_id))

                rows = await cur.fetchall()

                # Group by test
                tests = {}
                for row in rows:
                    test_id = row[0]
                    if test_id not in tests:
                        tests[test_id] = {
                            "test_id": test_id,
                            "specialization": row[1],
                            "profile": row[2],
                            "completed_at": row[3].isoformat() if row[3] else None,
                            "score": row[4],
                            "max_score": row[5],
                            "competencies": []
                        }

                    tests[test_id]["competencies"].append({
                        "competency_id": row[6],
                        "competency_name": row[7],
                        "self_rating": row[8],
                        "manager_rating": row[9]
                    })

                return {
                    "status": "success",
                    "employee_id": employee_id,
                    "tests": list(tests.values())
                }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/manager/competency-ratings")
async def submit_competency_ratings(data: CompetencyRatingSubmit, manager: dict = Depends(get_current_manager)):
    """Submit or update competency-based ratings for an employee's test"""
    manager_id = manager.get("user_id")
    department_id = manager.get("department_id")

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Verify test belongs to employee in manager's department
                await cur.execute("""
                    SELECT u.department_id, u.id as employee_id
                    FROM user_specialization_tests ust
                    JOIN users u ON ust.user_id = u.id
                    WHERE ust.id = %s
                """, (data.user_test_id,))

                test_info = await cur.fetchone()
                if not test_info:
                    raise HTTPException(status_code=404, detail="Test not found")

                if test_info[0] != department_id:
                    raise HTTPException(status_code=403, detail="Employee not in your department")

                employee_id = test_info[1]

                # Insert or update ratings for each competency
                for competency_id, rating in data.competency_ratings.items():
                    if not (1 <= rating <= 10):
                        raise HTTPException(status_code=400, detail=f"Rating must be between 1 and 10, got {rating}")

                    await cur.execute("""
                        INSERT INTO manager_competency_ratings
                            (employee_id, manager_id, user_test_id, competency_id, rating)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (user_test_id, competency_id, manager_id)
                        DO UPDATE SET
                            rating = EXCLUDED.rating,
                            updated_at = CURRENT_TIMESTAMP
                    """, (employee_id, manager_id, data.user_test_id, int(competency_id), rating))

                return {
                    "status": "success",
                    "message": "Competency ratings saved successfully"
                }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/hr/ratings")
async def get_all_ratings(hr_user: dict = Depends(verify_hr_cookie)):
    """Get all competency-based ratings from managers across all departments"""
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Get all competency ratings with employee, manager, and test info
                await cur.execute("""
                    SELECT
                        mcr.id,
                        mcr.employee_id,
                        emp.name as employee_name,
                        emp.surname as employee_surname,
                        emp.phone as employee_phone,
                        emp.company as employee_company,
                        emp.job_title as employee_job_title,
                        d_emp.name as employee_department,
                        mcr.manager_id,
                        mgr.name as manager_name,
                        mgr.surname as manager_surname,
                        d_mgr.name as manager_department,
                        mcr.user_test_id,
                        s.name as specialization,
                        p.name as profile,
                        c.name as competency_name,
                        mcr.competency_id,
                        mcr.rating,
                        mcr.created_at,
                        mcr.updated_at,
                        ust.score as test_score,
                        ust.max_score as test_max_score,
                        ust.completed_at,
                        csa.self_rating
                    FROM manager_competency_ratings mcr
                    JOIN users emp ON mcr.employee_id = emp.id
                    JOIN users mgr ON mcr.manager_id = mgr.id
                    LEFT JOIN departments d_emp ON emp.department_id = d_emp.id
                    LEFT JOIN departments d_mgr ON mgr.department_id = d_mgr.id
                    JOIN user_specialization_tests ust ON mcr.user_test_id = ust.id
                    JOIN specializations s ON ust.specialization_id = s.id
                    JOIN profiles p ON s.profile_id = p.id
                    JOIN competencies c ON mcr.competency_id = c.id
                    LEFT JOIN competency_self_assessments csa
                        ON csa.user_test_id = ust.id
                        AND csa.competency_id = mcr.competency_id
                    ORDER BY mcr.created_at DESC
                """)

                rows = await cur.fetchall()

                ratings = []
                for row in rows:
                    test_percentage = (row[20] / row[21] * 100) if row[21] > 0 else 0

                    ratings.append({
                        "id": row[0],
                        "employee_id": row[1],
                        "employee_name": f"{row[2]} {row[3]}",
                        "employee_phone": row[4],
                        "employee_company": row[5],
                        "employee_job_title": row[6],
                        "employee_department": row[7],
                        "manager_id": row[8],
                        "manager_name": f"{row[9]} {row[10]}",
                        "manager_department": row[11],
                        "user_test_id": row[12],
                        "specialization": row[13],
                        "profile": row[14],
                        "competency_name": row[15],
                        "competency_id": row[16],
                        "rating": row[17],
                        "created_at": row[18].isoformat() if row[18] else None,
                        "updated_at": row[19].isoformat() if row[19] else None,
                        "test_score": row[20],
                        "test_max_score": row[21],
                        "test_percentage": round(test_percentage, 1),
                        "test_completed_at": row[22].isoformat() if row[22] else None,
                        "self_rating": row[23]
                    })

                return {
                    "status": "success",
                    "ratings": ratings,
                    "total": len(ratings)
                }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================
# API - МОНИТОРИНГ
# =====================================================
def calculate_percentiles(values):
    if not values:
        return {"median": 0, "p95": 0}
    sorted_values = sorted(values)
    median = statistics.median(sorted_values)
    index_95 = int(len(sorted_values) * 0.95)
    p95 = sorted_values[min(index_95, len(sorted_values) - 1)]
    return {"median": round(median, 2), "p95": round(p95, 2)}

@app.get("/api/hr/monitoring/overview")
async def get_monitoring_overview():
    try:
        now = datetime.now()
        online_threshold = now - timedelta(minutes=5)
        online_count = sum(
            1 for last_activity in monitoring_data["active_users"].values()
            if last_activity > online_threshold
        )
        
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        
        return {
            "status": "success",
            "online_users": online_count,
            "cpu_percent": round(cpu_percent, 1),
            "ram_percent": round(memory.percent, 1),
            "timestamp": now.isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/hr/monitoring/realtime")
async def get_realtime_metrics():
    try:
        now = datetime.now()
        threshold = now - timedelta(seconds=10)
        
        recent_requests = [
            req for req in monitoring_data["requests"]
            if req["timestamp"] > threshold
        ]
        
        if not recent_requests:
            return {
                "status": "success",
                "median": 0,
                "p95": 0,
                "count": 0,
                "timestamp": now.isoformat()
            }
        
        response_times = [req["response_time"] for req in recent_requests]
        percentiles = calculate_percentiles(response_times)
        
        return {
            "status": "success",
            "median": percentiles["median"],
            "p95": percentiles["p95"],
            "count": len(recent_requests),
            "timestamp": now.isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/hr/monitoring/operations")
async def get_operations_stats():
    try:
        now = datetime.now()
        threshold = now - timedelta(minutes=5)
        
        recent_requests = [
            req for req in monitoring_data["requests"]
            if req["timestamp"] > threshold
        ]
        
        operations = {
            "submit_answer": {"name": "💬 Ответы на вопросы", "endpoint": "/api/submit-answer", "times": []},
            "register": {"name": "📝 Регистрация", "endpoint": "/api/register", "times": []},
            "start_test": {"name": "▶️ Старт теста", "endpoint": "/api/start-test", "times": []},
            "get_questions": {"name": "📄 Получение вопросов", "endpoint_pattern": "/api/test/", "times": []}
        }
        
        for req in recent_requests:
            endpoint = req["endpoint"]
            if endpoint == "/api/submit-answer":
                operations["submit_answer"]["times"].append(req["response_time"])
            elif endpoint == "/api/register":
                operations["register"]["times"].append(req["response_time"])
            elif endpoint == "/api/start-test":
                operations["start_test"]["times"].append(req["response_time"])
            elif "/api/test/" in endpoint and "/questions" in endpoint:
                operations["get_questions"]["times"].append(req["response_time"])
        
        result = []
        for op_key, op_data in operations.items():
            if op_data["times"]:
                percentiles = calculate_percentiles(op_data["times"])
                result.append({
                    "name": op_data["name"],
                    "median": percentiles["median"],
                    "p95": percentiles["p95"],
                    "count": len(op_data["times"])
                })
            else:
                result.append({
                    "name": op_data["name"],
                    "median": 0,
                    "p95": 0,
                    "count": 0
                })
        
        return {
            "status": "success",
            "operations": result,
            "timestamp": now.isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================
# DATABASE MIGRATION ENDPOINT (ONE-TIME SETUP)
# =====================================================
@app.get("/api/setup-self-assessment-table")
async def setup_self_assessment_table():
    """
    ONE-TIME SETUP: Create competency_self_assessments table
    Visit this URL once to create the table: /api/setup-self-assessment-table
    """
    try:
        migration_sql = """
        -- Create table for competency self-assessments
        CREATE TABLE IF NOT EXISTS competency_self_assessments (
            id SERIAL PRIMARY KEY,
            user_test_id INTEGER NOT NULL REFERENCES user_specialization_tests(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            competency_id INTEGER NOT NULL REFERENCES competencies(id) ON DELETE CASCADE,
            self_rating INTEGER NOT NULL CHECK (self_rating >= 1 AND self_rating <= 10),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_test_id, competency_id)
        );

        -- Indexes for performance
        CREATE INDEX IF NOT EXISTS idx_self_assessments_user_test ON competency_self_assessments(user_test_id);
        CREATE INDEX IF NOT EXISTS idx_self_assessments_user ON competency_self_assessments(user_id);
        CREATE INDEX IF NOT EXISTS idx_self_assessments_competency ON competency_self_assessments(competency_id);
        """

        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Execute the migration
                await cur.execute(migration_sql)
                await conn.commit()

                # Verify table was created
                await cur.execute("""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_name = 'competency_self_assessments'
                """)
                table_exists = await cur.fetchone()

                if table_exists:
                    return {
                        "status": "success",
                        "message": "✅ Table 'competency_self_assessments' created successfully!",
                        "table_name": table_exists[0],
                        "next_step": "You can now use the self-assessment feature. Complete a test to try it!"
                    }
                else:
                    return {
                        "status": "error",
                        "message": "Table creation command executed but table not found. Check database permissions."
                    }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to create table: {str(e)}",
            "error_type": type(e).__name__
        }

@app.get("/api/setup-hr-requirements")
async def setup_hr_requirements():
    """
    COMPREHENSIVE SETUP: Implement all HR requirements
    - Competency-based manager evaluations
    - Test time limits
    - Weighted score calculation

    Visit this URL once to update the database: /api/setup-hr-requirements
    """
    try:
        migration_steps = []

        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Step 1: Create self-assessment table if not exists
                migration_steps.append("Creating competency_self_assessments table...")
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS competency_self_assessments (
                        id SERIAL PRIMARY KEY,
                        user_test_id INTEGER NOT NULL REFERENCES user_specialization_tests(id) ON DELETE CASCADE,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        competency_id INTEGER NOT NULL REFERENCES competencies(id) ON DELETE CASCADE,
                        self_rating INTEGER NOT NULL CHECK (self_rating >= 1 AND self_rating <= 10),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(user_test_id, competency_id)
                    );
                    CREATE INDEX IF NOT EXISTS idx_self_assessments_user_test ON competency_self_assessments(user_test_id);
                    CREATE INDEX IF NOT EXISTS idx_self_assessments_user ON competency_self_assessments(user_id);
                    CREATE INDEX IF NOT EXISTS idx_self_assessments_competency ON competency_self_assessments(competency_id);
                """)

                # Step 2: Drop old employee_ratings and create new manager_competency_ratings
                migration_steps.append("Updating manager rating system to competency-based...")
                await cur.execute("""
                    DROP TABLE IF EXISTS employee_ratings CASCADE;

                    CREATE TABLE IF NOT EXISTS manager_competency_ratings (
                        id SERIAL PRIMARY KEY,
                        employee_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        manager_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        user_test_id INTEGER NOT NULL REFERENCES user_specialization_tests(id) ON DELETE CASCADE,
                        competency_id INTEGER NOT NULL REFERENCES competencies(id) ON DELETE CASCADE,
                        rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 10),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(user_test_id, competency_id, manager_id)
                    );
                    CREATE INDEX IF NOT EXISTS idx_manager_comp_ratings_employee ON manager_competency_ratings(employee_id);
                    CREATE INDEX IF NOT EXISTS idx_manager_comp_ratings_manager ON manager_competency_ratings(manager_id);
                    CREATE INDEX IF NOT EXISTS idx_manager_comp_ratings_test ON manager_competency_ratings(user_test_id);
                    CREATE INDEX IF NOT EXISTS idx_manager_comp_ratings_competency ON manager_competency_ratings(competency_id);
                """)

                # Step 3: Add time limit columns to tests
                migration_steps.append("Adding test time limit tracking...")
                await cur.execute("""
                    ALTER TABLE user_specialization_tests
                    ADD COLUMN IF NOT EXISTS time_limit_minutes INTEGER DEFAULT 40,
                    ADD COLUMN IF NOT EXISTS time_started_at TIMESTAMP,
                    ADD COLUMN IF NOT EXISTS time_expired BOOLEAN DEFAULT FALSE;

                    UPDATE user_specialization_tests
                    SET time_started_at = started_at
                    WHERE time_started_at IS NULL AND started_at IS NOT NULL;
                """)

                await conn.commit()

                # Verify all tables exist
                await cur.execute("""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_name IN ('competency_self_assessments', 'manager_competency_ratings')
                    ORDER BY table_name
                """)
                tables = await cur.fetchall()

                return {
                    "status": "success",
                    "message": "✅ All HR requirements implemented successfully!",
                    "migration_steps": migration_steps,
                    "tables_created": [t[0] for t in tables],
                    "changes": [
                        "✓ Self-assessment system ready",
                        "✓ Manager competency-based evaluations ready",
                        "✓ 40-minute test time limit added",
                        "✓ Weighted score calculation ready (Test 50%, Manager 40%, Self 10%)"
                    ],
                    "next_steps": [
                        "1. Complete a test to try self-assessment",
                        "2. Managers can now rate by competency (not just overall rating)",
                        "3. Final weighted scores will appear in results panels"
                    ]
                }

    except Exception as e:
        import traceback
        return {
            "status": "error",
            "message": f"Migration failed: {str(e)}",
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc()
        }

@app.get("/api/setup-ai-proctoring")
async def setup_ai_proctoring():
    """
    Setup AI Proctoring System
    - Creates proctoring_events table
    - Adds proctoring columns to user_specialization_tests
    - Creates proctoring_summary view
    - Sets up automatic triggers

    Visit this URL once to enable AI proctoring: /api/setup-ai-proctoring
    """
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                # Read and execute migration SQL
                migration_file = 'db/migrations/add_proctoring_events.sql'

                with open(migration_file, 'r') as f:
                    migration_sql = f.read()

                # Execute migration
                await cur.execute(migration_sql)
                await conn.commit()

                # Verify table was created
                await cur.execute("""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_name = 'proctoring_events'
                    ORDER BY ordinal_position
                """)
                columns = await cur.fetchall()

                # Check if proctoring columns added to tests table
                await cur.execute("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'user_specialization_tests'
                    AND column_name IN ('proctoring_enabled', 'suspicious_events_count', 'proctoring_risk_level')
                """)
                test_columns = await cur.fetchall()

                return {
                    "status": "success",
                    "message": "✅ AI Proctoring System enabled successfully!",
                    "features_enabled": [
                        "🎥 Live camera streaming",
                        "👤 Face detection (BlazeFace)",
                        "👁️ Eye gaze tracking (FaceMesh)",
                        "🚫 Multiple person detection",
                        "📑 Tab switching detection",
                        "🪟 Window focus tracking",
                        "🖱️ Right-click prevention",
                        "📊 Real-time event logging",
                        "⚠️ Automatic risk level calculation"
                    ],
                    "database_changes": {
                        "proctoring_events_table": f"Created with {len(columns)} columns",
                        "test_table_columns_added": len(test_columns),
                        "views_created": ["proctoring_summary"],
                        "triggers_created": ["trigger_update_suspicious_events"]
                    },
                    "event_types_tracked": [
                        "no_face_detected (high)",
                        "multiple_faces (critical)",
                        "looking_away (medium)",
                        "tab_switched (high)",
                        "window_blur (medium)",
                        "context_menu (low)"
                    ],
                    "next_steps": [
                        "1. Start a test - AI proctoring will activate automatically",
                        "2. Face detection runs every 2 seconds",
                        "3. Events are logged to proctoring_events table",
                        "4. View events via /api/proctoring/events/{test_id}",
                        "5. Check risk level via /api/proctoring/summary/{test_id}"
                    ],
                    "api_endpoints": [
                        "POST /api/proctoring/event - Log proctoring event",
                        "GET /api/proctoring/events/{test_id} - Get all events",
                        "GET /api/proctoring/summary/{test_id} - Get summary stats"
                    ]
                }

    except Exception as e:
        import traceback
        return {
            "status": "error",
            "message": f"Setup failed: {str(e)}",
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc(),
            "help": "Make sure db/migrations/add_proctoring_events.sql exists"
        }

# =====================================================
# RUN
# =====================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)