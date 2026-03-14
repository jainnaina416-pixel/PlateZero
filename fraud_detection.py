# fraud_detection.py
# Checks: Duplicate image, Similar images (cross-account), Timestamp, Location,
#         Screen-recapture / photographed-screen anti-spoofing

import imagehash
import numpy as np
from PIL import Image, ExifTags
import sqlite3
import time
from geopy.distance import geodesic

HASH_DB = "image_hashes.db"

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

# ── Screen-recapture detection thresholds ─────────────────────────────────
# How many high-amplitude peaks (excluding DC) to flag as a screen pattern
FFT_PEAK_THRESHOLD   = 5      # count peaks above ratio
FFT_PEAK_RATIO       = 0.85   # only very strong peaks count
# Noise floor: real photos have stddev > this in a uniform-region crop
NOISE_STDDEV_MIN     = 1.5    # lowered to avoid flagging high-quality sharp images
# EXIF Software tags that indicate a screenshot / screen-captured image
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
def check_screen_capture(image_path: str) -> dict:
    """
    Anti-spoofing: detect whether the uploaded photo was taken of a SCREEN
    (e.g. a laptop/phone displaying a plate image) rather than a real plate.

    Three independent signals are checked; any ONE failing is enough to flag.

    1. FFT moiré peak detection
       Screens have a regular backlit pixel grid that produces strong periodic
       frequencies in the 2-D FFT of the luminance channel. Real photographs
       of physical objects do NOT show this pattern.

    2. EXIF Software tag
       Screenshots taken with OS tools or edited in graphics software carry a
       'Software' EXIF tag (e.g. "Windows Photo Viewer", "SnagIt", "Preview").
       Raw camera captures usually have the camera firmware name instead.

    3. Sensor-noise floor
       Physical camera sensors add a small amount of random noise to every
       pixel. Photos of screens are rendered by a deterministic pixel grid
       and therefore have an abnormally low noise floor in flat areas.

    Returns:
      { "ok": True }                     – looks like a genuine camera shot
      { "ok": False, "reason": "..." }   – likely photographed from a screen
    """
    try:
        img = Image.open(image_path).convert("RGB")
    except Exception as e:
        return {"ok": False, "reason": f"Could not open image: {e}"}

    # ── Signal 1: EXIF Software tag ───────────────────────────────────────
    try:
        exif = img.getexif()
        if exif:
            # EXIF tag for Software is 0x0133 (307)
            software_val = str(exif.get(307, "")).lower()
            if software_val:
                for bad in SCREEN_SOFTWARE_TAGS:
                    if bad in software_val:
                        return {
                            "ok": False,
                            "reason": (
                                "Image appears to be a screenshot or edited file "
                                f"(software tag: '{software_val}'). "
                                "Please capture a live photo of the plate."
                            )
                        }
    except Exception:
        pass  # No EXIF at all is fine — press on

    # ── Signal 2: FFT moiré / screen-grid detection ───────────────────────
    try:
        # Work on luminance channel, resize for speed
        gray = np.array(img.convert("L").resize((512, 512)), dtype=np.float32)

        # 2-D FFT → shift DC to centre → magnitude spectrum
        fft_mag = np.abs(np.fft.fftshift(np.fft.fft2(gray)))

        # Blank out the central DC region (low-frequency background)
        cy, cx = fft_mag.shape[0] // 2, fft_mag.shape[1] // 2
        dc_radius = 20
        y_idx, x_idx = np.ogrid[-cy:fft_mag.shape[0]-cy, -cx:fft_mag.shape[1]-cx]
        dc_mask = (x_idx**2 + y_idx**2) <= dc_radius**2
        fft_no_dc = fft_mag.copy()
        fft_no_dc[dc_mask] = 0.0

        # Count peaks that are conspicuously above the local background
        max_val  = fft_no_dc.max()
        threshold = max_val * FFT_PEAK_RATIO
        peaks = fft_no_dc[fft_no_dc > threshold]
        peak_count = int(len(peaks))

        if peak_count > FFT_PEAK_THRESHOLD:
            return {
                "ok": False,
                "reason": (
                    "Screen-recapture pattern detected in the image (periodic "
                    f"frequency peaks: {peak_count}). "
                    "Please photograph your actual plate, not a screen showing one."
                )
            }
    except Exception:
        pass  # If numpy/FFT fails, skip this check gracefully

    # ── Signal 3: Sensor noise floor ──────────────────────────────────────
    try:
        # Sample a 64×64 patch from the centre of the image
        w, h   = img.size
        left   = (w - 64) // 2
        top    = (h - 64) // 2
        patch  = np.array(
            img.crop((left, top, left + 64, top + 64)).convert("L"),
            dtype=np.float32
        )
        noise_std = float(np.std(patch))

        if noise_std < NOISE_STDDEV_MIN:
            return {
                "ok": False,
                "reason": (
                    f"Image appears artificially smooth (noise level: {noise_std:.2f}), "
                    "which is typical of a screen capture. "
                    "Please take a direct photo of your plate."
                )
            }
    except Exception:
        pass

    return {"ok": True}
