# MedInfo - AI-Powered Medicine Intelligence System

Complete medicine identification, inventory management, and e-prescription system with AI integration.

---

## 🚀 Quick Start (3 Steps)

```bash
# 1. Install all dependencies
install_dependencies.bat

# 2. Verify installation
python diagnose_startup.py

# 3. Start the application
python app.py
```

**Access:** http://localhost:5000

---

## 📋 Prerequisites

- **Python 3.8 or higher**
- **Tesseract OCR** (for text recognition)
  - Download: https://github.com/UB-Mannheim/tesseract/wiki
  - Install to: `C:\Program Files\Tesseract-OCR`
  - Add to PATH

---

## 📦 Dependencies

All required packages are in `requirements.txt`:

- Flask, OpenCV, NumPy, PyTorch
- EasyOCR, Pytesseract, Roboflow
- Google Genai, Google APIs
- FPDF, QRCode, Twilio
- And more...

**Install:** `pip install -r requirements.txt`

---

## 🔧 Setup Guide

### Option 1: Automated Setup
```bash
install_dependencies.bat
```

### Option 2: Manual Setup
```bash
cd d:\Projects\MajorProject
python -m pip install -r requirements.txt
python diagnose_startup.py
```

**See:** `COMPLETE_SETUP_GUIDE.md` for detailed instructions.

---

## 🎯 Features

### For Patients
- 📱 Medicine scanner (YOLO + OCR)
- 📅 Expiry date detection
- 🤖 AI-powered medicine information
- 🌐 Multi-language support (English/Kannada)

### For Medical Staff
- 📦 Inventory management
- 🔔 Expiry alerts
- 📊 Low stock monitoring
- 🗺️ Location tracking (row/column)

### For Doctors
- 👥 Patient management
- 🎤 Voice-to-text prescription
- 🤖 Intelligent medicine extraction
- 📄 PDF prescription generation
- 📱 QR code for mobile access
- 💬 WhatsApp integration
- ☁️ Google Drive upload
- 📱 SMS notifications
- 🔍 Medicine interaction analysis
- 📜 Visit history tracking

---

## 🌐 Access URLs

| Device | URL | Notes |
|--------|-----|-------|
| **Laptop** | http://localhost:5000 | Local access |
| **Network** | http://10.158.88.1:5000 | Same Wi-Fi |
| **Mobile** | http://10.158.88.1:5000 | QR code works |

---

## 🔐 Login Credentials

### Doctor Dashboard
- URL: http://localhost:5000/doctor/login
- Username: `DOC001`
- Password: `DOCTOR@123`

### Medical Staff Dashboard
- URL: http://localhost:5000/staff/login
- Username: `STA001`
- Password: `STAFF@123`

---

## 📁 Project Structure

```
MajorProject/
├── app.py                    # Main Flask application
├── database.py               # Medicine inventory
├── doctor_database.py        # Patient & prescriptions
├── drive_upload.py           # Google Drive integration
├── sms.py                    # Twilio SMS
├── interaction_analysis.py   # Drug interactions
├── requirements.txt          # Python dependencies
├── .env                      # Configuration (API keys)
├── templates/
│   └── index.html           # Main UI
├── static/
│   ├── script.js            # Frontend logic
│   └── style.css            # Styles
└── generated/               # PDFs (auto-created)
```

---

## 🩺 Troubleshooting

### Import Errors
```bash
# Diagnose which packages are missing
python diagnose_startup.py

# Install missing package
pip install <package-name>
```

### Port Already in Use
```bash
taskkill /F /IM python.exe
```

### Tesseract Not Found
1. Install Tesseract OCR
2. Add to PATH: `C:\Program Files\Tesseract-OCR`
3. Restart terminal

### Cannot Access from Mobile
1. Check Wi-Fi (same network?)
2. Check FLASK_HOST=0.0.0.0 in .env
3. Check Windows Firewall
4. Verify IP: `python get_local_ip.py`

**See:** `COMPLETE_SETUP_GUIDE.md` for more solutions.

---

## 📚 Documentation

| File | Purpose |
|------|---------|
| `README.md` | This file (overview) |
| `COMPLETE_SETUP_GUIDE.md` | Full setup guide |
| `DEPENDENCIES_FIXED.md` | Dependency details |
| `START_APPLICATION.md` | Startup guide |
| `NETWORK_ACCESS_SETUP.md` | Network config |
| `QR_CODE_FIX_README.md` | QR code setup |
| `SETUP_COMPLETE.md` | Configuration summary |

---

## 🔄 Common Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Diagnose issues
python diagnose_startup.py

# Get network IP
python get_local_ip.py

# Verify setup
python verify_setup.py

# Start application
python app.py

# Stop application
Ctrl+C
```

---

## 🎨 Technology Stack

- **Backend:** Flask (Python)
- **Database:** SQLite
- **Computer Vision:** OpenCV, YOLO, EasyOCR
- **AI:** Google Gemini, Roboflow
- **PDF Generation:** FPDF
- **Cloud Storage:** Google Drive API
- **SMS:** Twilio API
- **Frontend:** HTML, CSS, JavaScript

---

## ⚙️ Environment Variables

Required in `.env`:

```bash
# API Keys
ROBOFLOW_API_KEY=your_key
GEMINI_API_KEY=your_key

# Flask Settings
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
APPLICATION_BASE_URL=http://10.158.88.1:5000

# Authentication
DOCTOR_ID=DOC001
DOCTOR_PASSWORD=DOCTOR@123
STAFF_ID=STA001
STAFF_PASSWORD=STAFF@123
```

---

## 🧪 Testing

```bash
# Test all imports
python diagnose_startup.py

# Expected output:
# ✓ ALL TESTS PASSED - Application ready to start!
```

---

## 📞 Support

For issues:
1. Run `python diagnose_startup.py`
2. Check error messages
3. Review documentation files
4. Verify .env configuration

---

## 🎉 Success Indicators

Application is ready when terminal shows:

```
🌐 Web interface: http://localhost:5000
📡 API endpoint: http://localhost:5000/process

 * Running on all addresses (0.0.0.0)
 * Running on http://127.0.0.1:5000
 * Running on http://10.158.88.1:5000
```

---

## 🔒 Security Notes

- Change default passwords in .env
- Secure API keys
- Use HTTPS in production
- Set FLASK_DEBUG=False in production

---

## 📄 License

[Your License Here]

---

## 🤝 Contributing

[Your Contributing Guidelines]

---

**Ready to start!**

Run: `python app.py`

Access: http://localhost:5000
