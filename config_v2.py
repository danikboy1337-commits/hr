import os
from dotenv import load_dotenv

load_dotenv()

# =====================================================
# DATABASE CONFIGURATION
# =====================================================
# V2: Using hr_test schema instead of hr
DATABASE_URL = os.getenv("DATABASE_URL", "")

# =====================================================
# ANTHROPIC API (OPTIONAL)
# =====================================================
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# =====================================================
# APP SETTINGS
# =====================================================
APP_HOST = os.getenv("HOST", "0.0.0.0")
APP_PORT = int(os.getenv("PORT", 8000))
DEBUG = os.getenv("DEBUG", "False").lower() == "true"

# =====================================================
# ORGANIZATION BRANDING
# =====================================================
ORG_NAME = "Халык банк"
ORG_LOGO = "/static/images/halyk_logo.png"
ORG_PRIMARY_COLOR = "#1DB584"

# =====================================================
# RECAPTCHA
# =====================================================
RECAPTCHA_SITE_KEY = os.getenv("RECAPTCHA_SITE_KEY", "")
RECAPTCHA_SECRET_KEY = os.getenv("RECAPTCHA_SECRET_KEY", "")

# =====================================================
# LDAP/ACTIVE DIRECTORY CONFIGURATION
# =====================================================
LDAP_ENABLED = os.getenv("LDAP_ENABLED", "False").lower() == "true"
LDAP_DOMAIN = os.getenv("LDAP_DOMAIN", "UNIVERSAL")
LDAP_HOST = os.getenv("LDAP_HOST", "ldap-server.company.local")
LDAP_PORT = int(os.getenv("LDAP_PORT", 389))
LDAP_BASE_DN = os.getenv("LDAP_BASE_DN", "OU=Employees,DC=company,DC=local")
LDAP_USE_SSL = os.getenv("LDAP_USE_SSL", "False").lower() == "true"
LDAP_USE_TLS = os.getenv("LDAP_USE_TLS", "False").lower() == "true"
LDAP_TIMEOUT = int(os.getenv("LDAP_TIMEOUT", 10))

# =====================================================
# PERMITTED USERS (WHITELIST)
# =====================================================
# Format: TAB_NUMBER:NAME:ROLE:PERMISSIONS;TAB_NUMBER:NAME:ROLE:PERMISSIONS
# Example: 00061221:Danial Aibassov:hr:read,write,admin;00058215:Manager Name:manager:read,write
PERMITTED_USERS_ENV = os.getenv("PERMITTED_USERS", "00061221:Danial Aibassov:hr:read,write,admin")

# =====================================================
# JWT SECRET KEY
# =====================================================
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "PLACEHOLDER-SECRET-KEY-CHANGE-IN-PRODUCTION-MIN-32-CHARS")

# =====================================================
# HR PANEL PASSWORD
# =====================================================
# V2: Externalized to environment
HR_PASSWORD = os.getenv("HR_PASSWORD", "111111")  # Change in production!

# =====================================================
# TEST CONFIGURATION (V2)
# =====================================================
# Number of triplets (themes) per test
THEMES_PER_TEST = 20

# Questions per triplet (junior, middle, senior)
QUESTIONS_PER_TRIPLET = 3

# Total questions per test
TOTAL_QUESTIONS = THEMES_PER_TEST * QUESTIONS_PER_TRIPLET  # 60

# =====================================================
# DATABASE SCHEMA (V2)
# =====================================================
# Important: V2 uses hr_test schema, not hr
DB_SCHEMA = "hr_test"

# =====================================================
# QUESTION ENCRYPTION (V2)
# =====================================================
# Questions are stored encrypted, decrypted on-the-fly
# Set this to your Fernet key when ready to decrypt
QUESTION_ENCRYPTION_KEY = os.getenv("QUESTION_ENCRYPTION_KEY", None)
