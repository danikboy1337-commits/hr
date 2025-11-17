"""
Authentication module V2
Uses tab_number instead of phone for user identification
"""

from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional
import os

# V2: Import from config_v2
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config_v2 import JWT_SECRET_KEY

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7  # Token lives 7 days

def create_access_token(
    user_id: int,
    tab_number: str,  # Changed from phone
    role: str = "employee",
    department_id: Optional[int] = None
) -> str:
    """
    Create JWT token for user (V2)

    Args:
        user_id: User database ID
        tab_number: Employee tab number (e.g., "00061221")
        role: User role (employee/hr/manager)
        department_id: Department ID (for managers)

    Returns:
        JWT token string
    """
    expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode = {
        "user_id": user_id,
        "tab_number": tab_number,  # Changed from phone
        "role": role,
        "department_id": department_id,
        "exp": expire
    }
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> Optional[dict]:
    """
    Verify JWT token and return data (V2)

    Returns:
        Dict with user_id, tab_number, role, department_id
        None if token is invalid
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("user_id")
        tab_number: str = payload.get("tab_number")  # Changed from phone
        role: str = payload.get("role", "employee")
        department_id: Optional[int] = payload.get("department_id")

        if user_id is None or tab_number is None:
            return None

        return {
            "user_id": user_id,
            "tab_number": tab_number,  # Changed from phone
            "role": role,
            "department_id": department_id
        }
    except JWTError:
        return None
