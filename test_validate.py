from app import validate_prescription_text, clean_prescription_text, parse_prescription

text = "Vijeta 20, female, Paracetamol 500MG, one per day for one week. Citrus and twice a day for three weeks."
print('raw:', text)
print('cleaned:', clean_prescription_text(text))
print('validate:', validate_prescription_text(text))
print('parse:', parse_prescription(clean_prescription_text(text)))
