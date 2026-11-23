# QR Code System - Quick Start Guide

## ✅ System Status: OPERATIONAL

Your QR code system is **fully functional** and ready to use!

## 🚀 To Test QR Codes Right Now

### Step 1: Both services are already running! ✓

```
✓ Flask Server: Running on http://10.39.203.1:5000
✓ Ngrok Tunnel: https://swinging-penpal-untainted.ngrok-free.dev
```

### Step 2: Generate a New Prescription

1. Open in your browser: **http://localhost:5000**
2. Login with: **DOC001** / **DOCTOR@123**
3. Click "New Patient Visit"
4. Fill in patient details
5. Use voice prescription or manual entry
6. Click "Generate Prescription"
7. Download the PDF

### Step 3: Scan the QR Code

1. Open the downloaded PDF on your computer
2. Take out your mobile phone
3. Open **Google Lens** (or any QR scanner app)
4. Point camera at the QR code in the PDF
5. You should see: `https://swinging-penpal-untainted.ngrok-free.dev/prescription/VIS-...`
6. **Tap the URL**
7. The prescription PDF should open in your mobile browser!

## 📱 Expected Result

✅ **Success looks like this:**
- QR scanner detects a URL starting with `https://swinging-penpal-untainted.ngrok-free.dev`
- Clicking opens the prescription PDF in mobile browser
- PDF displays inline (you can read it immediately)
- You can save, print, or share from browser

❌ **If you see these, something is wrong:**
- QR contains `localhost` or `127.0.0.1` → Restart Flask server
- "Could not connect" error → Check ngrok is running
- PDF downloads instead of opening → Check browser settings

## 🔧 If Services Stop Running

### Restart Ngrok
```powershell
ngrok http 5000
```

Then check if URL changed:
```powershell
curl http://127.0.0.1:4040/api/tunnels
```

If URL changed, update `.env` file with new `APPLICATION_BASE_URL` and restart Flask.

### Restart Flask
```powershell
python app.py
```

Wait ~15 seconds for models to load. You'll see:
```
🌐 Web interface: http://localhost:5000
 * Running on http://10.39.203.1:5000
```

## 🧪 Run Tests Anytime

```powershell
python test_qr_system.py
```

Should output:
```
✓ All tests passed!
```

## 📖 More Information

- **Full Technical Guide**: Read `QR_CODE_SYSTEM_GUIDE.md`
- **Fix Summary**: Read `QR_CODE_FIX_SUMMARY.md`
- **Run Tests**: `python test_qr_system.py`

## 💡 Tips

1. **Old PDFs** have old QR codes - generate new ones to test
2. **Ngrok free plan** shows warning page on first visit (users click "Visit Site")
3. **Ngrok URLs change** on restart (free plan) - update `.env` if needed
4. **Mobile needs internet** to access ngrok URLs
5. **Same WiFi** not required when using ngrok

## ⚡ One-Line Test

Test prescription route from command line:
```powershell
curl -I http://localhost:5000/prescription/VIS-F652FD9A32E04080
```

Expected output:
```
HTTP/1.1 200 OK
Content-Type: application/pdf
Content-Disposition: inline
```

## 🎉 That's It!

Your QR code system is working correctly. Just generate a prescription and test scanning the QR code with your mobile phone!

---

**Services Currently Running:**
- Flask: ✅ http://10.39.203.1:5000
- Ngrok: ✅ https://swinging-penpal-untainted.ngrok-free.dev

**QR Code Format:**
```
https://swinging-penpal-untainted.ngrok-free.dev/prescription/VIS-XXXXXXXXXXXXXXXX
```
