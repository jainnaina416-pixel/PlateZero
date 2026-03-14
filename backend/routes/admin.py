from fastapi import APIRouter
from backend.database import get_db_conn, get_auth_conn

router = APIRouter()

@router.get("/api/admin/dashboard_data")
def dashboard_data():
    conn = get_db_conn()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM attendance WHERE date(timestamp) = date('now')")
    today_attend = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM plate_snaps WHERE is_clean=1 AND date(timestamp) = date('now')")
    clean_plates_today = cursor.fetchone()[0]
    conn.close()
    
    waste_reduced_kg = round(clean_plates_today * 0.1, 1)
    savings = clean_plates_today * 15
    
    chart_data = {"breakfast": [], "lunch": [], "dinner": []}
    conn = get_db_conn()
    cursor = conn.cursor()
    for i in range(6, -1, -1):
        target_date = f"date('now', '-{i} days')"
        for meal in ["breakfast", "lunch", "dinner"]:
            cursor.execute(f"SELECT COUNT(*) FROM attendance WHERE date(timestamp) = {target_date} AND meal_id LIKE ?", (f"{meal}%",))
            count = cursor.fetchone()[0]
            chart_data[meal].append(count)
    conn.close()

    base_waste = today_attend * 8
    
    return {
        "kpis": {
            "waste_reduced": f"{waste_reduced_kg} kg",
            "attendance": today_attend,
            "savings": f"₹{savings}",
            "high_waste_alerts": max(0, 18 - clean_plates_today)
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
            { "id": 2, "type": "warning", "icon": "⚠️", "title": "Paneer curry wasted", "desc": "Prep -15% for next similar meal", "time": "14m ago" },
            { "id": 3, "type": "info", "icon": "💡", "title": "Smart Insight", "desc": "Opt for fruit cup additions for balanced plates", "time": "1h ago" }
        ]
    }

@router.get("/api/admin/students")
def get_students():
    auth_conn = get_auth_conn()
    auth_cursor = auth_conn.cursor()
    auth_cursor.execute("SELECT id, name, email, hostel FROM users WHERE role='student'")
    users = auth_cursor.fetchall()
    auth_conn.close()
    
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT student_id, eco_points, streak, clean_meals FROM student_stats")
    stats = {str(row[0]): row[1:] for row in cursor.fetchall()}
    conn.close()
    
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

@router.delete("/api/admin/alerts/{alert_id}")
def dismiss_alert(alert_id: int):
    return {"status": "success", "message": f"Alert {alert_id} dismissed"}

@router.get("/api/public_stats")
def get_public_stats():
    auth_conn = get_auth_conn()
    auth_cursor = auth_conn.cursor()
    auth_cursor.execute("SELECT COUNT(*) FROM users WHERE role='student'")
    total_students = auth_cursor.fetchone()[0]
    auth_conn.close()
    
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM plate_snaps WHERE is_clean=1")
    total_clean = cursor.fetchone()[0]
    conn.close()
    
    waste_reduced = round(total_clean * 0.1, 1)
    savings = total_clean * 15
    
    return {
        "total_students": f"{total_students}+",
        "waste_reduced": f"{waste_reduced}%" if waste_reduced < 100 else f"{waste_reduced}kg",
        "savings": f"₹{savings:,}"
    }
