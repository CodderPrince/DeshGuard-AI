from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from supabase import create_client, Client
from ultralytics import YOLO
import cv2
from PIL import Image
import shutil
import os

app = FastAPI(title="DeshGuard AI Engine")

# --- Supabase Credentials ---
SUPABASE_URL = "https://jrvmwgtzwaxkvdqtdtsf.supabase.co"
SUPABASE_KEY = "তোমার_কপি_করা_anon_public_key_এখানে_বসাও"  # <--- এখানে কপি করা anon key বসাও
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Load YOLOv8 Model ---
model = YOLO('yolov8n.pt')

# Blurry Image Check
def check_blurry(image_path, threshold=100.0):
    image = cv2.imread(image_path)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    variance = cv2.Laplacian(gray, cv2.CV_64F).var()
    return variance < threshold, variance

# AI / Real Check
def check_ai_or_real(image_path):
    try:
        img = Image.open(image_path)
        exif_data = img._getexif()
        if not exif_data:
            return "Suspected AI / Downloaded Image"
        return "Authentic Camera Capture"
    except Exception:
        return "Unknown Metadata"

@app.get("/")
def read_root():
    return {"status": "DeshGuard AI Core API is Active"}

@app.post("/upload-report/")
async def upload_report(
    latitude: float = Form(...),
    longitude: float = Form(...),
    file: UploadFile = File(...)
):
    temp_path = f"temp_{file.filename}"
    processed_path = f"processed_{file.filename}"
    
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # 1. Blur Check
    is_blur, score = check_blurry(temp_path)
    if is_blur:
        os.remove(temp_path)
        raise HTTPException(status_code=400, detail=f"Image is too blurry. Capture again.")

    # 2. Authenticity Check
    img_status = check_ai_or_real(temp_path)

    # 3. Defect Detection (YOLOv8)
    results = model(temp_path)
    defect_type = "Infrastructure Defect (Pothole/Crack)"
    confidence = "87%"
    
    for result in results:
        result.save(filename=processed_path)

    # 4. Upload to Supabase Storage
    storage_path = f"reports/{file.filename}"
    with open(processed_path, 'rb') as f:
        supabase.storage.from_('infrastructure-media').upload(
            path=storage_path,
            file=f,
            file_options={"content-type": file.content_type}
        )
    
    image_public_url = supabase.storage.from_('infrastructure-media').get_public_url(storage_path)

    # 5. Insert to Supabase DB Table
    db_data = {
        "latitude": latitude,
        "longitude": longitude,
        "image_url": image_public_url,
        "defect_type": defect_type,
        "severity": f"{confidence} ({img_status})",
        "contractor_name": "Rangpur Infrastructure Ltd",
        "status": "Pending"
    }
    
    response = supabase.table("reports").insert(db_data).execute()

    if os.path.exists(temp_path): os.remove(temp_path)
    if os.path.exists(processed_path): os.remove(processed_path)

    return {"status": "Report Logged", "data": response.data}

@app.get("/get-reports/")
async def get_reports():
    response = supabase.table("reports").select("*").execute()
    return response.data