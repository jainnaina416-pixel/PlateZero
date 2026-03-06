from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime

import sqlite3
import uuid
import os
import bcrypt
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# DATABASE
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "platezero.db")

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS attendance (
id INTEGER PRIMARY KEY AUTOINCREMENT,
student_id TEXT,
meal_id TEXT,
timestamp TEXT
)
""")

conn.commit()

print("Using database:", DB_PATH)

# AUTH DB
AUTH_DB_PATH = os.path.join(BASE_DIR, "auth.db")
auth_conn = sqlite3.connect(AUTH_DB_PATH, check_same_thread=False)
auth_cursor = auth_conn.cursor()

auth_cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
id INTEGER PRIMARY KEY AUTOINCREMENT,
name TEXT,
email TEXT UNIQUE,
role TEXT,
hostel TEXT,
password TEXT
)
""")
auth_conn.commit()
print("Using auth database:", AUTH_DB_PATH)

current_meal_id = None


class ScanData(BaseModel):
    student_id: str
    meal_id: str

class UserRegister(BaseModel):
    name: str
    email: str
    role: str
    hostel: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

@app.post("/register")
def register(user: UserRegister):
    auth_cursor.execute("SELECT * FROM users WHERE email=?", (user.email,))
    if auth_cursor.fetchone():
        return {"status": "error", "message": "Email already registered"}
    
    hashed_password = bcrypt.hashpw(user.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    auth_cursor.execute(
        "INSERT INTO users (name, email, role, hostel, password) VALUES (?, ?, ?, ?, ?)",
        (user.name, user.email, user.role, user.hostel, hashed_password)
    )
    auth_conn.commit()
    return {"status": "success", "message": "User registered successfully"}

@app.post("/login")
def login(user: UserLogin):
    auth_cursor.execute("SELECT * FROM users WHERE email=?", (user.email,))
    db_user = auth_cursor.fetchone()
    if not db_user:
        return {"status": "error", "message": "Invalid credentials"}
    
    user_id, name, email, role, hostel, hashed_password = db_user
    
    if bcrypt.checkpw(user.password.encode('utf-8'), hashed_password.encode('utf-8')):
        return {
            "status": "success", 
            "user": {
                "id": str(user_id),
                "name": name,
                "email": email,
                "role": role,
                "hostel": hostel
            }
        }
    else:
        return {"status": "error", "message": "Invalid credentials"}


# GENERATE QR
@app.get("/generate_qr/{meal_type}")
def generate_qr(meal_type: str):

    global current_meal_id

    current_meal_id = f"{meal_type}_{uuid.uuid4().hex[:6]}"

    print("QR session:", current_meal_id)

    return {
        "meal_id": current_meal_id,
        "qr_data": current_meal_id
    }


# SCAN QR
@app.post("/scan_qr")
def scan_qr(data: ScanData):

    print("Scan:", data.student_id, data.meal_id)

    cursor.execute(
        "SELECT * FROM attendance WHERE student_id=? AND meal_id=?",
        (data.student_id, data.meal_id)
    )

    if cursor.fetchone():
        return {"status": "already_scanned"}

    cursor.execute(
        "INSERT INTO attendance(student_id,meal_id,timestamp) VALUES (?,?,?)",
        (data.student_id, data.meal_id, str(datetime.now()))
    )

    conn.commit()

    return {"status": "scan_recorded"}


# ATTENDANCE
@app.get("/attendance/{meal_id}")
def attendance(meal_id: str):

    cursor.execute(
        "SELECT COUNT(*) FROM attendance WHERE meal_id=?",
        (meal_id,)
    )

    count = cursor.fetchone()[0]

    return {"attendance": count}


# DEBUG
@app.get("/all_scans")
def all_scans():

    cursor.execute("SELECT * FROM attendance")

    rows = cursor.fetchall()

    return {"records": rows}