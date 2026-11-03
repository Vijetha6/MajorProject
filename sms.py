import os
from dotenv import load_dotenv

load_dotenv()


def is_sms_configured():
    return all(os.getenv(key, "").strip() for key in (
        "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN",
        "TWILIO_PHONE_NUMBER",
    ))

def send_sms(patient_name, phone_number, download_url):
    if not is_sms_configured():
        raise RuntimeError("Twilio SMS is not configured.")

    if not phone_number or not phone_number.startswith("+"):
        raise ValueError("SMS recipient must be a valid E.164 phone number.")

    from twilio.rest import Client

    client = Client(
        os.environ["TWILIO_ACCOUNT_SID"],
        os.environ["TWILIO_AUTH_TOKEN"],
    )
    body = (
        f"Dear {patient_name}, your prescription is ready. "
        f"Download: {download_url}"
    )

    message = client.messages.create(
        body=body,
        from_=os.environ["TWILIO_PHONE_NUMBER"],
        to=phone_number,
    )

    return message.sid