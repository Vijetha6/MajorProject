"""
Diagnose startup issues by testing imports one by one.
"""
import sys

print("="*70)
print("DIAGNOSING STARTUP ISSUES")
print("="*70)

# Test 1: Basic Python
print("\n[Test 1] Python basics...")
try:
    import os, sys, json
    print("✓ Python standard library OK")
except Exception as e:
    print(f"✗ ERROR: {e}")
    sys.exit(1)

# Test 2: Flask
print("\n[Test 2] Flask...")
try:
    from flask import Flask
    print("✓ Flask imported")
except ImportError as e:
    print(f"✗ Flask not installed: {e}")
    print("  Fix: pip install Flask==2.3.3")
    sys.exit(1)

# Test 3: Computer Vision
print("\n[Test 3] Computer Vision libraries...")
try:
    import cv2
    print(f"✓ OpenCV imported (version: {cv2.__version__})")
except ImportError:
    print("✗ OpenCV not installed")
    print("  Fix: pip install opencv-python")
    sys.exit(1)

try:
    import numpy as np
    print(f"✓ NumPy imported (version: {np.__version__})")
except ImportError:
    print("✗ NumPy not installed")
    print("  Fix: pip install numpy")
    sys.exit(1)

try:
    from PIL import Image
    print("✓ Pillow imported")
except ImportError:
    print("✗ Pillow not installed")
    print("  Fix: pip install Pillow")
    sys.exit(1)

# Test 4: OCR
print("\n[Test 4] OCR libraries...")
try:
    import pytesseract
    print("✓ Pytesseract imported")
except ImportError:
    print("✗ Pytesseract not installed")
    print("  Fix: pip install pytesseract")
    sys.exit(1)

try:
    import easyocr
    print("✓ EasyOCR imported")
except ImportError:
    print("✗ EasyOCR not installed")
    print("  Fix: pip install easyocr")
    sys.exit(1)

# Test 5: ML Libraries
print("\n[Test 5] Machine Learning libraries...")
try:
    import torch
    print(f"✓ PyTorch imported (version: {torch.__version__})")
except ImportError:
    print("✗ PyTorch not installed")
    print("  Fix: pip install torch torchvision")
    sys.exit(1)

try:
    import roboflow
    print("✓ Roboflow imported")
except ImportError:
    print("✗ Roboflow not installed")
    print("  Fix: pip install roboflow")
    sys.exit(1)

# Test 6: Google APIs
print("\n[Test 6] Google APIs...")
try:
    from google import genai
    print("✓ Google Genai imported")
except ImportError:
    print("⚠ Google Genai not installed (optional)")
    print("  Fix: pip install google-genai")

try:
    from googleapiclient.discovery import build
    print("✓ Google API Client imported")
except ImportError:
    print("✗ Google API Client not installed")
    print("  Fix: pip install google-api-python-client google-auth-oauthlib")
    sys.exit(1)

# Test 7: PDF & QR
print("\n[Test 7] PDF & QR Code libraries...")
try:
    from fpdf import FPDF
    print("✓ FPDF imported")
except ImportError:
    print("✗ FPDF not installed")
    print("  Fix: pip install fpdf")
    sys.exit(1)

try:
    import qrcode
    print("✓ QRCode imported")
except ImportError:
    print("✗ QRCode not installed")
    print("  Fix: pip install qrcode")
    sys.exit(1)

# Test 8: Utils
print("\n[Test 8] Utility libraries...")
try:
    from dotenv import load_dotenv
    print("✓ python-dotenv imported")
except ImportError:
    print("✗ python-dotenv not installed")
    print("  Fix: pip install python-dotenv")
    sys.exit(1)

# Test 9: Project modules
print("\n[Test 9] Project modules...")
try:
    import database
    print("✓ database.py imported")
except Exception as e:
    print(f"✗ database.py error: {e}")
    sys.exit(1)

try:
    import doctor_database
    print("✓ doctor_database.py imported")
except Exception as e:
    print(f"✗ doctor_database.py error: {e}")
    sys.exit(1)

try:
    import drive_upload
    print("✓ drive_upload.py imported")
except Exception as e:
    print(f"✗ drive_upload.py error: {e}")
    sys.exit(1)

try:
    import interaction_analysis
    print("✓ interaction_analysis.py imported")
except Exception as e:
    print(f"✗ interaction_analysis.py error: {e}")
    sys.exit(1)

# Test 10: Try importing app.py
print("\n[Test 10] Main application...")
try:
    import app
    print("✓ app.py imported successfully")
    print("\n" + "="*70)
    print("✓ ALL TESTS PASSED - Application ready to start!")
    print("="*70)
    print("\nTo start the application, run:")
    print("  python app.py")
except Exception as e:
    print(f"✗ app.py import failed: {e}")
    import traceback
    print("\nFull traceback:")
    traceback.print_exc()
    sys.exit(1)
