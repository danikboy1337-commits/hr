import os
from dotenv import load_dotenv

load_dotenv()

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Anthropic API
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# HR PANEL
HR_PASSWORD = "111111"

# App Settings
APP_HOST = os.getenv("HOST", "0.0.0.0")
APP_PORT = int(os.getenv("PORT", 8000))
DEBUG = os.getenv("DEBUG", "False").lower() == "true"

# Organization
ORG_NAME = "Халык банк"
ORG_LOGO = "/static/images/halyk_logo.png"
ORG_PRIMARY_COLOR = "#1DB584"

RECAPTCHA_SITE_KEY = os.getenv("RECAPTCHA_SITE_KEY", "")
RECAPTCHA_SECRET_KEY = os.getenv("RECAPTCHA_SECRET_KEY", "")

# LDAP/Active Directory Configuration (PLACEHOLDER - Update in production)
LDAP_ENABLED = os.getenv("LDAP_ENABLED", "False").lower() == "true"
LDAP_DOMAIN = os.getenv("LDAP_DOMAIN", "UNIVERSAL")
LDAP_HOST = os.getenv("LDAP_HOST", "ldap-server.company.local")  # PLACEHOLDER
LDAP_PORT = int(os.getenv("LDAP_PORT", 389))
LDAP_BASE_DN = os.getenv("LDAP_BASE_DN", "OU=Employees,DC=company,DC=local")  # PLACEHOLDER
LDAP_USE_SSL = os.getenv("LDAP_USE_SSL", "False").lower() == "true"
LDAP_USE_TLS = os.getenv("LDAP_USE_TLS", "False").lower() == "true"
LDAP_TIMEOUT = int(os.getenv("LDAP_TIMEOUT", 10))

# Permitted Users Whitelist (PLACEHOLDER - Update in production)
# Format: EMPLOYEE_ID:NAME:ROLE:PERMISSIONS;EMPLOYEE_ID:NAME:ROLE:PERMISSIONS
# Example: 00058215:Nadir:hr:read,write,admin;00037099:Saltanat:hr:read,write,admin
PERMITTED_USERS_ENV = os.getenv("PERMITTED_USERS", "00061221:Danial Aibassov:hr:read,write,admin")

# JWT Secret Key (PLACEHOLDER - MUST change in production!)
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "PLACEHOLDER-SECRET-KEY-CHANGE-IN-PRODUCTION-MIN-32-CHARS")