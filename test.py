import easyocr
reader = easyocr.Reader(['ru']) # this needs to run only once to load the model into memory
result = reader.readtext('test_data3.png', detail=0)
print(result)