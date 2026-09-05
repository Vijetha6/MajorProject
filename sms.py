from twilio.rest import Client
import os
from dotenv import load_dotenv

load_dotenv()

client = Client(
    os.getenv("TWILIO_ACCOUNT_SID"),
    os.getenv("TWILIO_AUTH_TOKEN")
)

def send_sms(patient_name, phone_number, download_url):

    body = f"""
Shri XYZ Clinic

Dear {patient_name},

Your prescription is ready.

Download:
{download_url}

Regards,
Dr. XYZ
"""

    message = client.messages.create(
        body=body,
        from_=os.getenv("TWILIO_PHONE_NUMBER"),
        to=phone_number
    )

    print("SMS Sent Successfully!")
    print("Message SID:", message.sid)

    return message.sid