
import os
import re
import time
import shutil
import json
import logging
import uuid
import hashlib
import sqlite3
from database import (
    init_database,
    add_medicine,
    get_all_medicines,
    get_medicine,
    search_medicines,
    update_medicine,
    update_quantity,
    delete_medicine,
    get_expiring_medicines,
    get_expired_medicines,
    get_low_stock_medicines
)

from database import (
    init_prescription_database,
    save_prescription,
    get_patient_prescriptions,
    get_prescription_by_token,
    get_prescription_by_request_id,
)


from flask import abort
import cv2
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import pytesseract
import easyocr
try:
    from google import genai
except Exception:
    genai = None
from roboflow import Roboflow
from dotenv import load_dotenv
from drive_upload import upload_pdf_to_drive

try:
    from sms import send_sms, is_sms_configured
except Exception:
    def send_sms(patient_name, phone_number, download_url):
        raise RuntimeError("SMS support is unavailable.")

    def is_sms_configured():
        return False
from flask import Flask, request, jsonify, render_template, send_from_directory
from werkzeug.utils import secure_filename
from difflib import get_close_matches
from datetime import datetime, timedelta
from fpdf import FPDF
import qrcode
from PIL import Image, ImageDraw, ImageFont

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
logger = logging.getLogger(__name__)
if genai is None:
    client = None
    logger.warning("google.genai not available; Gemini features disabled")
elif not GEMINI_API_KEY:
    client = None
    logger.warning("GEMINI_API_KEY not set; Gemini features disabled")
else:
    client = genai.Client(api_key=GEMINI_API_KEY)
    print("✅ Gemini Loaded")


# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
logging.getLogger("urllib3").setLevel(logging.WARNING)

app = Flask(__name__)
init_database()
init_prescription_database()

UPLOAD_FOLDER = "uploads"
GENERATED_FOLDER = "generated"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(GENERATED_FOLDER, exist_ok=True)

# Initialize EasyOCR
try:
    reader = easyocr.Reader(['en'], gpu=False)
    logger.info("✓ EasyOCR initialized successfully")
except Exception as e:
    logger.error(f"✗ EasyOCR initialization failed: {e}")
    reader = None

# Configure Tesseract path
def setup_tesseract():
    possible_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        "/usr/bin/tesseract",
        "/usr/local/bin/tesseract",
        shutil.which("tesseract")
    ]
    
    for path in possible_paths:
        if path and os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            logger.info(f"✓ Tesseract found at: {path}")
            return True
    
    logger.error("✗ Tesseract not found! Please install Tesseract OCR")
    return False

setup_tesseract()

# Initialize YOLO model
model = None
try:
    api_key = os.getenv("ROBOFLOW_API_KEY")
    if not api_key:
        logger.warning("⚠️  ROBOFLOW_API_KEY not set in environment. YOLO detection disabled.")
    else:
        rf = Roboflow(api_key=api_key)
        project = rf.workspace().project("medicine-tkh2j-3a53i")
        model = project.version(5).model
        logger.info("✓ YOLO model initialized successfully")
except Exception as e:
    logger.error(f"✗ YOLO model initialization failed: {e}")
    model = None

# File cleanup: remove files older than 24 hours
def cleanup_old_files():
    """Remove uploaded files older than 24 hours to save disk space"""
    try:
        if not os.path.exists(UPLOAD_FOLDER):
            return
        
        now = datetime.now()
        cutoff_time = now - timedelta(hours=24)
        
        for filename in os.listdir(UPLOAD_FOLDER):
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            if os.path.isfile(filepath):
                file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                if file_time < cutoff_time:
                    try:
                        os.remove(filepath)
                        logger.info(f"Cleaned up old file: {filename}")
                    except Exception as e:
                        logger.error(f"Failed to cleanup {filename}: {e}")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")

COMMON_RX_MEDICINES = {
    'paracetamol': '500 mg', 'amoxicillin': '500 mg', 'crocin': '650 mg',
    'dolo': '650 mg', 'cipla': '150 mg', 'citizen': '150 mg', 'citizone': '10 mg',
    'cetirizine': '10 mg', 'amlodipine': '5 mg', 'metformin': '500 mg',
    'aspirin': '75 mg', 'ibuprofen': '400 mg', 'losartan': '50 mg',
    'omeprazole': '20 mg', 'pantoprazole': '40 mg', 'gastro': '150 mg'
}

COMMON_MEDICINES = [
    'paracetamol', 'amoxicillin', 'crocin', 'dolo', 'cipla', 'citizen', 'citizone',
    'cetirizine', 'amlodipine', 'metformin', 'aspirin', 'ibuprofen', 'losartan',
    'omeprazole', 'pantoprazole', 'gastro'
]

NOISE_WORDS = [ 
    'download', 'price', 'gas', 'station', 'stations',
    'zone', 'bandra', '3 is on', 'in a', 'day for',
    'once in', 'twice in', 'three is', 'on twice',
    'a week in', 'week in a', 'for 1 week', 'for 2 weeks',
    'resistance', 'season', 'half', 'trees'
]

REPLACEMENTS = {
    'citizone': 'cetirizine',
    'once in a day': 'once daily',
    'twice in a day': 'twice daily',
    'thrice in a day': 'thrice daily',
    'one per day': 'once daily',
    'two per day': 'twice daily',
    'three per day': 'thrice daily',
    'half per day': 'once daily',
    'one per week': 'once weekly',
    'two per week': 'twice weekly',
    'three per week': 'thrice weekly',
    'once in a week': 'once weekly',
    'twice in a week': 'twice weekly',
    "citrus": "cetirizine",
    "cetrizine": "cetirizine",
    "cetrazine": "cetirizine",
    "once in a day": "once daily",
    "twice in a day": "twice daily",
    "one per day": "once daily",
    "two per day": "twice daily",
    "three per day": "thrice daily",
    "half per day": "half daily"

}


def clean_prescription_text(text):

    lines = text.splitlines()

    cleaned = []

    for line in lines:

        line = line.lower()

        for wrong, correct in REPLACEMENTS.items():
            line = line.replace(wrong, correct)

        line = re.sub(r'\s+', ' ', line).strip()

        cleaned.append(line)

    return "\n".join(cleaned)


def validate_prescription_text(text):

    text = text.lower()

    medicine_found = any(
        med in text
        for med in COMMON_RX_MEDICINES
    )

    return medicine_found

def word_to_number(text):
    mapping = {
        "one": "1",
        "two": "2",
        "three": "3",
        "four": "4",
        "five": "5",
        "six": "6",
        "seven": "7",
        "half": "1/2"
    }

    words = text.split()
    converted = []

    for w in words:
        converted.append(mapping.get(w.lower(), w))

    return " ".join(converted)


def parse_prescription(text):

    text = clean_prescription_text(word_to_number(text))

    # Prescription text now contains ONLY medicines (no patient details)
    prescription = text

    # Split every medicine separately
    medicine_lines = [
        x.strip()
        for x in re.split(r'[\n\.]+', prescription)
        if x.strip()
    ]

    medicines = []

    for line in medicine_lines:

        line_lower = line.lower()

        # Medicine name
        med_match = re.match(r'^([A-Za-z]+)', line)

        if not med_match:
            continue

        medicine = med_match.group(1).title()

        # ---------------- Dosage ----------------

        dosage = "As directed"

        d = re.search(
            r'(\d+(?:/\d+)?)\s*(mg|ml|mcg|g|tablet|tab|capsule|cap)?',
            line_lower
        )

        if d:
            dosage = d.group(1)

            if d.group(2):
                dosage += " " + d.group(2)

        # ---------------- Frequency ----------------

        frequency = "As directed"

        if ("once daily" in line_lower or
            "once per day" in line_lower or
            "1 per day" in line_lower):

            frequency = "Once daily"

        elif ("twice daily" in line_lower or
              "twice a day" in line_lower or
              "2 per day" in line_lower):

            frequency = "Twice daily"

        elif ("thrice daily" in line_lower or
              "3 per day" in line_lower):

            frequency = "Thrice daily"

        elif ("once weekly" in line_lower or
              "once per week" in line_lower):

            frequency = "Once weekly"

        elif ("twice weekly" in line_lower or
              "twice per week" in line_lower):

            frequency = "Twice weekly"

        # ---------------- Duration ----------------

        duration = "As directed"

        dur = re.search(
            r'for\s+(\d+)\s+(day|days|week|weeks|month|months)',
            line_lower
        )

        if dur:
            duration = f"{dur.group(1)} {dur.group(2)}"

        medicines.append({
            "name": medicine,
            "dosage": dosage,
            "frequency": frequency,
            "duration": duration
        })

    return {
        "name": "",
        "age": "",
        "gender": "",
        "doctor": "",
        "clinic": "",
        "address": "",
        "phone": "",
        "email": "",
        "medicines": medicines
    }


def create_prescription_filename(patient_name):
    return f"prescription_{uuid.uuid4().hex}.pdf"


def _prescription_config():
    return {
        "doctor": os.getenv("DOCTOR_NAME", "").strip(),
        "clinic": os.getenv("CLINIC_NAME", "").strip(),
        "tagline": os.getenv("CLINIC_TAGLINE", "").strip(),
        "address": os.getenv("CLINIC_ADDRESS", "").strip(),
        "clinic_phone": os.getenv("CLINIC_PHONE", "").strip(),
        "clinic_email": os.getenv("CLINIC_EMAIL", "").strip(),
    }


def _pdf_detail(pdf, label, value, x, y, width):
    pdf.set_xy(x, y)
    pdf.set_font("Arial", "B", 9)
    pdf.cell(28, 6, label)
    pdf.set_font("Arial", "", 9)
    pdf.set_xy(x + 28, y)
    pdf.multi_cell(width - 28, 6, str(value))


def generate_prescription_pdf(data, download_url, filepath):
    class PrescriptionPDF(FPDF):
        def footer(self):
            self.set_y(-13)
            self.set_font("Arial", "I", 7)
            self.set_text_color(100, 100, 100)
            self.cell(
                0,
                5,
                "Generated for review. The prescribing doctor must sign this prescription.",
                0,
                0,
                "C",
            )
            self.set_text_color(0, 0, 0)

    pdf = PrescriptionPDF()
    pdf.set_margins(15, 14, 15)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.set_text_color(25, 50, 80)
    pdf.set_font("Arial", "B", 16)
    pdf.multi_cell(0, 8, data["clinic"], align="C")
    if data["tagline"]:
        pdf.set_font("Arial", "I", 9)
        pdf.multi_cell(0, 5, data["tagline"], align="C")
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", "", 9)
    if data["address"]:
        pdf.multi_cell(0, 5, data["address"], align="C")
    contact_details = []
    if data["clinic_phone"]:
        contact_details.append(f"Phone: {data['clinic_phone']}")
    if data["clinic_email"]:
        contact_details.append(f"Email: {data['clinic_email']}")
    if contact_details:
        pdf.multi_cell(0, 5, "   ".join(contact_details), align="C")
    pdf.ln(2)
    pdf.set_font("Arial", "B", 13)
    pdf.cell(0, 8, "PRESCRIPTION", 0, 1, "C")
    pdf.set_font("Arial", "", 9)
    pdf.cell(0, 6, f"Date: {data['prescription_date']}", 0, 1, "R")

    details_y = pdf.get_y() + 2
    _pdf_detail(pdf, "Patient:", data["name"], 15, details_y, 85)
    _pdf_detail(pdf, "Doctor:", data["doctor"], 110, details_y, 85)
    _pdf_detail(pdf, "Mobile:", data["phone_number"], 15, details_y + 7, 85)
    _pdf_detail(pdf, "Clinic:", data["clinic"], 110, details_y + 7, 85)
    _pdf_detail(pdf, "Age:", data["age"], 15, details_y + 14, 85)
    _pdf_detail(pdf, "Gender:", data["gender"], 110, details_y + 14, 85)
    pdf.set_y(details_y + 23)

    column_widths = [45, 28, 32, 38, 37]
    headers = ["Medicine Name", "Dosage", "Dose M-A-E-B", "Frequency", "Duration"]

    def draw_table_header():
        pdf.set_font("Arial", "B", 8)
        pdf.set_fill_color(220, 232, 244)
        for width, heading in zip(column_widths, headers):
            pdf.cell(width, 8, heading, border=1, align="C", fill=True)
        pdf.ln()

    draw_table_header()
    for medicine in data["medicines"]:
        values = [
            medicine["name"],
            medicine["dosage"],
            medicine.get("dose_schedule") or "-",
            medicine["frequency"],
            medicine["duration"],
        ]
        pdf.set_font("Arial", "", 8)
        wrapped = [
            pdf.multi_cell(width - 4, 4.5, value, split_only=True)
            for width, value in zip(column_widths, values)
        ]
        row_height = max(8, max(len(lines) for lines in wrapped) * 4.5 + 3)
        notes = []
        if medicine.get("timing"):
            notes.append("Timing: " + ", ".join(medicine["timing"]))
        if medicine.get("food_instruction"):
            notes.append("Food: " + medicine["food_instruction"])
        if medicine.get("special_instructions"):
            notes.append("Special instructions: " + medicine["special_instructions"])
        note_text = " | ".join(notes)
        note_lines = (
            pdf.multi_cell(sum(column_widths) - 4, 4.5, note_text, split_only=True)
            if note_text
            else []
        )
        note_height = len(note_lines) * 4.5 + 3 if note_lines else 0
        if pdf.get_y() + row_height + note_height > 264:
            pdf.add_page()
            draw_table_header()
        row_y = pdf.get_y()
        for index, (width, value, lines) in enumerate(zip(column_widths, values, wrapped)):
            x = 15 + sum(column_widths[:index])
            pdf.rect(x, row_y, width, row_height)
            pdf.set_xy(x + 2, row_y + 1.5)
            pdf.multi_cell(width - 4, 4.5, value, align="L")
        pdf.set_y(row_y + row_height)
        if note_text:
            pdf.set_font("Arial", "I", 8)
            pdf.set_fill_color(248, 250, 252)
            pdf.multi_cell(sum(column_widths), 4.5, note_text, border=1, fill=True)
            pdf.set_fill_color(255, 255, 255)

    if pdf.get_y() > 235:
        pdf.add_page()
    else:
        pdf.ln(10)
    signature_y = pdf.get_y()
    pdf.set_font("Arial", "B", 9)
    pdf.cell(90, 6, "Doctor's signature:", 0, 0)
    pdf.cell(0, 6, "Scan to download", 0, 1, "C")
    pdf.set_font("Arial", "", 9)
    pdf.cell(90, 8, "________________________________", 0, 1)
    pdf.cell(90, 6, data["doctor"], 0, 0)

    qr_path = os.path.join(GENERATED_FOLDER, f".qr_{uuid.uuid4().hex}.png")
    try:
        qr = qrcode.QRCode(
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=4,
            border=2,
        )
        qr.add_data(download_url)
        qr.make(fit=True)
        qr.make_image(fill_color="black", back_color="white").save(qr_path)
        pdf.image(qr_path, x=155, y=signature_y + 6, w=30, h=30)
        pdf.output(filepath)
    finally:
        if os.path.exists(qr_path):
            os.remove(qr_path)



@app.route('/generate-prescription', methods=['POST'])
def generate_prescription():
    filepath = None
    try:
        payload = request.get_json(silent=True) if request.is_json else request.form.to_dict()
        if not isinstance(payload, dict):
            return jsonify({"error": "A valid JSON or form request is required."}), 400

        def required_text(value, label, max_length):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{label} is required.")
            if len(value) > max_length:
                raise ValueError(f"{label} must be {max_length} characters or fewer.")
            if any(ord(char) < 32 and char not in "\t" for char in value):
                raise ValueError(f"{label} contains unsupported control characters.")
            return value.strip()

        patient_name = required_text(payload.get("patient_name"), "Patient name", 200)
        age = required_text(payload.get("age"), "Age", 3)
        if not age.isdecimal() or not 1 <= int(age) <= 150:
            return jsonify({"error": "Age must be a whole number between 1 and 150."}), 400

        gender = required_text(payload.get("gender"), "Gender", 20)
        if gender not in {"Male", "Female", "Other"}:
            return jsonify({"error": "Select Male, Female, or Other for gender."}), 400

        phone_number = required_text(payload.get("phone_number"), "Mobile number", 16)
        if re.fullmatch(r"[6-9]\d{9}", phone_number):
            phone_number = "+91" + phone_number
        elif not re.fullmatch(r"\+91[6-9]\d{9}", phone_number):
            return jsonify({"error": "Enter a valid 10-digit Indian mobile number, optionally prefixed with +91."}), 400

        medicines_raw = payload.get("medicines")
        legacy_text = payload.get("text")
        legacy_request = medicines_raw is None and isinstance(legacy_text, str)
        if legacy_request:
            legacy_lines = [line.strip() for line in legacy_text.splitlines() if line.strip()]
            if not legacy_lines:
                return jsonify({"error": "Add at least one medicine before generating the prescription."}), 400
            medicines_list = []
            frequency_pattern = (
                r"(?:once daily|once a day|once per day|twice daily|twice a day|"
                r"twice per day|thrice daily|three times a day|once weekly|"
                r"once per week|twice weekly|twice per week|as needed)"
            )
            for index, line in enumerate(legacy_lines, start=1):
                duration_match = re.search(
                    r"\bfor\s+(\d+\s+(?:days?|weeks?|months?))\s*\.?$",
                    line,
                    re.IGNORECASE,
                )
                if not duration_match:
                    return jsonify({"error": f"Legacy medicine line {index} must include a frequency and duration; use the structured form if it cannot be parsed exactly."}), 400
                before_duration = line[:duration_match.start()].rstrip()
                frequency_match = re.search(
                    rf"\b({frequency_pattern})\s*$",
                    before_duration,
                    re.IGNORECASE,
                )
                if not frequency_match:
                    return jsonify({"error": f"Legacy medicine line {index} must include a recognized frequency."}), 400
                medicine_and_dosage = before_duration[:frequency_match.start()].rstrip()
                dosage_match = re.search(
                    r"(?P<dosage>\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|tablet|tablets|tab|capsule|capsules))$",
                    medicine_and_dosage,
                    re.IGNORECASE,
                )
                if not dosage_match:
                    return jsonify({"error": f"Legacy medicine line {index} must include a dosage with units."}), 400
                name = medicine_and_dosage[:dosage_match.start()].strip()
                if not name:
                    return jsonify({"error": f"Legacy medicine line {index} is missing the medicine name."}), 400
                medicines_list.append({
                    "name": name,
                    "dosage": dosage_match.group("dosage"),
                    "dose_schedule": "",
                    "frequency": frequency_match.group(1),
                    "timing": [],
                    "food_instruction": "Not specified in legacy text",
                    "duration": duration_match.group(1),
                    "special_instructions": "",
                })
        else:
            if not isinstance(medicines_raw, list) or not medicines_raw:
                return jsonify({"error": "Add at least one medicine before generating the prescription."}), 400
            if len(medicines_raw) > 50:
                return jsonify({"error": "A prescription can contain at most 50 medicines."}), 400
            if payload.get("review_confirmed") is not True:
                return jsonify({"error": "Review the patient details and all medicines, then confirm before generating."}), 400

            medicines_list = []
            valid_timings = {"Morning", "Afternoon", "Evening", "Bedtime"}
            for index, medicine in enumerate(medicines_raw, start=1):
                if not isinstance(medicine, dict):
                    return jsonify({"error": f"Medicine #{index} has an invalid format."}), 400
                try:
                    name = required_text(medicine.get("name"), f"Medicine #{index} name", 200)
                    dosage = required_text(medicine.get("dosage"), f"Medicine #{index} dosage", 100)
                    frequency = required_text(medicine.get("frequency"), f"Medicine #{index} frequency", 100)
                    food = required_text(medicine.get("food_instruction"), f"Medicine #{index} food instruction", 100)
                    duration = required_text(medicine.get("duration"), f"Medicine #{index} duration", 100)
                    special = medicine.get("special_instructions", "")
                    if not isinstance(special, str) or len(special) > 500:
                        raise ValueError(f"Medicine #{index} special instructions must be 500 characters or fewer.")
                    dose_schedule = medicine.get("dose_schedule", "")
                    if not isinstance(dose_schedule, str) or len(dose_schedule) > 32:
                        raise ValueError(f"Medicine #{index} dose schedule must be 32 characters or fewer.")
                    dose_schedule = dose_schedule.strip()
                    if dose_schedule and not re.fullmatch(
                        r"\d+(?:\.\d+)?(?:[- ]+\d+(?:\.\d+)?){3}",
                        dose_schedule,
                    ):
                        raise ValueError(
                            f"Medicine #{index} dose schedule must contain four values in Morning-Afternoon-Evening-Bedtime order, such as 1-0-0-1 or 1 0 0 1."
                        )
                    if "\n" in name or "\r" in name or "\n" in dosage or "\r" in dosage:
                        raise ValueError(f"Medicine #{index} name and dosage must each be a single line.")
                    timing = medicine.get("timing", [])
                    if not isinstance(timing, list) or any(
                        not isinstance(item, str) or item not in valid_timings for item in timing
                    ):
                        raise ValueError(f"Medicine #{index} has an invalid timing selection.")
                    if len(set(timing)) != len(timing):
                        raise ValueError(f"Medicine #{index} timing selections must not be duplicated.")
                    if frequency.casefold() != "as needed" and not timing:
                        raise ValueError(f"Medicine #{index} requires at least one timing selection.")
                    medicines_list.append({
                        "name": name,
                        "dosage": dosage,
                        "dose_schedule": dose_schedule,
                        "frequency": frequency,
                        "timing": timing,
                        "food_instruction": food,
                        "duration": duration,
                        "special_instructions": special.strip(),
                    })
                except ValueError as exc:
                    return jsonify({"error": str(exc)}), 400

        config = _prescription_config()
        config_keys = {
            "doctor": "DOCTOR_NAME",
            "clinic": "CLINIC_NAME",
            "tagline": "CLINIC_TAGLINE",
            "address": "CLINIC_ADDRESS",
            "clinic_phone": "CLINIC_PHONE",
            "clinic_email": "CLINIC_EMAIL",
        }
        required_config = ("doctor", "clinic")
        missing_config = [key for key in required_config if not config[key]]
        if missing_config:
            missing_names = ", ".join(config_keys[key] for key in missing_config)
            return jsonify({
                "error": f"Prescription clinic configuration is incomplete. Set these values in .env: {missing_names}."
            }), 503

        data = {
            "name": patient_name,
            "age": f"{age} years",
            "gender": gender,
            "phone_number": phone_number,
            "doctor": config["doctor"],
            "clinic": config["clinic"],
            "tagline": config["tagline"],
            "address": config["address"],
            "clinic_phone": config["clinic_phone"],
            "clinic_email": config["clinic_email"],
            "prescription_date": datetime.now().strftime("%d/%m/%Y"),
            "medicines": medicines_list,
        }
        canonical_request = {
            key: data[key]
            for key in (
                "name", "age", "gender", "phone_number", "doctor", "clinic",
                "tagline", "address", "clinic_phone", "clinic_email", "medicines",
            )
        }
        request_hash = hashlib.sha256(
            json.dumps(canonical_request, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

        request_id = request.headers.get("Idempotency-Key") or payload.get("request_id")
        if request_id is None:
            request_id = uuid.uuid4().hex
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", request_id):
            return jsonify({"error": "Idempotency-Key must contain 1-128 letters, digits, dots, underscores, colons, or hyphens."}), 400

        existing = get_prescription_by_request_id(request_id)
        if existing:
            if existing["request_hash"] != request_hash:
                return jsonify({"error": "This request key was already used for different prescription details."}), 409
            return jsonify(_prescription_response(existing, request.host_url)), 200

        public_base_url = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
        if public_base_url and not re.fullmatch(r"https?://[^/\s]+(?:/[^ \s]*)?", public_base_url):
            return jsonify({"error": "PUBLIC_BASE_URL must be an absolute http(s) URL."}), 503
        download_base_url = public_base_url or request.host_url.rstrip("/")
        download_token = uuid.uuid4().hex
        secure_download_url = (
            f"{download_base_url}/patient/prescriptions/download/{download_token}"
        )
        filename = create_prescription_filename(patient_name)
        filepath = os.path.join(GENERATED_FOLDER, filename)
        os.makedirs(GENERATED_FOLDER, exist_ok=True)
        generate_prescription_pdf(data, secure_download_url, filepath)

        if not os.path.isfile(filepath) or os.path.getsize(filepath) < 100:
            raise RuntimeError("The PDF could not be generated as a valid non-empty document.")
        with open(filepath, "rb") as pdf_file:
            if pdf_file.read(5) != b"%PDF-":
                raise RuntimeError("The generated file is not a valid PDF.")

        try:
            prescription_id, _ = save_prescription({
                "patient_name": patient_name,
                "phone_number": phone_number,
                "age": data["age"],
                "gender": gender,
                "filename": filename,
                "download_token": download_token,
                "doctor_name": config["doctor"],
                "clinic_name": config["clinic"],
                "prescription_data": data,
                "request_id": request_id,
                "request_hash": request_hash,
            })
        except sqlite3.IntegrityError:
            existing = get_prescription_by_request_id(request_id)
            if existing:
                os.remove(filepath)
                filepath = None
                if existing["request_hash"] == request_hash:
                    return jsonify(_prescription_response(existing, request.host_url)), 200
                return jsonify({
                    "error": "This request key was already used for different prescription details."
                }), 409
            raise

        drive_url = None
        if os.getenv("GOOGLE_DRIVE_UPLOAD_ENABLED", "").strip().casefold() == "true":
            try:
                drive_url = upload_pdf_to_drive(filepath)
            except Exception:
                logger.exception("Google Drive upload failed; local prescription remains available.")

        sms_url = drive_url or (secure_download_url if public_base_url else None)
        if is_sms_configured() and phone_number and sms_url:
            try:
                send_sms(patient_name, phone_number, sms_url)
            except Exception:
                logger.exception("SMS delivery failed; local prescription remains available.")

        return jsonify({
            "success": True,
            "download_url": secure_download_url,
            "local_download_url": secure_download_url,
            "drive_url": drive_url,
            "filename": filename,
            "patient": patient_name,
            "phone_number": phone_number,
            "age": data["age"],
            "gender": gender,
            "medicines": medicines_list,
            "prescription_id": prescription_id,
        }), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as e:
        logger.exception("Prescription generation failed")
        if filepath and os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                logger.exception("Could not remove incomplete prescription PDF.")
        return jsonify({"error": "Prescription generation failed. Please check the server logs."}), 500


def _prescription_response(record, request_host):
    download_base_url = (
        os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
        or request_host.rstrip("/")
    )
    download_url = (
        download_base_url
        + "/patient/prescriptions/download/"
        + record["download_token"]
    )
    try:
        stored_data = json.loads(record.get("prescription_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        stored_data = {}
    return {
        "success": True,
        "duplicate": True,
        "download_url": download_url,
        "local_download_url": download_url,
        "drive_url": None,
        "filename": record["filename"],
        "patient": record["patient_name"],
        "phone_number": record["phone_number"],
        "age": record["age"],
        "gender": record["gender"],
        "medicines": stored_data.get("medicines", []),
        "prescription_id": record["id"],
    }


@app.route('/generated/<path:filename>')
def serve_generated_file(filename):
    return send_from_directory(GENERATED_FOLDER, filename, as_attachment=True)

@app.route("/download/<filename>")
def download_file(filename):
    return send_from_directory(
        GENERATED_FOLDER,
        filename,
        as_attachment=True
    )


# ==================== PATIENT PRESCRIPTION HISTORY ====================

@app.route("/patient/prescriptions", methods=["GET"])
def patient_prescriptions():
    """
    Return prescription history for a phone number.

    Security note: This endpoint is NOT authenticated – it requires only a
    phone number which is not a secret.  Do NOT use in production without
    adding OTP / session authentication.  The endpoint is intentionally
    limited to metadata; actual PDF bytes are only served via the opaque
    per-prescription token.
    """
    phone_number = (
        request.args.get("phone_number")
        or request.args.get("phone")
        or ""
    ).strip()
    if not phone_number:
        return jsonify({"error": "phone_number query parameter is required."}), 400

    try:
        records = get_patient_prescriptions(phone_number)
        # Strip filename from the public response – clients should use the token.
        safe_records = [
            {
                "id":             r["id"],
                "patient_name":   r["patient_name"],
                "age":            r["age"],
                "gender":         r["gender"],
                "created_at":     r["created_at"],
                "download_token": r["download_token"],
            }
            for r in records
        ]
        return jsonify({"count": len(safe_records), "prescriptions": safe_records}), 200
    except Exception as e:
        logger.exception("Failed to retrieve patient prescriptions")
        return jsonify({"error": str(e)}), 500


@app.route("/patient/prescriptions/download/<token>", methods=["GET"])
def patient_prescription_download(token):
    """
    Download a prescription PDF by its opaque token.

    The token is a 32-character hex string generated at prescription-creation
    time.  Guessing it is computationally infeasible.
    """
    # Validate token format to prevent unexpected DB lookups.
    if not re.fullmatch(r"[0-9a-f]{32}", token):
        abort(404)

    try:
        record = get_prescription_by_token(token)
    except Exception as e:
        logger.exception("DB error during token lookup")
        return jsonify({"error": "Internal server error."}), 500

    if record is None:
        abort(404)

    filename = record["filename"]
    # Prevent directory traversal: strip any path components.
    from werkzeug.utils import secure_filename as _sfn
    safe_name = _sfn(filename)
    if not safe_name or safe_name != filename:
        logger.warning("Suspicious filename rejected: %s", filename)
        abort(404)

    pdf_path = os.path.join(GENERATED_FOLDER, safe_name)
    if not os.path.isfile(pdf_path):
        return jsonify({"error": "PDF file not found on server."}), 404

    return send_from_directory(
        GENERATED_FOLDER,
        safe_name,
        as_attachment=True,
        download_name=safe_name,
        mimetype="application/pdf",
    )


def get_medicine_info_gemini(medicine_ocr, expiry_ocr="", language='English'):
    """Get medicine information from Gemini using OCR text"""
    if not medicine_ocr or client is None:
        return None

    if language.lower() == 'kannada':
        language_instruction = """
Respond in Kannada.
Use simple Kannada that an ordinary patient can understand.
Keep medicine names, brand names, generic names and scientific
terms in English where translation could cause confusion.
"""
    else:
        language_instruction = """
Respond in clear, simple English.
"""

    prompt = f"""
You are a medicine information assistant.

You are given OCR text extracted from a medicine package.

MEDICINE OCR:
{medicine_ocr}

EXPIRY OCR:
{expiry_ocr}

{language_instruction}

Your job is to understand the medicine package from the OCR text.

IMPORTANT:
The OCR may contain spelling mistakes, noise, duplicated words,
packaging instructions, company information and other irrelevant text.

Use the meaningful medicine-related information from the OCR.

Identify:

1. Generic/active ingredient
2. Brand name
3. Strength
4. Dosage form
5. Expiry date
6. Main established/common uses
7. Common side effects
8. Suitable alternatives

For the expiry date:
- Look specifically for words such as EXP, EXPIRY, EXP DATE,
  EXPIRY DATE, etc.
- Understand common OCR mistakes.
- Extract the expiry month and year.
- Do NOT confuse MFG/MFD/manufacturing date with expiry date.
- If both MFG and EXP dates appear, return only the EXP date.
- If the expiry date cannot be determined reliably, return
  "Information not available".

For medicine identification:
- Distinguish the BRAND NAME from the GENERIC/ACTIVE INGREDIENT.
- For example, if OCR contains a brand name and an ingredient,
  do not treat the brand as the generic name.
- Do not assume that the first readable OCR word is the medicine name.
- Ignore words such as Tablets, Capsules, IP, Batch, MFG,
  Storage, Warning, etc. when identifying the brand/generic name.

IMPORTANT:
Do not invent information.
If something cannot be determined reliably, write:
"Information not available".

Return ONLY valid JSON in exactly this format:

{{
    "generic_name": "",
    "brand_name": "",
    "strength": "",
    "dosage_form": "",
    "expiry_date": "",
    "uses": [],
    "side_effects": [],
    "alternatives": []
}}

Keep each list concise (max 5 items per list).
"""

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )

        text = response.text.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        data = json.loads(text)

        if not isinstance(data, dict):
            logger.warning("Gemini returned non-dict JSON")
            return None

        result = {
            'generic_name': 'Information not available',
            'brand_name': 'Information not available',
            'strength': 'Information not available',
            'dosage_form': 'Information not available',
            'expiry_date': 'Information not available',
            'uses': [],
            'side_effects': [],
            'alternatives': [],
            'source': 'Gemini'
        }

        result['generic_name'] = data.get('generic_name', 'Information not available') or 'Information not available'
        result['brand_name'] = data.get('brand_name', 'Information not available') or 'Information not available'
        result['strength'] = data.get('strength', 'Information not available') or 'Information not available'
        result['dosage_form'] = data.get('dosage_form', 'Information not available') or 'Information not available'
        result['expiry_date'] = data.get('expiry_date', 'Information not available') or 'Information not available'

        for key in ['uses', 'side_effects', 'alternatives']:
            value = data.get(key, [])
            if isinstance(value, list):
                cleaned = [item for item in value if isinstance(item, str) and item.strip()]
                result[key] = cleaned[:5]
            else:
                result[key] = []

        return result

    except json.JSONDecodeError as e:
        logger.warning("Gemini returned invalid JSON: %s", e)
        return None
    except Exception as e:
        logger.exception("Gemini error")
        return None
# ===============================
# IMAGE PROCESSING FUNCTIONS
# ===============================

def preprocess_for_ocr(image):
    try:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        gray = clahe.apply(gray)
        gray = cv2.GaussianBlur(gray, (3,3), 0)
        return gray
    except Exception as e:
        logger.error(f"OCR preprocessing error: {e}")
        return image


def extract_text_with_ocr(image):
    """Extract text using Tesseract and EasyOCR with multiple PSM modes."""
    if image is None:
        return ""

    texts = []
    processed = preprocess_for_ocr(image)

    for psm in [6, 7, 11, 12, 13]:
        try:
            text = pytesseract.image_to_string(processed, config=f"--oem 3 --psm {psm}")
            if text and text.strip():
                texts.append((text.strip(), "tesseract"))
        except Exception as e:
            logger.debug(f"Tesseract PSM {psm} error: {e}")

    if reader:
        try:
            easyocr_result = reader.readtext(image, detail=0, paragraph=True)
            if easyocr_result:
                easyocr_text = " ".join(easyocr_result).strip()
                if len(easyocr_text) > 3:
                    texts.append((easyocr_text, "easyocr"))
        except Exception as e:
            logger.debug(f"EasyOCR error: {e}")

    if texts:
        easyocr_texts = [t[0] for t in texts if t[1] == "easyocr"]
        if easyocr_texts:
            return min(easyocr_texts, key=len)

        tesseract_texts = [t[0] for t in texts if t[1] == "tesseract"]
        if tesseract_texts:
            return min(tesseract_texts, key=len)

    return ""

def extract_medicine_name(text):
    """Extract medicine name or brand candidate from OCR text."""
    if not text:
        return None

    if re.search(r"\bPARACIP\b", text, re.IGNORECASE):
        return "Paracip-500"

    # First, prefer brand/product-style candidates with numbers, strengths, or uppercase brand text.
    candidate = None

    # Look across each line for compact brand-like patterns first.
    for line in text.splitlines():
        if not line or len(line.strip()) < 3:
            continue

        cleaned_line = line.strip()
        if re.search(r'\b(EXP|EXPIRY|MFG|BATCH|PACK|LOT|MANU|USE BY|BEST BEFORE|TABLET|TAB|CAPSULE|SUSTAINED|RELEASE|IP|MG|ML)\b', cleaned_line, re.I):
            # Still allow the respected brand line if it includes strength and a product-like name earlier
            pass

        # Prefer lines with a brand name plus dosage or strength
        match = re.search(r'([A-Za-z][A-Za-z0-9\-]{2,}(?:\s+[A-Za-z0-9\-]{1,})*\s+\d{1,4}(?:\s*(?:mg|ml|g|mcg|mg\/ml|mg\/tab|tablet|tab|capsule|xt|sr|mr|xr))?)', cleaned_line, re.I)
        if match:
            candidate = match.group(1).strip()
            candidate = re.sub(r'\s{2,}', ' ', candidate)
            if len(candidate) > 3 and not re.search(r'\b(EXP|EXPIRY|BATCH|MFG|USE BY|BEST BEFORE)\b', candidate, re.I):
                logger.info(f"✓ Found medicine (brand candidate with strength): {candidate}")
                return candidate

        # Prefer shorter brand-like text with uppercase or mixed-case and digits/hyphens
        match = re.search(r'([A-Za-z][A-Za-z0-9\-]{2,}(?:\s+[A-Za-z0-9\-]{2,})*\s+\d{1,4})', cleaned_line)
        if match:
            candidate = match.group(1).strip()
            if len(candidate) > 3 and not re.search(r'\b(EXP|EXPIRY|BATCH|MFG|USE BY|BEST BEFORE|TABLET|TAB|CAPSULE)\b', candidate, re.I):
                logger.info(f"✓ Found medicine (brand candidate): {candidate}")
                return candidate

    # Fallback: prefer uppercase or product-like short phrases without numeric strength, but still brand-like
    uppercase_candidates = re.findall(r'([A-Z][A-Z0-9\-]{2,}(?:\s+[A-Z][A-Z0-9\-]{2,})*)', text)
    for match in uppercase_candidates:
        cleaned = match.strip()
        if len(cleaned) > 3 and not re.search(r'\b(EXP|EXPIRY|MFG|BATCH|TABLET|TAB|CAPSULE|MG|ML|USE BY|BEST BEFORE|SUSTAINED|RELEASE|IP)\b', cleaned, re.I):
            logger.info(f"✓ Found medicine (uppercase candidate): {cleaned}")
            return cleaned

    text_lower = text.lower()
    # Clean the text for direct matching against known items
    cleaned_text = re.sub(r'[^a-z\s]', ' ', text_lower)
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text)

    # Direct match against known medicines
    for medicine in COMMON_MEDICINES:
        if medicine in cleaned_text:
            logger.info(f"✓ Found medicine (direct): {medicine}")
            return medicine

    # Fuzzy matching against known medicines
    words = cleaned_text.split()
    for i in range(len(words)):
        if i < len(words) - 1:
            two_words = f"{words[i]} {words[i+1]}"
            matches = get_close_matches(two_words, COMMON_MEDICINES, n=1, cutoff=0.8)
            if matches:
                logger.info(f"✓ Found medicine (2-word): {matches[0]}")
                return matches[0]

        if len(words[i]) > 3:
            matches = get_close_matches(words[i], COMMON_MEDICINES, n=1, cutoff=0.8)
            if matches:
                logger.info(f"✓ Found medicine (single): {matches[0]}")
                return matches[0]

    return None


def extract_labeled_expiry_date(text):
    """Prefer a date explicitly labeled as expiry over manufacturing dates."""
    if not text:
        return "NOT FOUND"

    month_numbers = {
        "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04",
        "MAY": "05", "JUN": "06", "JUL": "07", "AUG": "08",
        "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
    }
    months = "|".join(month_numbers)
    match = re.search(
        rf"(?:\bEXP(?:IRY)?\b|2XP)\s*[A-Z]{{0,2}}[^A-Z0-9]{{0,2}}"
        rf"({months})\s*[^A-Z0-9]{{0,2}}(20\d{{2}}|\d{{2}})\b",
        text.upper(),
    )
    if not match:
        return "NOT FOUND"

    year = match.group(2)
    if len(year) == 2:
        year = f"20{year}"
    return f"{month_numbers[match.group(1)]}/{year}"


def build_local_medicine_info(ocr_text, medicine_name, expiry_date):
    """Return only medicine details supported by local OCR or a known label."""
    brand_name = medicine_name or "Not detected"
    generic_name = "Information not available"
    strength = "Information not available"
    dosage_form = "Information not available"

    if re.search(r"\bPARACIP\b", ocr_text, re.IGNORECASE):
        brand_name = "Paracip-500"
        generic_name = "Paracetamol"
        strength = "500 mg"
        dosage_form = "Tablet"
    else:
        strength_match = re.search(
            r"\b(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml)\b",
            ocr_text,
            re.IGNORECASE,
        )
        if strength_match:
            strength = f"{strength_match.group(1)} {strength_match.group(2).lower()}"
        if re.search(r"\b(TABLET|TABLETS|TAB)\b", ocr_text, re.IGNORECASE):
            dosage_form = "Tablet"
        elif re.search(r"\b(CAPSULE|CAPSULES|CAP)\b", ocr_text, re.IGNORECASE):
            dosage_form = "Capsule"

    labeled_expiry = extract_labeled_expiry_date(ocr_text)
    return {
        "brand_name": brand_name,
        "generic_name": generic_name,
        "strength": strength,
        "dosage_form": dosage_form,
        "expiry_date": labeled_expiry if labeled_expiry != "NOT FOUND" else expiry_date,
        "uses": ["Information not available"],
        "side_effects": ["Information not available"],
        "alternatives": ["Information not available"],
        "source": "Local OCR",
    }





def extract_name(image):
    try:
        rotated_text, _ = extract_with_rotations(image)   # unpack the tuple
        med = extract_medicine_name(rotated_text)
        if med:
            return med
    except Exception as e:
        logger.debug(f"extract_with_rotations failed: {e}")

    try:
        text = extract_text_with_ocr(image)
        return extract_medicine_name(text)
    except Exception as e:
        logger.debug(f"Fallback OCR failed: {e}")
        return None

def resize_for_yolo(image_path, max_dim=1024):
    """Resize image if oversized; return path to (possibly new) file, or None on failure."""
    img = cv2.imread(image_path)
    if img is None:
        return None
    h, w = img.shape[:2]
    if max(h, w) <= max_dim:
        return image_path
    scale = max_dim / max(h, w)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(img, (new_w, new_h))
    name, ext = os.path.splitext(image_path)
    temp_path = f"{name}_resized{ext}"
    cv2.imwrite(temp_path, resized)
    return temp_path


def yolo_crop(image_path):
    """Run YOLO and return ALL detected regions as a list of {"label", "image"} dicts,
    instead of collapsing to just one medicine crop + one expiry crop."""
    if not model:
        logger.warning("YOLO model not available, skipping YOLO detection")
        return []

    img = cv2.imread(image_path)
    if img is None:
        return []

    try:
        result = model.predict(image_path, confidence=0.3).json()
    except Exception as e:
        logger.error(f"YOLO prediction error: {e}")
        return []

    predictions = result.get('predictions', [])
    logger.info(f"YOLO found {len(predictions)} predictions")

    crops = []
    for pred in predictions:
        class_name = pred.get('class', '').lower()
        x, y, width, height = pred['x'], pred['y'], pred['width'], pred['height']
        x1 = max(0, int(x - width / 2))
        y1 = max(0, int(y - height / 2))
        x2 = min(img.shape[1], int(x + width / 2))
        y2 = min(img.shape[0], int(y + height / 2))
        crop_img = img[y1:y2, x1:x2]
        if crop_img.size == 0:
            continue
        crops.append({"label": class_name, "image": crop_img})

    return crops


def extract_generic_medicines(text):
    """Return ALL medicine names matched in OCR text, not just the first."""
    if not text:
        return []

    text_lower = re.sub(r'[^a-z\s]', ' ', text.lower())
    text_lower = re.sub(r'\s+', ' ', text_lower)

    found = []

    for medicine in COMMON_MEDICINES:
        if medicine in text_lower and medicine not in found:
            found.append(medicine)

    if not found:
        words = text_lower.split()
        for i in range(len(words)):
            if i < len(words) - 1:
                two_words = f"{words[i]} {words[i+1]}"
                matches = get_close_matches(two_words, COMMON_MEDICINES, n=1, cutoff=0.8)
                if matches and matches[0] not in found:
                    found.append(matches[0])
            if len(words[i]) > 3:
                matches = get_close_matches(words[i], COMMON_MEDICINES, n=1, cutoff=0.8)
                if matches and matches[0] not in found:
                    found.append(matches[0])

    return found


# ============================================================
# IMPROVED EXPIRY DATE OCR
# ============================================================

def preprocess_expiry_for_ocr(image):
    """
    Strong preprocessing specifically for expiry-date text.
    Upscales small YOLO crops and creates multiple OCR-friendly
    versions.
    """
    if image is None:
        return []

    try:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Upscale small expiry crops
        h, w = gray.shape[:2]

        scale = 4
        enlarged = cv2.resize(
            gray,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC
        )

        # Improve contrast
        clahe = cv2.createCLAHE(
            clipLimit=3.0,
            tileGridSize=(8, 8)
        )

        enhanced = clahe.apply(enlarged)

        # Light denoising
        blurred = cv2.GaussianBlur(
            enhanced,
            (3, 3),
            0
        )

        # Binary threshold
        _, binary = cv2.threshold(
            blurred,
            0,
            255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        # Adaptive threshold
        adaptive = cv2.adaptiveThreshold(
            enhanced,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            11
        )

        return [
            enlarged,
            enhanced,
            binary,
            adaptive
        ]

    except Exception as e:
        logger.error(
            f"Expiry preprocessing error: {e}"
        )
        return [image]


# ============================================================
# EXPIRY DATE PATTERN EXTRACTION
# ============================================================

def clean_expiry(text):

    if not text:
        return "NOT FOUND"

    # Uppercase
    text = text.upper()

    # Normalize common OCR mistakes
    replacements = {
        "EXPIRY": "EXP",
        "EXP.": "EXP",
        "EXP:": "EXP",
        "EXF": "EXP",
        "E XP": "EXP",
        "E.X.P": "EXP",

        # Common OCR confusion
        "O": "0",
        "I": "1",
        "L": "1"
    }

    for wrong, correct in replacements.items():
        text = text.replace(wrong, correct)

    # Normalize spaces
    text = re.sub(
        r'\s+',
        ' ',
        text
    ).strip()

    # --------------------------------------------------------
    # Pattern 1
    # EXP 07/2027
    # EXP 07-2027
    # EXP 07.2027
    # EXP 07 2027
    # --------------------------------------------------------

    match = re.search(
        r'\bEXP\b\s*'
        r'([0-1]?\d)'
        r'\s*[/\-.\s]\s*'
        r'(20\d{2}|\d{2})\b',
        text
    )

    if match:

        month = int(match.group(1))
        year = match.group(2)

        if 1 <= month <= 12:

            if len(year) == 2:
                year = "20" + year

            return f"{month:02d}/{year}"

    # --------------------------------------------------------
    # Pattern 2
    # EXP JAN 2027
    # EXP JAN-2027
    # EXP JAN/27
    # --------------------------------------------------------

    months = {
        "JAN": "01",
        "FEB": "02",
        "MAR": "03",
        "APR": "04",
        "MAY": "05",
        "JUN": "06",
        "JUL": "07",
        "AUG": "08",
        "SEP": "09",
        "OCT": "10",
        "NOV": "11",
        "DEC": "12"
    }

    month_pattern = (
        "JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|"
        "SEP|OCT|NOV|DEC"
    )

    match = re.search(
        rf'\bEXP\b\s*'
        rf'({month_pattern})'
        r'\s*[/\-.\s]*'
        r'(20\d{2}|\d{2})\b',
        text
    )

    if match:

        month = match.group(1)
        year = match.group(2)

        if len(year) == 2:
            year = "20" + year

        return f"{months[month]}/{year}"

    # --------------------------------------------------------
    # Pattern 3
    # Just MM/YYYY
    # --------------------------------------------------------

    match = re.search(
        r'\b(0?[1-9]|1[0-2])'
        r'\s*[/\-.\s]\s*'
        r'(20\d{2}|\d{2})\b',
        text
    )

    if match:

        month = int(match.group(1))
        year = match.group(2)

        if len(year) == 2:
            year = "20" + year

        return f"{month:02d}/{year}"

    # --------------------------------------------------------
    # Pattern 4
    # JAN 2027
    # --------------------------------------------------------

    match = re.search(
        rf'\b({month_pattern})'
        r'\s*[/\-.\s]*'
        r'(20\d{2}|\d{2})\b',
        text
    )

    if match:

        month = match.group(1)
        year = match.group(2)

        if len(year) == 2:
            year = "20" + year

        return f"{months[month]}/{year}"

        # --------------------------------------------------------
    # Final fallback: find any valid MM/YY or MM/YYYY
    # --------------------------------------------------------

    numbers = re.findall(
        r'\b(0?[1-9]|1[0-2])\s*[/\-\.]\s*(20\d{2}|\d{2})\b',
        text
    )

    if numbers:
        month, year = numbers[-1]

        if len(year) == 2:
            year = "20" + year

        return f"{int(month):02d}/{year}"

    return "NOT FOUND"


# ============================================================
# EXPIRY OCR WITH ROTATIONS
# ============================================================

def extract_with_rotations(image):
    """
    Dedicated expiry-date OCR.

    Uses:
    - 4 rotations
    - image upscaling
    - contrast enhancement
    - thresholding
    - Tesseract digit/date-focused OCR
    - EasyOCR fallback
    """

    if image is None:
        return "", "NOT FOUND"

    angles = [0, 90, 180, 270]

    best_text = ""
    best_expiry = "NOT FOUND"

    for angle in angles:

        try:

            # ------------------------------------------------
            # Rotate
            # ------------------------------------------------

            if angle == 0:
                rotated = image

            elif angle == 90:
                rotated = cv2.rotate(
                    image,
                    cv2.ROTATE_90_CLOCKWISE
                )

            elif angle == 180:
                rotated = cv2.rotate(
                    image,
                    cv2.ROTATE_180
                )

            else:
                rotated = cv2.rotate(
                    image,
                    cv2.ROTATE_90_COUNTERCLOCKWISE
                )

            # ------------------------------------------------
            # Create OCR versions
            # ------------------------------------------------

            versions = preprocess_expiry_for_ocr(
                rotated
            )

            for processed in versions:

                # --------------------------------------------
                # Tesseract
                # --------------------------------------------

                configs = [
                        "--oem 3 --psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/.-:",
                        "--oem 3 --psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/.-:",
                        "--oem 3 --psm 11 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/.-:"
                    ]

                for config in configs:

                    try:

                        text = pytesseract.image_to_string(
                            processed,
                            config=config
                        )

                        if not text:
                            continue

                        text = text.strip()

                        if len(text) > len(best_text):
                            best_text = text

                        # ------------------------------------
                        # Immediately check expiry
                        # ------------------------------------

                        expiry = clean_expiry(text)

                        if expiry != "NOT FOUND":

                            logger.info(
                                f"✓ EXPIRY FOUND "
                                f"at rotation {angle}: "
                                f"{expiry}"
                            )

                            return text, expiry

                    except Exception as e:

                        logger.debug(
                            f"Tesseract expiry OCR error: {e}"
                        )

                # --------------------------------------------
                # EasyOCR
                # --------------------------------------------

                if reader:

                    try:

                        easy_result = reader.readtext(
                            processed,
                            detail=0,
                            paragraph=False
                        )

                        if easy_result:

                            text = " ".join(
                                easy_result
                            ).strip()

                            if len(text) > len(best_text):
                                best_text = text

                            expiry = clean_expiry(text)

                            if expiry != "NOT FOUND":

                                logger.info(
                                    f"✓ EXPIRY FOUND "
                                    f"using EasyOCR "
                                    f"at rotation {angle}: "
                                    f"{expiry}"
                                )

                                return text, expiry

                    except Exception as e:

                        logger.debug(
                            f"EasyOCR expiry error: {e}"
                        )

        except Exception as e:

            logger.error(
                f"Rotation {angle} failed: {e}"
            )

    # --------------------------------------------------------
    # Nothing found
    # --------------------------------------------------------

    logger.warning(
        f"⚠️ Expiry not detected. OCR text: "
        f"{repr(best_text)}"
    )

    return best_text, best_expiry


def extract_expiry_date(text):
    """Extract expiry date from text"""
    if not text:
        return "NOT FOUND"
    
    text = text.upper()
    
    # Common expiry patterns
    patterns = [
        # EXP: MM/YYYY or MM/YY
        r'(?:EXP|EXPIRY|EXP DATE|USE BY|BEST BEFORE)[:\s]*(\d{1,2})[/\-\.](\d{2,4})',
        # Just MM/YYYY or MM/YY
        r'(\d{1,2})[/\-\.](\d{2,4})',
        # Month name format
        r'(?:EXP|EXPIRY)[:\s]*([A-Z]{3,9})[\s\.\-]*(\d{2,4})',
        # Year first format
        r'(\d{4})[/\-\.](\d{1,2})',
    ]
    
    month_map = {
        'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04',
        'MAY': '05', 'JUN': '06', 'JUL': '07', 'AUG': '08',
        'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12'
    }
    
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            if isinstance(match, tuple) and len(match) == 2:
                first, second = match
                
                # Check if first is month name
                if first in month_map:
                    month = month_map[first]
                    year = second[-2:] if len(second) > 2 else second
                    return f"{month}/{year}"
                
                # Check if numeric
                try:
                    if first.isdigit() and second.isdigit():
                        if int(first) <= 12 and len(second) in [2, 4]:
                            month = first.zfill(2)
                            year = second[-2:]
                            return f"{month}/{year}"
                        elif int(second) <= 12 and len(first) in [2, 4]:
                            month = second.zfill(2)
                            year = first[-2:]
                            return f"{month}/{year}"
                except ValueError:
                    continue
    
    return "NOT FOUND"

# ===============================
# NEW COLAB OCR PIPELINE
# ===============================

def upscale_for_ocr(image, scale=2):
    """Upscale image for better OCR accuracy"""
    h, w = image.shape[:2]
    return cv2.resize(
        image,
        (w * scale, h * scale),
        interpolation=cv2.INTER_CUBIC
    )

def extract_medicine_with_easyocr_rotations(image):
    """Extract medicine text using EasyOCR with rotation analysis"""
    # Upscale image for better accuracy
    image = upscale_for_ocr(image, scale=3)
    
    rotations = [
        ("0", image),
        ("90", cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)),
        ("180", cv2.rotate(image, cv2.ROTATE_180)),
        ("270", cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE))
    ]
    
    candidates = []
    
    for angle, rotated in rotations:
        if reader is None:
            continue
            
        try:
            results = reader.readtext(
                rotated,
                detail=1,
                paragraph=False
            )
            
            for box, text, confidence in results:
                text = text.strip()
                if not text:
                    continue
                
                letters = sum(c.isalpha() for c in text)
                if letters < 2:
                    continue
                
                candidates.append({
                    "text": text,
                    "confidence": float(confidence),
                    "rotation": angle,
                    "box": box
                })
        except Exception as e:
            logger.debug(f"EasyOCR rotation {angle} error: {e}")
    
    return candidates

def filter_medicine_candidates(candidates):
    """Filter OCR candidates to keep useful ones"""
    useful = []
    
    for c in candidates:
        text = c["text"].strip()
        confidence = c["confidence"]
        letters = sum(ch.isalpha() for ch in text)
        
        if len(text) < 2:
            continue
        if letters < 2:
            continue
        
        if confidence >= 0.20:
            useful.append(c)
        elif len(text) >= 6 and letters >= 4:
            useful.append(c)
    
    return useful

def choose_best_rotation(candidates):
    """Choose the best rotation based on confidence and text quality"""
    rotations = {}
    
    for c in candidates:
        rotation = c["rotation"]
        text = c["text"].strip()
        
        if not text:
            continue
        
        letters = sum(ch.isalpha() for ch in text)
        if letters < 2:
            continue
        
        if rotation not in rotations:
            rotations[rotation] = []
        rotations[rotation].append(c)
    
    scores = {}
    for rotation, items in rotations.items():
        score = 0
        for c in items:
            text = c["text"]
            confidence = c["confidence"]
            letters = sum(ch.isalpha() for ch in text)
            
            score += confidence * letters
            if len(text) >= 5:
                score += 3
            if len(text.split()) >= 2:
                score += 2
        
        scores[rotation] = score
    
    if not scores:
        return "0"
    
    best_rotation = max(scores, key=scores.get)
    return best_rotation

def clean_medicine_ocr(results):
    """Clean and filter OCR results for medicine"""
    words = []
    
    for item in results:
        if isinstance(item, (list, tuple)) and len(item) >= 3:
            box, text, confidence = item[0], item[1], item[2]
        else:
            text = item.get("text", "") if isinstance(item, dict) else str(item)
            confidence = item.get("confidence", 0) if isinstance(item, dict) else 0
        
        text = text.strip()
        if not text:
            continue
        
        if len(text) < 2:
            continue
        
        letters = sum(c.isalpha() for c in text)
        if letters < 2:
            continue
        
        words.append({
            "text": text,
            "confidence": float(confidence)
        })
    
    return words

def build_medicine_label(filtered):
    """Build final medicine label from filtered OCR results"""
    if not filtered:
        return "NOT DETECTED"
    
    stop_phrases = [
        "medicine:", "medicine", "keep out", "keep out of reach",
        "reach of children", "warning", "warnings", "dosage", "dose",
        "storage", "store in", "store below", "manufactured by",
        "manufactured", "marketed by", "batch", "batch no", "mfg",
        "expiry", "exp", "composition", "each tablet contains",
        "each capsule contains", "prescription", "physician", "doctor",
        "for external use", "side effects"
    ]
    
    valid = []
    for item in filtered:
        text = item["text"].strip()
        if not text:
            continue
        
        lower = text.lower()
        if any(phrase in lower for phrase in stop_phrases):
            continue
        
        letters = sum(ch.isalpha() for ch in text)
        if letters < 2:
            continue
        
        valid.append(item)
    
    if not valid:
        return "NOT DETECTED"
    
    final_words = []
    for item in valid:
        text = item["text"].strip()
        if text not in final_words:
            final_words.append(text)
    
    return " ".join(final_words)

def clean_expiry_v2(text):
    """Improved expiry date extraction with comprehensive pattern matching"""
    if not text:
        return "NOT FOUND"
    
    text = text.upper()
    
    # Normalize EXP variations
    text = text.replace("EXP.", "EXP ")
    text = text.replace("EXP:", "EXP ")
    text = text.replace("EXP,", "EXP ")
    
    month_numbers = {
        "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04",
        "MAY": "05", "JUN": "06", "JUL": "07", "AUG": "08",
        "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12"
    }
    
    # Pattern 1: EXP + MONTH NAME + YEAR
    match = re.search(
        r'\b(?:EXP|EXPIRY)\s*'
        r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)'
        r'[\s\.\:/\-]*'
        r'(20\d{2}|\d{2})',
        text
    )
    if match:
        month = match.group(1)
        year = match.group(2)
        if len(year) == 2:
            year = "20" + year
        return f"{month_numbers[month]}/{year}"
    
    # Pattern 2: EXP + MM/YYYY
    match = re.search(
        r'\b(?:EXP|EXPIRY)\s*'
        r'(0[1-9]|1[0-2])'
        r'[\./\-]'
        r'(20\d{2}|\d{2})',
        text
    )
    if match:
        month = match.group(1)
        year = match.group(2)
        if len(year) == 2:
            year = "20" + year
        return f"{month}/{year}"
    
    # Pattern 3: EXP + MM + OCR NOISE + YYYY
    match = re.search(
        r'\b(?:EXP|EXPIRY)\s*'
        r'(0[1-9]|1[0-2])'
        r'[^0-9\s]?'
        r'(?:[ILTOZ])?'
        r'(20\d{2})',
        text
    )
    if match:
        month = match.group(1)
        year = match.group(2)
        return f"{month}/{year}"
    
    # Pattern 4: EXP + MM + YYYY with any single OCR character
    match = re.search(
        r'\b(?:EXP|EXPIRY)\s*'
        r'(0[1-9]|1[0-2])'
        r'.?'
        r'(20\d{2})',
        text
    )
    if match:
        month = match.group(1)
        year = match.group(2)
        return f"{month}/{year}"
    
    # Pattern 5: MONTH NAME + YEAR WITHOUT EXP
    match = re.search(
        r'\b(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)'
        r'[\s\.\:/\-]*'
        r'(20\d{2}|\d{2})',
        text
    )
    if match:
        month = match.group(1)
        year = match.group(2)
        if len(year) == 2:
            year = "20" + year
        return f"{month_numbers[month]}/{year}"
    
    # Pattern 6: NORMAL NUMERIC DATE
    match = re.search(
        r'\b(0?[1-9]|1[0-2])'
        r'[\./\-]'
        r'(20\d{2}|\d{2})\b',
        text
    )
    if match:
        month = match.group(1).zfill(2)
        year = match.group(2)
        if len(year) == 2:
            year = "20" + year
        return f"{month}/{year}"
    
    # Pattern 7: MONTH + YEAR WITH OCR NOISE
    match = re.search(
        r'\b(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)'
        r'[\s\.\:/\-_]*'
        r'(20\d{2})\b',
        text
    )
    if match:
        month = match.group(1)
        year = match.group(2)
        return f"{month_numbers[month]}/{year}"
    
    return "NOT FOUND"

def extract_expiry_with_rotations(image):
    """Extract expiry date with rotation analysis"""
    if image is None:
        return "NOT FOUND", None, ""
    
    rotations = [
        ("0", image),
        ("90", cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)),
        ("180", cv2.rotate(image, cv2.ROTATE_180)),
        ("270", cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE))
    ]
    
    candidates = []
    
    for angle, rotated_image in rotations:
        if reader is None:
            continue
            
        try:
            results = reader.readtext(
                rotated_image,
                detail=1,
                paragraph=False
            )
            
            texts = []
            for box, text, confidence in results:
                text = text.strip()
                if not text:
                    continue
                texts.append(text)
            
            combined_text = " ".join(texts)
            expiry = clean_expiry_v2(combined_text)
            
            if expiry != "NOT FOUND":
                confidences = [
                    confidence for box, text, confidence in results
                    if text.strip()
                ]
                avg_confidence = (
                    sum(confidences) / len(confidences)
                    if confidences else 0
                )
                
                candidates.append({
                    "rotation": angle,
                    "expiry": expiry,
                    "ocr": combined_text,
                    "confidence": avg_confidence
                })
        except Exception as e:
            logger.debug(f"Expiry rotation {angle} error: {e}")
    
    if candidates:
        best = max(candidates, key=lambda x: x["confidence"])
        logger.info(f"✓ Best expiry: {best['expiry']} at rotation {best['rotation']}")
        return best["expiry"], best["rotation"], best["ocr"]
    
    logger.info("❌ Expiry date not identified")
    return "NOT FOUND", None, ""

# ===============================
# YOLO PROCESSING
# ===============================

def process_with_yolo(image_path):
    """Process image with YOLO to detect medicine and expiry regions"""
    if not model:
        logger.warning("YOLO model not available, skipping YOLO detection")
        return None, None
    
    try:
        # Resize image if too large
        img = cv2.imread(image_path)
        if img is None:
            return None, None
        
        h, w = img.shape[:2]
        if max(h, w) > 1024:
            scale = 1024 / max(h, w)
            new_w, new_h = int(w * scale), int(h * scale)
            img = cv2.resize(img, (new_w, new_h))
            # Fix: split filename and extension properly
            name, ext = os.path.splitext(image_path)
            temp_path = f"{name}_resized{ext}"
            cv2.imwrite(temp_path, img)
            image_path = temp_path
        
        # Run YOLO prediction
        result = model.predict(image_path, confidence=0.15).json()
        predictions = result.get('predictions', [])
        
        logger.info(f"YOLO found {len(predictions)} predictions")
        
        medicine_region = None
        expiry_region = None
        
        for pred in predictions:
            class_name = pred.get('class', '').lower()
            confidence = pred.get('confidence', 0)
            
            # Get coordinates
            x, y, width, height = pred['x'], pred['y'], pred['width'], pred['height']
            # Add padding around YOLO bounding box
            pad_x = int(width * 0.30)
            pad_y = int(height * 0.50)

            x1 = max(0, int(x - width/2) - pad_x)
            y1 = max(0, int(y - height/2) - pad_y)

            x2 = min(img.shape[1], int(x + width/2) + pad_x)
            y2 = min(img.shape[0], int(y + height/2) + pad_y)

            crop = img[y1:y2, x1:x2]
            
            
            if any(keyword in class_name for keyword in ['name', 'medicine', 'drug', 'product']):
                medicine_region = crop
                logger.info(f"Found medicine region with confidence: {confidence}")
            elif any(keyword in class_name for keyword in ['exp', 'expiry', 'date', 'mfg']):
                expiry_region = crop
                logger.info(f"Found expiry region with confidence: {confidence}")
        
        return medicine_region, expiry_region
    
    except Exception as e:
        logger.error(f"YOLO processing error: {e}")
        return None, None

# ===============================
# FLASK ROUTES
# ===============================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process_image():
    try:
        # Run cleanup before processing
        cleanup_old_files()

        if 'images' not in request.files:
            return jsonify({'error': 'No image uploaded'}), 400

        language = request.form.get('language', 'en')
        files = request.files.getlist('images')
        results = []

        for file in files:
            if file.filename == '':
                continue

            filename = secure_filename(file.filename)
            name, ext = os.path.splitext(filename)
            unique_filename = f"{name}_{uuid.uuid4().hex[:8]}{ext}"
            filepath = os.path.join(UPLOAD_FOLDER, unique_filename)
            file.save(filepath)

            try:
                logger.info(f"Processing: {filename}")

                image = cv2.imread(filepath)
                if image is None:
                    raise ValueError('Could not read image')

                medicine_name = None
                medicine_ocr = ""
                expiry_date = "NOT FOUND"
                expiry_ocr = ""

                medicine_region, expiry_region = process_with_yolo(filepath)

                # =====================================================
                # MEDICINE OCR PIPELINE (from Colab)
                # =====================================================
                if medicine_region is not None:
                    logger.info("Medicine region detected, running OCR pipeline")
                    
                    # Extract candidates using EasyOCR with rotations
                    candidates = extract_medicine_with_easyocr_rotations(medicine_region)
                    
                    # Filter candidates
                    useful = filter_medicine_candidates(candidates)
                    
                    if useful:
                        # Choose best rotation
                        best_rotation = choose_best_rotation(useful)
                        
                        # Get candidates for best rotation
                        best_candidates = [
                            c for c in useful
                            if c["rotation"] == best_rotation
                        ]
                        
                        # Convert to tuples for clean_medicine_ocr
                        ocr_results = [
                                (c["box"], c["text"], c["confidence"])
                                for c in best_candidates
                            ]
                        
                        # Clean OCR
                        filtered = clean_medicine_ocr(ocr_results)
                        
                        # Build medicine label
                        medicine_name = build_medicine_label(filtered)
                        
                        # Store medicine OCR text
                        medicine_ocr = " ".join(
                            item["text"] for item in filtered
                        )
                        
                        logger.info(f"Medicine: {medicine_name}")
                        logger.info(f"Medicine OCR: {medicine_ocr}")

                # =====================================================
                # EXPIRY OCR PIPELINE (from Colab)
                # =====================================================
                if expiry_region is not None:
                    logger.info("Expiry region detected, running OCR pipeline")
                    
                    # Save debug crop
                    debug_expiry_path = os.path.join(
                        UPLOAD_FOLDER,
                        "debug_expiry_crop.jpg"
                    )
                    cv2.imwrite(debug_expiry_path, expiry_region)
                    logger.info(f"✓ Expiry crop saved: {debug_expiry_path}")
                    
                    # Extract expiry with rotations
                    expiry_date, expiry_rotation, expiry_ocr = extract_expiry_with_rotations(
                        expiry_region
                    )                    
                    logger.info(f"📅 FINAL EXPIRY: {expiry_date}")

                # =====================================================
                # FALLBACK: OCR the full image for missing regions
                # =====================================================
                if not medicine_name:
                    logger.info("YOLO didn't find medicine, trying full image")
                    full_text = extract_text_with_ocr(image)
                    medicine_name = extract_medicine_name(full_text)
                    medicine_ocr = full_text

                if expiry_date == "NOT FOUND":
                    logger.info("Expiry region unavailable, scanning full image")
                    expiry_date, _, expiry_ocr = extract_expiry_with_rotations(image)

                # Always provide Gemini with OCR text, even if the detector crop
                # was too small or noisy to produce a medicine candidate.
                if not medicine_ocr:
                    logger.info("Medicine crop OCR unavailable, scanning full image")
                    medicine_ocr = extract_text_with_ocr(image)
                    if not medicine_name and medicine_ocr:
                        medicine_name = extract_medicine_name(medicine_ocr)

                labeled_expiry = extract_labeled_expiry_date(
                    f"{expiry_ocr} {medicine_ocr}"
                )
                if labeled_expiry != "NOT FOUND":
                    expiry_date = labeled_expiry

                # =====================================================
                # GEMINI: Send OCR text (not just medicine name)
                # =====================================================
                if medicine_ocr:
                    gemini_language = 'Kannada' if language == 'kn' else 'English'
                    medicine_info = get_medicine_info_gemini(
                        medicine_ocr,
                        expiry_ocr,
                        gemini_language
                    )

                    if not medicine_info:
                        medicine_info = build_local_medicine_info(
                            medicine_ocr,
                            medicine_name,
                            expiry_date,
                        )

                    gemini_expiry = medicine_info.get('expiry_date', '')
                    if expiry_date == "NOT FOUND" and gemini_expiry not in {
                        '', 'NOT FOUND', 'Information not available'
                    }:
                        expiry_date = gemini_expiry

                    brand_name = medicine_info.get('brand_name', medicine_name or 'Not detected')
                    generic_name = medicine_info.get('generic_name', 'Information not available')
                    strength = medicine_info.get('strength', 'Information not available')
                    dosage_form = medicine_info.get('dosage_form', 'Information not available')
                    uses = medicine_info.get('uses', [])
                    side_effects = medicine_info.get('side_effects', [])
                    alternatives = medicine_info.get('alternatives', [])

                    formatted_uses = []
                    for use in uses:
                        if isinstance(use, str) and len(use.strip()) > 2:
                            clean_use = re.sub(r'\([^)]*\)', '', use)
                            clean_use = re.sub(r'\s+', ' ', clean_use).strip()
                            if clean_use:
                                formatted_uses.append(clean_use)

                    formatted_effects = []
                    for effect in side_effects:
                        if isinstance(effect, str) and len(effect.strip()) > 2:
                            clean_effect = re.sub(r'\s+', ' ', effect).strip()
                            if clean_effect:
                                formatted_effects.append(clean_effect)

                    print("\n" + "="*80)
                    print(f"📋 BRAND: {brand_name}")
                    print(f"🧬 GENERIC: {generic_name}")
                    print(f"💪 STRENGTH: {strength}")
                    print(f"💊 DOSAGE FORM: {dosage_form}")
                    print(f"📅 EXPIRY DATE: {expiry_date}")
                    print(f"📊 DATA SOURCE: {medicine_info.get('source', 'Gemini')}")
                    print("\n💊 USES:")
                    if formatted_uses:
                        for i, use in enumerate(formatted_uses, 1):
                            print(f"  {i}. {use}")
                    else:
                        print("  No uses information available")
                    print("\n⚠️ SIDE EFFECTS:")
                    if formatted_effects:
                        for i, effect in enumerate(formatted_effects, 1):
                            print(f"  {i}. {effect}")
                    else:
                        print("  No side effects information available")
                    print("\n🔄 ALTERNATIVE MEDICINES:")
                    if alternatives:
                        for i, alt in enumerate(alternatives, 1):
                            print(f"  {i}. {alt}")
                    else:
                        print("  No alternatives information available")
                    print("="*80 + "\n")

                    results.append({

                        'filename': filename,

                        'medicine_name': generic_name,

                        'brand_name': brand_name,

                        'generic_name': generic_name,

                        'strength': strength,

                        'dosage_form': dosage_form,

                        'expiry_date': expiry_date,

                        'source': medicine_info.get('source', 'Gemini'),

                        'uses': formatted_uses,

                        'side_effects': formatted_effects,

                        'alternatives': alternatives

                    })
                else:
                    logger.info(f"No medicine OCR detected in {filename}")
                    results.append({
                        'filename': filename,
                        'brand_name': 'Not detected',
                        'generic_name': 'Information not available',
                        'expiry_date': expiry_date,
                        'error': 'Could not extract medicine information'
                    })
            except Exception as file_error:
                logger.exception("❌ PROCESSING ERROR for %s", filename)
                results.append({
                    'filename': filename,
                    'medicine_name': 'Not detected',
                    'expiry_date': 'NOT FOUND',
                    'error': str(file_error)
                })

        return jsonify(results)

    except Exception as e:
        logger.exception("❌ PROCESSING ERROR")
        return jsonify({
            "error": str(e),
            "message": "Medicine image processing failed."
        }), 500
# ==================== MEDICINE INVENTORY API ====================

@app.route('/add-medicine', methods=['POST'])
def add_medicine_api():
    data = request.get_json()

    if not data or not data.get('medicine_name') or not data.get('expiry_date'):
        return jsonify({
            "error": "medicine_name and expiry_date are required"
        }), 400

    try:
        quantity = int(data.get('quantity', 0))

        if quantity < 0:
            return jsonify({"error": "quantity cannot be negative"}), 400

        medicine_id = add_medicine({
            "medicine_name": data["medicine_name"],
            "brand_name": data.get("brand_name"),
            "generic_name": data.get("generic_name"),
            "strength": data.get("strength"),
            "dosage_form": data.get("dosage_form"),
            "expiry_date": data["expiry_date"],
            "quantity": quantity,
            "row_number": data.get("row_number"),
            "column_number": data.get("column_number")
        })

        return jsonify({
            "message": "Medicine added successfully",
            "medicine_id": medicine_id
        }), 201

    except ValueError:
        return jsonify({"error": "quantity must be a number"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/medicines', methods=['GET'])
def get_medicines_api():
    try:
        medicines = get_all_medicines()

        return jsonify({
            "count": len(medicines),
            "medicines": medicines
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/medicine/<int:medicine_id>', methods=['GET'])
def get_medicine_api(medicine_id):
    try:
        medicine = get_medicine(medicine_id)

        if not medicine:
            return jsonify({
                "error": "Medicine not found"
            }), 404

        return jsonify(medicine), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/search-medicine', methods=['GET'])
def search_medicine_api():
    search_text = request.args.get('q', '').strip()

    if not search_text:
        return jsonify({
            "error": "Search text is required"
        }), 400

    try:
        medicines = search_medicines(search_text)

        return jsonify({
            "count": len(medicines),
            "medicines": medicines
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/medicine/<int:medicine_id>', methods=['PUT'])
def update_medicine_api(medicine_id):
    data = request.get_json()

    if not data or not data.get('medicine_name') or not data.get('expiry_date'):
        return jsonify({
            "error": "medicine_name and expiry_date are required"
        }), 400

    try:
        quantity = int(data.get('quantity', 0))

        if quantity < 0:
            return jsonify({"error": "quantity cannot be negative"}), 400

        updated = update_medicine(medicine_id, {
            "medicine_name": data["medicine_name"],
            "brand_name": data.get("brand_name"),
            "generic_name": data.get("generic_name"),
            "strength": data.get("strength"),
            "dosage_form": data.get("dosage_form"),
            "expiry_date": data["expiry_date"],
            "quantity": quantity,
            "row_number": data.get("row_number"),
            "column_number": data.get("column_number")
        })

        if not updated:
            return jsonify({
                "error": "Medicine not found"
            }), 404

        return jsonify({
            "message": "Medicine updated successfully"
        }), 200

    except ValueError:
        return jsonify({"error": "quantity must be a number"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/medicine/<int:medicine_id>/quantity', methods=['PUT'])
def update_medicine_quantity_api(medicine_id):
    data = request.get_json()

    if not data or "quantity" not in data:
        return jsonify({
            "error": "quantity is required"
        }), 400

    try:
        quantity = int(data["quantity"])

        if quantity < 0:
            return jsonify({
                "error": "quantity cannot be negative"
            }), 400

        updated = update_quantity(medicine_id, quantity)

        if not updated:
            return jsonify({
                "error": "Medicine not found"
            }), 404

        return jsonify({
            "message": "Quantity updated successfully",
            "quantity": quantity
        }), 200

    except ValueError:
        return jsonify({
            "error": "quantity must be a number"
        }), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/medicine/<int:medicine_id>', methods=['DELETE'])
def delete_medicine_api(medicine_id):
    try:
        deleted = delete_medicine(medicine_id)

        if not deleted:
            return jsonify({
                "error": "Medicine not found"
            }), 404

        return jsonify({
            "message": "Medicine deleted successfully"
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
        # ==================== INVENTORY ALERT API ====================

@app.route('/medicines/expiring', methods=['GET'])
def expiring_medicines_api():
    try:
        days = int(request.args.get('days', 30))

        if days < 0:
            return jsonify({
                "error": "days cannot be negative"
            }), 400

        medicines = get_expiring_medicines(days)

        return jsonify({
            "count": len(medicines),
            "days": days,
            "medicines": medicines
        }), 200

    except ValueError:
        return jsonify({
            "error": "days must be a number"
        }), 400

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/medicines/expired', methods=['GET'])
def expired_medicines_api():
    try:
        medicines = get_expired_medicines()

        return jsonify({
            "count": len(medicines),
            "medicines": medicines
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/medicines/low-stock', methods=['GET'])
def low_stock_medicines_api():
    try:
        threshold = int(request.args.get('threshold', 10))

        if threshold < 0:
            return jsonify({
                "error": "threshold cannot be negative"
            }), 400

        medicines = get_low_stock_medicines(threshold)

        return jsonify({
            "count": len(medicines),
            "threshold": threshold,
            "medicines": medicines
        }), 200

    except ValueError:
        return jsonify({
            "error": "threshold must be a number"
        }), 400

    except Exception as e:
        return jsonify({"error": str(e)}), 500
# ==================== MEDICINE LOCATION API ====================

@app.route('/medicine/<int:medicine_id>/location', methods=['GET'])
def medicine_location_api(medicine_id):
    try:
        medicine = get_medicine(medicine_id)

        if not medicine:
            return jsonify({
                "error": "Medicine not found"
            }), 404

        return jsonify({
            "medicine_id": medicine["id"],
            "medicine_name": medicine["medicine_name"],
            "row_number": medicine["row_number"],
            "column_number": medicine["column_number"]
        }), 200

    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500

if __name__ == '__main__':
    print("\n" + "="*60)
    print("Medicine Detection API Started")
    print("="*60)
    print("\nUpload medicine images to extract:")
    print("   - Medicine name (YOLO + OCR)")
    print("   - Expiry date (YOLO + OCR)")
    print("   - Generic name (Gemini)")
    print("   - Uses (Gemini)")
    print("   - Side effects (Gemini)")
    print("   - Alternatives (Gemini)")
    print("\nDATA SOURCE: Gemini + YOLO + OCR")
    print("\nWeb interface: http://localhost:5000")
    print("API endpoint: http://localhost:5000/process")
    print("\n" + "="*60 + "\n")
    
    # Use environment variables for debug mode and host
    debug_mode = os.getenv("FLASK_DEBUG", "False").lower() == "true"
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", "5000"))
    
    app.run(debug=debug_mode, host=host, port=port)