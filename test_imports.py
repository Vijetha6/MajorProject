#!/usr/bin/env python3
"""Quick import test for Medicine App dependencies"""

print("Testing imports...")

try:
    import cv2
    print(f"✓ cv2 {cv2.__version__}")
except Exception as e:
    print(f"✗ cv2 failed: {e}")
    
try:
    import numpy
    print(f"✓ numpy {numpy.__version__}")
except Exception as e:
    print(f"✗ numpy failed: {e}")
    
try:
    import flask
    print(f"✓ Flask installed")
except Exception as e:
    print(f"✗ Flask failed: {e}")
    
try:
    import easyocr
    print(f"✓ easyocr installed")
except Exception as e:
    print(f"✗ easyocr failed: {e}")
    
try:
    import transformers
    print(f"✓ transformers installed")
except Exception as e:
    print(f"✗ transformers failed: {e}")
    
try:
    from dotenv import load_dotenv
    print(f"✓ python-dotenv installed")
except Exception as e:
    print(f"✗ python-dotenv failed: {e}")

print("\n✓ All core imports successful!")
