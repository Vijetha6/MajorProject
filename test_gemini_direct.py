"""
Direct test of Gemini functionality by importing from app.py
This bypasses Flask authentication and tests the Gemini client directly
"""
import os
import sys
from dotenv import load_dotenv

# Load environment
load_dotenv()

print("=" * 70)
print("GEMINI DIRECT FUNCTIONALITY TEST")
print("=" * 70)

print("\n1. Importing app module...")
try:
    # Import the app module which initializes Gemini client
    import app
    print("   ✓ App module imported successfully")
except Exception as e:
    print(f"   ✗ Failed to import app: {e}")
    sys.exit(1)

print("\n2. Checking Gemini client status...")
if app.client is None:
    print("   ✗ Gemini client is None (not initialized)")
    print("   This means Gemini is disabled or failed to load")
    sys.exit(1)
else:
    print("   ✓ Gemini client is initialized")

print(f"   Model: {app.GEMINI_MODEL}")

# Check API key (without exposing it)
if app.GEMINI_API_KEY:
    key_len = len(app.GEMINI_API_KEY)
    key_prefix = app.GEMINI_API_KEY[:6]
    print(f"   API Key: Present ({key_len} chars, starts with {key_prefix}...)")
else:
    print("   ✗ API Key: Not found")
    sys.exit(1)

print("\n3. Testing prescription extraction with Gemini...")

test_prescription = """
Patient needs:
Paracetamol 500mg tablets - take 1 tablet twice daily after food for 3 days
Amoxicillin 250mg capsules - take 1 capsule three times daily for 5 days
Cetirizine 10mg - take 1 tablet at bedtime for 7 days
"""

print(f"   Test input: {test_prescription[:60]}...")

try:
    result = app.extract_prescription_with_gemini(test_prescription)
    
    print("   ✓ Function executed without errors")
    
    print("\n4. Analyzing extraction result...")
    
    extraction_source = result.get("extraction_source", "unknown")
    print(f"   Extraction source: {extraction_source}")
    
    if extraction_source == "gemini":
        print("   ✓✓✓ GEMINI IS WORKING! ✓✓✓")
    elif extraction_source == "fallback":
        print("   ✗ Gemini failed, used fallback")
        note = result.get("note", "")
        if note:
            print(f"   Failure reason: {note}")
    
    medicines = result.get("medicines", [])
    print(f"\n5. Medicines extracted: {len(medicines)}")
    
    if medicines:
        for idx, med in enumerate(medicines, 1):
            name = med.get("medicine", "unknown")
            dosage = med.get("dosage", "")
            frequency = med.get("frequency", "")
            duration = med.get("duration", "")
            
            print(f"\n   Medicine {idx}: {name}")
            if dosage:
                print(f"      Dosage: {dosage}")
            if frequency:
                print(f"      Frequency: {frequency}")
            if duration:
                print(f"      Duration: {duration}")
    else:
        print("   ⚠ No medicines extracted")
    
    # Check general advice
    advice = result.get("general_advice", [])
    if advice:
        print(f"\n6. General Advice: {len(advice)} items")
        for idx, adv in enumerate(advice, 1):
            print(f"   {idx}. {adv}")
    
    print("\n" + "=" * 70)
    print("FINAL VERDICT")
    print("=" * 70)
    
    if extraction_source == "gemini" and len(medicines) > 0:
        print("✓✓✓ GEMINI IS FULLY OPERATIONAL ✓✓✓")
        print("\nThe Gemini API is working correctly in your Flask application!")
        print("\nCapabilities verified:")
        print("  ✓ API authentication successful")
        print("  ✓ Prescription text parsing")
        print("  ✓ Medicine extraction")
        print("  ✓ Structured data generation")
        print("\nYour application is ready to use!")
        
    elif extraction_source == "gemini" and len(medicines) == 0:
        print("⚠ GEMINI IS RESPONDING BUT NOT EXTRACTING MEDICINES")
        print("\nGemini API is working, but the extraction logic may need adjustment")
        
    else:
        print("✗ GEMINI IS NOT WORKING")
        print("\nThe application is using fallback parser instead of Gemini")
        print("\nCheck Flask server logs for error details")
        note = result.get("note", "No error note provided")
        print(f"Error: {note}")
    
    print("=" * 70)
    
except Exception as e:
    print(f"   ✗ Extraction failed with exception: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
