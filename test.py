import easyocr
reader = easyocr.Reader(['en']) # this needs to run only once to load the model into memory
result = reader.readtext('./docs/doc1.jpg', detail=0)
print(result)