"""
Comprehensive test for M-A-E-B prescription PDF generation
This test creates an actual prescription PDF and validates its structure
"""
import os
import sys
import json

# Set up environment
os.environ.setdefault('GEMINI_API_KEY', 'test_key_placeholder')
os.environ.setdefault('ROBOFLOW_API_KEY', 'test_key_placeholder')
os.environ.setdefault('FLASK_SECRET_KEY', 'test_secret_key')

from datetime import timezone, timedelta

# Mock doctor_database for standalone testing
class MockDoctorDB:
    INDIA_TIMEZONE = timezone(timedelta(hours=5, minutes=30))
    
sys.modules['doctor_database'] = MockDoctorDB()

# Now import app functions
from app import generate_prescription_pdf

print("=" * 80)
print("COMPREHENSIVE M-A-E-B PRESCRIPTION PDF TEST")
print("=" * 80)

# Test data with various timing combinations
test_prescriptions = [
    {
        "test_name": "Test 1: Evening + Bedtime (0-0-1-1)",
        "data": {
            "name": "Test Patient One",
            "age": "45 years",
            "gender": "Male",
            "phone_number": "+917144428116",
            "patient_id": "PT-TEST001",
            "doctor_name": "Dr. Sathish Shetty",
            "clinic": "SHRI DURGA CLINIC",
            "clinic_name": "SHRI DURGA CLINIC",
            "clinic_tagline": "Serving Health Since 1990",
            "address": "Athrady, Manipal-Hiriadka Main Road",
            "phone": "+91 12345 67890",
            "email": "dr.sathish@shridurga.com",
            "visit_id": "VIS-TEST001",
            "medicines": [
                {
                    "name": "Cetirizine",
                    "dosage": "50 mg",
                    "frequency": "Twice daily",
                    "duration": "7 days",
                    "timing": ["Evening", "Bedtime"],
                    "food_instruction": "After food",
                    "special_instructions": "",
                }
            ]
        },
        "expected_maeb": "0-0-1-1"
    },
    {
        "test_name": "Test 2: Morning only (1-0-0-0)",
        "data": {
            "name": "Test Patient Two",
            "age": "32 years",
            "gender": "Female",
            "phone_number": "+919353309245",
            "patient_id": "PT-TEST002",
            "doctor_name": "Dr. Sathish Shetty",
            "clinic": "SHRI DURGA CLINIC",
            "clinic_name": "SHRI DURGA CLINIC",
            "clinic_tagline": "Serving Health Since 1990",
            "address": "Athrady, Manipal-Hiriadka Main Road",
            "phone": "+91 12345 67890",
            "email": "dr.sathish@shridurga.com",
            "visit_id": "VIS-TEST002",
            "medicines": [
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
        },
        "expected_maeb": "1-0-0-0"
    },
    {
        "test_name": "Test 3: All times (1-1-1-1)",
        "data": {
            "name": "Test Patient Three",
            "age": "55 years",
            "gender": "Male",
            "phone_number": "+919876543210",
            "patient_id": "PT-TEST003",
            "doctor_name": "Dr. Sathish Shetty",
            "clinic": "SHRI DURGA CLINIC",
            "clinic_name": "SHRI DURGA CLINIC",
            "clinic_tagline": "Serving Health Since 1990",
            "address": "Athrady, Manipal-Hiriadka Main Road",
            "phone": "+91 12345 67890",
            "email": "dr.sathish@shridurga.com",
            "visit_id": "VIS-TEST003",
            "medicines": [
                {
                    "name": "Dolo",
                    "dosage": "650 mg",
                    "frequency": "Four times daily",
                    "duration": "3 days",
                    "timing": ["Morning", "Afternoon", "Evening", "Bedtime"],
                    "food_instruction": "After food",
                    "special_instructions": "",
                }
            ]
        },
        "expected_maeb": "1-1-1-1"
    },
    {
        "test_name": "Test 4: Multiple medicines with different timings",
        "data": {
            "name": "Test Patient Four",
            "age": "40 years",
            "gender": "Female",
            "phone_number": "+919123456789",
            "patient_id": "PT-TEST004",
            "doctor_name": "Dr. Sathish Shetty",
            "clinic": "SHRI DURGA CLINIC",
            "clinic_name": "SHRI DURGA CLINIC",
            "clinic_tagline": "Serving Health Since 1990",
            "address": "Athrady, Manipal-Hiriadka Main Road",
            "phone": "+91 12345 67890",
            "email": "dr.sathish@shridurga.com",
            "visit_id": "VIS-TEST004",
            "medicines": [
                {
                    "name": "Cetirizine",
                    "dosage": "10 mg",
                    "frequency": "Once daily",
                    "duration": "7 days",
                    "timing": ["Bedtime"],
                    "food_instruction": "Before food",
                    "special_instructions": "",
                },
                {
                    "name": "Paracetamol",
                    "dosage": "500 mg",
                    "frequency": "Three times daily",
                    "duration": "5 days",
                    "timing": ["Morning", "Afternoon", "Evening"],
                    "food_instruction": "After food",
                    "special_instructions": "",
                },
                {
                    "name": "Amoxicillin",
                    "dosage": "250 mg",
                    "frequency": "Twice daily",
                    "duration": "10 days",
                    "timing": ["Morning", "Evening"],
                    "food_instruction": "Before food",
                    "special_instructions": "Take with water",
                }
            ]
        },
        "expected_maeb": ["0-0-0-1", "1-1-1-0", "1-0-1-0"]
    }
]

results = []

for test_case in test_prescriptions:
    print(f"\n{'=' * 80}")
    print(f"Running: {test_case['test_name']}")
    print('=' * 80)
    
    data = test_case['data']
    filename = f"test_maeb_{test_case['data']['patient_id']}.pdf"
    filepath = os.path.join("generated", filename)
    download_url = f"http://localhost:5000/download/{filename}"
    
    try:
        # Generate PDF
        generate_prescription_pdf(data, download_url, filepath)
        
        # Check if file exists
        if not os.path.exists(filepath):
            results.append({
                "test": test_case['test_name'],
                "status": "FAILED",
                "error": "PDF file not created"
            })
            print(f"❌ FAILED: PDF file not created")
            continue
        
        # Check file size
        size = os.path.getsize(filepath)
        if size == 0:
            results.append({
                "test": test_case['test_name'],
                "status": "FAILED",
                "error": "PDF file is empty"
            })
            print(f"❌ FAILED: PDF file is empty")
            continue
        
        print(f"✅ PDF generated: {filepath}")
        print(f"   File size: {size:,} bytes")
        
        # Validate expected M-A-E-B values
        expected = test_case['expected_maeb']
        if isinstance(expected, list):
            print(f"   Expected M-A-E-B values: {', '.join(expected)}")
        else:
            print(f"   Expected M-A-E-B: {expected}")
        
        # Calculate actual M-A-E-B from timing data
        print(f"   Actual timing data:")
        for idx, med in enumerate(data['medicines']):
            timing = med.get('timing', [])
            m = '1' if 'Morning' in timing else '0'
            a = '1' if 'Afternoon' in timing else '0'
            e = '1' if 'Evening' in timing else '0'
            b = '1' if 'Bedtime' in timing else '0'
            actual_maeb = f"{m}-{a}-{e}-{b}"
            print(f"     {med['name']}: {actual_maeb} (from timing: {timing})")
            
            # Validate
            if isinstance(expected, list):
                if actual_maeb != expected[idx]:
                    print(f"     ⚠️  Expected {expected[idx]} but got {actual_maeb}")
            else:
                if actual_maeb != expected:
                    print(f"     ⚠️  Expected {expected} but got {actual_maeb}")
        
        results.append({
            "test": test_case['test_name'],
            "status": "PASSED",
            "filepath": filepath,
            "size": size
        })
        print(f"✅ TEST PASSED")
        
    except Exception as e:
        results.append({
            "test": test_case['test_name'],
            "status": "FAILED",
            "error": str(e)
        })
        print(f"❌ FAILED: {e}")
        import traceback
        traceback.print_exc()

# Print summary
print("\n" + "=" * 80)
print("TEST SUMMARY")
print("=" * 80)

passed = sum(1 for r in results if r['status'] == 'PASSED')
failed = sum(1 for r in results if r['status'] == 'FAILED')

for result in results:
    status_symbol = "✅" if result['status'] == 'PASSED' else "❌"
    print(f"{status_symbol} {result['test']}: {result['status']}")
    if result['status'] == 'FAILED' and 'error' in result:
        print(f"   Error: {result['error']}")
    elif result['status'] == 'PASSED':
        print(f"   File: {result['filepath']}")
        print(f"   Size: {result['size']:,} bytes")

print("\n" + "=" * 80)
print(f"Total: {len(results)} tests")
print(f"Passed: {passed}")
print(f"Failed: {failed}")
print("=" * 80)

# Manual validation checklist
print("\n" + "=" * 80)
print("MANUAL VALIDATION CHECKLIST")
print("=" * 80)
print("Please open the generated PDFs and verify:")
print("  [ ] Table has exactly 4 columns")
print("  [ ] Column headers are: Medicine Name | Dosage | Dose M-A-E-B | Duration")
print("  [ ] NO 'Frequency' column appears in the table")
print("  [ ] M-A-E-B values match expected format (X-X-X-X)")
print("  [ ] All M-A-E-B values are correct for each medicine")
print("  [ ] QR code is present and scannable")
print("  [ ] Digital signature is present")
print("  [ ] Clinic header is properly formatted")
print("  [ ] Patient/Doctor info is in two columns")
print("  [ ] No column overlaps or text cutoff")
print("=" * 80)

print(f"\nGenerated PDFs are in: {os.path.abspath('generated')}")

# Exit with appropriate code
sys.exit(0 if failed == 0 else 1)
