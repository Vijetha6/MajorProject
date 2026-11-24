# MedInfo - Application Startup Guide

## Quick Start

### Method 1: Batch Script (Recommended)
```bash
# Double-click this file:
start_network.bat
```

### Method 2: Command Line
```bash
cd d:\Projects\MajorProject
python app.py
```

---

## First-Time Setup

### Step 1: Install Dependencies
```bash
# Double-click this file to install all packages:
install_dependencies.bat

# Or manually:
cd d:\Projects\MajorProject
python -m pip install -r requirements.txt
```

### Step 2: Configure Environment
The `.env` file is already configured. Verify these settings:

```bash
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
APPLICATION_BASE_URL=http://10.158.88.1:5000
```

### Step 3: Start the Application
```bash
python app.py
```

---

## Access URLs

| Device | URL |
|--------|-----|
| **Laptop** | http://localhost:5000 |
| **Network** | http://10.158.88.1:5000 |
| **Mobile** | http://10.158.88.1:5000 (same Wi-Fi) |

---

## Login Credentials

### Doctor Login
- **URL**: http://localhost:5000/doctor/login
- **Username**: DOC001
- **Password**: DOCTOR@123

### Medical Staff Login
- **URL**: http://localhost:5000/staff/login
- **Username**: STA001
- **Password**: STAFF@123

---

## Required Packages

### Core Framework
- Flask==2.3.3
- Werkzeug==2.3.7

### Computer Vision
- opencv-python==4.13.0.92
- Pillow==10.1.0
- pytesseract==0.3.13
- easyocr==1.7.1

### Machine Learning
- numpy==2.4.2
- torch==2.3.0
- torchvision==0.18.0
- roboflow==1.1.13
- transformers==4.36.2
- google-genai

### Data Processing
- pandas
- matplotlib

### PDF & QR Code
- fpdf==1.7.2
- qrcode==7.3.1

### Google APIs
- google-api-python-client
- google-auth-oauthlib
- google-auth-httplib2

### SMS
- twilio

### Utilities
- python-dotenv==1.2.1
- requests==2.31.0
- pytz

---

## Troubleshooting

### Error: ModuleNotFoundError
**Solution**: Install missing package
```bash
pip install <package-name>
```

### Error: Port 5000 already in use
**Solution**: Kill existing Python processes
```bash
taskkill /F /IM python.exe
```

### Error: Import easyocr fails
**Solution**: EasyOCR requires torch. Install torch first:
```bash
pip install torch torchvision
pip install easyocr
```

### Error: Tesseract not found
**Solution**: Install Tesseract OCR executable
1. Download from: https://github.com/UB-Mannheim/tesseract/wiki
2. Install to: C:\Program Files\Tesseract-OCR
3. Add to PATH environment variable

### Error: Cannot access from mobile
**Solution**: Check these:
1. Laptop and mobile on same Wi-Fi
2. Windows Firewall allows Python
3. FLASK_HOST=0.0.0.0 in .env
4. IP address hasn't changed (run: python get_local_ip.py)

---

## Verify Installation

### Check Python
```bash
python --version
# Should show: Python 3.8 or higher
```

### Check All Imports
```bash
python -c "import flask, cv2, numpy, pytesseract, easyocr, roboflow, fpdf, qrcode; print('All imports OK')"
```

### Check Database
```bash
# Database will be created automatically on first run
# Location: d:\Projects\MajorProject\MED.db
```

---

## Features

✅ Medicine scanner (YOLO + OCR)
✅ Expiry date detection
✅ Medicine information (Gemini AI)
✅ Inventory management
✅ Doctor dashboard
✅ E-prescription generation
✅ Voice-to-text prescription
✅ PDF generation with QR code
✅ Google Drive upload
✅ SMS notifications (Twilio)
✅ WhatsApp Click-to-Chat
✅ Patient management
✅ Visit history
✅ Medicine interaction analysis

---

## Stopping the Application

Press `Ctrl+C` in the terminal where app.py is running

Or kill all Python processes:
```bash
taskkill /F /IM python.exe
```

---

## Production Deployment

For production deployment:

1. Set `FLASK_DEBUG=False` in .env
2. Use a production WSGI server (Gunicorn/uWSGI)
3. Set up reverse proxy (Nginx/Apache)
4. Configure HTTPS/SSL certificates
5. Update APPLICATION_BASE_URL to your domain
6. Secure the .env file
7. Set strong passwords
8. Enable authentication

---

## Support

For issues:
1. Check `SETUP_COMPLETE.md`
2. Check `NETWORK_ACCESS_SETUP.md`
3. Check `QR_CODE_FIX_README.md`
4. Review error logs in console

---

## File Structure

```
MajorProject/
├── app.py                          # Main Flask application
├── database.py                     # Medicine inventory database
├── doctor_database.py              # Patient & prescription database
├── drive_upload.py                 # Google Drive integration
├── sms.py                          # Twilio SMS integration
├── interaction_analysis.py         # Medicine interaction checker
├── requirements.txt                # Python dependencies
├── .env                            # Environment configuration
├── templates/
│   └── index.html                  # Main UI
├── static/
│   ├── script.js                   # Frontend JavaScript
│   └── style.css                   # Styles
├── generated/                      # Generated PDFs (auto-created)
├── MED.db                          # SQLite database (auto-created)
└── doctor.db                       # Doctor database (auto-created)
```

---

**You're all set!** Start the application with: `python app.py`
