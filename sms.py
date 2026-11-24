from twilio.rest import Client
import os
from textwrap import dedent
from dotenv import load_dotenv

load_dotenv()

def send_sms(patient_name, phone_number, download_url):
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    from_number = os.getenv("TWILIO_PHONE_NUMBER", "").strip()
    missing_settings = [
        name
        for name, value in (
            ("TWILIO_ACCOUNT_SID", account_sid),
            ("TWILIO_AUTH_TOKEN", auth_token),
            ("TWILIO_PHONE_NUMBER", from_number),
        )
        if not value
    ]
    if missing_settings:
        raise RuntimeError(
            "SMS is not configured; missing " + ", ".join(missing_settings)
        )
    if not phone_number or not phone_number.startswith("+"):
        raise ValueError("The patient phone number must use international format.")

    body = dedent(f"""\
        Shri XYZ Clinic

        Dear {patient_name},

        Your prescription is ready.

        Download:
        {download_url}

        Regards,
        Dr. XYZ
        """).strip()

    message = Client(account_sid, auth_token).messages.create(
        body=body,
        from_=from_number,
        to=phone_number,
    )

    return message.sid