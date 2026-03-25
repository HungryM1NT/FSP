import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

database = os.environ['POSTGRES_DB']
user = os.environ['POSTGRES_USER']
password = os.environ['POSTGRES_DB_PASSWORD']

conn = psycopg2.connect(
    database=database,
    user=user,
    password=password,
    host="localhost",
    port="5432"
)
cursor = conn.cursor()


def get_user_by_email(email: str):
    cursor.execute("SELECT * FROM users WHERE email = %s;", (email,))
    return cursor.fetchone()

def create_user(username: str, email: str, hashed_password: str):
    cursor.execute(
        "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s) RETURNING id, username, email;", 
        (username, email, hashed_password)
    )
    conn.commit()
    return cursor.fetchone()

def insert_document(user_id: int, file_name: str, file_path: str, ocr_name: str, ocr_date: str, ocr_sum: str):
    cursor.execute("""
        INSERT INTO user_files (user_id, file_name, file_path, ocr_name, ocr_date, ocr_sum) 
        VALUES (%s, %s, %s, %s, %s, %s) RETURNING id, created_at;
    """, (user_id, file_name, file_path, ocr_name, ocr_date, ocr_sum))
    inserted_file = cursor.fetchone()
    conn.commit()
    return inserted_file

def get_document_by_id_and_user(doc_id: int, user_id: int):
    cursor.execute("SELECT file_path FROM user_files WHERE id = %s AND user_id = %s;", (doc_id, user_id))
    return cursor.fetchone()

def delete_document_by_id(doc_id: int):
    cursor.execute("DELETE FROM user_files WHERE id = %s;", (doc_id,))
    conn.commit()

def get_user_documents(user_id: int):
    cursor.execute("""
        SELECT id, file_name, file_path, ocr_name, ocr_date, ocr_sum, created_at 
        FROM user_files 
        WHERE user_id = %s 
        ORDER BY created_at DESC;
    """, (user_id,))
    return cursor.fetchall()