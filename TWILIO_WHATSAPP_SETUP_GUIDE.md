# Twilio WhatsApp Integration Setup Guide

## Overview
This guide explains how to set up automatic WhatsApp PDF sending for MedInfo prescription system using Twilio WhatsApp API.

## Features Implemented
- ✅ Automatic WhatsApp message with PDF attachment after prescription generation
- ✅ No manual "Send WhatsApp" button click required
- ✅ PDF sent as WhatsApp document attachment (not just link)
- ✅ Proper phone number normalization (E.164 format)
- ✅ Graceful error handling and logging
- ✅ Backwards compatible with existing SMS functionality

---

## Prerequisites

### 1. Twilio Account
You need a Twilio account with WhatsApp capabilities:
- Free account available at: https://www.twilio.com/try-twilio
- Credit card required (but $15 free trial credit provided)

### 2. WhatsApp Sandbox (Development)
For testing, use Twilio's WhatsApp Sandbox:
- Go to: https://www.twilio.com/console/sms/whatsapp/sandbox
- Follow instructions to connect your WhatsApp number
- You'll need to send a specific message (like "join <sandbox-code>") to Twilio's sandbox number

### 3. WhatsApp Business API (Production)
For production use with real patients:
- Apply for WhatsApp Business API approval
- Go to: https://www.twilio.com/console/sms/whatsapp/senders
- Requires business verification and message template approval
- Takes 1-3 days for approval

---

## Step-by-Step Setup

### Step 1: Get Twilio Credentials

1. Log in to Twilio Console: https://www.twilio.com/console
2. Find your credentials on the dashboard:
   - **Account SID**: Starts with "AC..."
   - **Auth Token**: Click "View" to reveal (keep secret!)

### Step 2: Set Up WhatsApp Sandbox

1. Go to WhatsApp Sandbox: https://www.twilio.com/console/sms/whatsapp/sandbox
2. Note your sandbox number (format: `whatsapp:+14155238886`)
3. On your phone, open WhatsApp
4. Send the join message to the sandbox number (e.g., "join example-word")
5. You should receive a confirmation message

### Step 3: Update .env File

Open `d:\Projects\MajorProject\.env` and update these values:

```env
# Twilio Configuration
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_secret_auth_token_here
TWILIO_PHONE_NUMBER=+1234567890
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
```

**Important Notes:**
- Replace `ACxxxxx...` with your actual Account SID
- Replace `your_secret_auth_token_here` with your actual Auth Token
- `TWILIO_PHONE_NUMBER` is for SMS (if you have one)
- `TWILIO_WHATSAPP_NUMBER` should be your sandbox number with `whatsapp:` prefix
- For production, replace sandbox number with your approved WhatsApp number

### Step 4: Make Your Server Publicly Accessible

**The Problem:**
- Twilio needs to download the PDF from a public URL
- Your local server (http://10.158.88.1:5000) is NOT accessible from Twilio's servers
- QR code URLs use your LAN IP which Twilio cannot reach

**Solution Options:**

#### Option A: Use ngrok (Recommended for Development)

1. Install ngrok: https://ngrok.com/download
2. Run ngrok to expose your Flask app:
   ```bash
   ngrok http 5000
   ```
3. You'll get a public URL like: `https://abc123.ngrok.io`
4. Update `.env`:
   ```env
   APPLICATION_BASE_URL=https://abc123.ngrok.io
   ```
5. Restart Flask app

**Important:** ngrok URLs change each time you restart (unless you have a paid account). You'll need to update `.env` each time.

#### Option B: Deploy to Cloud (Recommended for Production)

Deploy your app to a platform with public access:
- **Heroku**: Easy deployment, requires database migration
- **Railway**: Similar to Heroku, better pricing
- **Vercel**: Requires serverless adaptation (see VERCEL_MIGRATION_GUIDE.md)
- **DigitalOcean**: Full control, requires server management
- **AWS EC2**: Enterprise-grade, more complex setup

For production deployment, you'll also need:
- Cloud database (PostgreSQL on Heroku/Railway/Supabase)
- Cloud file storage (AWS S3, Cloudinary, or Vercel Blob)
- See `VERCEL_MIGRATION_GUIDE.md` for detailed migration steps

---

## How It Works

### Automatic Flow

1. **Doctor generates prescription** in the dashboard
2. **System automatically:**
   - Generates PDF with QR code
   - Saves PDF to `generated/` folder
   - Creates visit record in database
   - **Sends WhatsApp message with PDF attachment** (NEW!)
   - Uploads to Google Drive (if configured)
   - Sends SMS with download link (if configured)
3. **Patient receives:**
   - WhatsApp message with PDF as document attachment
   - Can view/download PDF directly in WhatsApp
   - QR code on PDF points to web-accessible version

### Code Flow

**File: `app.py` (line ~1375-1400)**
```python
# After PDF generation and database save...

# Send WhatsApp with PDF automatically
from sms import send_whatsapp_with_pdf

whatsapp_result = send_whatsapp_with_pdf(
    patient_name=data["name"],
    phone_number=data["phone_number"],
    pdf_url=qr_code_url  # Public prescription URL
)
```

**File: `sms.py` - New function:**
```python
def send_whatsapp_with_pdf(patient_name, phone_number, pdf_url, message_body=None):
    """
    Sends WhatsApp with PDF attachment via Twilio WhatsApp API
    """
    # Normalizes phone to E.164 format (+919876543210)
    # Converts to WhatsApp format (whatsapp:+919876543210)
    # Sends message with media_url parameter
    # Returns message SID or None
```

### Phone Number Normalization

The system automatically handles various phone formats:

| Input Format | Normalized Output | WhatsApp Format |
|--------------|-------------------|-----------------|
| `9876543210` | `+919876543210` | `whatsapp:+919876543210` |
| `+919876543210` | `+919876543210` | `whatsapp:+919876543210` |
| `+91 98765 43210` | `+919876543210` | `whatsapp:+919876543210` |
| `98765-43210` | `+919876543210` | `whatsapp:+919876543210` |

**Note:** Currently assumes India (+91) if no country code provided. Modify `normalize_phone_number()` in `sms.py` for other countries.

---

## Testing

### Test 1: Verify Twilio Connection

Create a test script `test_twilio.py`:

```python
from sms import send_whatsapp_with_pdf
import os
from dotenv import load_dotenv

load_dotenv()

# Test with your own WhatsApp number (must be joined to sandbox)
result = send_whatsapp_with_pdf(
    patient_name="Test Patient",
    phone_number="+919876543210",  # Your number
    pdf_url="https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"
)

if result:
    print(f"✅ Success! Message SID: {result}")
else:
    print("❌ Failed! Check console output for errors")
```

Run:
```bash
python test_twilio.py
```

### Test 2: Full Prescription Flow

1. Start your Flask app with ngrok:
   ```bash
   # Terminal 1: Start Flask
   python app.py
   
   # Terminal 2: Start ngrok
   ngrok http 5000
   ```

2. Update `.env` with ngrok URL:
   ```env
   APPLICATION_BASE_URL=https://abc123.ngrok.io
   ```

3. Restart Flask app

4. Generate a prescription:
   - Log in to doctor dashboard
   - Select a patient (use your own WhatsApp number for testing)
   - Generate prescription
   - Check WhatsApp - you should receive the PDF!

5. Scan QR code on PDF:
   - Should open the prescription in browser
   - URL should be: `https://abc123.ngrok.io/prescription/VIS-xxxxx`

---

## Troubleshooting

### Error: "Twilio client not initialized"

**Cause:** Missing or invalid credentials in `.env`

**Solution:**
1. Check `.env` file has correct values
2. Ensure no quotes around values
3. Restart Flask app after changing `.env`
4. Check credentials at https://www.twilio.com/console

### Error: "WhatsApp send failed: Unable to create record"

**Cause:** Phone number not joined to sandbox OR invalid WhatsApp number

**Solution:**
1. Verify patient's phone number is correct in database
2. If testing, ensure YOUR number is joined to Twilio sandbox
3. Send "join <sandbox-code>" to Twilio's WhatsApp sandbox number
4. Wait for confirmation message before testing

### Error: "Unable to fetch content from url"

**Cause:** Twilio cannot access the PDF URL (most common issue)

**Possible Reasons:**
- Using localhost URL (`http://127.0.0.1:5000`)
- Using LAN IP (`http://10.158.88.1:5000`)
- ngrok not running
- ngrok URL not updated in `.env`
- Firewall blocking Twilio's servers

**Solution:**
1. Verify ngrok is running: `ngrok http 5000`
2. Copy the HTTPS URL from ngrok (e.g., `https://abc123.ngrok.io`)
3. Update `.env`: `APPLICATION_BASE_URL=https://abc123.ngrok.io`
4. Restart Flask app
5. Test by opening `https://abc123.ngrok.io/prescription/VIS-xxx` in browser
6. If you can't access it, neither can Twilio

### Error: "Invalid phone number"

**Cause:** Phone number format not recognized

**Solution:**
1. Check patient's mobile number in database
2. Should be 10 digits for India (e.g., `9876543210`)
3. System automatically adds +91 prefix
4. For other countries, modify `normalize_phone_number()` in `sms.py`

### WhatsApp Message Sent But No PDF Attachment

**Cause:** PDF URL returned 404 or access denied

**Solution:**
1. Check Flask logs for errors
2. Verify visit was saved to database successfully
3. Check PDF file exists: `generated/prescription_xxx.pdf`
4. Test URL directly in browser: `https://your-url/prescription/VIS-xxx`
5. Check Flask logs for any authentication errors

### Production: "Sandbox phone numbers can only receive messages..."

**Cause:** Trying to send to non-sandbox number in development

**Solution:**
1. For testing: Only send to numbers joined to your sandbox
2. For production: Apply for WhatsApp Business API approval
3. Go to: https://www.twilio.com/console/sms/whatsapp/senders
4. Complete business verification
5. Create and approve message templates
6. Update `TWILIO_WHATSAPP_NUMBER` to your approved number

---

## Production Deployment Checklist

### Before Going Live:

- [ ] Apply for Twilio WhatsApp Business API approval
- [ ] Create and get message templates approved
- [ ] Deploy app to cloud platform (Heroku/Railway/Vercel)
- [ ] Migrate SQLite to PostgreSQL/MongoDB
- [ ] Set up cloud file storage (S3/Cloudinary/Vercel Blob)
- [ ] Update `APPLICATION_BASE_URL` to production domain
- [ ] Add all Twilio credentials to production environment variables
- [ ] Test with real patient phone numbers (not sandbox)
- [ ] Set up monitoring and error alerts
- [ ] Configure Twilio webhook URLs (if using delivery status callbacks)
- [ ] Enable HTTPS (required for production)
- [ ] Test QR code scanning from actual PDF
- [ ] Verify WhatsApp delivery with test accounts

### Security Considerations:

- [ ] Never commit `.env` file to Git (already in `.gitignore`)
- [ ] Use environment variables for all secrets
- [ ] Rotate Twilio Auth Token periodically
- [ ] Monitor Twilio usage to prevent abuse
- [ ] Implement rate limiting on prescription generation
- [ ] Validate phone numbers before sending
- [ ] Add delivery status logging for compliance
- [ ] Enable Two-Factor Authentication on Twilio account

---

## Cost Considerations

### Twilio Pricing (as of 2024):

**WhatsApp Messages:**
- **User-Initiated (24h window)**: $0.005 per message (cheaper)
- **Business-Initiated**: $0.042+ per message (varies by country)
- **Media messages**: Same price as text messages

**Free Trial:**
- $15 credit when you sign up
- Can send ~300 WhatsApp messages
- Sandbox has no additional costs

**Estimates for MedInfo:**
- 100 prescriptions/day = $0.50/day = $15/month
- 500 prescriptions/day = $2.50/day = $75/month
- 1000 prescriptions/day = $5/day = $150/month

**Cost Optimization:**
- Use business-initiated messages only when necessary
- Consider SMS fallback for non-urgent notifications
- Batch notifications during business hours
- Implement opt-in/opt-out preferences

---

## Alternative: Click-to-Chat (Free)

If Twilio costs are too high, the existing Click-to-Chat implementation is still available:

**Pros:**
- ✅ Completely free
- ✅ No Twilio account needed
- ✅ Already implemented in `static/script.js`

**Cons:**
- ❌ Doctor must manually click WhatsApp button
- ❌ Doctor must manually attach PDF
- ❌ Not automatic
- ❌ Requires doctor to have WhatsApp on device

To use Click-to-Chat only, simply don't configure Twilio credentials in `.env`.

---

## Support and Resources

**Twilio Documentation:**
- WhatsApp API: https://www.twilio.com/docs/whatsapp
- WhatsApp Sandbox: https://www.twilio.com/docs/whatsapp/sandbox
- Media Messages: https://www.twilio.com/docs/whatsapp/api#media-messages
- Error Codes: https://www.twilio.com/docs/api/errors

**MedInfo Documentation:**
- API Documentation: `API_DOCUMENTATION.md`
- Complete Setup Guide: `COMPLETE_SETUP_GUIDE.md`
- Vercel Migration: `VERCEL_MIGRATION_GUIDE.md` (to be created)

**Ngrok Documentation:**
- Getting Started: https://ngrok.com/docs/getting-started
- Reserved Domains: https://ngrok.com/docs/using-ngrok/reserve-domain (for consistent URLs)

---

## Summary

**What Was Implemented:**
1. ✅ `sms.py` - Added `send_whatsapp_with_pdf()` function
2. ✅ `sms.py` - Added `normalize_phone_number()` helper
3. ✅ `sms.py` - Improved error handling and logging
4. ✅ `app.py` - Automatic WhatsApp sending after PDF generation
5. ✅ `.env` - Added Twilio WhatsApp configuration placeholders

**What You Need To Do:**
1. Sign up for Twilio account
2. Set up WhatsApp Sandbox
3. Update `.env` with your credentials
4. Use ngrok for development testing
5. Plan cloud migration for production

**Next Steps:**
1. Test with ngrok and sandbox
2. Verify WhatsApp messages are received
3. Plan production deployment (see VERCEL_MIGRATION_GUIDE.md)
4. Apply for WhatsApp Business API approval
5. Migrate databases and file storage to cloud

Good luck! 🚀
