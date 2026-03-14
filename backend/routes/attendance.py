from fastapi import APIRouter
import uuid
from datetime import datetime
from backend.database import get_db_conn
from backend.models import ScanData
from backend import database

router = APIRouter()

@router.get("/generate_qr/{meal_type}")
def generate_qr(meal_type: str):
    database.current_meal_id = f"{meal_type}_{uuid.uuid4().hex[:6]}"
    
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO active_qrs (meal_id, meal_type, created_at) VALUES (?, ?, ?)",
        (database.current_meal_id, meal_type, str(datetime.now()))
    )
    conn.commit()
    conn.close()

    print("QR session:", database.current_meal_id)
    return {
        "meal_id": database.current_meal_id,
        "qr_data": database.current_meal_id
    }

@router.post("/scan_qr")
def scan_qr(data: ScanData):
    print("Scan:", data.student_id, data.meal_id)

    conn = get_db_conn()
    cursor = conn.cursor()
    
    # Validate if QR is active
    cursor.execute("SELECT * FROM active_qrs WHERE meal_id=?", (data.meal_id,))
    if not cursor.fetchone():
        conn.close()
        return {"status": "invalid_qr", "message": "The scanned QR code is either invalid or expired."}

    cursor.execute(
        "SELECT * FROM attendance WHERE student_id=? AND meal_id=?",
        (data.student_id, data.meal_id)
    )
    if cursor.fetchone():
        conn.close()
        return {"status": "already_scanned"}

    cursor.execute(
        "INSERT INTO attendance(student_id,meal_id,timestamp) VALUES (?,?,?)",
        (data.student_id, data.meal_id, str(datetime.now()))
    )
    conn.commit()
    conn.close()
    return {"status": "scan_recorded"}

@router.get("/attendance/{meal_id}")
def attendance(meal_id: str):
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM attendance WHERE meal_id=?",
        (meal_id,)
    )
    count = cursor.fetchone()[0]
    conn.close()
    return {"attendance": count}

@router.get("/all_scans")
def all_scans():
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM attendance")
    rows = cursor.fetchall()
    conn.close()
    return {"records": rows}
