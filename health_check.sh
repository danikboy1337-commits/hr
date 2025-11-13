#!/bin/bash

#############################################################################
# Health Check Script for HR Testing Platform
#
# This script monitors the health of the application and can be used
# for automated monitoring or alerting.
#
# Usage:
#   ./health_check.sh
#
# Scheduling with cron (check every 5 minutes):
#   sudo crontab -e
#   Add line: */5 * * * * /opt/hr_testing/health_check.sh
#
# Exit codes:
#   0 - Health check passed
#   1 - Health check failed
#
# Author: Development Team
# Version: 1.0
#############################################################################

# Configuration
APP_URL="http://localhost:8000/health"
EXPECTED_RESPONSE="healthy"
LOG_FILE="/var/log/hr_testing/health_check.log"
MAX_RESPONSE_TIME=5  # seconds

# Service management (optional - uncomment to auto-restart on failure)
AUTO_RESTART=false
SERVICE_NAME="hr-testing.service"

# Alert configuration (optional - configure email alerts)
ENABLE_EMAIL_ALERTS=false
ALERT_EMAIL="admin@company.local"

# Consecutive failures before taking action
FAILURE_THRESHOLD=3
FAILURE_COUNT_FILE="/home/ocds_mukhtar/00061221/hr_testing_health_failures"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Functions
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

log_console() {
    echo -e "$1"
}

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

# Initialize failure counter if it doesn't exist
if [ ! -f "$FAILURE_COUNT_FILE" ]; then
    echo "0" > "$FAILURE_COUNT_FILE"
fi

# Perform health check with timeout
log "Performing health check..."
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}:%{time_total}" --max-time $MAX_RESPONSE_TIME "$APP_URL" 2>&1)
HTTP_CODE=$(echo "$RESPONSE" | cut -d':' -f1)
RESPONSE_TIME=$(echo "$RESPONSE" | cut -d':' -f2)

# Check if curl succeeded
if [ -z "$HTTP_CODE" ] || [ "$HTTP_CODE" == "000" ]; then
    log_console "${RED}❌ Health check FAILED: Cannot connect to application${NC}"
    log "FAILED: Cannot connect to $APP_URL"
    log "Possible causes: Application not running, port not listening, firewall blocking"

    # Increment failure counter
    FAILURES=$(cat "$FAILURE_COUNT_FILE")
    FAILURES=$((FAILURES + 1))
    echo "$FAILURES" > "$FAILURE_COUNT_FILE"

    log "Consecutive failures: $FAILURES"

    # Check if we've reached failure threshold
    if [ $FAILURES -ge $FAILURE_THRESHOLD ]; then
        log "CRITICAL: Failure threshold reached ($FAILURE_THRESHOLD consecutive failures)"

        # Auto-restart if enabled
        if [ "$AUTO_RESTART" = true ]; then
            log "Attempting to restart service: $SERVICE_NAME"
            systemctl restart "$SERVICE_NAME"

            if [ $? -eq 0 ]; then
                log "Service restarted successfully"
                log_console "${YELLOW}⚠️  Service was automatically restarted${NC}"

                # Send email alert if enabled
                if [ "$ENABLE_EMAIL_ALERTS" = true ]; then
                    echo "HR Testing Platform was automatically restarted at $(date)" | \
                        mail -s "ALERT: HR Testing Platform Restarted" "$ALERT_EMAIL"
                fi
            else
                log "ERROR: Failed to restart service"
                log_console "${RED}❌ Failed to restart service${NC}"
            fi

            # Reset counter after restart attempt
            echo "0" > "$FAILURE_COUNT_FILE"
        else
            log_console "${RED}❌ CRITICAL: $FAILURES consecutive failures (auto-restart disabled)${NC}"

            # Send email alert if enabled
            if [ "$ENABLE_EMAIL_ALERTS" = true ]; then
                echo "HR Testing Platform has failed health checks $FAILURES times at $(date)" | \
                    mail -s "CRITICAL: HR Testing Platform Health Check Failed" "$ALERT_EMAIL"
            fi
        fi
    fi

    exit 1
elif [ "$HTTP_CODE" == "200" ]; then
    # Convert response time to milliseconds for better readability
    RESPONSE_MS=$(echo "$RESPONSE_TIME * 1000" | bc | cut -d'.' -f1)

    log_console "${GREEN}✅ Health check PASSED (HTTP $HTTP_CODE, ${RESPONSE_MS}ms)${NC}"
    log "SUCCESS: HTTP $HTTP_CODE, Response time: ${RESPONSE_MS}ms"

    # Check response time warning
    if (( $(echo "$RESPONSE_TIME > 1.0" | bc -l) )); then
        log_console "${YELLOW}⚠️  WARNING: Slow response time (${RESPONSE_MS}ms)${NC}"
        log "WARNING: Slow response time: ${RESPONSE_MS}ms"
    fi

    # Reset failure counter on success
    echo "0" > "$FAILURE_COUNT_FILE"

    exit 0
else
    log_console "${RED}❌ Health check FAILED (HTTP $HTTP_CODE)${NC}"
    log "FAILED: HTTP $HTTP_CODE, Response time: ${RESPONSE_TIME}s"

    # Increment failure counter
    FAILURES=$(cat "$FAILURE_COUNT_FILE")
    FAILURES=$((FAILURES + 1))
    echo "$FAILURES" > "$FAILURE_COUNT_FILE"

    log "Consecutive failures: $FAILURES"

    exit 1
fi
