from fastapi import APIRouter
import bcrypt
from backend.database import get_auth_conn
from backend.models import UserRegister, UserLogin

router = APIRouter()

@router.post("/register")
def register(user: UserRegister):
    conn = get_auth_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email=?", (user.email,))
    if cursor.fetchone():
        conn.close()
        return {"status": "error", "message": "Email already registered"}
    
    hashed_password = bcrypt.hashpw(user.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    cursor.execute(
        "INSERT INTO users (name, email, role, hostel, password) VALUES (?, ?, ?, ?, ?)",
        (user.name, user.email, user.role, user.hostel, hashed_password)
    )
    conn.commit()
    user_id = cursor.lastrowid
    conn.close()
    return {"status": "success", "message": "User registered successfully", "id": str(user_id)}

@router.post("/login")
def login(user: UserLogin):
    conn = get_auth_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email=?", (user.email,))
    db_user = cursor.fetchone()
    conn.close()
    
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
