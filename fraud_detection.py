# fraud_detection.py
# Checks: Duplicate image, Similar images (cross-account), Timestamp, Location,
#         Screen-recapture / photographed-screen anti-spoofing

import imagehash
import numpy as np
from PIL import Image, ExifTags
import sqlite3
import time
import os
from geopy.distance import geodesic

# FIX: absolute path so DB is always found regardless of working directory
HASH_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "image_hashes.db")

MEAL_WINDOWS = {
    "breakfast": (7, 11),
    "lunch":     (12, 15),
    "dinner":    (19, 22),
}

DINING_LOCATION = (28.7041, 77.1025)
MAX_DISTANCE_KM  = 0.5
HASH_THRESHOLD = 10

FFT_PEAK_THRESHOLD   = 5
FFT_PEAK_RATIO       = 0.85
NOISE_STDDEV_MIN     = 1.5
SCREEN_SOFTWARE_TAGS = {
    "adobe", "photoshop", "lightroom", "snagit", "greenshot", "screenpresso",
    "windows photo", "snipping", "screenshot", "preview", "gyroflow",
    "paint", "gimp", "canva", "figma", "sketch",
}


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
    meal = meal.lower()
    if meal not in MEAL_WINDOWS:
        return False
    start, end = MEAL_WINDOWS[meal]
    hour = time.localtime().tm_hour
    return start <= hour <= end


def check_location(user_lat: float, user_lon: float) -> bool:
    distance = geodesic(DINING_LOCATION, (user_lat, user_lon)).km
    return distance <= MAX_DISTANCE_KM


def check_duplicate_or_similar(image_path: str, student_id: str, meal: str) -> dict:
    img = Image.open(image_path).convert("RGB")
    new_hash = imagehash.phash(img)
    today    = _today()

    conn = sqlite3.connect(HASH_DB)
    c = conn.cursor()
    c.execute(
        "SELECT student_id, hash_val FROM image_hashes WHERE meal=? AND date=?",
        (meal, today)
    )
    rows = c.fetchall()

    for (sid, stored_hash_str) in rows:
        stored_hash = imagehash.hex_to_hash(stored_hash_str)
        distance    = new_hash - stored_hash
        if distance == 0:
            conn.close()
            if sid == student_id:
                return {"ok": False, "reason": "You already submitted a photo for this meal today."}
            else:
                return {"ok": False, "reason": "Duplicate image detected — same photo used by another account."}
        if distance <= HASH_THRESHOLD:
            conn.close()
            return {
                "ok": False,
                "reason": f"Image too similar to an existing submission (similarity score: {distance}). Please capture a fresh photo."
            }

    c.execute(
        "INSERT INTO image_hashes (student_id, meal, date, hash_val, submitted_at) VALUES (?,?,?,?,?)",
        (student_id, meal, today, str(new_hash), time.strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()
    return {"ok": True}


def check_screen_capture(image_path: str) -> dict:
    try:
        img = Image.open(image_path).convert("RGB")
    except Exception as e:
        return {"ok": False, "reason": f"Could not open image: {e}"}

    # Signal 1: EXIF Software tag
    try:
        exif = img.getexif()
        if exif:
            software_val = str(exif.get(307, "")).lower()
            if software_val:
                for bad in SCREEN_SOFTWARE_TAGS:
                    if bad in software_val:
                        return {
                            "ok": False,
                            "reason": f"Image appears to be a screenshot or edited file (software tag: '{software_val}'). Please capture a live photo of the plate."
                        }
    except Exception:
        pass

    # Signal 2: FFT moire detection
    try:
        gray = np.array(img.convert("L").resize((512, 512)), dtype=np.float32)
        fft_mag = np.abs(np.fft.fftshift(np.fft.fft2(gray)))
        cy, cx = fft_mag.shape[0] // 2, fft_mag.shape[1] // 2
        y_idx, x_idx = np.ogrid[-cy:fft_mag.shape[0]-cy, -cx:fft_mag.shape[1]-cx]
        dc_mask = (x_idx**2 + y_idx**2) <= 20**2
        fft_no_dc = fft_mag.copy()
        fft_no_dc[dc_mask] = 0.0
        peak_count = int(len(fft_no_dc[fft_no_dc > fft_no_dc.max() * FFT_PEAK_RATIO]))
        if peak_count > FFT_PEAK_THRESHOLD:
            return {
                "ok": False,
                "reason": f"Screen-recapture pattern detected (periodic frequency peaks: {peak_count}). Please photograph your actual plate."
            }
    except Exception:
        pass

    # Signal 3: Sensor noise floor
    try:
        w, h = img.size
        patch = np.array(
            img.crop(((w-64)//2, (h-64)//2, (w-64)//2+64, (h-64)//2+64)).convert("L"),
            dtype=np.float32
        )
        if float(np.std(patch)) < NOISE_STDDEV_MIN:
            return {
                "ok": False,
                "reason": "Image appears artificially smooth, typical of a screen capture. Please take a direct photo of your plate."
            }
    except Exception:
        pass

    return {"ok": True}
