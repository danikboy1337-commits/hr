import os
import sys

# CRITICAL: Enable OpenSSL legacy provider for MD4 support (required for NTLM/LDAP)
# This must be done BEFORE importing ldap3
os.environ['OPENSSL_CONF'] = os.path.join(os.path.dirname(__file__), 'openssl_legacy.cnf')

import logging
import datetime
from typing import Optional, Dict, Any
from ldap3 import Server, Connection, ALL, NTLM, SIMPLE, Tls
from fastapi import HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext
import config  # Import config module instead of os

# Configure logging
logging.basicConfig(
    filename='login_history.log',
    level=logging.INFO,
    format='%(asctime)s:%(levelname)s:%(message)s'
)

# JWT Configuration (from config.py)
SECRET_KEY = config.JWT_SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 hours

# LDAP Configuration (from config.py - PLACEHOLDER values until activated)
LDAP_CONFIG = {
    'domain': config.LDAP_DOMAIN,
    'host': config.LDAP_HOST,
    'port': config.LDAP_PORT,
    'base_dn': config.LDAP_BASE_DN,
    'use_ssl': config.LDAP_USE_SSL,
    'use_tls': config.LDAP_USE_TLS,
    'timeout': config.LDAP_TIMEOUT,
}

def parse_permitted_users():
    # Default permitted users (PLACEHOLDER - Replace with real employee IDs in production)
    default_users = {
        'PLACEHOLDER_EMPLOYEE_ID_1': {
            'name': 'Test User 1',
            'role': 'hr',
            'permissions': ['read', 'write', 'admin']
        },
        'PLACEHOLDER_EMPLOYEE_ID_2': {
            'name': 'Test User 2',
            'role': 'manager',
            'permissions': ['read', 'write']
        },
        'PLACEHOLDER_EMPLOYEE_ID_3': {
            'name': 'Test User 3',
            'role': 'employee',
            'permissions': ['read']
        },
    }

    # Try to read from environment variable (from config.py)
    users_env = config.PERMITTED_USERS_ENV
    
    if not users_env:
        logging.info("No PERMITTED_USERS environment variable found, using default users")
        return default_users
    
    try:
        permitted_users = {}
        user_entries = users_env.split(';')
        
        for entry in user_entries:
            if not entry.strip():
                continue
                
            parts = entry.strip().split(':')
            if len(parts) != 4:
                logging.warning(f"Invalid user entry format: {entry}. Expected format: USER_ID:NAME:ROLE:PERMISSIONS")
                continue
            
            user_id, name, role, permissions_str = parts
            permissions = [p.strip() for p in permissions_str.split(',') if p.strip()]
            
            permitted_users[user_id] = {
                'name': name,
                'role': role,
                'permissions': permissions
            }
        
        if permitted_users:
            logging.info(f"Loaded {len(permitted_users)} permitted users from environment variable")
            return permitted_users
        else:
            logging.warning("No valid users found in PERMITTED_USERS environment variable, using defaults")
            return default_users
            
    except Exception as e:
        logging.error(f"Error parsing PERMITTED_USERS environment variable: {e}")
        logging.info("Using default permitted users")
        return default_users

# Load permitted users from environment or use defaults
PERMITTED_USERS = parse_permitted_users()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def check_ldap_password(username: str, password: str) -> bool:
    """
    Authenticate user against LDAP server
    Adapted from original Streamlit code

    When LDAP_ENABLED=False, uses mock authentication for testing
    Mock password: "test123" (accepts any username in permitted list)
    """
    # Mock authentication when LDAP is disabled
    if not config.LDAP_ENABLED:
        logging.info(f"🧪 MOCK MODE: Authenticating {username} with password {'*' * len(password)}")
        if password == "test123":
            logging.info(f"✅ MOCK: Authentication successful for {username}")
            return True
        else:
            logging.info(f"❌ MOCK: Authentication failed for {username} (use 'test123' as password)")
            return False

    # Real LDAP authentication
    try:
        server = Server(
            LDAP_CONFIG['host'],
            port=LDAP_CONFIG['port'],
            use_ssl=LDAP_CONFIG['use_ssl'],
            get_info=ALL
        )

        if LDAP_CONFIG['use_tls']:
            tls_configuration = Tls(validate=False)  # ssl.CERT_NONE equivalent
            server.tls = tls_configuration

        # Try multiple authentication formats for compatibility
        # Format 1: username@DOMAIN (UPN format - most common for AD with SIMPLE auth)
        user_dn_upn = f"{username}@{LDAP_CONFIG['domain']}"
        # Format 2: DOMAIN\username (for NTLM - but may fail with MD4 error)
        user_dn_ntlm = f"{LDAP_CONFIG['domain']}\\{username}"

        # Try SIMPLE authentication with UPN format (works with modern OpenSSL, no MD4 needed)
        logging.info(f"Attempting SIMPLE authentication for user: {username}")
        logging.info(f"Trying UPN format: {user_dn_upn}")

        try:
            conn = Connection(
                server,
                user=user_dn_upn,
                password=password,
                authentication=SIMPLE,
                auto_bind=False
            )

            if conn.bind():
                logging.info(f"✅ Successfully authenticated user {username} using SIMPLE authentication (UPN format)")
                conn.unbind()
                return True
            else:
                logging.warning(f"SIMPLE authentication (UPN) failed for {username}: {conn.result}")
        except Exception as e:
            logging.warning(f"SIMPLE authentication (UPN) error for {username}: {e}")

        # Fallback: Try DOMAIN\username with SIMPLE
        logging.info(f"Trying DOMAIN\\username format: {user_dn_ntlm}")
        try:
            conn = Connection(
                server,
                user=user_dn_ntlm,
                password=password,
                authentication=SIMPLE,
                auto_bind=False
            )

            if conn.bind():
                logging.info(f"✅ Successfully authenticated user {username} using SIMPLE authentication (DOMAIN\\username format)")
                conn.unbind()
                return True
            else:
                logging.warning(f"SIMPLE authentication (DOMAIN\\username) failed for {username}: {conn.result}")
        except Exception as e:
            logging.warning(f"SIMPLE authentication (DOMAIN\\username) error for {username}: {e}")

        # Fallback: Try just username with SIMPLE
        logging.info(f"Trying plain username: {username}")
        try:
            conn = Connection(
                server,
                user=username,
                password=password,
                authentication=SIMPLE,
                auto_bind=False
            )

            if conn.bind():
                logging.info(f"✅ Successfully authenticated user {username} using SIMPLE authentication (plain username)")
                conn.unbind()
                return True
            else:
                logging.warning(f"SIMPLE authentication (plain username) failed for {username}: {conn.result}")
        except Exception as e:
            logging.warning(f"SIMPLE authentication (plain username) error for {username}: {e}")

        # All authentication methods failed
        logging.error(f"❌ All authentication methods failed for user: {username}")
        logging.error(f"LDAP Config: host={LDAP_CONFIG['host']}, port={LDAP_CONFIG['port']}, domain={LDAP_CONFIG['domain']}")
        return False

    except Exception as e:
        logging.error(f"LDAP authentication error for user {username}: {e}")
        logging.error(f"LDAP Config: host={LDAP_CONFIG['host']}, port={LDAP_CONFIG['port']}, domain={LDAP_CONFIG['domain']}")
        return False

def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None):
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.datetime.utcnow() + expires_delta
    else:
        expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify JWT token and return user data"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
        return payload
    except JWTError:
        return None

def authenticate_user(username: str, password: str) -> Dict[str, Any]:
    """
    Authenticate user and return user info
    """
    now = datetime.datetime.now()
    
    # Check if user is in permitted list
    if username not in PERMITTED_USERS:
        logging.info(f"Not approved user {username} at {now}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ к ресурсу отсутствует"
        )
    
    # Authenticate against LDAP
    if not check_ldap_password(username, password):
        logging.info(f"Incorrect login attempt for user {username} at {now}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The username or password you have entered is incorrect."
        )
    
    # Get user info
    user_info = PERMITTED_USERS[username]
    logging.info(f"Successful login for user {username} ({user_info['name']}) at {now}")
    
    return {
        "username": username,
        "name": user_info['name'],
        "role": user_info['role'],
        "permissions": user_info['permissions']
    }

def get_current_user(token: str) -> Dict[str, Any]:
    """Get current user from token"""
    payload = verify_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    username = payload.get("sub")
    if username not in PERMITTED_USERS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not authorized"
        )
    
    user_info = PERMITTED_USERS[username]
    return {
        "username": username,
        "name": user_info['name'],
        "role": user_info['role'],
        "permissions": user_info['permissions']
    }