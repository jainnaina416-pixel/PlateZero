import fraud_detection
import os
import shutil
from PIL import Image
import numpy as np

def test_fraud_detection():
    print("--- Testing Fraud Detection Module ---")
    
    # Init DB
    if os.path.exists("image_hashes.db"):
        os.remove("image_hashes.db")
    fraud_detection.init_hash_db()
    
    test_image = "plate.jpg"
    if not os.path.exists(test_image):
        print(f"Error: {test_image} not found. Creating a dummy image.")
        dummy_img = Image.fromarray(np.uint8(np.random.rand(512, 512, 3) * 255))
        dummy_img.save(test_image)

    # 1. Test Time
    print("\n[1] Testing check_time:")
    meals = ["breakfast", "lunch", "dinner", "invalid"]
    for meal in meals:
        res = fraud_detection.check_time(meal)
        print(f"  - {meal}: {res}")

    # 2. Test Location
    print("\n[2] Testing check_location:")
    # DINING_LOCATION = (28.7041, 77.1025)
    locs = [
        (28.7041, 77.1025, True),   # Exact
        (28.7045, 77.1030, True),   # Close
        (29.0, 78.0, False)         # Far
    ]
    for lat, lon, expected in locs:
        res = fraud_detection.check_location(lat, lon)
        print(f"  - ({lat}, {lon}): {res} (Expected: {expected})")

    # 3. Test Duplicate/Similar
    print("\n[3] Testing check_duplicate_or_similar:")
    res1 = fraud_detection.check_duplicate_or_similar(test_image, "S1", "lunch")
    print(f"  - First submission: {res1}")
    
    res2 = fraud_detection.check_duplicate_or_similar(test_image, "S1", "lunch")
    print(f"  - Duplicate (same student): {res2}")
    
    res3 = fraud_detection.check_duplicate_or_similar(test_image, "S2", "lunch")
    print(f"  - Duplicate (different student): {res3}")

    # 4. Test Screen Capture
    print("\n[4] Testing check_screen_capture:")
    res_real = fraud_detection.check_screen_capture(test_image)
    print(f"  - Real image ({test_image}): {res_real}")
    
    # Create a "smooth" image to trigger Signal 3 (noise floor)
    smooth_img_path = "smooth_test.jpg"
    smooth_img = Image.new("RGB", (512, 512), (200, 200, 200))
    smooth_img.save(smooth_img_path)
    res_smooth = fraud_detection.check_screen_capture(smooth_img_path)
    print(f"  - Smooth image: {res_smooth}")
    
    # Create an image with periodic pattern to trigger Signal 2 (FFT)
    pattern_img_path = "pattern_test.jpg"
    data = np.zeros((512, 512))
    for i in range(0, 512, 8):
        data[i, :] = 255
    for j in range(0, 512, 8):
        data[:, j] = 255
    pattern_img = Image.fromarray(np.uint8(data)).convert("RGB")
    pattern_img.save(pattern_img_path)
    res_pattern = fraud_detection.check_screen_capture(pattern_img_path)
    print(f"  - Pattern image: {res_pattern}")

if __name__ == "__main__":
    test_fraud_detection()
