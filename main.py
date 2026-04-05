from fastapi import FastAPI, File, UploadFile, HTTPException, status, Depends, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from models import *
import os
from dotenv import load_dotenv
from passlib.context import CryptContext
from datetime import datetime, timedelta
from jose import JWTError, jwt
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import shutil
import database as db
from worker import process_scan, celery_app
import logging
from prometheus_fastapi_instrumentator import Instrumentator

load_dotenv()

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

def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        
        user = db.get_user_by_email(email)
        if user is None: 
            raise HTTPException(status_code=401)
        return {"id": user[0], "username": user[1], "email": user[2]}
    except JWTError:
        raise HTTPException(status_code=401)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/storage", StaticFiles(directory="storage"), name="storage")


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("api_logger")

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Входящий запрос: {request.method} {request.url.path}")
    response = await call_next(request)
    logger.info(f"Запрос завершен: {request.method} {request.url.path} - Статус: {response.status_code}")
    return response

Instrumentator().instrument(app).expose(app, endpoint="/metrics")

@app.post("/upload")
def upload_file(
    file: UploadFile = File(...), 
    current_user: dict = Depends(get_current_user),
):
    os.makedirs("storage", exist_ok=True)
    file_location = f"storage/{file.filename}"
    
    with open(file_location, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    task = process_scan.delay(current_user["id"], file.filename, file_location)
    
    return {
        "task_id": task.id,
        "status": "В очереди на обработку",
        "file_name": file.filename
    }

@app.get("/tasks/{task_id}")
def get_task_status(task_id: str):
    task_result = celery_app.AsyncResult(task_id)
    return {
        "task_id": task_id,
        "status": task_result.status,
        "result": task_result.result if task_result.ready() else None
    }
    
@app.post("/register", status_code=201)
def register(user: UserCreate):
    db_user = db.get_user_by_email(user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="User already exists")
    
    hashed_password = hash_password(user.password)
    new_user = db.create_user(user.username, user.email, hashed_password)
    
    return {"id": new_user[0], "username": new_user[1], "email": new_user[2]}

@app.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    db_user = db.get_user_by_email(form_data.username)
    
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
    file_record = db.get_document_by_id_and_user(doc_id, current_user["id"])
    
    if not file_record:
        raise HTTPException(status_code=404, detail="Документ не найден или у вас нет прав на его удаление")
    
    file_path = file_record[0]
    db.delete_document_by_id(doc_id)
    
    if os.path.exists(file_path):
        os.remove(file_path)
        
    return {"message": "Документ успешно удален"}

@app.get("/documents")
def get_documents(current_user: dict = Depends(get_current_user)):
    records = db.get_user_documents(current_user["id"])
    
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

@app.put("/documents/{doc_id}")
def update_document(doc_id: int, doc_update: DocumentUpdate, current_user: dict = Depends(get_current_user)):
    updated = db.update_document_fields(
        doc_id, 
        current_user["id"], 
        doc_update.file_name, 
        doc_update.ocr_name, 
        doc_update.ocr_date, 
        doc_update.ocr_sum
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Документ не найден или у вас нет прав на его изменение")
    
    return {"message": "Документ успешно обновлен"}