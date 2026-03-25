from fastapi import FastAPI, File, UploadFile, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import easyocr
import re
# import numpy as np
import cv2
from models import *
import os
from dotenv import load_dotenv
import psycopg2
from passlib.context import CryptContext
from datetime import datetime, timedelta
from jose import JWTError, jwt
import hashlib
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import shutil


load_dotenv()

# DATABASE
database = os.environ['POSTGRES_DB']
user = os.environ['POSTGRES_USER']
password = os.environ['POSTGRES_DB_PASSWORD']
conn = psycopg2.connect(database=database,
                        user=user,
                        password=password,
                        host="localhost",
                        port="5432", )
cursor = conn.cursor()

# HASH
SECRET_KEY = os.environ['HASH_SECRET_KEY']
ALGORITHM = os.environ['HASH_ALGORITHM']
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        cursor.execute("SELECT * FROM users WHERE email = %s;", (email,))
        user = cursor.fetchone()
        conn.commit()
        if user is None: raise HTTPException(status_code=401)
        return {"id": user[0], "username": user[1], "email": user[2]}
    except JWTError:
        raise HTTPException(status_code=401)

# FASTAPI
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/storage", StaticFiles(directory="storage"), name="storage")

# EasyOCR
reader = easyocr.Reader(['en'])

@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...), 
    current_user: dict = Depends(get_current_user),
):

    os.makedirs("storage", exist_ok=True)
    file_location = f"storage/{file.filename}"
    
    with open(file_location, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    

    img = cv2.imread(file_location)
    results = reader.readtext(img, detail=0)
    text_block = " ".join(results)
    

    date_match = re.search(r'\d{2}/\d{2}/\d{4}', text_block)
    ocr_date = date_match.group(0) if date_match else "Не найдено"
    
    sum_match = re.search(r'TOTAL[:\s]*([\d\.,]+)', text_block, re.IGNORECASE)
    ocr_sum = sum_match.group(1) if sum_match else "Не найдено"
    
    ocr_name = "Документ"
    if "Cash Bill" in text_block: ocr_name = "Cash Bill"
    elif "Invoice" in text_block: ocr_name = "Invoice"

    cursor.execute("""
        INSERT INTO user_files (user_id, file_name, file_path, ocr_name, ocr_date, ocr_sum) 
        VALUES (%s, %s, %s, %s, %s, %s) RETURNING id, created_at;
    """, (current_user["id"], file.filename, file_location, ocr_name, ocr_date, ocr_sum))
    
    inserted_file = cursor.fetchone()
    conn.commit()
    
    return {
        "id": inserted_file[0],
        "file_name": file.filename,
        "file_url": f"http://localhost:8000/{file_location}",
        "ocr_name": ocr_name,
        "ocr_date": ocr_date,
        "ocr_sum": ocr_sum,
        "created_at": inserted_file[1].strftime("%H:%M %d.%m.%Y")
    }
    
    
@app.post("/register", status_code=201)
async def register(user: UserCreate):
    cursor.execute("SELECT * FROM users WHERE email = %s;", (user.email,))
    db_user = cursor.fetchone()
    conn.commit()
    if db_user:
        raise HTTPException(status_code=400, detail="User already exists")
    
    hashed_password = hash_password(user.password)
    
    cursor.execute("INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s);", (user.username, user.email, hashed_password))
    conn.commit()
    
    cursor.execute("SELECT * FROM users WHERE email = %s;", (user.email,))
    new_user = cursor.fetchone()
    conn.commit()
    
    new_user = {"id": new_user[0],
                "username": new_user[1],
                "email": new_user[2]}
    return new_user


@app.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    cursor.execute("SELECT * FROM users WHERE email = %s;", (form_data.username,))
    db_user = cursor.fetchone()
    conn.commit()
    if not db_user or not verify_password(form_data.password, db_user[3]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    access_token = create_access_token(data={"sub": db_user[2]})
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "username": db_user[1] 
    }
    
@app.delete("/documents/{doc_id}")
def delete_document(doc_id: int, current_user: dict = Depends(get_current_user)):
    cursor.execute("SELECT file_path FROM user_files WHERE id = %s AND user_id = %s;", (doc_id, current_user["id"]))
    file_record = cursor.fetchone()
    
    if not file_record:
        raise HTTPException(status_code=404, detail="Документ не найден или у вас нет прав на его удаление")
    
    file_path = file_record[0]
    
    cursor.execute("DELETE FROM user_files WHERE id = %s;", (doc_id,))
    conn.commit()
    
    if os.path.exists(file_path):
        os.remove(file_path)
        
    return {"message": "Документ успешно удален"}

@app.get("/documents")
async def get_documents(current_user: dict = Depends(get_current_user)):
    cursor.execute("""
        SELECT id, file_name, file_path, ocr_name, ocr_date, ocr_sum, created_at 
        FROM user_files 
        WHERE user_id = %s 
        ORDER BY created_at DESC;
    """, (current_user["id"],))
    records = cursor.fetchall()
    conn.commit()
    
    documents = []
    for row in records:
        documents.append({
            "id": row[0],
            "file_name": row[1],
            "file_url": f"http://localhost:8000/{row[2]}",
            "ocr_name": row[3],
            "ocr_date": row[4],
            "ocr_sum": row[5],
            "created_at": row[6].strftime("%H:%M %d.%m.%Y")
        })
    return documents