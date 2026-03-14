rom fastapi import APIRouter, File, UploadFile, Form
from typing import Optional
import os
import uuid
import tempfile
from datetime import datetime
from backend.database import get_db_conn, get_auth_conn
from backend.models import WellnessUpdate

from vision_ai.predict import predict_image
from fraud_detection import (
    check_time,
    check_location,
    check_duplicate_or_similar,
    check_screen_capture,
)

router = APIRouter()


@router.get("/student/{student_id}")
def get_student_stats(student_id: str):
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT eco_points, streak, clean_meals FROM student_stats WHERE student_id=?", (student_id,))
    row = cursor.fetchone()

    if not row:
        cursor.execute("INSERT INTO student_stats (student_id) VALUES (?)", (student_id,))
        conn.commit()
        eco_points, streak, clean_meals = 0, 0, 0
    else:
        eco_points, streak, clean_meals = row

    cursor.execute("SELECT COUNT(*) FROM student_stats WHERE eco_points > ?", (eco_points,))
    rank = cursor.fetchone()[0] + 1
    conn.close()

    return {
        "eco_points": eco_points,
        "streak": streak,
        "clean_meals": clean_meals,
        "rank": rank
    }


@router.post("/snap_plate")
async def snap_plate(
    student_id: str = Form("demo"),
    meal: str      = Form("meal"),
    lat: Optional[float] = Form(None),
    lon: Optional[float] = Form(None),
    image: UploadFile = File(...)
):
    try:
        # 1. Meal-time check
        if not check_time(meal):
            return {
                "status": "fraud",
                "clean": False,
                "reason": f"Outside {meal} time window. Snaps only accepted during meal hours."
            }

        # 2. Location check (only if GPS provided)
        if lat is not None and lon is not None:
            if not check_location(lat, lon):
                return {
                    "status": "fraud",
                    "clean": False,
                    "reason": "You appear to be outside the dining hall. Please snap from the mess."
                }

        # 3. Save upload to temp file
        temp_dir  = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, f"snap_{uuid.uuid4().hex}.jpg")
        img_bytes = await image.read()

        # FIX: guard against empty upload
        if not img_bytes:
            return {"status": "error", "clean": False, "reason": "Empty image received. Please try again."}

        with open(temp_path, "wb") as f:
            f.write(img_bytes)

        # 4. Duplicate / cross-account similarity check
        try:
            fraud_result = check_duplicate_or_similar(temp_path, student_id, meal)
        except Exception:
            fraud_result = {"ok": True}  # Don't block if hash DB fails

        if not fraud_result["ok"]:
            try: os.remove(temp_path)
            except: pass
            return {"status": "fraud", "clean": False, "reason": fraud_result["reason"]}

        # 5. Screen-capture anti-spoofing
        try:
            screen_result = check_screen_capture(temp_path)
        except Exception:
            screen_result = {"ok": True}

        if not screen_result["ok"]:
            try: os.remove(temp_path)
            except: pass
            return {"status": "fraud", "clean": False, "reason": screen_result["reason"]}

        # 6. AI plate verification
        try:
            result = predict_image(temp_path)
        except Exception as e:
            result = {"error": str(e)}

        try: os.remove(temp_path)
        except: pass

        # FIX: handle AI model errors gracefully instead of crashing
        if "error" in result:
            return {
                "status": "error",
                "clean": False,
                "reason": f"AI model unavailable: {result['error']}. Please contact admin."
            }

        is_clean = False
        status   = "failed"
        prediction_label = "unknown"

        if "prediction" in result:
            prediction_label = result["prediction"]
            if prediction_label.lower() == "clean":
                is_clean = True
            status = "success" if is_clean else "failed"

        # 7. Log snap & update stats
        now_str = str(datetime.now())
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO plate_snaps (student_id, meal_type, is_clean, timestamp) VALUES (?, ?, ?, ?)",
            (student_id, meal, is_clean, now_str)
        )

        if is_clean:
            cursor.execute("SELECT eco_points, streak, clean_meals FROM student_stats WHERE student_id=?", (student_id,))
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

        # FIX: always commit — was only inside is_clean block before
        conn.commit()
        conn.close()

        return {
            "status": status,
            "clean": is_clean,
            "prediction": prediction_label
        }

    except Exception as e:
        # FIX: catch-all so server never returns a raw 500 crash
        return {
            "status": "error",
            "clean": False,
            "reason": f"Server error: {str(e)}"
        }


@router.get("/api/leaderboard")
def get_leaderboard():
    auth_conn = get_auth_conn()
    auth_cursor = auth_conn.cursor()
    auth_cursor.execute("SELECT id, name FROM users")
    users = {str(row[0]): row[1] for row in auth_cursor.fetchall()}
    auth_conn.close()

    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT student_id, eco_points FROM student_stats ORDER BY eco_points DESC LIMIT 10")
    rows = cursor.fetchall()
    conn.close()

    leaderboard = []
    for idx, (sid, pts) in enumerate(rows):
        leaderboard.append({
            "rank": idx + 1,
            "name": users.get(sid, f"Student {sid}"),
            "points": pts,
            "id": sid
        })
    return leaderboard


@router.get("/student/{student_id}/history")
def get_student_history(student_id: str):
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT is_clean, timestamp FROM plate_snaps WHERE student_id=? ORDER BY timestamp ASC", (student_id,))
    rows = cursor.fetchall()
    conn.close()
    history = {}
    for is_clean, ts in rows:
        date_str = ts.split(' ')[0]
        history[date_str] = "clean" if is_clean else "partial"
    return history


@router.get("/student/{student_id}/impact")
def get_student_impact(student_id: str):
    conn = get_db_conn()
    cursor = conn.cursor()
    # FIX: filter to last 7 days so "Weekly Impact" card shows weekly data
    cursor.execute(
        "SELECT COUNT(*) FROM plate_snaps WHERE student_id=? AND is_clean=1 AND timestamp >= datetime('now', '-7 days')",
        (student_id,)
    )
    clean_count = cursor.fetchone()[0]
    conn.close()

    waste_saved  = round(clean_count * 0.1, 1)
    savings      = clean_count * 15
    water_saved  = round(clean_count * 0.2, 1)
    co2_reduced  = round(clean_count * 0.05, 2)

    return {
        "waste_prevented": f"{waste_saved}kg",
        "mess_savings":    f"₹{savings}",
        "water_saved":     f"{water_saved}L",
        "co2_reduced":     f"{co2_reduced}kg"
    }


@router.get("/student/{student_id}/wellness")
def get_wellness(student_id: str):
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT hydration, mood, eco_pledge FROM wellness_metrics WHERE student_id=?", (student_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return {"hydration": 0, "mood": "neutral", "eco_pledge": ""}
    return {"hydration": row[0], "mood": row[1], "eco_pledge": row[2]}


@router.post("/student/wellness")
def update_wellness(req: WellnessUpdate):
    now_str = str(datetime.now())
    conn = get_db_conn()
    cursor = conn.cursor()
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
    conn.close()
    return {"status": "success"}

