from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime
import qrcode
import uuid
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

app = FastAPI()

# allow frontend HTML dashboard to call backend API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# create folder for QR images
if not os.path.exists("qr_codes"):
    os.makedirs("qr_codes")

# serve QR images
app.mount("/qr_codes", StaticFiles(directory="qr_codes"), name="qr_codes")

attendance_logs = []
current_meal_id = None


class ScanData(BaseModel):
    student_id: str
    meal_id: str


# generate QR for mess
@app.get("/generate_qr/{meal_type}")
def generate_qr(meal_type: str):

    global current_meal_id

    current_meal_id = f"{meal_type}_{uuid.uuid4().hex[:6]}"

    return {
        "meal_id": current_meal_id,
        "qr_data": current_meal_id
    }
# student scan endpoint
@app.post("/scan_qr")
def scan_qr(data: ScanData):

    for record in attendance_logs:
        if record["student_id"] == data.student_id and record["meal_id"] == data.meal_id:
            return {"status": "already scanned"}

    attendance_logs.append({
        "student_id": data.student_id,
        "meal_id": data.meal_id,
        "timestamp": str(datetime.now())
    })

    return {"status": "scan recorded"}


# attendance count
@app.get("/attendance/{meal_id}")
def attendance(meal_id: str):

    count = sum(1 for r in attendance_logs if r["meal_id"] == meal_id)

    return {"attendance": count}