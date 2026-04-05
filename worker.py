import os
from celery import Celery
from inference import ReceiptExtractor
import database as db

REDIS_URL = os.environ["REDIS_URL"]

celery_app = Celery("ocr_worker", broker=REDIS_URL, backend=REDIS_URL)

extractor = ReceiptExtractor(use_gpu=True) 

@celery_app.task(name="process_scan")
def process_scan(user_id: int, file_name: str, file_location: str):
    try:
        result = extractor.predict(file_location)
        
        ocr_date = result.get("date", "Не найдено")
        ocr_sum = result.get("total", "Не найдено")
        ocr_name = result.get("company", "Документ")
        
        inserted_file = db.insert_document(user_id, file_name, file_location, ocr_name, ocr_date, ocr_sum)
        
        return {
            "id": inserted_file[0],
            "file_name": file_name,
            "file_url": f"http://localhost:8000/{file_location}",
            "ocr_name": ocr_name,
            "ocr_date": ocr_date,
            "ocr_sum": ocr_sum,
            "created_at": inserted_file[1].strftime("%H:%M %d.%m.%Y")
        }
    except Exception as e:
        raise e