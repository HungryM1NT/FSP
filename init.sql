CREATE TABLE IF NOT EXISTS users (
    user_id SERIAL PRIMARY KEY,
    username VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_files (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
    file_name VARCHAR(255),
    file_path VARCHAR(255),
    ocr_name VARCHAR(255),
    ocr_date VARCHAR(50),
    ocr_sum VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);