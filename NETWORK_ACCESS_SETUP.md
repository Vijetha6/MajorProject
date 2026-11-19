# Network Access & QR Code Configuration Guide

## Problem
The QR codes in prescription PDFs contain `http://127.0.0.1:5000` which can't be accessed from mobile devices scanning the QR code.

## Solution
Configure the application to use your laptop's local network IP address so mobile devices on the same Wi-Fi can access it.

---

## Quick Setup (Current Configuration)

Your application is already configured for network access:

### Current Settings in `.env`:
```bash
FLASK_HOST=0.0.0.0
APPLICATION_BASE_URL=http://10.158.88.1:5000
```

### To Run the Application:
```bash
cd d:\Projects\MajorProject
python app.py
```

### Access URLs:
- **From your laptop**: http://localhost:5000 OR http://10.158.88.1:5000
- **From mobile/tablet (same Wi-Fi)**: http://10.158.88.1:5000
- **QR codes in PDFs will contain**: http://10.158.88.1:5000/doctor/patients/...

---

## How It Works

1. **FLASK_HOST=0.0.0.0**: Flask listens on all network interfaces (not just localhost)
2. **APPLICATION_BASE_URL**: Overrides the QR code URL generation
   - If set: Uses this base URL for QR codes
   - If empty: Uses Flask's auto-detection (request host)

---

## Configuration Scenarios

### Scenario 1: Local Development Only (Localhost)
```bash
FLASK_HOST=127.0.0.1
APPLICATION_BASE_URL=
```
- App accessible only from your laptop
- QR codes will use `http://127.0.0.1:5000`

### Scenario 2: Local Network Access (Current)
```bash
FLASK_HOST=0.0.0.0
APPLICATION_BASE_URL=http://10.158.88.1:5000
```
- App accessible from any device on the same Wi-Fi
- QR codes will use `http://10.158.88.1:5000`

### Scenario 3: Production Deployment (HTTPS Domain)
```bash
FLASK_HOST=0.0.0.0
APPLICATION_BASE_URL=https://yourdomain.com
```
- App accessible from anywhere
- QR codes will use `https://yourdomain.com`

---

## Finding Your Local IP Address

### Method 1: Use the Helper Script
```bash
cd d:\Projects\MajorProject
python get_local_ip.py
```

### Method 2: Manual Detection (Windows)
```bash
ipconfig
```
Look for "IPv4 Address" under your Wi-Fi adapter (usually starts with 192.168.x.x or 10.x.x.x)

### Method 3: Manual Detection (Linux/Mac)
```bash
ifconfig
```
or
```bash
ip addr show
```

---

## Important Notes

⚠️ **IP Address May Change**: Your local IP (10.158.88.1) may change if:
- You reconnect to Wi-Fi
- Your router restarts
- DHCP lease expires

If your IP changes:
1. Run `python get_local_ip.py` again
2. Update `APPLICATION_BASE_URL` in `.env`
3. Restart the Flask application

⚠️ **Firewall Settings**: Ensure Windows Firewall allows Python to accept incoming connections on port 5000.

⚠️ **Same Wi-Fi Network**: Mobile devices must be on the same Wi-Fi network as your laptop to access the application.

---

## Testing the QR Code

1. Start the application:
   ```bash
   python app.py
   ```

2. Access from laptop: http://10.158.88.1:5000

3. Log in as doctor (DOC001 / DOCTOR@123)

4. Create a prescription for a patient

5. Download the generated PDF

6. Open the PDF and locate the QR code in the bottom-right corner

7. Scan the QR code with your mobile phone

8. ✅ You should be redirected to the prescription download page

---

## Troubleshooting

### Mobile can't access the application
- Verify both devices are on the same Wi-Fi network
- Check Windows Firewall settings
- Verify Flask is running with `FLASK_HOST=0.0.0.0`

### QR code still shows localhost
- Verify `APPLICATION_BASE_URL` is set in `.env`
- Restart the Flask application after changing `.env`
- Generate a NEW prescription (old PDFs won't update)

### "This site can't be reached" when scanning QR code
- Verify your mobile device is on the same Wi-Fi network
- Ping the IP address from your mobile device
- Check if your laptop's IP address has changed (run `python get_local_ip.py`)

---

## Production Deployment Checklist

When deploying to a production server:

1. ✅ Set `FLASK_HOST=0.0.0.0`
2. ✅ Set `FLASK_DEBUG=False`
3. ✅ Set `APPLICATION_BASE_URL` to your public domain (e.g., `https://yourdomain.com`)
4. ✅ Use a production WSGI server (Gunicorn, uWSGI) instead of `app.run()`
5. ✅ Set up HTTPS/SSL certificates
6. ✅ Configure reverse proxy (Nginx, Apache)
7. ✅ Set strong passwords in `.env`
8. ✅ Restrict access with authentication

---

## Contact
For issues or questions, refer to the main project README.
