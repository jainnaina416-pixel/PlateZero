from fastapi import APIRouter, File, UploadFile
import os
import tempfile
from vision_ai.predict import predict_image

router = APIRouter()

@router.post("/analyze_sanitation")
async def analyze_sanitation(file: UploadFile = File(...)):
    temp_dir = tempfile.gettempdir()
    temp_path = os.path.join(temp_dir, "temp_upload.jpg")
    
    with open(temp_path, "wb") as buffer:
        buffer.write(await file.read())
        
    result = predict_image(temp_path)
    
    if os.path.exists(temp_path):
        try: os.remove(temp_path)
        except: pass
        
    return result
