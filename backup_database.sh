#!/bin/bash

#############################################################################
# Database Backup Script for HR Testing Platform
#
# This script creates a compressed backup of the PostgreSQL database.
#
# Usage:
#   ./backup_database.sh
#
# Scheduling with cron (daily at 2 AM):
#   sudo crontab -e -u hrapp
#   Add line: 0 2 * * * /opt/hr_testing/backup_database.sh
#
# Configuration:
#   Edit the variables below to match your environment
#
# Author: Development Team
# Version: 1.0
#############################################################################

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration - EDIT THESE VALUES
DB_HOST="localhost"              # PostgreSQL server IP or hostname
DB_PORT="5432"                   # PostgreSQL port
DB_NAME="hr_testing"             # Database name
DB_USER="hrapp"                  # Database user
DB_PASSWORD=""                   # Database password (leave empty to use .pgpass)

# Backup configuration
BACKUP_DIR="/home/ocds_mukhtar/00061221/backups"  # Backup directory
RETENTION_DAYS=30                # Keep backups for 30 days
LOG_FILE="/var/log/hr_testing/backup.log"

# Generate timestamp
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/hr_testing_$DATE.sql"

# Functions
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}" | tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] SUCCESS: $1${NC}" | tee -a "$LOG_FILE"
}

log_info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] INFO: $1${NC}" | tee -a "$LOG_FILE"
}

# Create backup directory if it doesn't exist
if [ ! -d "$BACKUP_DIR" ]; then
    mkdir -p "$BACKUP_DIR"
    if [ $? -eq 0 ]; then
        log_info "Created backup directory: $BACKUP_DIR"
    else
        log_error "Failed to create backup directory: $BACKUP_DIR"
        exit 1
    fi
fi

# Start backup
log_info "Starting database backup..."
log_info "Database: $DB_NAME on $DB_HOST:$DB_PORT"
log_info "Backup file: $BACKUP_FILE"

# Perform backup
if [ -n "$DB_PASSWORD" ]; then
    # Use password from variable
    PGPASSWORD="$DB_PASSWORD" pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME" > "$BACKUP_FILE"
else
    # Use .pgpass or prompt for password
    pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME" > "$BACKUP_FILE"
fi

# Check if backup succeeded
if [ $? -eq 0 ] && [ -f "$BACKUP_FILE" ]; then
    # Get backup size
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    log_success "Database dump completed successfully ($BACKUP_SIZE)"

    # Compress backup
    log_info "Compressing backup..."
    gzip "$BACKUP_FILE"

    if [ $? -eq 0 ]; then
        COMPRESSED_SIZE=$(du -h "${BACKUP_FILE}.gz" | cut -f1)
        log_success "Backup compressed successfully ($COMPRESSED_SIZE)"
        log_success "Backup file: ${BACKUP_FILE}.gz"

        # Delete old backups
        log_info "Cleaning up old backups (older than $RETENTION_DAYS days)..."
        DELETED_COUNT=$(find "$BACKUP_DIR" -name "hr_testing_*.sql.gz" -mtime +$RETENTION_DAYS -delete -print | wc -l)

        if [ $DELETED_COUNT -gt 0 ]; then
            log_info "Deleted $DELETED_COUNT old backup(s)"
        else
            log_info "No old backups to delete"
        fi

        # List current backups
        BACKUP_COUNT=$(find "$BACKUP_DIR" -name "hr_testing_*.sql.gz" | wc -l)
        TOTAL_SIZE=$(du -sh "$BACKUP_DIR" | cut -f1)
        log_info "Total backups: $BACKUP_COUNT (Total size: $TOTAL_SIZE)"

        log_success "Backup completed successfully!"
        exit 0
    else
        log_error "Backup compression failed!"
        exit 1
    fi
else
    log_error "Database dump failed!"
    log_error "Check database connection settings and credentials"

    # Remove empty or partial backup file
    if [ -f "$BACKUP_FILE" ]; then
        rm -f "$BACKUP_FILE"
        log_info "Removed partial backup file"
    fi

    exit 1
fi
