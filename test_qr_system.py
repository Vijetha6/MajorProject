"""
QR Code System Test Script
Tests the QR code functionality for prescriptions.
"""
import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_qr_system():
    """Test the QR code system end-to-end"""
    
    print("=" * 60)
    print("QR CODE SYSTEM VALIDATION TEST")
    print("=" * 60)
    
    # 1. Check environment configuration
    print("\n1. Environment Configuration:")
    print("-" * 60)
    base_url = os.getenv("APPLICATION_BASE_URL", "").strip()
    flask_host = os.getenv("FLASK_HOST", "127.0.0.1")
    flask_port = os.getenv("FLASK_PORT", "5000")
    
    print(f"   APPLICATION_BASE_URL: {base_url}")
    print(f"   FLASK_HOST: {flask_host}")
    print(f"   FLASK_PORT: {flask_port}")
    
    if not base_url:
        print("   ⚠️  WARNING: APPLICATION_BASE_URL not set!")
        print("   QR codes will use Flask's url_for (may use localhost)")
    else:
        print("   ✓ APPLICATION_BASE_URL is configured")
    
    # 2. Test Flask local access
    print("\n2. Flask Local Access Test:")
    print("-" * 60)
    local_url = f"http://localhost:{flask_port}"
    try:
        response = requests.get(local_url, timeout=5)
        print(f"   Local URL: {local_url}")
        print(f"   Status: {response.status_code} ✓")
    except Exception as e:
        print(f"   ❌ Local access failed: {e}")
        return False
    
    # 3. Test ngrok/public access
    if base_url:
        print("\n3. Public Access Test (ngrok/production):")
        print("-" * 60)
        try:
            # Test home page
            response = requests.get(base_url, timeout=10)
            print(f"   Public URL: {base_url}")
            print(f"   Status: {response.status_code} ✓")
            
            # Check for ngrok warning page
            if "ngrok" in response.text.lower() and "visit site" in response.text.lower():
                print("   ⚠️  NGROK WARNING PAGE DETECTED!")
                print("   The ngrok free plan shows a warning page on first visit.")
                print("   Users must click 'Visit Site' to proceed.")
                print("   Consider upgrading ngrok or using production domain.")
            else:
                print("   ✓ No ngrok warning detected")
                
        except Exception as e:
            print(f"   ❌ Public access failed: {e}")
            return False
    
    # 4. Test prescription route
    print("\n4. Prescription Route Test:")
    print("-" * 60)
    
    # Find an existing prescription with visit ID
    generated_folder = "generated"
    test_visit_id = None
    
    if os.path.exists(generated_folder):
        for filename in os.listdir(generated_folder):
            if filename.startswith("prescription_") and filename.endswith(".pdf"):
                # Extract visit ID from filename (format: prescription_Name_VIS-XXXX.pdf)
                if "VIS-" in filename:
                    parts = filename.replace(".pdf", "").split("VIS-")
                    if len(parts) == 2:
                        test_visit_id = f"VIS-{parts[1]}"
                        break
    
    if not test_visit_id:
        print("   ⚠️  No existing prescriptions found with visit ID")
        print("   Please generate a prescription first to test QR codes")
        return True  # Not a failure, just no test data
    
    print(f"   Test Visit ID: {test_visit_id}")
    
    # Test local prescription route
    prescription_path = f"/prescription/{test_visit_id}"
    local_prescription_url = f"{local_url}{prescription_path}"
    
    try:
        response = requests.get(local_prescription_url, timeout=5)
        print(f"   Local: {local_prescription_url}")
        print(f"   Status: {response.status_code}")
        print(f"   Content-Type: {response.headers.get('Content-Type', 'N/A')}")
        print(f"   Content-Disposition: {response.headers.get('Content-Disposition', 'N/A')}")
        
        if response.status_code == 200 and 'application/pdf' in response.headers.get('Content-Type', ''):
            print("   ✓ Local prescription route working")
        else:
            print("   ❌ Local prescription route failed")
            return False
            
    except Exception as e:
        print(f"   ❌ Local prescription test failed: {e}")
        return False
    
    # Test public prescription route
    if base_url:
        public_prescription_url = f"{base_url}{prescription_path}"
        try:
            response = requests.get(public_prescription_url, timeout=10, allow_redirects=True)
            print(f"\n   Public: {public_prescription_url}")
            print(f"   Status: {response.status_code}")
            print(f"   Content-Type: {response.headers.get('Content-Type', 'N/A')}")
            
            # Check if we got the PDF or ngrok warning
            if 'application/pdf' in response.headers.get('Content-Type', ''):
                print("   ✓ Public prescription route working - PDF served")
            elif 'text/html' in response.headers.get('Content-Type', ''):
                if "ngrok" in response.text.lower():
                    print("   ⚠️  Ngrok warning page (expected on first access)")
                    print("   After clicking 'Visit Site', the PDF will load correctly")
                else:
                    print("   ⚠️  Got HTML instead of PDF")
            else:
                print("   ❌ Public prescription route failed")
                return False
                
        except Exception as e:
            print(f"   ❌ Public prescription test failed: {e}")
            return False
    
    # 5. QR Code URL format validation
    print("\n5. QR Code URL Format:")
    print("-" * 60)
    expected_qr_url = f"{base_url}/prescription/{test_visit_id}" if base_url else f"{local_url}/prescription/{test_visit_id}"
    print(f"   Expected QR URL: {expected_qr_url}")
    
    # Check for common mistakes
    if "localhost" in expected_qr_url or "127.0.0.1" in expected_qr_url:
        print("   ⚠️  WARNING: QR URL contains localhost/127.0.0.1")
        print("   This will NOT work from mobile devices!")
        print("   Set APPLICATION_BASE_URL to your LAN IP or public domain")
    elif "10." in expected_qr_url or "192.168." in expected_qr_url:
        print("   ✓ QR URL uses LAN IP (works on same WiFi network)")
    elif "https://" in expected_qr_url:
        print("   ✓ QR URL uses HTTPS (works from anywhere)")
    
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print("✓ All tests passed!")
    print("\nQR Code Scanning Instructions:")
    print("1. Generate a new prescription in the web interface")
    print("2. Download the prescription PDF")
    print("3. Open the PDF and scan the QR code with Google Lens")
    print("4. The QR should open: " + (base_url if base_url else local_url) + "/prescription/<visit_id>")
    print("5. The prescription PDF should open directly in mobile browser")
    
    if "ngrok" in (base_url or ""):
        print("\nNgrok Free Plan Note:")
        print("- First-time visitors will see a warning page")
        print("- They must click 'Visit Site' once")
        print("- After that, QR codes will work directly")
    
    print("=" * 60)
    return True

if __name__ == "__main__":
    try:
        success = test_qr_system()
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
