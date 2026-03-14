from fastapi import APIRouter
from datetime import datetime
from backend.database import get_db_conn
from backend.models import RedeemRequest

router = APIRouter()

@router.post("/redeem")
def redeem_reward(req: RedeemRequest):
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT eco_points FROM student_stats WHERE student_id=?", (req.student_id,))
    row = cursor.fetchone()
    
    if not row or row[0] < req.cost:
        conn.close()
        return {"status": "error", "message": "Not enough EcoPoints"}
    
    new_points = row[0] - req.cost
    cursor.execute("UPDATE student_stats SET eco_points=? WHERE student_id=?", (new_points, req.student_id))
    
    cursor.execute(
        "INSERT INTO rewards_history (student_id, reward_name, cost, timestamp) VALUES (?, ?, ?, ?)",
        (req.student_id, req.reward, req.cost, str(datetime.now()))
    )
    conn.commit()
    conn.close()
    
    return {"status": "success", "new_points": new_points}
