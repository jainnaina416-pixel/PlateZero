import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "QR_attendance", "platezero.db")
AUTH_DB_PATH = os.path.join(BASE_DIR, "QR_attendance", "auth.db")

# Ensure the directories exist
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

def get_db_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def get_auth_conn():
    return sqlite3.connect(AUTH_DB_PATH, check_same_thread=False)

def init_db():
    conn = get_db_conn()
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT,
        meal_id TEXT,
        timestamp TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS student_stats (
        student_id TEXT PRIMARY KEY,
        eco_points INTEGER DEFAULT 0,
        streak INTEGER DEFAULT 0,
        clean_meals INTEGER DEFAULT 0,
        last_meal_date TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS active_qrs (
        meal_id TEXT PRIMARY KEY,
        meal_type TEXT,
        created_at TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS plate_snaps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT,
        meal_type TEXT,
        is_clean BOOLEAN,
        timestamp TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS rewards_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT,
        reward_name TEXT,
        cost INTEGER,
        timestamp TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS wellness_metrics (
        student_id TEXT PRIMARY KEY,
        hydration INTEGER DEFAULT 0,
        mood TEXT DEFAULT 'neutral',
        eco_pledge TEXT,
        last_updated TEXT
    )
    """)

    conn.commit()
    conn.close()

def init_auth_db():
    conn = get_auth_conn()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        role TEXT,
        hostel TEXT,
        password TEXT
    )
    """)
    conn.commit()
    conn.close()

# Global state
current_meal_id = None
