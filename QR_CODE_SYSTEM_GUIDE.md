# QR Code System - Complete Guide

## 🎯 Overview

The prescription system embeds QR codes in generated PDF prescriptions. When scanned with Google Lens or any QR scanner on a mobile device, the QR code opens the prescription PDF directly in the mobile browser.

## ✅ Current Status

**System is fully functional!** All tests pass.

- ✅ QR codes use correct public URL from `APPLICATION_BASE_URL`
- ✅ QR codes point to `/prescription/<visit_id>` route
- ✅ Route serves PDFs with `Content-Disposition: inline` (opens in browser)
- ✅ Works with both local network (LAN IP) and public access (ngrok/HTTPS)
- ✅ Flask server running on `0.0.0.0:5000` (accessible from network)
- ✅ Ngrok tunnel active: `https://swinging-penpal-untainted.ngrok-free.dev`

## 🔧 System Architecture

### QR Code Generation (in app.py)

```python
# Line 1337-1350: QR URL generation logic
base_url = os.getenv("APPLICATION_BASE_URL", "").strip()
if base_url:
    base_url = base_url.rstrip('/')
    qr_code_url = f"{base_url}/prescription/{visit_id}"
else:
    qr_code_url = url_for("view_prescription_by_visit_id", 
                          visit_id=visit_id, _external=True)
```

### Prescription Route (in app.py)

```python
# Line 3182-3194: Public prescription viewing
@app.route("/prescription/<visit_id>", methods=["GET"])
def view_prescription_by_visit_id(visit_id):
    """Public route to view prescription by visit ID (embedded in QR codes)"""
    visit = get_visit_by_id(visit_id)
    if not visit:
        return "Prescription not found", 404
    
    filename = visit["prescription_path"]
    return send_from_directory(
        GENERATED_FOLDER, 
        filename, 
        mimetype='application/pdf', 
        as_attachment=False  # Opens inline in browser
    )
```

## 📱 How It Works

1. **Doctor generates prescription** → PDF created with embedded QR code
2. **QR code contains URL**: `https://swinging-penpal-untainted.ngrok-free.dev/prescription/VIS-XXXXXXXXXXXXXXXX`
3. **Patient scans QR with Google Lens** → Opens URL in mobile browser
4. **Flask serves PDF** → PDF opens inline (not downloaded)
5. **Patient views prescription** → Can save, print, or share from browser

## 🌐 Configuration

### Environment Variables (.env)

```env
# Public URL for QR codes (REQUIRED for mobile access)
APPLICATION_BASE_URL=https://swinging-penpal-untainted.ngrok-free.dev

# Flask server configuration
FLASK_HOST=0.0.0.0        # Accessible from network
FLASK_PORT=5000           # Port number
```

### Two Deployment Modes

#### Mode 1: Local Network (Same WiFi)
```env
APPLICATION_BASE_URL=http://10.39.203.1:5000
```
- Works only when mobile and laptop are on same WiFi
- Find your LAN IP: `ipconfig` (Windows) or `ifconfig` (Mac/Linux)
- Look for IPv4 address starting with `10.` or `192.168.`

#### Mode 2: Public Access (Internet)
```env
APPLICATION_BASE_URL=https://swinging-penpal-untainted.ngrok-free.dev
```
- Works from anywhere with internet connection
- Requires ngrok tunnel or production deployment
- **Current setup uses this mode**

## 🚀 Setup Instructions

### 1. Start Ngrok Tunnel

```powershell
# Start ngrok
ngrok http 5000
```

This will output something like:
```
Forwarding   https://swinging-penpal-untainted.ngrok-free.dev -> http://localhost:5000
```

### 2. Update .env File

Copy the HTTPS URL from ngrok and update `.env`:

```env
APPLICATION_BASE_URL=https://swinging-penpal-untainted.ngrok-free.dev
```

**Important**: Ngrok free plan generates new URLs on each restart unless you have a paid account with reserved domains.

### 3. Start Flask Server

```powershell
python app.py
```

Wait for the startup message:
```
🌐 Web interface: http://localhost:5000
📡 API endpoint: http://localhost:5000/process
 * Running on all addresses (0.0.0.0)
 * Running on http://10.39.203.1:5000
```

### 4. Verify System

Run the test script:

```powershell
python test_qr_system.py
```

Expected output:
```
✓ All tests passed!
```

## 📋 Testing QR Codes

### Step-by-Step Test Procedure

1. **Generate a new prescription**:
   - Open web interface: http://localhost:5000
   - Login as doctor (DOC001 / DOCTOR@123)
   - Create new patient visit
   - Use voice prescription or manual entry
   - Generate PDF

2. **Download the PDF**:
   - Click "Download PDF" button
   - Open downloaded PDF on your computer

3. **Scan QR code with mobile phone**:
   - Open PDF file
   - Use Google Lens or any QR scanner app
   - Point camera at QR code in the PDF

4. **Verify result**:
   - QR scanner should detect URL: `https://swinging-penpal-untainted.ngrok-free.dev/prescription/VIS-XXXX...`
   - Clicking the URL should open the prescription PDF in mobile browser
   - PDF should display inline (not download)

### Expected URLs

✅ **Correct QR URLs**:
```
https://swinging-penpal-untainted.ngrok-free.dev/prescription/VIS-F652FD9A32E04080
http://10.39.203.1:5000/prescription/VIS-F652FD9A32E04080
```

❌ **Incorrect QR URLs** (will NOT work from mobile):
```
http://localhost:5000/prescription/VIS-...
http://127.0.0.1:5000/prescription/VIS-...
file:///d:/Projects/MajorProject/generated/prescription_...
```

## ⚠️ Ngrok Free Plan Considerations

### Ngrok Warning Page

Ngrok's free plan shows an interstitial warning page on first visit:

```
You are about to visit:
swinging-penpal-untainted.ngrok-free.dev

This site may be operated by an individual or organization you don't know.

[Visit Site] [Go Back]
```

**Impact on QR Codes**:
- First-time scanners will see this warning
- They must click "Visit Site" to proceed
- After that, subsequent visits work directly

**Solutions**:
1. **Free**: Accept the warning page (users click through once)
2. **Paid ngrok** ($8/month): Reserved domain + no warning page
3. **Production**: Deploy to real domain (Heroku, Railway, Vercel, etc.)

### Ngrok URL Changes

Free ngrok URLs change on each restart. After stopping/starting ngrok:

1. Check new URL: `curl http://127.0.0.1:4040/api/tunnels`
2. Update `.env` with new `APPLICATION_BASE_URL`
3. Restart Flask server
4. Generate new prescriptions (old PDFs have old URLs)

## 🔍 Troubleshooting

### Problem: QR code doesn't work from mobile

**Check 1**: What URL is in the QR code?
```powershell
# Generate test prescription and check logs
python test_qr_system.py
```

If URL contains `localhost` or `127.0.0.1`:
- ❌ Set `APPLICATION_BASE_URL` in `.env`
- ✅ Restart Flask server

**Check 2**: Is ngrok running?
```powershell
# Check ngrok status
curl http://127.0.0.1:4040/api/tunnels
```

If error:
- ❌ Ngrok not running
- ✅ Start: `ngrok http 5000`

**Check 3**: Is Flask accessible?
```powershell
# Test from local network
curl http://10.39.203.1:5000

# Test from public
curl https://swinging-penpal-untainted.ngrok-free.dev
```

### Problem: PDF doesn't open inline

Check response headers:
```powershell
curl -I http://localhost:5000/prescription/VIS-XXXXXXXXXXXXXXXX
```

Expected:
```
Content-Type: application/pdf
Content-Disposition: inline; filename=prescription_...
```

If you see `Content-Disposition: attachment`:
- Check line 3192 in `app.py`
- Should be: `as_attachment=False`

### Problem: Old prescriptions have wrong URLs

Old PDFs have embedded QR codes with old URLs. Solutions:

1. **Generate new prescriptions**: New PDFs will have correct URLs
2. **For testing**: Use newly generated prescriptions
3. **For patients**: Regenerate prescriptions from visit history

## 📊 Visit ID Format

Visit IDs use format: `VIS-{16 hexadecimal characters}`

Example: `VIS-F652FD9A32E04080`

- Stored in database: `doctor_database.py`
- Retrieved by: `get_visit_by_id(visit_id)` function
- Used in route: `/prescription/<visit_id>`

## 🔒 Security Notes

- Visit IDs are UUIDs (cryptographically random)
- No authentication required for prescription viewing
- PDFs are public if you have the visit ID
- Consider adding:
  - Rate limiting on prescription route
  - Expiry dates for QR codes
  - Optional password protection

## 📁 File Structure

```
MajorProject/
├── app.py                      # Main Flask app
├── doctor_database.py          # Database functions
├── .env                        # Configuration (DO NOT COMMIT)
├── generated/                  # Generated PDFs
│   └── prescription_*.pdf      # PDF files with QR codes
├── test_qr_system.py          # Validation test script
└── QR_CODE_SYSTEM_GUIDE.md    # This guide
```

## 🎉 Success Criteria

Your QR code system is working when:

1. ✅ You can generate a prescription
2. ✅ The PDF contains a QR code
3. ✅ Scanning with Google Lens detects a URL
4. ✅ The URL starts with your ngrok domain (not localhost)
5. ✅ Opening the URL on mobile shows the PDF
6. ✅ The PDF opens inline in browser (not downloads)

## 📞 Additional Features

### WhatsApp Integration

Prescriptions are automatically sent via WhatsApp after generation:
- Uses Twilio API
- Sends PDF as attachment
- Includes visit ID and QR instructions
- Configured in `.env` with `TWILIO_*` variables

### Google Drive Upload

Prescriptions are automatically uploaded to Google Drive:
- Uses Drive API
- Returns shareable link
- Link is different from QR URL (Drive preview vs direct PDF)
- Configured in `drive_upload.py`

## 🛠️ Maintenance Commands

### Check ngrok URL
```powershell
curl http://127.0.0.1:4040/api/tunnels | ConvertFrom-Json | 
    Select-Object -ExpandProperty tunnels | 
    Where-Object {$_.proto -eq 'https'} | 
    Select-Object -ExpandProperty public_url
```

### Check Flask status
```powershell
curl -I http://localhost:5000
```

### Test prescription route
```powershell
curl -I http://localhost:5000/prescription/VIS-F652FD9A32E04080
```

### Run validation tests
```powershell
python test_qr_system.py
```

### Get local IP address
```powershell
ipconfig | Select-String "IPv4"
```

## 📝 Notes

- Flask must be running before testing QR codes
- Ngrok must be running for public access
- Each restart of ngrok (free plan) generates new URL
- Old PDFs retain old embedded QR URLs
- Mobile device needs internet connection to access ngrok URLs
- Mobile device needs same WiFi for LAN IP URLs

---

**Last Updated**: November 23, 2026
**System Status**: ✅ Fully Operational
**Current URL**: `https://swinging-penpal-untainted.ngrok-free.dev`
