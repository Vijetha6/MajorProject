"""
Verify that Gemini is working in the running Flask application
Tests the actual prescription extraction endpoint
"""
import requests
import json

print("=" * 70)
print("GEMINI INTEGRATION VERIFICATION")
print("=" * 70)

# Test prescription text
test_prescription = """
Patient prescribed:
Paracetamol 500mg twice daily after meals for 3 days
Amoxicillin 250mg three times daily for 5 days
"""

print("\n1. Testing Flask server accessibility...")
try:
    response = requests.get("http://localhost:5000", timeout=5)
    if response.status_code == 200:
        print("   ✓ Flask server is running")
    else:
        print(f"   ✗ Flask returned status {response.status_code}")
        exit(1)
except Exception as e:
    print(f"   ✗ Cannot connect to Flask: {e}")
    print("   Make sure Flask is running: python app.py")
    exit(1)

print("\n2. Testing Gemini prescription extraction...")
print(f"   Test input: {test_prescription[:50]}...")

try:
    response = requests.post(
        "http://localhost:5000/extract-prescription",
        json={"prescription_text": test_prescription},
        timeout=30
    )
    
    if response.status_code == 200:
        result = response.json()
        
        print(f"   ✓ Request successful (HTTP 200)")
        print(f"\n3. Analyzing response...")
        
        # Check extraction source
        extraction_source = result.get("extraction_source", "unknown")
        print(f"   Extraction source: {extraction_source}")
        
        if extraction_source == "gemini":
            print(f"   ✓ ✓ ✓ GEMINI IS WORKING! ✓ ✓ ✓")
        elif extraction_source == "fallback":
            print(f"   ✗ Used fallback parser (Gemini failed)")
            note = result.get("note", "")
            if note:
                print(f"   Error note: {note}")
        else:
            print(f"   ⚠ Unknown extraction source")
        
        # Check medicines extracted
        medicines = result.get("medicines", [])
        print(f"\n4. Medicines extracted: {len(medicines)}")
        
        for idx, med in enumerate(medicines, 1):
            med_name = med.get("medicine", "unknown")
            dosage = med.get("dosage", "")
            duration = med.get("duration", "")
            print(f"   {idx}. {med_name}")
            if dosage:
                print(f"      Dosage: {dosage}")
            if duration:
                print(f"      Duration: {duration}")
        
        # Final verdict
        print(f"\n" + "=" * 70)
        print("VERDICT")
        print("=" * 70)
        
        if extraction_source == "gemini":
            print("✓ ✓ ✓ GEMINI API IS FULLY OPERATIONAL ✓ ✓ ✓")
            print("\nYour Flask application is successfully using Gemini for:")
            print("  • Intelligent prescription extraction")
            print("  • Medicine information enrichment")
            print("  • Generic name identification")
            print("  • Uses and side effects lookup")
            print("\nNo further action needed!")
        elif extraction_source == "fallback":
            print("✗ GEMINI IS NOT WORKING - USING FALLBACK")
            print("\nPossible causes:")
            print("  1. API key is still invalid")
            print("  2. Flask didn't reload the new key properly")
            print("  3. API quota exceeded")
            print("  4. Network connectivity issue")
            print("\nTo troubleshoot:")
            print("  1. Run: python diagnose_gemini_config.py")
            print("  2. Check the error message in Flask logs")
            print("  3. Verify API key at: https://aistudio.google.com/app/apikey")
        
        print("=" * 70)
        
    else:
        print(f"   ✗ Request failed with status {response.status_code}")
        print(f"   Response: {response.text[:200]}")
        
except Exception as e:
    print(f"   ✗ Request failed: {e}")
    exit(1)
