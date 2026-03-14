"""
waste_intelligence.py
=====================
PlateZero – AI-Powered Waste Intelligence Module

Pipeline:
  1. SQLite storage  → mess_waste_log table (auto-seeded with 6-week demo data)
  2. XGBoost model   → predicts waste_kg from (day_of_week, meal_type, attendance)
  3. Behavioral lens → waste/student ratio, peak periods, high-waste meal patterns
  4. Recommender     → prep-reduction suggestions based on predicted vs. baseline
"""

import os
import sqlite3
import random
import math
from datetime import datetime, timedelta

import numpy as np

# ── Optional heavy deps (graceful fallback if not installed) ─────────────────
try:
    from xgboost import XGBRegressor
    _XGB_AVAILABLE = True
except ImportError:
    _XGB_AVAILABLE = False

try:
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import mean_absolute_error, r2_score
    _SKL_AVAILABLE = True
except ImportError:
    _SKL_AVAILABLE = False

# ── Constants ────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WASTE_DB  = os.path.join(BASE_DIR, "mess_waste.db")

MEAL_TYPES  = ["breakfast", "lunch", "dinner"]
DAY_NAMES   = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Realistic baseline waste (kg) per meal — used by recommender & seed
MEAL_BASELINE_KG = {
    ("breakfast",): 6.0,
    ("lunch",):    10.0,
    ("dinner",):    8.0,
}

# ── DB Helpers ───────────────────────────────────────────────────────────────

def _get_conn():
    return sqlite3.connect(WASTE_DB, check_same_thread=False)


def init_waste_db():
    """Create mess_waste_log table if it doesn't exist."""
    conn = _get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS mess_waste_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            date         TEXT    NOT NULL,
            day_of_week  INTEGER NOT NULL,   -- 0=Mon … 6=Sun
            meal_type    TEXT    NOT NULL,   -- breakfast / lunch / dinner
            attendance   INTEGER NOT NULL,
            waste_kg     REAL    NOT NULL,
            logged_at    TEXT    NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def _row_count():
    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM mess_waste_log")
    n = c.fetchone()[0]
    conn.close()
    return n


def seed_demo_data(weeks: int = 6):
    """
    Seed 6 weeks of realistic synthetic meal data so the model has
    something to train on immediately after installation.
    """
    if _row_count() >= 10:
        return  # Already seeded

    random.seed(42)
    start = datetime.now() - timedelta(weeks=weeks)
    rows = []
    for d in range(weeks * 7):
        day_dt = start + timedelta(days=d)
        dow    = day_dt.weekday()  # 0=Mon
        date_s = day_dt.strftime("%Y-%m-%d")
        now_s  = str(datetime.now())

        for meal in MEAL_TYPES:
            # Attendance: 60-90% of 300 capacity, lower on weekends + breakfast
            base_attend = 300
            attend_frac = random.uniform(0.55, 0.90)
            if dow >= 5:               attend_frac -= 0.10   # weekend dip
            if meal == "breakfast":    attend_frac -= 0.10   # breakfast skipped more
            if meal == "dinner":       attend_frac += 0.05   # dinner more popular
            attendance = max(30, int(base_attend * attend_frac))

            # Waste: baseline + noise + day patterns
            base_waste = {"breakfast": 5.5, "lunch": 9.5, "dinner": 7.8}[meal]
            noise      = random.gauss(0, 1.2)
            dow_factor = 1.0 + 0.08 * math.sin(dow * math.pi / 3.5)  # gentle weekly cycle
            waste_kg   = max(0.5, round((base_waste + noise) * dow_factor, 2))

            rows.append((date_s, dow, meal, attendance, waste_kg, now_s))

    conn = _get_conn()
    c = conn.cursor()
    c.executemany(
        "INSERT INTO mess_waste_log (date, day_of_week, meal_type, attendance, waste_kg, logged_at) VALUES (?,?,?,?,?,?)",
        rows
    )
    conn.commit()
    conn.close()


# ── Data Access ───────────────────────────────────────────────────────────────

def log_meal_entry(date: str, day_of_week: int, meal_type: str,
                   attendance: int, waste_kg: float) -> dict:
    """Insert one new waste-log entry."""
    conn = _get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO mess_waste_log (date, day_of_week, meal_type, attendance, waste_kg, logged_at) VALUES (?,?,?,?,?,?)",
        (date, day_of_week, meal_type.lower(), attendance, round(float(waste_kg), 2), str(datetime.now()))
    )
    conn.commit()
    conn.close()
    return {"status": "logged", "rows_total": _row_count()}


def _fetch_all_data():
    """Return all log rows as list of dicts."""
    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT date, day_of_week, meal_type, attendance, waste_kg FROM mess_waste_log ORDER BY date")
    rows = c.fetchall()
    conn.close()
    return [
        {"date": r[0], "day_of_week": r[1], "meal_type": r[2],
         "attendance": r[3], "waste_kg": r[4]}
        for r in rows
    ]


# ── Feature Engineering ───────────────────────────────────────────────────────

def _encode_features(rows: list) -> tuple:
    """
    Feature matrix X:  [day_of_week, attendance, is_breakfast, is_lunch, is_dinner]
    Target vector y:   waste_kg
    """
    X, y = [], []
    for r in rows:
        meal = r["meal_type"].lower()
        feat = [
            r["day_of_week"],
            r["attendance"],
            1 if meal == "breakfast" else 0,
            1 if meal == "lunch"     else 0,
            1 if meal == "dinner"    else 0,
        ]
        X.append(feat)
        y.append(r["waste_kg"])
    return np.array(X, dtype=float), np.array(y, dtype=float)


def _encode_single(day_of_week: int, meal_type: str, attendance: int) -> np.ndarray:
    meal = meal_type.lower()
    return np.array([[
        day_of_week,
        attendance,
        1 if meal == "breakfast" else 0,
        1 if meal == "lunch"     else 0,
        1 if meal == "dinner"    else 0,
    ]], dtype=float)


# ── Model Training ──────────────────────────────────────────────────────────

def train_model():
    """
    Train an XGBoost (or Ridge fallback) regressor.
    Returns (model, metrics_dict).
    """
    rows = _fetch_all_data()
    if len(rows) < 5:
        return None, {"error": "Not enough data to train (need ≥ 5 rows)"}

    X, y = _encode_features(rows)

    # Simple 80/20 split
    split = max(1, int(len(rows) * 0.8))
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

    if _XGB_AVAILABLE:
        model = XGBRegressor(
            n_estimators=200,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            verbosity=0
        )
        model.fit(X_train, y_train)
    elif _SKL_AVAILABLE:
        scaler = StandardScaler()
        X_train = scaler.fit_transform(X_train)
        X_test  = scaler.transform(X_test)
        model   = Ridge(alpha=1.0)
        model.fit(X_train, y_train)
        # Attach scaler so predict can use it
        model._scaler = scaler
    else:
        return None, {"error": "Neither xgboost nor scikit-learn is installed."}

    metrics = {}
    if len(X_test) > 0:
        y_pred = model.predict(X_test)
        metrics["mae"]  = round(float(mean_absolute_error(y_test, y_pred)), 3) if _SKL_AVAILABLE else round(float(np.mean(np.abs(y_test - y_pred))), 3)
        metrics["r2"]   = round(float(r2_score(y_test, y_pred)), 3)            if _SKL_AVAILABLE else None
        metrics["rows"] = len(rows)
    else:
        metrics = {"rows": len(rows), "mae": None, "r2": None}

    return model, metrics


# ── Prediction ────────────────────────────────────────────────────────────────

def predict_waste(day_of_week: int, meal_type: str, attendance: int) -> dict:
    """
    Predict waste_kg for a future meal.
    Also estimates expected attendance by averaging historical same-day-meal data.
    """
    rows = _fetch_all_data()

    # Expected attendance: average for same day+meal
    same = [r["attendance"] for r in rows
            if r["day_of_week"] == day_of_week and r["meal_type"].lower() == meal_type.lower()]
    expected_attendance = round(float(np.mean(same)), 0) if same else attendance

    model, metrics = train_model()
    if model is None:
        return {"error": metrics.get("error", "Model training failed"), "expected_attendance": int(expected_attendance)}

    feat = _encode_single(day_of_week, meal_type, attendance)

    if hasattr(model, "_scaler"):
        feat = model._scaler.transform(feat)

    raw_pred = float(model.predict(feat)[0])
    predicted_waste_kg = round(max(0.0, raw_pred), 2)

    # Baseline comparison
    baseline = {"breakfast": 5.5, "lunch": 9.5, "dinner": 7.8}.get(meal_type.lower(), 8.0)
    delta_pct = round((predicted_waste_kg - baseline) / baseline * 100, 1)

    return {
        "day": DAY_NAMES[day_of_week],
        "meal_type": meal_type,
        "expected_attendance": int(expected_attendance),
        "predicted_waste_kg": predicted_waste_kg,
        "baseline_waste_kg": baseline,
        "delta_pct": delta_pct,          # + means above baseline
        "model_mae": metrics.get("mae"),
        "training_rows": metrics.get("rows"),
    }


# ── Trends ────────────────────────────────────────────────────────────────────

def get_trends(days: int = 7) -> dict:
    """
    Return 7-day rolling data for the admin chart:
      attendance[] and waste_kg[] indexed by date label.
    """
    conn = _get_conn()
    c = conn.cursor()

    labels, attendance_vals, waste_vals = [], [], []

    for i in range(days - 1, -1, -1):
        target = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        c.execute("SELECT AVG(attendance), SUM(waste_kg) FROM mess_waste_log WHERE date=?", (target,))
        row = c.fetchone()
        labels.append((datetime.now() - timedelta(days=i)).strftime("%a"))
        attendance_vals.append(round(float(row[0] or 0), 1))
        waste_vals.append(round(float(row[1] or 0), 2))

    conn.close()
    return {
        "labels": labels,
        "attendance": attendance_vals,
        "waste_kg":   waste_vals,
    }


# ── Behavioral Analysis ───────────────────────────────────────────────────────

def get_behavioral_analysis() -> dict:
    """
    Returns:
      - waste_per_student  : avg kg waste per attending student
      - peak_period        : day+meal combo with highest attendance
      - high_waste_meals   : top 3 day+meal combos by avg waste_kg
      - low_waste_meals    : top 3 day+meal combos by lowest avg waste_kg
    """
    rows = _fetch_all_data()
    if not rows:
        return {"error": "No data available"}

    # waste_per_student
    wps_vals = [r["waste_kg"] / r["attendance"] for r in rows if r["attendance"] > 0]
    waste_per_student = round(float(np.mean(wps_vals)) * 1000, 1)  # in grams

    # group by (day_of_week, meal_type)
    groups: dict = {}
    for r in rows:
        key = (r["day_of_week"], r["meal_type"].lower())
        if key not in groups:
            groups[key] = {"attendance": [], "waste": []}
        groups[key]["attendance"].append(r["attendance"])
        groups[key]["waste"].append(r["waste_kg"])

    group_stats = []
    for (dow, meal), vals in groups.items():
        group_stats.append({
            "day":         DAY_NAMES[dow],
            "meal_type":   meal,
            "avg_attend":  round(float(np.mean(vals["attendance"])), 1),
            "avg_waste":   round(float(np.mean(vals["waste"])), 2),
        })

    # peak attendance
    peak = max(group_stats, key=lambda x: x["avg_attend"])

    # high & low waste sorted
    sorted_waste = sorted(group_stats, key=lambda x: x["avg_waste"])
    low_waste  = sorted_waste[:3]
    high_waste = sorted_waste[-3:][::-1]

    # day-level summary
    day_summary = []
    for dow in range(7):
        day_rows = [r for r in rows if r["day_of_week"] == dow]
        if day_rows:
            day_summary.append({
                "day":       DAY_NAMES[dow],
                "avg_waste": round(float(np.mean([r["waste_kg"] for r in day_rows])), 2),
                "avg_attend": round(float(np.mean([r["attendance"] for r in day_rows])), 0),
            })

    # meal-level summary
    meal_summary = {}
    for meal in MEAL_TYPES:
        meal_rows = [r for r in rows if r["meal_type"].lower() == meal]
        if meal_rows:
            meal_summary[meal] = {
                "avg_waste":  round(float(np.mean([r["waste_kg"]  for r in meal_rows])), 2),
                "avg_attend": round(float(np.mean([r["attendance"] for r in meal_rows])), 0),
            }

    return {
        "waste_per_student_grams": waste_per_student,
        "peak_period":  {"day": peak["day"], "meal": peak["meal_type"], "avg_attendance": peak["avg_attend"]},
        "high_waste_meals": high_waste,
        "low_waste_meals":  low_waste,
        "day_summary":  day_summary,
        "meal_summary": meal_summary,
    }


# ── Recommendation Engine ─────────────────────────────────────────────────────

def get_recommendations() -> dict:
    """
    Compare each day+meal predicted waste vs. baseline.
    Generate actionable preparation reduction suggestions.
    """
    rows = _fetch_all_data()
    if not rows:
        return {"recommendations": [], "summary": "No data to generate recommendations."}

    model, metrics = train_model()
    if model is None:
        return {"recommendations": [], "summary": "Model not ready yet. Log more data."}

    baselines = {"breakfast": 5.5, "lunch": 9.5, "dinner": 7.8}
    recs = []

    # Build average attendance per (dow, meal)
    groups: dict = {}
    for r in rows:
        key = (r["day_of_week"], r["meal_type"].lower())
        if key not in groups:
            groups[key] = {"attendance": [], "waste": []}
        groups[key]["attendance"].append(r["attendance"])
        groups[key]["waste"].append(r["waste_kg"])

    for (dow, meal), vals in groups.items():
        avg_attend = int(np.mean(vals["attendance"]))
        feat = _encode_single(dow, meal, avg_attend)
        if hasattr(model, "_scaler"):
            feat = model._scaler.transform(feat)

        predicted = max(0.0, float(model.predict(feat)[0]))
        baseline  = baselines.get(meal, 8.0)
        delta_pct = (predicted - baseline) / baseline * 100

        severity = "info"
        action   = ""

        if delta_pct >= 20:
            severity = "danger"
            action   = f"⚠️ Reduce {meal} food prep by ~{round(delta_pct)}% on {DAY_NAMES[dow]}s — predicted waste ({predicted:.1f} kg) is significantly above baseline ({baseline} kg)."
        elif delta_pct >= 8:
            severity = "warning"
            action   = f"🔶 Consider trimming {meal} portions by ~{round(delta_pct)}% on {DAY_NAMES[dow]}s — predicted waste ({predicted:.1f} kg) slightly high."
        elif delta_pct <= -15:
            severity = "success"
            action   = f"✅ {DAY_NAMES[dow]} {meal} is efficient! Predicted waste ({predicted:.1f} kg) is {abs(round(delta_pct))}% below baseline — keep current portions."
        else:
            continue  # within acceptable range, no recommendation

        recs.append({
            "day":           DAY_NAMES[dow],
            "meal":          meal,
            "severity":      severity,
            "action":        action,
            "predicted_kg":  round(predicted, 2),
            "baseline_kg":   baseline,
            "delta_pct":     round(delta_pct, 1),
        })

    # Sort: danger first, then warning, then success
    order = {"danger": 0, "warning": 1, "success": 2, "info": 3}
    recs.sort(key=lambda x: (order.get(x["severity"], 3), -abs(x["delta_pct"])))

    total_excess = sum(r["predicted_kg"] - r["baseline_kg"] for r in recs if r["severity"] in ("danger", "warning"))
    summary = (
        f"Found {len([r for r in recs if r['severity'] in ('danger','warning')])} high-waste meal slots. "
        f"Estimated excess prep: {round(total_excess, 1)} kg/week if unaddressed."
        if recs else "All meals within acceptable waste range. Great efficiency! 🌿"
    )

    return {
        "recommendations": recs[:10],   # cap at 10
        "summary": summary,
        "model_mae": metrics.get("mae"),
        "training_rows": metrics.get("rows"),
    }


# ── Bootstrap on import ───────────────────────────────────────────────────────

init_waste_db()
seed_demo_data()
