from twilio.rest import Client
import os
from dotenv import load_dotenv

load_dotenv()

# Initialize Twilio client only if credentials are provided
account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")

client = None
if account_sid and auth_token and account_sid != "your_account_sid_here":
    try:
        client = Client(account_sid, auth_token)
    except Exception as e:
        print(f"Twilio client initialization failed: {e}")


def normalize_phone_number(phone_number):
    """
    Normalize phone number to E.164 format required by Twilio.
    Removes spaces, hyphens, and ensures proper format.
    
    Examples:
        "+919876543210" -> "+919876543210"
        "9876543210" -> "+919876543210"
        "+91 98765 43210" -> "+919876543210"
    """
    if not phone_number:
        return None
    
    # Remove all non-digit characters except leading +
    cleaned = ''.join(c for c in phone_number if c.isdigit() or (c == '+' and phone_number.index(c) == 0))
    
    # If no country code, assume India (+91)
    if not cleaned.startswith('+'):
        cleaned = f'+91{cleaned}'
    
    return cleaned


def send_sms(patient_name, phone_number, download_url):
    """
    Send SMS with prescription download link using Twilio SMS API.
    """
    if not client:
        print("Twilio client not initialized. Check your credentials in .env file.")
        return None

    body = f"""
Shri XYZ Clinic

Dear {patient_name},

Your prescription is ready.

Download:
{download_url}

Regards,
Dr. XYZ
"""

    normalized_phone = normalize_phone_number(phone_number)
    if not normalized_phone:
        print(f"Invalid phone number: {phone_number}")
        return None

    try:
        message = client.messages.create(
            body=body,
            from_=os.getenv("TWILIO_PHONE_NUMBER"),
            to=normalized_phone
        )

        print("SMS Sent Successfully!")
        print("Message SID:", message.sid)
        return message.sid
    except Exception as e:
        print(f"SMS send failed: {e}")
        return None


def send_whatsapp_with_pdf(patient_name, phone_number, pdf_url, message_body=None):
    """
    Send WhatsApp message with PDF attachment using Twilio WhatsApp API.
    
    Args:
        patient_name: Name of the patient
        phone_number: Patient's phone number (can be with or without country code)
        pdf_url: Publicly accessible URL of the PDF file (Twilio will download from this URL)
        message_body: Optional custom message body
    
    Returns:
        Message SID if successful, None otherwise
        
    Note:
        - PDF must be accessible via public URL (not localhost or LAN IPs)
        - For development, use ngrok to expose local server
        - For production, use cloud storage (S3, Cloudinary, Vercel Blob, etc.)
    """
    if not client:
        print("Twilio client not initialized. Check your credentials in .env file.")
        print("Required: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_NUMBER")
        return None
    
    # Normalize phone number to E.164 format
    normalized_phone = normalize_phone_number(phone_number)
    if not normalized_phone:
        print(f"Invalid phone number: {phone_number}")
        return None
    
    # WhatsApp phone format: 'whatsapp:+919876543210'
    whatsapp_to = f'whatsapp:{normalized_phone}'
    whatsapp_from = os.getenv("TWILIO_WHATSAPP_NUMBER")
    
    if not whatsapp_from:
        print("TWILIO_WHATSAPP_NUMBER not configured in .env file")
        return None
    
    # Ensure from number is in whatsapp: format
    if not whatsapp_from.startswith('whatsapp:'):
        whatsapp_from = f'whatsapp:{whatsapp_from}'
    
    # Default message if not provided
    if not message_body:
        message_body = f"""Dear {patient_name},

Your prescription from XYZ Clinic is ready. Please find the attached PDF document.

Regards,
Dr. XYZ
XYZ Clinic"""
    
    try:
        # Send WhatsApp message with PDF attachment
        message = client.messages.create(
            body=message_body,
            from_=whatsapp_from,
            to=whatsapp_to,
            media_url=[pdf_url]  # Twilio will download PDF from this URL
        )
        
        print(f"WhatsApp sent successfully to {normalized_phone}")
        print(f"Message SID: {message.sid}")
        print(f"Status: {message.status}")
        
        return message.sid
        
    except Exception as e:
        print(f"WhatsApp send failed for {normalized_phone}: {e}")
        print(f"PDF URL attempted: {pdf_url}")
        return None