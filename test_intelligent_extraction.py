"""
Test intelligent prescription extraction with Gemini
"""
import os
import sys
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Import extraction function from app
from app import extract_prescription_with_gemini

# Test prescription from requirements
TEST_PRESCRIPTION = """
Hello, this is a prescription recording test.

For the first medicine, prescribe Paracetamol, 500 milligrams. The patient should take one tablet in the morning and one tablet in the evening for five days. Take it after food.

For the second medicine, prescribe Cetirizine, 10 milligrams. The patient should take one tablet at bedtime for three days.

For the third medicine, prescribe Dolo, 650 milligrams. The patient should take one tablet in the morning for two days, after food.

Also, advise the patient to drink plenty of water, get adequate rest, and maintain a healthy diet.

Please make sure the medicine names, dosages, timings, and durations are recorded correctly.

That completes the prescription. Thank you.
"""

def test_extraction():
    print("=" * 80)
    print("TESTING INTELLIGENT PRESCRIPTION EXTRACTION")
    print("=" * 80)
    print()
    print("INPUT PRESCRIPTION TEXT:")
    print("-" * 80)
    print(TEST_PRESCRIPTION)
    print("-" * 80)
    print()
    
    print("Extracting prescription data with Gemini...")
    result = extract_prescription_with_gemini(TEST_PRESCRIPTION)
    
    print()
    print("=" * 80)
    print("EXTRACTION RESULT")
    print("=" * 80)
    print()
    print(f"Extraction Source: {result.get('extraction_source', 'unknown')}")
    if result.get('note'):
        print(f"Note: {result['note']}")
    print()
    
    medicines = result.get('medicines', [])
    print(f"MEDICINES EXTRACTED: {len(medicines)}")
    print("-" * 80)
    
    expected_medicines = [
        {
            "name": "Paracetamol",
            "dosage": "500 mg",
            "frequency": "Twice daily",
            "duration": "5 days",
            "timing": ["Morning", "Evening"],
            "food_instruction": "After food"
        },
        {
            "name": "Cetirizine",
            "dosage": "10 mg",
            "frequency": "Once daily",
            "duration": "3 days",
            "timing": ["Bedtime"]
        },
        {
            "name": "Dolo",
            "dosage": "650 mg",
            "frequency": "Once daily",
            "duration": "2 days",
            "timing": ["Morning"],
            "food_instruction": "After food"
        }
    ]
    
    for idx, medicine in enumerate(medicines, 1):
        print(f"\nMedicine {idx}:")
        print(f"  Name:              {medicine.get('name', 'N/A')}")
        print(f"  Dosage:            {medicine.get('dosage', 'N/A')}")
        print(f"  Frequency:         {medicine.get('frequency', 'N/A')}")
        print(f"  Duration:          {medicine.get('duration', 'N/A')}")
        print(f"  Timing:            {', '.join(medicine.get('timing', [])) or 'N/A'}")
        print(f"  Food Instruction:  {medicine.get('food_instruction', 'N/A')}")
        print(f"  Special Instructions: {medicine.get('special_instructions', 'N/A')}")
    
    print()
    print("-" * 80)
    
    general_advice = result.get('general_advice', [])
    print(f"\nGENERAL ADVICE: {len(general_advice)} items")
    print("-" * 80)
    for idx, advice in enumerate(general_advice, 1):
        print(f"{idx}. {advice}")
    
    print()
    print("=" * 80)
    print("VALIDATION")
    print("=" * 80)
    print()
    
    # Validate results
    errors = []
    warnings = []
    
    if len(medicines) != 3:
        errors.append(f"Expected 3 medicines, got {len(medicines)}")
    
    if len(medicines) >= 1:
        med1 = medicines[0]
        if "paracetamol" not in med1.get('name', '').lower():
            errors.append(f"Medicine 1: Expected Paracetamol, got {med1.get('name')}")
        if "500" not in med1.get('dosage', ''):
            errors.append(f"Medicine 1: Expected dosage 500 mg, got {med1.get('dosage')}")
        if "5" not in med1.get('duration', ''):
            warnings.append(f"Medicine 1: Expected duration 5 days, got {med1.get('duration')}")
        if "Morning" not in med1.get('timing', []) or "Evening" not in med1.get('timing', []):
            warnings.append(f"Medicine 1: Expected Morning and Evening timing, got {med1.get('timing')}")
    
    if len(medicines) >= 2:
        med2 = medicines[1]
        if "cetirizine" not in med2.get('name', '').lower():
            errors.append(f"Medicine 2: Expected Cetirizine, got {med2.get('name')}")
        if "10" not in med2.get('dosage', ''):
            errors.append(f"Medicine 2: Expected dosage 10 mg, got {med2.get('dosage')}")
        if "3" not in med2.get('duration', ''):
            warnings.append(f"Medicine 2: Expected duration 3 days, got {med2.get('duration')}")
    
    if len(medicines) >= 3:
        med3 = medicines[2]
        if "dolo" not in med3.get('name', '').lower():
            errors.append(f"Medicine 3: Expected Dolo, got {med3.get('name')}")
        if "650" not in med3.get('dosage', ''):
            errors.append(f"Medicine 3: Expected dosage 650 mg, got {med3.get('dosage')}")
        if "2" not in med3.get('duration', ''):
            warnings.append(f"Medicine 3: Expected duration 2 days, got {med3.get('duration')}")
    
    if general_advice:
        expected_advice_keywords = ['water', 'rest', 'diet']
        found_keywords = [kw for kw in expected_advice_keywords if any(kw in advice.lower() for advice in general_advice)]
        if len(found_keywords) < 2:
            warnings.append(f"General advice: Expected mentions of water/rest/diet, found {found_keywords}")
    else:
        warnings.append("No general advice extracted")
    
    if errors:
        print("❌ ERRORS:")
        for error in errors:
            print(f"  - {error}")
        print()
    
    if warnings:
        print("⚠️  WARNINGS:")
        for warning in warnings:
            print(f"  - {warning}")
        print()
    
    if not errors and not warnings:
        print("✅ ALL CHECKS PASSED!")
        print()
        print("The intelligent extraction system successfully:")
        print("  - Identified exactly 3 medicines")
        print("  - Extracted correct medicine names, dosages, and durations")
        print("  - Understood context across multiple sentences")
        print("  - Separated medicines from general advice")
        print()
    elif not errors:
        print("✅ EXTRACTION SUCCESSFUL (with minor warnings)")
        print()
    else:
        print("❌ EXTRACTION FAILED")
        print()
        return False
    
    return True


if __name__ == "__main__":
    try:
        success = test_extraction()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ TEST FAILED WITH ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
