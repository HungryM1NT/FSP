from fastapi import FastAPI, File, UploadFile
import easyocr
import numpy as np
import cv2


app = FastAPI()
reader = easyocr.Reader(['ru'])


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    try:
        contents = await file.read()

        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        result = reader.readtext(img, detail=0) 
        return{'result': result}
    
    except Exception as e:
        return {'error': str(e)}
