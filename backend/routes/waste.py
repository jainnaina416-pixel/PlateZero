from fastapi import APIRouter
from backend.models import WasteLogEntry
from waste_ai.waste_intelligence import (
    log_meal_entry,
    predict_waste,
    get_trends,
    get_behavioral_analysis,
    get_recommendations,
)

router = APIRouter()

@router.post("/api/waste/log")
def waste_log(entry: WasteLogEntry):
    return log_meal_entry(
        date=entry.date,
        day_of_week=entry.day_of_week,
        meal_type=entry.meal_type,
        attendance=entry.attendance,
        waste_kg=entry.waste_kg,
    )

@router.get("/api/waste/predict")
def waste_predict(meal_type: str = "lunch", day_of_week: int = 0, attendance: int = 200):
    return predict_waste(day_of_week=day_of_week, meal_type=meal_type, attendance=attendance)

@router.get("/api/waste/trends")
def waste_trends(days: int = 7):
    return get_trends(days=days)

@router.get("/api/waste/behavior")
def waste_behavior():
    return get_behavioral_analysis()

@router.get("/api/waste/recommendations")
def waste_recommendations():
    return get_recommendations()
