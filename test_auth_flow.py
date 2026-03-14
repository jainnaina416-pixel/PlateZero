import requests
import os
import subprocess
import time
import json
from PIL import Image

BASE_URL = "http://127.0.0.1:8000"
PLATE_IMG = "test_plate.jpg"

def test_full_flow():
    # 1. Register
    reg_data = {
        "name": "Test Student",
        "email": "test@student.edu",
        "role": "student",
        "hostel": "Block A",
        "password": "password123"
    }
    print(f"Registering student: {reg_data['email']}")
    try:
        res = requests.post(f"{BASE_URL}/register", json=reg_data)
        print(f"Register Response: {res.status_code}, {res.text}")
    except Exception as e:
        print(f"FAILED to connect to backend: {e}")
        return

    # 2. Login
    login_data = {
        "email": "test@student.edu",
        "password": "password123"
    }
    print(f"Logging in: {login_data['email']}")
    res = requests.post(f"{BASE_URL}/login", json=login_data)
    print(f"Login Response: {res.status_code}, {res.text}")
    
    login_res = res.json()
    if login_res.get("status") != "success":
        print("Login failed, cannot proceed to snap_plate")
        return
    
    student_id = login_res["user"]["id"]
    print(f"Student ID from login: {student_id}")

    # 3. Snap Plate
    # Create a dummy image
    dummy_img = Image.new('RGB', (224, 224), color = (73, 109, 137))
    dummy_img.save(PLATE_IMG)

    # --- TEST CASES ---
    
    # 1. Valid Snap Flow (Expect fraud if outside window)
    print("\n--- [1] Testing Snap Flow ---")
    files = {'image': ('plate.jpg', open(PLATE_IMG, 'rb'), 'image/jpeg')}
    data = {'student_id': student_id, 'meal': 'lunch'}
    res = requests.post(f"{BASE_URL}/snap_plate", files=files, data=data)
    print(f"Snap Status: {res.status_code}, Response: {res.json()}")

    # 2. Empty Student ID
    print("\n--- [2] Testing Empty Student ID ---")
    files = {'image': ('plate.jpg', open(PLATE_IMG, 'rb'), 'image/jpeg')}
    data = {'student_id': '', 'meal': 'lunch'}
    res = requests.post(f"{BASE_URL}/snap_plate", files=files, data=data)
    print(f"Empty SID Status: {res.status_code}, Response: {res.json()}")

    # 3. Invalid QR Scan (Unauthorized code)
    print("\n--- [3] Testing Invalid QR Scan ---")
    data = {'student_id': student_id, 'meal_id': 'hacker_token_666'}
    res = requests.post(f"{BASE_URL}/scan_qr", json=data)
    print(f"Invalid Scan Response: {res.json()}")

    # 4. Valid QR Scan (Must generate first)
    print("\n--- [4] Testing Valid QR Scan ---")
    gen_res = requests.get(f"{BASE_URL}/generate_qr/lunch")
    meal_id = gen_res.json()['meal_id']
    print(f"Generated Meal ID: {meal_id}")
    
    data = {'student_id': student_id, 'meal_id': meal_id}
    res = requests.post(f"{BASE_URL}/scan_qr", json=data)
    print(f"Valid Scan Response: {res.json()}")

    # 5. Unknown Student ID in Stats
    print("\n--- [5] Testing Unknown Student Stats ---")
    res = requests.get(f"{BASE_URL}/student/unknown_user_999")
    print(f"Stats Status: {res.status_code}, Response: {res.json()}")

def run_tests():
    # Kill any existing server on port 8000
    print("Cleaning up port 8000...")
    if os.name == 'nt':
        # Find PID on port 8000 and kill it
        cmd = 'for /f "tokens=5" %a in (\'netstat -aon ^| findstr :8000\') do taskkill /f /pid %a >nul 2>&1'
        os.system(cmd)
    else:
        os.system("fuser -k 8000/tcp >/dev/null 2>&1")
    
    time.sleep(2)

    # Start server in background
    print("Starting PlateZero server...")
    server = subprocess.Popen(["python", "QR_attendance/qr.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3) # Wait for server to start

    try:
        test_full_flow()
    finally:
        print("Stopping server...")
        server.terminate()
        server.wait()
        
        # Cleanup
        if os.path.exists(PLATE_IMG):
            try:
                os.remove(PLATE_IMG)
                print(f"Deleted {PLATE_IMG}")
            except Exception as e:
                print(f"Failed to delete image: {e}")

if __name__ == "__main__":
    run_tests()
