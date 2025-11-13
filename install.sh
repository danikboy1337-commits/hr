#!/bin/bash

#############################################################################
# HR Testing Platform - Automated Installation Script
# For Ubuntu Server 20.04+ / 22.04+
#
# This script automates the installation and configuration of the
# HR Testing Platform on a local company server.
#
# Usage:
#   sudo ./install.sh
#
# What it does:
#   1. Installs system dependencies (Python 3.11, PostgreSQL client, etc.)
#   2. Creates application user and directories
#   3. Sets up Python virtual environment
#   4. Installs Python dependencies
#   5. Creates configuration templates
#   6. Initializes database (if configured)
#   7. Sets up systemd service
#
# Prerequisites:
#   - Ubuntu Server 20.04+ or 22.04+
#   - Root/sudo access
#   - Internet connection (for package installation)
#   - PostgreSQL database server accessible
#   - LDAP server details from IT department
#
# Author: Development Team
# Version: 1.0
# Date: 2025-01-11
#############################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
APP_USER="ocds_mukhtar"
APP_DIR="/home/ocds_mukhtar/00061221/hr_testing"
LOG_DIR="/home/ocds_mukhtar/00061221/hr_testing/logs"
BACKUP_DIR="/home/ocds_mukhtar/00061221/hr_testing/backup"
PYTHON_VERSION="3.11"

# Functions
print_header() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

check_root() {
    if [ "$EUID" -ne 0 ]; then
        print_error "This script must be run as root or with sudo"
        echo "Usage: sudo ./install.sh"
        exit 1
    fi
}

check_ubuntu() {
    if [ ! -f /etc/os-release ]; then
        print_error "Cannot detect OS version"
        exit 1
    fi

    . /etc/os-release
    if [[ "$ID" != "ubuntu" ]]; then
        print_warning "This script is designed for Ubuntu. Detected: $ID"
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi

    print_success "OS detected: Ubuntu $VERSION"
}

install_system_packages() {
    print_header "Installing System Packages"

    print_info "Updating package list..."
    apt update

    print_info "Installing Python $PYTHON_VERSION..."
    # Check if Python 3.11 is available
    if ! apt-cache show python${PYTHON_VERSION} > /dev/null 2>&1; then
        print_warning "Python ${PYTHON_VERSION} not in default repos, adding deadsnakes PPA..."
        apt install -y software-properties-common
        add-apt-repository -y ppa:deadsnakes/ppa
        apt update
    fi

    apt install -y \
        python${PYTHON_VERSION} \
        python${PYTHON_VERSION}-venv \
        python${PYTHON_VERSION}-dev \
        python3-pip \
        postgresql-client \
        libpq-dev \
        libldap2-dev \
        libsasl2-dev \
        build-essential \
        git \
        curl \
        nano \
        net-tools

    print_success "System packages installed"
}

create_app_user() {
    print_header "Creating Application User"

    if id "$APP_USER" &>/dev/null; then
        print_warning "User $APP_USER already exists, skipping creation"
    else
        useradd -m -s /bin/bash $APP_USER
        print_success "Created user: $APP_USER"
    fi
}

create_directories() {
    print_header "Creating Application Directories"

    # Application directory
    if [ ! -d "$APP_DIR" ]; then
        mkdir -p $APP_DIR
        print_success "Created directory: $APP_DIR"
    else
        print_warning "Directory already exists: $APP_DIR"
    fi

    # Log directory
    if [ ! -d "$LOG_DIR" ]; then
        mkdir -p $LOG_DIR
        print_success "Created directory: $LOG_DIR"
    else
        print_warning "Directory already exists: $LOG_DIR"
    fi

    # Backup directory
    if [ ! -d "$BACKUP_DIR" ]; then
        mkdir -p $BACKUP_DIR
        print_success "Created directory: $BACKUP_DIR"
    else
        print_warning "Directory already exists: $BACKUP_DIR"
    fi

    # Set ownership
    chown -R $APP_USER:$APP_USER $APP_DIR
    chown -R $APP_USER:$APP_USER $LOG_DIR
    chown -R $APP_USER:$APP_USER $BACKUP_DIR

    print_success "Directory ownership set to $APP_USER"
}

setup_application() {
    print_header "Setting Up Application Files"

    # Check if we're already in the application directory
    if [ -f "main.py" ] && [ -f "requirements.txt" ]; then
        print_info "Application files detected in current directory"
        print_info "Copying files to $APP_DIR..."

        # Copy all files except .git
        rsync -a --exclude='.git' --exclude='venv' --exclude='__pycache__' --exclude='*.pyc' ./ $APP_DIR/

        chown -R $APP_USER:$APP_USER $APP_DIR
        print_success "Application files copied to $APP_DIR"
    else
        print_warning "Application files not found in current directory"
        print_info "Please copy application files to $APP_DIR manually"
        print_info "Or run this script from the application directory"

        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

setup_python_env() {
    print_header "Setting Up Python Virtual Environment"

    cd $APP_DIR

    if [ -d "venv" ]; then
        print_warning "Virtual environment already exists"
        read -p "Recreate? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf venv
        else
            print_info "Skipping virtual environment creation"
            return
        fi
    fi

    print_info "Creating virtual environment..."
    sudo -u $APP_USER python${PYTHON_VERSION} -m venv venv

    print_info "Upgrading pip..."
    sudo -u $APP_USER $APP_DIR/venv/bin/pip install --upgrade pip

    if [ -f "requirements.txt" ]; then
        print_info "Installing Python dependencies..."
        sudo -u $APP_USER $APP_DIR/venv/bin/pip install -r requirements.txt
        print_success "Python dependencies installed"
    else
        print_error "requirements.txt not found!"
        exit 1
    fi
}

create_env_file() {
    print_header "Creating Environment Configuration"

    if [ -f "$APP_DIR/.env" ]; then
        print_warning ".env file already exists"
        read -p "Overwrite? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_info "Skipping .env creation"
            return
        fi
    fi

    if [ ! -f "$APP_DIR/.env.template" ]; then
        print_error ".env.template not found!"
        exit 1
    fi

    cp $APP_DIR/.env.template $APP_DIR/.env
    chown $APP_USER:$APP_USER $APP_DIR/.env
    chmod 600 $APP_DIR/.env

    print_success "Created .env file from template"
    print_warning "IMPORTANT: Edit $APP_DIR/.env with your actual configuration!"
    print_info "Required settings:"
    echo "  - DATABASE_URL (PostgreSQL connection string)"
    echo "  - LDAP settings (LDAP_HOST, LDAP_DOMAIN, LDAP_BASE_DN, etc.)"
    echo "  - PERMITTED_USERS (employee whitelist)"
    echo "  - JWT_SECRET_KEY (generate with: python -c \"import secrets; print(secrets.token_urlsafe(32))\")"
}

setup_systemd_service() {
    print_header "Setting Up systemd Service"

    SERVICE_FILE="/etc/systemd/system/hr-testing.service"

    if [ -f "$SERVICE_FILE" ]; then
        print_warning "Service file already exists"
        read -p "Overwrite? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_info "Skipping service creation"
            return
        fi
    fi

    cat > $SERVICE_FILE <<EOF
[Unit]
Description=HR Testing Platform - Halyk Bank
Documentation=https://github.com/YOUR_ORG/hr_testing
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=notify
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin"

# Load environment variables from .env file
EnvironmentFile=$APP_DIR/.env

# Start application with Gunicorn + Uvicorn workers
ExecStart=$APP_DIR/venv/bin/gunicorn main:app \\
    --workers 4 \\
    --worker-class uvicorn.workers.UvicornWorker \\
    --bind 0.0.0.0:8000 \\
    --timeout 120 \\
    --access-logfile $LOG_DIR/access.log \\
    --error-logfile $LOG_DIR/error.log \\
    --log-level info

# Restart policy
Restart=always
RestartSec=10

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$APP_DIR $LOG_DIR

# Resource limits
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF

    print_success "Created systemd service file"

    systemctl daemon-reload
    print_success "Reloaded systemd daemon"

    systemctl enable hr-testing.service
    print_success "Enabled hr-testing service (will start on boot)"
}

setup_logrotate() {
    print_header "Setting Up Log Rotation"

    LOGROTATE_FILE="/etc/logrotate.d/hr-testing"

    cat > $LOGROTATE_FILE <<EOF
$LOG_DIR/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 $APP_USER $APP_USER
    sharedscripts
    postrotate
        systemctl reload hr-testing.service > /dev/null 2>&1 || true
    endscript
}

$APP_DIR/login_history.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 0640 $APP_USER $APP_USER
    maxsize 10M
}
EOF

    print_success "Created log rotation configuration"
}

test_configuration() {
    print_header "Testing Configuration"

    # Test Python
    print_info "Testing Python..."
    if $APP_DIR/venv/bin/python --version > /dev/null 2>&1; then
        print_success "Python: OK"
    else
        print_error "Python: FAILED"
    fi

    # Test imports
    print_info "Testing Python imports..."
    if $APP_DIR/venv/bin/python -c "import fastapi, psycopg, ldap3" 2>/dev/null; then
        print_success "Python dependencies: OK"
    else
        print_error "Python dependencies: FAILED"
    fi

    # Test .env file
    print_info "Testing .env file..."
    if [ -f "$APP_DIR/.env" ]; then
        print_success ".env file: EXISTS"

        # Check if it's been configured
        if grep -q "PLACEHOLDER" $APP_DIR/.env; then
            print_warning ".env file contains PLACEHOLDER values - needs configuration!"
        else
            print_success ".env file: CONFIGURED"
        fi
    else
        print_error ".env file: MISSING"
    fi
}

generate_jwt_secret() {
    print_header "JWT Secret Key Generation"

    print_info "Generating cryptographically secure JWT secret key..."
    JWT_SECRET=$($APP_DIR/venv/bin/python -c "import secrets; print(secrets.token_urlsafe(32))")

    echo ""
    print_success "Generated JWT Secret Key:"
    echo ""
    echo -e "${GREEN}$JWT_SECRET${NC}"
    echo ""
    print_info "Add this to your .env file as JWT_SECRET_KEY"
    echo ""
}

print_next_steps() {
    print_header "Installation Complete!"

    echo ""
    print_success "The HR Testing Platform has been installed successfully!"
    echo ""

    print_info "NEXT STEPS:"
    echo ""
    echo "1️⃣  Configure the application:"
    echo "   sudo nano $APP_DIR/.env"
    echo ""
    echo "   Update the following:"
    echo "   - DATABASE_URL (PostgreSQL connection)"
    echo "   - LDAP_ENABLED=True"
    echo "   - LDAP_HOST, LDAP_DOMAIN, LDAP_BASE_DN"
    echo "   - PERMITTED_USERS (employee whitelist from HR)"
    echo "   - JWT_SECRET_KEY (use generated key above)"
    echo ""

    echo "2️⃣  Initialize the database:"
    echo "   sudo -u $APP_USER -i"
    echo "   cd $APP_DIR"
    echo "   source venv/bin/activate"
    echo "   python db/create_tables.py"
    echo "   python db/run_migration.py db/migration_add_roles_departments.sql"
    echo "   python db/run_migration.py db/migrations/add_test_time_limit.sql"
    echo "   python db/run_migration.py db/migrations/update_manager_evaluations_competency_based.sql"
    echo "   python db/load_questions.py"
    echo "   python db/import_specializations.py"
    echo ""

    echo "3️⃣  Test LDAP connection:"
    echo "   sudo -u $APP_USER -i"
    echo "   cd $APP_DIR"
    echo "   source venv/bin/activate"
    echo "   python test_ldap_connection.py"
    echo ""

    echo "4️⃣  Start the service:"
    echo "   sudo systemctl start hr-testing.service"
    echo "   sudo systemctl status hr-testing.service"
    echo ""

    echo "5️⃣  Access the application:"
    echo "   http://YOUR_SERVER_IP:8000/login"
    echo ""

    echo "6️⃣  Monitor logs:"
    echo "   sudo journalctl -u hr-testing.service -f"
    echo "   sudo tail -f $LOG_DIR/error.log"
    echo "   sudo tail -f $APP_DIR/login_history.log"
    echo ""

    print_info "For detailed instructions, see: $APP_DIR/MIGRATION_GUIDE.md"
    echo ""
}

# Main installation flow
main() {
    clear

    print_header "HR Testing Platform - Automated Installation"

    echo "This script will install and configure the HR Testing Platform"
    echo "on this Ubuntu server."
    echo ""
    echo "Installation location: $APP_DIR"
    echo "Application user: $APP_USER"
    echo "Python version: $PYTHON_VERSION"
    echo ""

    read -p "Continue with installation? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "Installation cancelled"
        exit 0
    fi

    check_root
    check_ubuntu

    install_system_packages
    create_app_user
    create_directories
    setup_application
    setup_python_env
    create_env_file
    setup_systemd_service
    setup_logrotate
    generate_jwt_secret
    test_configuration

    print_next_steps
}

# Run main function
main
