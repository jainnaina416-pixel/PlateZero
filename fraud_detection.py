# fraud_detection.py
# Checks: Duplicate image, Similar images (cross-account), Timestamp, Location

import imagehash
from PIL import Image
import sqlite3
import time
import os
from geopy.distance import geodesic

# Always store the hash DB next to this script, regardless of working directory
HASH_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "image_hashes.db")

# ── Meal windows (24-hour) ──────────────────────────────────────────────────
MEAL_WINDOWS = {
    "breakfast": (7, 11),
    "lunch":     (12, 15),
    "dinner":    (19, 22),
}

# ── Campus dining location ─────────────────────────────────────────────────
DINING_LOCATION = (28.7041, 77.1025)   # e.g. IIT Delhi mess
MAX_DISTANCE_KM  = 0.5                 # allow within 500m

# ── Similarity threshold (Hamming distance) ────────────────────────────────
# Two hashes with distance <= HASH_THRESHOLD are considered "too similar"
HASH_THRESHOLD = 10


def init_hash_db():
    """Create the image-hash table if it doesn't exist."""
    conn = sqlite3.connect(HASH_DB)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS image_hashes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id  TEXT    NOT NULL,
            meal        TEXT    NOT NULL,
            date        TEXT    NOT NULL,
            hash_val    TEXT    NOT NULL,
            submitted_at TEXT   NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def _today():
    return time.strftime("%Y-%m-%d")


def check_time(meal: str) -> bool:
    """Return True if current time is inside the allowed window for this meal."""
    meal = meal.lower()
    if meal not in MEAL_WINDOWS:
        return False
    start, end = MEAL_WINDOWS[meal]
    hour = time.localtime().tm_hour
    return start <= hour <= end


def check_location(user_lat: float, user_lon: float) -> bool:
    """Return True if the user is within MAX_DISTANCE_KM of the dining hall."""
    distance = geodesic(DINING_LOCATION, (user_lat, user_lon)).km
    return distance <= MAX_DISTANCE_KM


def check_duplicate_or_similar(image_path: str, student_id: str, meal: str) -> dict:
    """
    Hash the uploaded image using perceptual hashing (pHash) and compare
    against ALL stored hashes for the same meal+date across every account.

    Returns a dict:
      { "ok": True }                         – first-time clean submission
      { "ok": False, "reason": "..." }       – duplicate or too-similar image
    """
    img = Image.open(image_path).convert("RGB")
    new_hash = imagehash.phash(img)
    today    = _today()

    conn = sqlite3.connect(HASH_DB)
    c = conn.cursor()

    # Fetch all hashes for this meal on today (across all students)
    c.execute(
        "SELECT student_id, hash_val FROM image_hashes WHERE meal=? AND date=?",
        (meal, today)
    )
    rows = c.fetchall()

    for (sid, stored_hash_str) in rows:
        stored_hash = imagehash.hex_to_hash(stored_hash_str)
        distance    = new_hash - stored_hash          # Hamming distance

        if distance == 0:
            if sid == student_id:
                conn.close()
                return {"ok": False, "reason": "You already submitted a photo for this meal today."}
            else:
                conn.close()
                return {"ok": False, "reason": "Duplicate image detected — same photo used by another account."}

        if distance <= HASH_THRESHOLD:
            conn.close()
            return {
                "ok": False,
                "reason": f"Image too similar to an existing submission (similarity score: {distance}). "
                          "Please capture a fresh photo."
            }

    # All good — store the new hash
    c.execute(
        "INSERT INTO image_hashes (student_id, meal, date, hash_val, submitted_at) VALUES (?,?,?,?,?)",
        (student_id, meal, today, str(new_hash), time.strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()
    return {"ok": True}

