"""Quick test for M-A-E-B PDF generation"""
import os
os.environ.setdefault('GEMINI_API_KEY', 'test')
os.environ.setdefault('ROBOFLOW_API_KEY', 'test')

import sys
import pytz

# Mock doctor_database
class MockDB:
    INDIA_TIMEZONE = pytz.timezone('Asia/Kolkata')
sys.modules['doctor_database'] = MockDB()

# Now import after mocking
from app import generate_prescription_pdf

data = {
    "name": "Ravi",
    "age": "45 years",
    "gender": "Male",
    "phone_number": "+917144428116",
    "patient_id": "PT-123",
    "doctor_name": "Dr. Sathish",
    "clinic": "SHRI DURGA CLINIC",
    "clinic_tagline": "HEALTH IS WEALTH",
    "address": "Udupi",
    "phone": "+91 7484428116",
    "email": "glynhs@gmail.com",
    "visit_id": "VIS-TEST",
    "medicines": [
        {
            "name": "Cetirizine",
            "dosage": "50 mg",
            "frequency": "Twice daily",
            "duration": "70",
            "timing": ["Evening", "Bedtime"],
            "food_instruction": "After food",
            "special_instructions": "",
        },
        {
            "name": "Paracetamol",
            "dosage": "500 mg",
            "frequency": "Once daily",
            "duration": "5 days",
            "timing": ["Morning"],
            "food_instruction": "",
            "special_instructions": "",
        }
    ]
}

filepath = "generated/test_maeb_quick.pdf"
url = "http://test.com/download"

print("Generating PDF with M-A-E-B column...")
try:
    generate_prescription_pdf(data, url, filepath)
    print(f"SUCCESS: PDF created at {filepath}")
    print(f"Size: {os.path.getsize(filepath)} bytes")
    print("\nExpected columns: Medicine Name | Dosage | Dose M-A-E-B | Duration")
    print("Expected values:")
    print("  Cetirizine: 0-0-1-1 (Evening, Bedtime)")
    print("  Paracetamol: 1-0-0-0 (Morning)")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
