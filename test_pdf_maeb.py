"""Test the updated PDF with Dose M-A-E-B column instead of Frequency"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

# Set up minimal environment
os.environ.setdefault('GEMINI_API_KEY', 'test_key')
os.environ.setdefault('ROBOFLOW_API_KEY', 'test_key')

from datetime import datetime
import pytz

# Create a minimal doctor_db module for testing
class MockDoctorDB:
    INDIA_TIMEZONE = pytz.timezone('Asia/Kolkata')

sys.modules['doctor_database'] = type(sys)('doctor_database')
sys.modules['doctor_database'].INDIA_TIMEZONE = pytz.timezone('Asia/Kolkata')

from app import generate_prescription_pdf

print("=" * 80)
print("Testing PDF Generation with Dose M-A-E-B Column")
print("=" * 80)

# Test data with timing information
test_data = {
    "name": "Test Patient",
    "age": "45 years",
    "gender": "Male",
    "phone_number": "+917144428116",
    "patient_id": "PT-TEST456",
    "doctor_name": "Dr. Test Doctor",
    "doctor": "Dr. Test Doctor",
    "clinic": "SHRI DURGA CLINIC",
    "clinic_name": "SHRI DURGA CLINIC",
    "clinic_tagline": "HEALTH IS WEALTH",
    "address": "Test Address, Test City",
    "phone": "+91 1234567890",
    "email": "test@clinic.com",
    "visit_id": "VIS-TESTMAEB123",
    "medicines": [
        {
            "name": "Cetirizine",
            "dosage": "50 mg",
            "frequency": "Twice daily",  # This should NOT appear in PDF
            "duration": "7 days",
            "timing": ["Evening", "Bedtime"],  # Should show as 0-0-1-1
            "food_instruction": "After food",
            "special_instructions": "",
            "instructions": ""
        },
        {
            "name": "Paracetamol",
            "dosage": "500 mg",
            "frequency": "Once daily",  # This should NOT appear in PDF
            "duration": "5 days",
            "timing": ["Morning"],  # Should show as 1-0-0-0
            "food_instruction": "After food",
            "special_instructions": "",
            "instructions": ""
        },
        {
            "name": "Amoxicillin",
            "dosage": "250 mg",
            "frequency": "Three times daily",  # This should NOT appear in PDF
            "duration": "10 days",
            "timing": ["Morning", "Afternoon", "Evening"],  # Should show as 1-1-1-0
            "food_instruction": "Before food",
            "special_instructions": "Take with water",
            "instructions": "Take with water"
        },
        {
            "name": "Dolo",
            "dosage": "650 mg",
            "frequency": "Four times daily",  # This should NOT appear in PDF
            "duration": "3 days",
            "timing": ["Morning", "Afternoon", "Evening", "Bedtime"],  # Should show as 1-1-1-1
            "food_instruction": "",
            "special_instructions": "",
            "instructions": ""
        }
    ]
}

output_path = os.path.join("generated", "test_prescription_maeb.pdf")
download_url = "http://localhost:5000/download/test_prescription_maeb.pdf"

print("\nTest Data:")
print(f"Patient: {test_data['name']}")
print(f"Medicines: {len(test_data['medicines'])}")
print("\nExpected M-A-E-B values:")
for med in test_data['medicines']:
    timing = med.get('timing', [])
    m = '1' if 'Morning' in timing else '0'
    a = '1' if 'Afternoon' in timing else '0'
    e = '1' if 'Evening' in timing else '0'
    b = '1' if 'Bedtime' in timing else '0'
    dose_maeb = f"{m}-{a}-{e}-{b}"
    print(f"  {med['name']}: {dose_maeb}")

print("\n" + "-" * 80)
print("Generating PDF...")
print("-" * 80)

try:
    generate_prescription_pdf(test_data, download_url, output_path)
    print(f"\n✓ PDF generated successfully: {output_path}")
    
    if os.path.exists(output_path):
        size = os.path.getsize(output_path)
        print(f"  File size: {size:,} bytes")
        if size > 0:
            print("  ✓ PDF file is valid (non-empty)")
            print("\n" + "=" * 80)
            print("VALIDATION CHECKLIST:")
            print("=" * 80)
            print("Please open the PDF and verify:")
            print("  [ ] Exactly 4 columns in medicine table")
            print("  [ ] Column 1: Medicine Name")
            print("  [ ] Column 2: Dosage")
            print("  [ ] Column 3: Dose M-A-E-B (format: X-X-X-X)")
            print("  [ ] Column 4: Duration")
            print("  [ ] NO Frequency column present")
            print("  [ ] Cetirizine shows: 0-0-1-1")
            print("  [ ] Paracetamol shows: 1-0-0-0")
            print("  [ ] Amoxicillin shows: 1-1-1-0")
            print("  [ ] Dolo shows: 1-1-1-1")
            print("  [ ] QR code present and scannable")
            print("  [ ] Digital signature present")
            print("  [ ] No overlapping columns")
            print("=" * 80)
        else:
            print("  ✗ WARNING: PDF file is empty")
    else:
        print("  ✗ ERROR: PDF file was not created")
        
except Exception as e:
    print(f"\n✗ PDF generation failed: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
print("Test completed!")
print("=" * 80)
print(f"\nPDF Location: {os.path.abspath(output_path)}")
print("Open this file to verify the table structure.")
