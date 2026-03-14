from fastapi import FastAPI, File, UploadFile
from pydantic import BaseModel
from datetime import datetime

import sqlite3
import uuid
import os
import sys
import bcrypt
import tempfile
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

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

# Setup path for vision_ai + fraud_detection imports
PARENT_DIR = os.path.dirname(BASE_DIR)
if PARENT_DIR not in sys.path:
    sys.path.append(PARENT_DIR)

from vision_ai.predict import predict_image
from fraud_detection import (
    init_hash_db,
    check_time,
    check_location,
    check_duplicate_or_similar,
)

# Initialise the image-hash fraud DB on startup
init_hash_db()

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


# NEW INDIVIDUAL STUDENT API

@app.get("/student/{student_id}")
def get_student_stats(student_id: str):
    cursor.execute("SELECT eco_points, streak, clean_meals FROM student_stats WHERE student_id=?", (student_id,))
    row = cursor.fetchone()
    
    if not row:
        # Initialize student stats if they don't exist yet
        cursor.execute("INSERT INTO student_stats (student_id) VALUES (?)", (student_id,))
        conn.commit()
        eco_points, streak, clean_meals = 0, 0, 0
    else:
        eco_points, streak, clean_meals = row

    # Calculate rank based on eco_points (Count how many have more points + 1)
    cursor.execute("SELECT COUNT(*) FROM student_stats WHERE eco_points > ?", (eco_points,))
    rank = cursor.fetchone()[0] + 1

    return {
        "eco_points": eco_points,
        "streak": streak,
        "clean_meals": clean_meals,
        "rank": rank
    }

from fastapi import Form

@app.post("/snap_plate")
async def snap_plate(
    student_id: str = Form("demo"),
    meal: str      = Form("meal"),
    lat: Optional[float] = Form(None),
    lon: Optional[float] = Form(None),
    image: UploadFile = File(...)
):
    try:
        # ── 1. MEAL-TIME CHECK ────────────────────────────────────────────────
        if not check_time(meal):
            return {
                "status": "fraud",
                "clean": False,
                "reason": f"Outside {meal} time window. Snaps only accepted during meal hours."
            }

        # ── 2. LOCATION CHECK (only if GPS was provided) ──────────────────────
        if lat is not None and lon is not None:
            if not check_location(lat, lon):
                return {
                    "status": "fraud",
                    "clean": False,
                    "reason": "You appear to be outside the dining hall. Please snap from the mess."
                }

        # ── 3. SAVE UPLOAD TO TEMP FILE ───────────────────────────────────────
        temp_dir  = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, f"snap_{uuid.uuid4().hex}.jpg")
        img_bytes = await image.read()

        if not img_bytes:
            return {"status": "error", "clean": False, "reason": "Empty image received. Please try again."}

        with open(temp_path, "wb") as f:
            f.write(img_bytes)

        # ── 4. DUPLICATE / CROSS-ACCOUNT SIMILARITY CHECK ────────────────────
        try:
            fraud_result = check_duplicate_or_similar(temp_path, student_id, meal)
        except Exception as e:
            fraud_result = {"ok": True}  # If hash DB fails, don't block the upload

        if not fraud_result["ok"]:
            try:
                os.remove(temp_path)
            except Exception:
                pass
            return {
                "status": "fraud",
                "clean": False,
                "reason": fraud_result["reason"]
            }

        # ── 5. AI PLATE VERIFICATION ──────────────────────────────────────────
        try:
            result = predict_image(temp_path)
        except Exception as e:
            result = {"error": str(e)}

        try:
            os.remove(temp_path)
        except Exception:
            pass

        is_clean = False
        status   = "failed"
        prediction_label = "unknown"

        if "error" in result:
            # AI model unavailable — fail gracefully instead of crashing
            return {
                "status": "error",
                "clean": False,
                "reason": f"AI model unavailable: {result['error']}. Please contact admin."
            }

        if "prediction" in result:
            prediction_label = result["prediction"]
            if prediction_label.lower() == "clean":
                is_clean = True
            status = "success" if is_clean else "failed"

        # ── 6. LOG SNAP & UPDATE STATS ────────────────────────────────────────
        now_str = str(datetime.now())
        cursor.execute(
            "INSERT INTO plate_snaps (student_id, meal_type, is_clean, timestamp) VALUES (?, ?, ?, ?)",
            (student_id, meal, is_clean, now_str)
        )

        if is_clean:
            cursor.execute(
                "SELECT eco_points, streak, clean_meals FROM student_stats WHERE student_id=?",
                (student_id,)
            )
            row = cursor.fetchone()
            if row:
                eco_points, streak, clean_meals = row
                cursor.execute(
                    "UPDATE student_stats SET eco_points=?, streak=?, clean_meals=?, last_meal_date=? WHERE student_id=?",
                    (eco_points + 30, streak + 1, clean_meals + 1, now_str, student_id)
                )
            else:
                cursor.execute(
                    "INSERT INTO student_stats (student_id, eco_points, streak, clean_meals, last_meal_date) VALUES (?, ?, ?, ?, ?)",
                    (student_id, 30, 1, 1, now_str)
                )

        conn.commit()  # Always commit — was missing for non-clean snaps

        return {
            "status": status,
            "clean": is_clean,
            "prediction": prediction_label
        }

    except Exception as e:
        # Catch-all: return a proper JSON error instead of a 500 crash
        return {
            "status": "error",
            "clean": False,
            "reason": f"Server error: {str(e)}"
        }


@app.get("/api/leaderboard")
def get_leaderboard():
    # Join student_stats with auth.users to get names
    # Note: Using auth_cursor for reading from auth.db
    auth_cursor.execute("SELECT id, name FROM users")
    users = {str(row[0]): row[1] for row in auth_cursor.fetchall()}
    
    cursor.execute("SELECT student_id, eco_points FROM student_stats ORDER BY eco_points DESC LIMIT 10")
    rows = cursor.fetchall()
    
    leaderboard = []
    for idx, (sid, pts) in enumerate(rows):
        leaderboard.append({
            "rank": idx + 1,
            "name": users.get(sid, f"Student {sid}"),
            "points": pts,
            "id": sid
        })
    return leaderboard

@app.get("/student/{student_id}/history")
def get_student_history(student_id: str):
    cursor.execute("SELECT is_clean, timestamp FROM plate_snaps WHERE student_id=? ORDER BY timestamp ASC", (student_id,))
    rows = cursor.fetchall()
    # Format: { "2024-03-12": "clean", ... }
    history = {}
    for is_clean, ts in rows:
        date_str = ts.split(' ')[0]
        history[date_str] = "clean" if is_clean else "partial"
    return history

@app.get("/student/{student_id}/impact")
def get_student_impact(student_id: str):
    # Filter to last 7 days so the "Weekly Impact" card is accurate
    cursor.execute(
        "SELECT COUNT(*) FROM plate_snaps WHERE student_id=? AND is_clean=1 AND timestamp >= datetime('now', '-7 days')",
        (student_id,)
    )
    clean_count = cursor.fetchone()[0]
    
    waste_saved = round(clean_count * 0.1, 1) # 0.1kg per plate
    savings = clean_count * 15 # ₹15 saved per plate
    water_saved = round(clean_count * 0.2, 1) # 0.2L water saved per plate
    co2_reduced = round(clean_count * 0.05, 2) # 0.05kg CO2
    
    return {
        "waste_prevented": f"{waste_saved}kg",
        "mess_savings": f"₹{savings}",
        "water_saved": f"{water_saved}L",
        "co2_reduced": f"{co2_reduced}kg"
    }

class RedeemRequest(BaseModel):
    student_id: str
    reward: str
    cost: int

@app.post("/redeem")
def redeem_reward(req: RedeemRequest):
    cursor.execute("SELECT eco_points FROM student_stats WHERE student_id=?", (req.student_id,))
    row = cursor.fetchone()
    
    if not row or row[0] < req.cost:
        return {"status": "error", "message": "Not enough EcoPoints"}
    
    # Deduct points
    new_points = row[0] - req.cost
    cursor.execute("UPDATE student_stats SET eco_points=? WHERE student_id=?", (new_points, req.student_id))
    
    # Log reward
    cursor.execute(
        "INSERT INTO rewards_history (student_id, reward_name, cost, timestamp) VALUES (?, ?, ?, ?)",
        (req.student_id, req.reward, req.cost, str(datetime.now()))
    )
    conn.commit()
    
    return {"status": "success", "new_points": new_points}


# ADMIN DASHBOARD API
@app.get("/api/admin/dashboard_data")
def dashboard_data():
    cursor.execute("SELECT COUNT(*) FROM attendance WHERE date(timestamp) = date('now')")
    today_attend = cursor.fetchone()[0]
    
    # Calculate Waste Metrics based on plate snaps
    cursor.execute("SELECT COUNT(*) FROM plate_snaps WHERE is_clean=1 AND date(timestamp) = date('now')")
    clean_plates_today = cursor.fetchone()[0]
    
    # Basic simulated logic: each clean plate saves roughly 0.1 kg of waste
    waste_reduced_kg = round(clean_plates_today * 0.1, 1)
    savings = clean_plates_today * 15 # Simulated 15 rupees saved per clean plate
    
    # Calculate last 7 days chart data
    chart_data = {"breakfast": [], "lunch": [], "dinner": []}
    
    for i in range(6, -1, -1):
        target_date = f"date('now', '-{i} days')"
        
        for meal in ["breakfast", "lunch", "dinner"]:
            cursor.execute(f"SELECT COUNT(*) FROM attendance WHERE date(timestamp) = {target_date} AND meal_id LIKE ?", (f"{meal}%",))
            count = cursor.fetchone()[0]
            chart_data[meal].append(count)

    # Waste Distribution (Simulated based on historical data context, adjusting slightly based on attendance)
    # Since we don't have a physical waste bin scale integrated yet, we keep this partially mock but dynamic
    base_waste = today_attend * 8 # assume 8g waste per person average
    
    return {
        "kpis": {
            "waste_reduced": f"{waste_reduced_kg} kg",
            "attendance": today_attend,
            "savings": f"₹{savings}",
            "high_waste_alerts": max(0, 18 - clean_plates_today) # simulated alert count dropping as clean plates rise
        },
        "chartData": chart_data,
        "wasteDistribution": {
            "total": base_waste,
            "unit": "grams",
            "categories": [
                {"name": "Rice", "percentage": 35, "color": "var(--green)", "stroke": "#1db954"},
                {"name": "Dal", "percentage": 25, "color": "var(--amber)", "stroke": "#ff9500"},
                {"name": "Roti", "percentage": 22, "color": "var(--blue)", "stroke": "#4d9fff"},
                {"name": "Other", "percentage": 18, "color": "var(--purple)", "stroke": "#a855f7"}
            ]
        },
        "alerts": [
            {
                "id": 1,
                "type": "danger",
                "icon": "🚨",
                "title": f"Low Engagement Today",
                "desc": f"Only {clean_plates_today} clean plates snapped out of {today_attend} attendees",
                "time": "Just now"
            } if clean_plates_today < today_attend * 0.3 else {
                "id": 1,
                "type": "success",
                "icon": "🌟",
                "title": "Great Engagement!",
                "desc": f"High number of clean plates today ({clean_plates_today})",
                "time": "Just now"
            },
            {
                "id": 2,
                "type": "warning",
                "icon": "⚠️",
                "title": "Paneer curry wasted",
                "desc": "Prep -15% for next similar meal",
                "time": "14m ago"
            },
            {
                "id": 3,
                "type": "info",
                "icon": "💡",
                "title": "Smart Insight",
                "desc": "Opt for fruit cup additions for balanced plates",
                "time": "1h ago"
            }
        ]
    }

class WellnessUpdate(BaseModel):
    student_id: str
    hydration: int = None
    mood: str = None
    eco_pledge: str = None

@app.get("/student/{student_id}/wellness")
def get_wellness(student_id: str):
    cursor.execute("SELECT hydration, mood, eco_pledge FROM wellness_metrics WHERE student_id=?", (student_id,))
    row = cursor.fetchone()
    if not row:
        return {"hydration": 0, "mood": "neutral", "eco_pledge": ""}
    return {"hydration": row[0], "mood": row[1], "eco_pledge": row[2]}

@app.post("/student/wellness")
def update_wellness(req: WellnessUpdate):
    now_str = str(datetime.now())
    cursor.execute("SELECT 1 FROM wellness_metrics WHERE student_id=?", (req.student_id,))
    exists = cursor.fetchone()
    
    if exists:
        if req.hydration is not None:
            cursor.execute("UPDATE wellness_metrics SET hydration=?, last_updated=? WHERE student_id=?", (req.hydration, now_str, req.student_id))
        if req.mood is not None:
            cursor.execute("UPDATE wellness_metrics SET mood=?, last_updated=? WHERE student_id=?", (req.mood, now_str, req.student_id))
        if req.eco_pledge is not None:
            cursor.execute("UPDATE wellness_metrics SET eco_pledge=?, last_updated=? WHERE student_id=?", (req.eco_pledge, now_str, req.student_id))
    else:
        cursor.execute(
            "INSERT INTO wellness_metrics (student_id, hydration, mood, eco_pledge, last_updated) VALUES (?, ?, ?, ?, ?)",
            (req.student_id, req.hydration or 0, req.mood or 'neutral', req.eco_pledge or '', now_str)
        )
    conn.commit()
    return {"status": "success"}

@app.get("/api/admin/students")
def get_students():
    # Get all users who are students
    auth_cursor.execute("SELECT id, name, email, hostel FROM users WHERE role='student'")
    users = auth_cursor.fetchall()
    
    # Get their stats
    cursor.execute("SELECT student_id, eco_points, streak, clean_meals FROM student_stats")
    stats = {str(row[0]): row[1:] for row in cursor.fetchall()}
    
    student_list = []
    for uid, name, email, hostel in users:
        s_stats = stats.get(str(uid), (0, 0, 0))
        student_list.append({
            "id": uid,
            "name": name,
            "email": email,
            "hostel": hostel,
            "eco_points": s_stats[0],
            "streak": s_stats[1],
            "clean_meals": s_stats[2]
        })
    return student_list

@app.delete("/api/admin/alerts/{alert_id}")
def dismiss_alert(alert_id: int):
    # Mock deletion
    return {"status": "success", "message": f"Alert {alert_id} dismissed"}


# SANITATION AI
@app.post("/analyze_sanitation")
async def analyze_sanitation(file: UploadFile = File(...)):
    temp_dir = tempfile.gettempdir()
    temp_path = os.path.join(temp_dir, "temp_upload.jpg")
    
    with open(temp_path, "wb") as buffer:
        buffer.write(await file.read())
        
    result = predict_image(temp_path)
    
    if os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except Exception:
            pass
        
    return result

@app.get("/api/public_stats")
def get_public_stats():
    # Total Students
    auth_cursor.execute("SELECT COUNT(*) FROM users WHERE role='student'")
    total_students = auth_cursor.fetchone()[0]
    
    # Total Waste Reduced & Savings
    cursor.execute("SELECT COUNT(*) FROM plate_snaps WHERE is_clean=1")
    total_clean = cursor.fetchone()[0]
    
    waste_reduced = round(total_clean * 0.1, 1)
    savings = total_clean * 15
    
    return {
        "total_students": f"{total_students}+",
        "waste_reduced": f"{waste_reduced}%" if waste_reduced < 100 else f"{waste_reduced}kg",
        "savings": f"₹{savings:,}"
    }
