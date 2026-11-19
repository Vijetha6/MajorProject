"""
Test script to verify Twilio WhatsApp integration setup
"""
import os
from dotenv import load_dotenv

load_dotenv()

print("=" * 70)
print("TWILIO WHATSAPP INTEGRATION VERIFICATION")
print("=" * 70)

# Check if credentials are loaded
print("\n1. CHECKING ENVIRONMENT VARIABLES:")
print("-" * 70)

account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
phone_number = os.getenv("TWILIO_PHONE_NUMBER")
whatsapp_number = os.getenv("TWILIO_WHATSAPP_NUMBER")

print(f"TWILIO_ACCOUNT_SID: {'✓ Found' if account_sid else '✗ Missing'}")
if account_sid:
    print(f"  Value: {account_sid[:10]}...{account_sid[-4:]}")
    
print(f"TWILIO_AUTH_TOKEN: {'✓ Found' if auth_token else '✗ Missing'}")
if auth_token:
    print(f"  Value: {'*' * len(auth_token[:10])}...{auth_token[-4:]}")
    
print(f"TWILIO_PHONE_NUMBER: {'✓ Found' if phone_number else '✗ Missing'}")
if phone_number:
    print(f"  Value: {phone_number}")
    
print(f"TWILIO_WHATSAPP_NUMBER: {'✓ Found' if whatsapp_number else '✗ Missing'}")
if whatsapp_number:
    print(f"  Value: {whatsapp_number}")

# Check if credentials are placeholders
print("\n2. CHECKING IF CREDENTIALS ARE REAL:")
print("-" * 70)

if account_sid and account_sid != "your_account_sid_here":
    print("✓ Account SID appears to be real (not placeholder)")
else:
    print("✗ Account SID is still placeholder or missing")

if auth_token and auth_token != "your_auth_token_here":
    print("✓ Auth Token appears to be real (not placeholder)")
else:
    print("✗ Auth Token is still placeholder or missing")

# Try to initialize Twilio client
print("\n3. TESTING TWILIO CLIENT INITIALIZATION:")
print("-" * 70)

try:
    from twilio.rest import Client
    
    if account_sid and auth_token and account_sid != "your_account_sid_here":
        client = Client(account_sid, auth_token)
        print("✓ Twilio client initialized successfully")
        
        # Try to get account info
        try:
            account = client.api.accounts(account_sid).fetch()
            print(f"✓ Successfully connected to Twilio account")
            print(f"  Account Status: {account.status}")
            print(f"  Account Friendly Name: {account.friendly_name}")
        except Exception as e:
            print(f"✗ Failed to fetch account info: {e}")
    else:
        print("✗ Cannot initialize client - credentials missing or placeholder")
        
except ImportError:
    print("✗ Twilio library not installed. Run: pip install twilio")
except Exception as e:
    print(f"✗ Error initializing Twilio client: {e}")

# Test the WhatsApp function
print("\n4. TESTING WHATSAPP FUNCTION IMPORT:")
print("-" * 70)

try:
    from sms import send_whatsapp_with_pdf, normalize_phone_number
    print("✓ send_whatsapp_with_pdf function imported successfully")
    print("✓ normalize_phone_number function imported successfully")
    
    # Test phone normalization
    print("\n  Testing phone number normalization:")
    test_numbers = [
        "9876543210",
        "+919876543210",
        "+91 98765 43210",
        "91-98765-43210"
    ]
    
    for num in test_numbers:
        normalized = normalize_phone_number(num)
        print(f"    {num:20} → {normalized}")
        
except Exception as e:
    print(f"✗ Error importing WhatsApp function: {e}")

# Check if function is called in app.py
print("\n5. CHECKING INTEGRATION IN APP.PY:")
print("-" * 70)

try:
    with open("app.py", "r", encoding="utf-8") as f:
        content = f.read()
        
    if "send_whatsapp_with_pdf" in content:
        print("✓ send_whatsapp_with_pdf is imported in app.py")
    else:
        print("✗ send_whatsapp_with_pdf NOT found in app.py")
        
    if "whatsapp_result = send_whatsapp_with_pdf(" in content:
        print("✓ send_whatsapp_with_pdf is called in app.py")
    else:
        print("✗ send_whatsapp_with_pdf NOT called in app.py")
        
    # Check if it's in the right location (after PDF generation)
    lines = content.split('\n')
    found_generate_pdf = False
    found_whatsapp_call = False
    
    for i, line in enumerate(lines):
        if "generate_prescription_pdf" in line and "def " not in line:
            found_generate_pdf = True
        if found_generate_pdf and "send_whatsapp_with_pdf(" in line:
            found_whatsapp_call = True
            break
    
    if found_whatsapp_call:
        print("✓ WhatsApp sending is integrated after PDF generation")
    else:
        print("✗ WhatsApp sending position unclear")
        
except Exception as e:
    print(f"✗ Error checking app.py: {e}")

# Summary
print("\n" + "=" * 70)
print("SUMMARY:")
print("=" * 70)

issues = []
warnings = []

if not account_sid or account_sid == "your_account_sid_here":
    issues.append("Twilio Account SID not configured")
if not auth_token or auth_token == "your_auth_token_here":
    issues.append("Twilio Auth Token not configured")
if not whatsapp_number:
    issues.append("Twilio WhatsApp number not configured")

# Check if using local URL
app_base_url = os.getenv("APPLICATION_BASE_URL", "")
if "localhost" in app_base_url or "127.0.0.1" in app_base_url:
    warnings.append("APPLICATION_BASE_URL uses localhost - Twilio cannot access")
elif app_base_url.startswith("http://10.") or app_base_url.startswith("http://192.168."):
    warnings.append("APPLICATION_BASE_URL uses LAN IP - Twilio cannot access (use ngrok)")

if issues:
    print("\n❌ ISSUES FOUND:")
    for issue in issues:
        print(f"  - {issue}")
else:
    print("\n✓ No critical issues found")

if warnings:
    print("\n⚠️  WARNINGS:")
    for warning in warnings:
        print(f"  - {warning}")

print("\n" + "=" * 70)
print("NEXT STEPS:")
print("=" * 70)

if issues:
    print("\n1. Update .env file with real Twilio credentials")
    print("2. Get credentials from: https://www.twilio.com/console")
    print("3. Set up WhatsApp Sandbox: https://www.twilio.com/console/sms/whatsapp/sandbox")
    
if warnings:
    print("\n4. Install ngrok: https://ngrok.com/download")
    print("5. Run: ngrok http 5000")
    print("6. Update APPLICATION_BASE_URL in .env with ngrok HTTPS URL")
    print("7. Restart Flask app")

if not issues:
    print("\n✓ Configuration looks good!")
    print("  - Test by generating a prescription with your phone number")
    print("  - Check WhatsApp for PDF delivery")

print("\n" + "=" * 70)
