from pydantic import BaseModel
from typing import Optional

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

class RedeemRequest(BaseModel):
    student_id: str
    reward: str
    cost: int

class WellnessUpdate(BaseModel):
    student_id: str
    hydration: int = None
    mood: str = None
    eco_pledge: str = None

class WasteLogEntry(BaseModel):
    date: str
    day_of_week: int
    meal_type: str
    attendance: int
    waste_kg: float
