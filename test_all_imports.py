"""Test all required imports."""
import sys

def test_import(module_name, package_name=None):
    """Test if a module can be imported."""
    try:
        __import__(module_name)
        print(f"✓ {module_name:30} OK")
        return True
    except ImportError as e:
        pkg = package_name or module_name
        print(f"✗ {module_name:30} MISSING (pip install {pkg})")
        return False

print("="*70)
print("CHECKING ALL REQUIRED IMPORTS")
print("="*70)

# Test all imports
missing = []

# Core
if not test_import('flask', 'Flask'): missing.append('Flask')
if not test_import('werkzeug', 'Werkzeug'): missing.append('Werkzeug')

# Computer Vision
if not test_import('cv2', 'opencv-python'): missing.append('opencv-python')
if not test_import('PIL', 'Pillow'): missing.append('Pillow')
if not test_import('pytesseract'): missing.append('pytesseract')
if not test_import('easyocr'): missing.append('easyocr')

# ML/AI
if not test_import('numpy'): missing.append('numpy')
if not test_import('torch'): missing.append('torch')
if not test_import('torchvision'): missing.append('torchvision')
if not test_import('roboflow'): missing.append('roboflow')
if not test_import('transformers'): missing.append('transformers')

# Google
try:
    from google import genai
    print(f"✓ {'google.genai':30} OK")
except ImportError:
    print(f"✗ {'google.genai':30} MISSING (pip install google-genai)")
    missing.append('google-genai')

if not test_import('googleapiclient', 'google-api-python-client'): missing.append('google-api-python-client')
if not test_import('google_auth_oauthlib'): missing.append('google-auth-oauthlib')
if not test_import('google.auth'): missing.append('google-auth-httplib2')

# Data
if not test_import('pandas'): missing.append('pandas')
if not test_import('matplotlib'): missing.append('matplotlib')

# PDF
if not test_import('fpdf'): missing.append('fpdf')
if not test_import('qrcode'): missing.append('qrcode')

# SMS
if not test_import('twilio'): missing.append('twilio')

# Utils
if not test_import('dotenv', 'python-dotenv'): missing.append('python-dotenv')
if not test_import('requests'): missing.append('requests')
if not test_import('pytz'): missing.append('pytz')

print("="*70)
if missing:
    print(f"\n✗ {len(missing)} PACKAGES MISSING")
    print("\nInstall missing packages:")
    print(f"  pip install {' '.join(missing)}")
else:
    print("\n✓ ALL PACKAGES INSTALLED")

print("="*70)
sys.exit(len(missing))
