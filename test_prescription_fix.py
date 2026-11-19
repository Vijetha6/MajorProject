"""
Test the improved prescription parsing with problematic voice transcripts
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app import (
    extract_medicines_from_voice_transcript,
    parse_medicine_segment,
    is_likely_medicine_name,
    generate_prescription_pdf
)

# Test case 1: The problematic transcript from the second PDF
problematic_transcript = """
Hello doctor speaking I am for the patient paracetamol Uh for the five after food
prescribe cetirizine Uh 10 mg Twice daily 3 day
prescribed dollar 650 mill Dose not specified Twice daily One
take adequate risk rest Uh Dose not specified As directed As directed
for the prescription Recording completed
"""

print("=" * 80)
print("TEST 1: Problematic Voice Transcript")
print("=" * 80)
print(f"Input: {problematic_transcript}\n")

medicines = extract_medicines_from_voice_transcript(problematic_transcript)
print(f"\nExtracted {len(medicines)} medicines:\n")
for idx, med in enumerate(medicines, 1):
    print(f"Medicine {idx}:")
    print(f"  Name: {med['name']}")
    print(f"  Dosage: {med['dosage']}")
    print(f"  Frequency: {med['frequency']}")
    print(f"  Duration: {med['duration']}")
    print(f"  Food: {med.get('food_instruction', '')}")
    print(f"  Instructions: {med.get('special_instructions', '')}")
    print()

# Test case 2: Clean prescription
clean_prescription = """
Prescribe Paracetamol 500 mg once daily for 5 days after food.
Also prescribe Cetirizine 10 mg twice daily for 3 days before food.
Prescribe Dolo 650 mg twice daily for 2 weeks after food.
Patient should drink plenty of water and take adequate rest.
"""

print("\n" + "=" * 80)
print("TEST 2: Clean Prescription")
print("=" * 80)
print(f"Input: {clean_prescription}\n")

medicines = extract_medicines_from_voice_transcript(clean_prescription)
print(f"\nExtracted {len(medicines)} medicines:\n")
for idx, med in enumerate(medicines, 1):
    print(f"Medicine {idx}:")
    print(f"  Name: {med['name']}")
    print(f"  Dosage: {med['dosage']}")
    print(f"  Frequency: {med['frequency']}")
    print(f"  Duration: {med['duration']}")
    print(f"  Food: {med.get('food_instruction', '')}")
    print()

# Test case 3: Test is_likely_medicine_name
print("\n" + "=" * 80)
print("TEST 3: Medicine Name Detection")
print("=" * 80)

test_names = [
    "Paracetamol",
    "Hello doctor speaking",
    "take adequate rest",
    "Cetirizine",
    "drink plenty of water",
    "Dolo 650",
    "recording completed",
    "prescribed dollar",
    "Amoxicillin"
]

for name in test_names:
    is_medicine = is_likely_medicine_name(name)
    print(f"  '{name}' -> {'MEDICINE' if is_medicine else 'NOT MEDICINE'}")

print("\n" + "=" * 80)
print("TEST 4: Generate Sample PDF")
print("=" * 80)

# Create a test prescription PDF
test_data = {
    "name": "Test Patient",
    "age": "34 years",
    "gender": "Male",
    "phone_number": "+915674836527",
    "patient_id": "PT-TEST123",
    "doctor_name": "Dr. Test Doctor",
    "doctor": "Dr. Test Doctor",
    "clinic": "Test Clinic",
    "clinic_name": "Test Clinic",
    "address": "Test Address, Test City",
    "phone": "+91 1234567890",
    "email": "test@clinic.com",
    "visit_id": "VIS-TEST123",
    "medicines": [
        {
            "name": "Paracetamol",
            "dosage": "500 mg",
            "frequency": "Once daily",
            "duration": "5 days",
            "timing": ["Morning"],
            "food_instruction": "After food",
            "special_instructions": "",
            "instructions": ""
        },
        {
            "name": "Cetirizine",
            "dosage": "10 mg",
            "frequency": "Twice daily",
            "duration": "3 days",
            "timing": [],
            "food_instruction": "Before food",
            "special_instructions": "",
            "instructions": ""
        },
        {
            "name": "Dolo",
            "dosage": "650 mg",
            "frequency": "Twice daily",
            "duration": "2 weeks",
            "timing": [],
            "food_instruction": "After food",
            "special_instructions": "",
            "instructions": ""
        }
    ]
}

output_path = os.path.join("generated", "test_prescription_fixed.pdf")
download_url = "http://localhost:5000/download/test_prescription_fixed.pdf"

try:
    generate_prescription_pdf(test_data, download_url, output_path)
    print(f"✓ PDF generated successfully: {output_path}")
    
    if os.path.exists(output_path):
        size = os.path.getsize(output_path)
        print(f"  File size: {size} bytes")
        if size > 0:
            print("  ✓ PDF file is valid (non-empty)")
        else:
            print("  ✗ WARNING: PDF file is empty")
    else:
        print("  ✗ ERROR: PDF file was not created")
        
except Exception as e:
    print(f"✗ PDF generation failed: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
print("All tests completed!")
print("=" * 80)
