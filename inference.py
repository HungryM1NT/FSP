import easyocr
import re
import json
import argparse
import os
from pdf2image import convert_from_path
import numpy as np


class ReceiptExtractor:
    def __init__(self, lang_list=['en'], use_gpu=True):
        self.reader = easyocr.Reader(lang_list, gpu=use_gpu)

    def extract_entities(self, text_lines):
        full_text = " ".join(text_lines).upper()
        extracted = {
            "company": "UNKNOWN",
            "date": "UNKNOWN",
            "total": "UNKNOWN"
        }
        
        # DD/MM/YYYY   DD-MM-YYYY
        date_match = re.search(r'\b\d{2}[/-]\d{2}[/-]\d{4}\b', full_text)
        if date_match:
            extracted["date"] = date_match.group(0)
            
        total_idx = -1
        # Ищем строку, где есть ключевые слова
        for i, line in enumerate(text_lines):
            if "TOTAL" in line.upper() or "AMOUNT" in line.upper() or "CASH" in line.upper():
                total_idx = i
                break
                
        # Если нашли - берем текущую строку и две следующие
        if total_idx != -1:
            search_area = " ".join(text_lines[total_idx:total_idx+3]).upper()
            amounts = re.findall(r'\b\d+\.\d{2}\b', search_area)
            if amounts:
                extracted["total"] = f"{max([float(a) for a in amounts]):.2f}"
        
        # Если не нашли сумму - ищем максимальное число с лимитом от телефонов и прочих данных
        if extracted["total"] == "UNKNOWN":
            all_amounts = re.findall(r'\b\d+\.\d{2}\b', full_text)
            valid_amounts = [float(a) for a in all_amounts if float(a) < 10000]
            if valid_amounts:
                extracted["total"] = f"{max(valid_amounts):.2f}"

        # Ищем первую строку с буквами длиннее 3 символов для наименования компании
        for line in text_lines:
            cleaned = line.strip()
            if len(cleaned) > 3 and re.search('[A-Z]', cleaned.upper()):
                extracted["company"] = cleaned
                break
                
        return extracted

    def predict(self, file_path):
        if not os.path.exists(file_path):
            return {"error": f"Файл {file_path} не найден."}

        text_lines = []
        ext = file_path.lower().split('.')[-1]

        try:
            if ext == 'pdf':
                images = convert_from_path(file_path)
                
                for img in images:
                    img_array = np.array(img)
                    results = self.reader.readtext(img_array)
                    text_lines.extend([res[1] for res in results])
            else:
                results = self.reader.readtext(file_path)
                text_lines = [res[1] for res in results]
                
            return self.extract_entities(text_lines)
            
        except Exception as e:
            return {"error": f"Ошибка обработки файла: {str(e)}"}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Инференс модели извлечения данных из чеков")
    parser.add_argument("--image", type=str, required=True, help="Путь к изображению чека")
    parser.add_argument("--gpu", action="store_true", help="Использовать GPU для ускорения")
    
    args = parser.parse_args()

    extractor = ReceiptExtractor(use_gpu=args.gpu)
    
    result = extractor.predict(args.image)
    
    print(json.dumps(result, indent=4, ensure_ascii=False))