# MedInfo - Complete Setup & Dependency Guide

## 🚀 Quick Start (3 Steps)

```bash
# Step 1: Install dependencies
install_dependencies.bat

# Step 2: Diagnose any issues
python diagnose_startup.py

# Step 3: Start application
python app.py
```

---

## 📦 Required Dependencies

### Complete List

```
Core Framework:
  - Flask==2.3.3
  - Werkzeug==2.3.7

Computer Vision:
  - opencv-python==4.13.0.92
  - Pillow==10.1.0
  - pytesseract==0.3.13
  - easyocr==1.7.1

Machine Learning:
  - numpy==2.4.2
  - torch==2.3.0
  - torchvision==0.18.0
  - roboflow==1.1.13
  - transformers==4.36.2
  - google-genai

Data Processing:
  - pandas
  - matplotlib

PDF & QR Code:
  - fpdf==1.7.2
  - qrcode==7.3.1

Google APIs:
  - google-api-python-client
  - google-auth-oauthlib
  - google-auth-httplib2

SMS:
  - twilio

Utilities:
  - python-dotenv==1.2.1
  - requests==2.31.0
  - pytz
```

---

## 🔧 Installation Methods

### Method 1: Automated (Recommended)
```bash
# Double-click or run:
install_dependencies.bat
```

### Method 2: Manual
```bash
cd d:\Projects\MajorProject
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Method 3: Individual Packages
```bash
# Install one by one (if batch install fails)
pip install Flask==2.3.3
pip install opencv-python==4.13.0.92
pip install numpy==2.4.2
pip install pytesseract==0.3.13
pip install easyocr==1.7.1
pip install torch==2.3.0
pip install torchvision==0.18.0
pip install roboflow==1.1.13
pip install transformers==4.36.2
pip install pandas
pip install matplotlib
pip install fpdf==1.7.2
pip install qrcode==7.3.1
pip install google-genai
pip install google-api-python-client
pip install google-auth-oauthlib
pip install google-auth-httplib2
pip install twilio
pip install python-dotenv==1.2.1
pip install requests==2.31.0
pip install pytz
```

---

## 🩺 Diagnosis & Verification

### Run Diagnostic Script
```bash
python diagnose_startup.py
```

This will test all imports and identify missing packages.

### Manual Verification
```bash
# Test core imports
python -c "import flask; print('Flask OK')"
python -c "import cv2; print('OpenCV OK')"
python -c "import numpy; print('NumPy OK')"
python -c "import pytesseract; print('Pytesseract OK')"
python -c "import easyocr; print('EasyOCR OK')"
python -c "import roboflow; print('Roboflow OK')"
python -c "import fpdf; print('FPDF OK')"
python -c "import qrcode; print('QRCode OK')"
python -c "from dotenv import load_dotenv; print('python-dotenv OK')"
```

---

## ⚠️ Common Issues & Solutions

### Issue 1: ModuleNotFoundError: No module named 'flask'
**Solution:**
```bash
pip install Flask==2.3.3
```

### Issue 2: ModuleNotFoundError: No module named 'cv2'
**Solution:**
```bash
pip install opencv-python==4.13.0.92
```

### Issue 3: ModuleNotFoundError: No module named 'easyocr'
**Solution:**
EasyOCR requires torch to be installed first:
```bash
pip install torch torchvision
pip install easyocr
```

### Issue 4: ModuleNotFoundError: No module named 'google.genai'
**Solution:**
```bash
pip install google-genai
```

### Issue 5: Tesseract executable not found
**Solution:**
1. Download Tesseract OCR from: https://github.com/UB-Mannheim/tesseract/wiki
2. Install to: `C:\Program Files\Tesseract-OCR`
3. Add to Windows PATH:
   - Open System Properties → Environment Variables
   - Edit PATH
   - Add: `C:\Program Files\Tesseract-OCR`
4. Restart terminal

### Issue 6: Port 5000 already in use
**Solution:**
```bash
# Kill existing Python processes
taskkill /F /IM python.exe

# Or use a different port in .env:
FLASK_PORT=5001
```

### Issue 7: Import errors after pip install
**Solution:**
```bash
# Upgrade pip
python -m pip install --upgrade pip

# Clear pip cache
pip cache purge

# Reinstall requirements
pip install --no-cache-dir -r requirements.txt
```

### Issue 8: "Cannot access from mobile"
**Solution:**
1. Ensure both devices are on the same Wi-Fi
2. Check FLASK_HOST=0.0.0.0 in .env
3. Allow Python through Windows Firewall
4. Verify IP hasn't changed: `python get_local_ip.py`

---

## 📁 Project Files

### Main Application Files
- `app.py` - Main Flask application (medicine scanner, prescriptions)
- `database.py` - Medicine inventory database
- `doctor_database.py` - Patient & prescription database
- `drive_upload.py` - Google Drive integration
- `sms.py` - Twilio SMS integration
- `interaction_analysis.py` - Medicine interaction checker

### Configuration Files
- `requirements.txt` - Python dependencies
- `.env` - Environment configuration (API keys, settings)

### Utility Scripts
- `install_dependencies.bat` - Install all packages
- `diagnose_startup.py` - Diagnose import issues
- `scan_dependencies.py` - Scan project for dependencies
- `get_local_ip.py` - Get network IP address
- `verify_setup.py` - Verify network configuration
- `start_network.bat` - Start app with network access

### Documentation
- `START_APPLICATION.md` - Startup guide
- `SETUP_COMPLETE.md` - QR code fix summary
- `NETWORK_ACCESS_SETUP.md` - Network configuration guide
- `QR_CODE_FIX_README.md` - QR code quick reference
- `COMPLETE_SETUP_GUIDE.md` - This file

---

## 🎯 Environment Configuration

### .env File Structure
```bash
# Roboflow API (required for medicine detection)
ROBOFLOW_API_KEY=your_key_here

# Flask Configuration
FLASK_DEBUG=False
FLASK_HOST=0.0.0.0
FLASK_PORT=5000

# Application Base URL (for QR codes)
APPLICATION_BASE_URL=http://10.158.88.1:5000

# Clinic Information
DOCTOR_NAME=abc
CLINIC_NAME=XYZ
CLINIC_TAGLINE=HEALTH IS WEALTH
CLINIC_ADDRESS=yyy
CLINIC_PHONE=xxx
CLINIC_EMAIL=xyz@gmail.com

# AI Configuration
GEMINI_API_KEY=your_gemini_key
GEMINI_MODEL=gemini-3.5-flash-lite

# Authentication
DOCTOR_ID=DOC001
DOCTOR_PASSWORD=DOCTOR@123
STAFF_ID=STA001
STAFF_PASSWORD=STAFF@123
```

---

## 🔐 Login Credentials

### Doctor Dashboard
- **URL**: http://localhost:5000/doctor/login
- **Username**: DOC001
- **Password**: DOCTOR@123

### Medical Staff Dashboard
- **URL**: http://localhost:5000/staff/login
- **Username**: STA001
- **Password**: STAFF@123

---

## 🌐 Access URLs

| Device | URL | Notes |
|--------|-----|-------|
| Laptop (localhost) | http://localhost:5000 | Local access only |
| Laptop (network) | http://10.158.88.1:5000 | Network IP |
| Mobile/Tablet | http://10.158.88.1:5000 | Same Wi-Fi required |

---

## ✅ Verification Checklist

Before starting the application:

- [ ] Python 3.8+ installed
- [ ] All packages installed (run: `diagnose_startup.py`)
- [ ] .env file configured with API keys
- [ ] Tesseract OCR installed (for pytesseract)
- [ ] Windows Firewall allows Python
- [ ] Port 5000 is available
- [ ] No import errors when running `python diagnose_startup.py`

---

## 🚀 Starting the Application

### Option 1: Batch Script
```bash
start_network.bat
```

### Option 2: Command Line
```bash
cd d:\Projects\MajorProject
python app.py
```

### Option 3: Background Mode
```bash
start /B python app.py
```

---

## 🛑 Stopping the Application

### Method 1: Keyboard
Press `Ctrl+C` in the terminal

### Method 2: Task Manager
```bash
taskkill /F /IM python.exe
```

---

## 📊 Features

✅ Medicine scanner (YOLO object detection)
✅ OCR (Tesseract + EasyOCR)
✅ Expiry date detection
✅ AI-powered medicine information (Gemini)
✅ Inventory management
✅ Doctor dashboard
✅ E-prescription generation
✅ Voice-to-text prescription
✅ Intelligent medicine extraction
✅ PDF generation with QR code
✅ Google Drive upload
✅ SMS notifications (Twilio)
✅ WhatsApp Click-to-Chat
✅ Patient management
✅ Visit history tracking
✅ Medicine interaction analysis
✅ Low stock alerts
✅ Expiry monitoring

---

## 🔄 Update Dependencies

To update all packages to latest versions:

```bash
pip install --upgrade -r requirements.txt
```

To check for outdated packages:

```bash
pip list --outdated
```

---

## 🧪 Testing

### Test Basic Functionality
```bash
# Run diagnostic script
python diagnose_startup.py

# Should output:
# ✓ ALL TESTS PASSED - Application ready to start!
```

### Test Network Access
```bash
# Get current IP
python get_local_ip.py

# Verify configuration
python verify_setup.py

# Should output:
# ✓ Configuration is CORRECT for network access
```

---

## 📞 Support & Troubleshooting

If you encounter issues:

1. Run `python diagnose_startup.py` to identify missing packages
2. Check error messages in terminal
3. Verify .env configuration
4. Check Windows Firewall settings
5. Ensure all API keys are valid
6. Review documentation files

---

## 🎉 Success Indicators

Application is ready when you see:

```
🌐 Web interface: http://localhost:5000
📡 API endpoint: http://localhost:5000/process

 * Running on all addresses (0.0.0.0)
 * Running on http://127.0.0.1:5000
 * Running on http://10.158.88.1:5000
```

---

**You're all set!** 

Run: `python app.py` to start the application.
