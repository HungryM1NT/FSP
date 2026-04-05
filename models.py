from pydantic import BaseModel, EmailStr, Field

class UserCreate(BaseModel):
    username: str = Field(..., min_length=4) 
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=72)

class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)

class Token(BaseModel):
    access_token: str
    token_type: str
    username: str

class UserOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    
class DocumentUpdate(BaseModel):
    file_name: str
    ocr_name: str
    ocr_date: str
    ocr_sum: str