"""
Database connection pool for V2 (hr_test schema)
Uses tab_number instead of phone for user identification
"""

import asyncio
from contextlib import asynccontextmanager
from psycopg_pool import AsyncConnectionPool
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config_v2 import DATABASE_URL, DB_SCHEMA
import logging

logger = logging.getLogger(__name__)

# Global connection pool
pool = None

async def init_db_pool():
    """Initialize database connection pool with hr_test schema"""
    global pool
    try:
        pool = AsyncConnectionPool(
            conninfo=DATABASE_URL,
            min_size=50,  # Increased from 30
            max_size=300,  # Increased from 150 (for 2000 users)
            timeout=30,
            max_waiting=400,  # Increased from 200
            kwargs={
                "autocommit": True,
                "options": f"-c search_path={DB_SCHEMA},public"  # Use hr_test schema
            }
        )
        await pool.open()
        logger.info(f"✅ Database pool initialized (schema: {DB_SCHEMA})")
        print(f"✅ Database pool initialized (schema: {DB_SCHEMA})")
    except Exception as e:
        logger.error(f"❌ Failed to initialize database pool: {e}")
        raise

async def close_db_pool():
    """Close database connection pool"""
    global pool
    if pool:
        await pool.close()
        logger.info("Database pool closed")
        print("✅ Database pool closed")

@asynccontextmanager
async def get_db_connection():
    """Get database connection from pool"""
    global pool
    if not pool:
        raise Exception("Database pool not initialized")

    async with pool.connection() as conn:
        yield conn

async def execute_query(query: str, params: tuple = None):
    """Execute query and return results"""
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params or ())
            try:
                return await cur.fetchall()
            except:
                return None

async def execute_one(query: str, params: tuple = None):
    """Execute query and return one result"""
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params or ())
            try:
                return await cur.fetchone()
            except:
                return None
