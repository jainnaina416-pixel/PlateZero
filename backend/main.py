from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import sys

# Setup path for internal imports
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
if PARENT_DIR not in sys.path:
    sys.path.append(PARENT_DIR)

from backend.database import init_db, init_auth_db
from backend.routes import auth, attendance, student, admin, sanitation, waste, rewards
# FIX: initialise fraud hash DB on startup so image_hashes.db always exists
from fraud_detection import init_hash_db

# Initialize databases
init_db()
init_auth_db()
init_hash_db()

app = FastAPI(title="PlateZero Modular API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(auth.router)
app.include_router(attendance.router)
app.include_router(student.router)
app.include_router(admin.router)
app.include_router(sanitation.router)
app.include_router(waste.router)
app.include_router(rewards.router)

@app.get("/")
def read_root():
    return {"message": "PlateZero Modular API is running!"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)

