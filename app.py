
import os
import re
import time
import shutil
import json
import hashlib
import logging
import uuid
import hmac
import secrets
from functools import wraps
import doctor_database as doctor_db
from interaction_analysis import analyze_medicine_interactions
from database import (
    init_database,
    normalize_expiry,
    add_medicine,
    get_all_medicines,
    get_medicine,
    search_medicines,
    update_medicine,
    update_quantity,
    delete_medicine,
    get_expiring_medicines,
    get_expired_medicines,
    get_low_stock_medicines,
    sell_medicine,
    get_sales_history,
    SaleError,
    save_training_image,
    update_training_image,
)
import cv2
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import pytesseract
# Initialize EasyOCR
try:
    import easyocr
    reader = easyocr.Reader(['en'], gpu=False)
    print("EasyOCR initialized successfully")
except Exception as e:
    print(f"EasyOCR initialization failed: {e}")
    reader = None
try:
    from google import genai
except Exception:
    genai = None
from roboflow import Roboflow
from dotenv import load_dotenv
from drive_upload import upload_pdf_to_drive

try:
    from sms import send_sms
except Exception:
    def send_sms(patient_name, phone_number, download_url):
        return None
from flask import Flask, request, jsonify, render_template, send_from_directory, session, redirect, url_for
from werkzeug.utils import secure_filename
from difflib import get_close_matches
from datetime import datetime, timedelta
try:
    from fpdf import FPDF
except Exception:
    class FPDF:
        def __init__(self):
            pass
        def add_page(self):
            pass
        def set_auto_page_break(self, val):
            pass
        def set_font(self, *args, **kwargs):
            pass
        def set_text_color(self, *args, **kwargs):
            pass
        def cell(self, *args, **kwargs):
            pass
        def ln(self, *args, **kwargs):
            pass
        def set_xy(self, *args, **kwargs):
            pass
        def output(self, filepath):
            with open(filepath, 'wb') as f:
                f.write(b'')
        def image(self, *args, **kwargs):
            return None
try:
    import qrcode
except Exception:
    # Minimal qrcode stub using PIL for tests
    import types as _types
    from PIL import Image as _Image

    qrcode = _types.SimpleNamespace()
    qrcode.constants = _types.SimpleNamespace(ERROR_CORRECT_H=1)

    class _QR:
        def __init__(self, **kwargs):
            self.data = None
        def add_data(self, d):
            self.data = d
        def make(self, fit=True):
            return True
        def make_image(self, fill_color="black", back_color="white"):
            return _Image.new('RGB', (120, 120), color=back_color)

    qrcode.QRCode = _QR
from PIL import Image, ImageDraw, ImageFont

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
if genai is None:
    client = None
    logger = logging.getLogger(__name__)
    logger.warning("google.genai not available; Gemini features disabled")
else:
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not found in .env")
    client = genai.Client(api_key=GEMINI_API_KEY)
    print("✅ Gemini Loaded")


# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    EXPIRY_WARNING_DAYS=int(os.getenv("EXPIRY_WARNING_DAYS", "7")),
    AUTH_USERS={
        "doctor": {
            "user_id": os.getenv("DOCTOR_ID", ""),
            "password": os.getenv("DOCTOR_PASSWORD", ""),
        },
        "medical_staff": {
            "user_id": os.getenv("STAFF_ID", ""),
            "password": os.getenv("STAFF_PASSWORD", ""),
        },
    },
)
if not os.getenv("FLASK_SECRET_KEY"):
    logger.warning("FLASK_SECRET_KEY is unset; sessions will not survive application restarts.")
init_database()
doctor_db.init_database()


def role_required(role, api=False):
    def decorator(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            current_role = session.get("role")
            if current_role != role:
                if current_role:
                    if api:
                        return jsonify({"error": "You do not have permission to access this resource."}), 403
                    dashboard = (
                        "doctor_dashboard"
                        if current_role == "doctor"
                        else "staff_dashboard"
                    )
                    return redirect(url_for(dashboard))
                if api:
                    return jsonify({"error": "Authentication required."}), 401
                login_page = "doctor_login" if role == "doctor" else "staff_login"
                return redirect(url_for(login_page))
            return view(*args, **kwargs)

        return wrapped_view
    return decorator


UPLOAD_FOLDER = "uploads"
GENERATED_FOLDER = "generated"
TRAINING_IMAGES_FOLDER = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "training_data",
    "images",
)
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


def archive_uploaded_training_image(filepath, original_filename):
    """Keep the original upload outside the temporary upload cleanup folder."""
    os.makedirs(TRAINING_IMAGES_FOLDER, exist_ok=True)
    extension = os.path.splitext(secure_filename(original_filename))[1].lower()
    if extension not in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}:
        extension = ".bin"

    image_id = uuid.uuid4().hex
    stored_filename = f"{image_id}{extension}"
    archived_path = os.path.join(TRAINING_IMAGES_FOLDER, stored_filename)
    shutil.copyfile(filepath, archived_path)

    digest = hashlib.sha256()
    with open(archived_path, "rb") as image_file:
        for chunk in iter(lambda: image_file.read(1024 * 1024), b""):
            digest.update(chunk)

    try:
        save_training_image(
            image_id,
            stored_filename,
            secure_filename(original_filename) or "upload",
            digest.hexdigest(),
        )
    except Exception:
        if os.path.exists(archived_path):
            os.remove(archived_path)
        raise

    return image_id


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
        dosage_text = re.sub(
            r'\bfor\s+\d+\s+(?:day|days|week|weeks|month|months)\b.*$',
            '',
            line_lower
        )
        dosage_text = re.sub(
            r'\b(?:once|twice|thrice)\s+(?:daily|a day|per day|weekly|a week|per week)\b',
            '',
            dosage_text
        )
        dosage_text = re.sub(
            r'\b\d+\s*(?:times?\s+(?:daily|a day|per day)|per day)\b',
            '',
            dosage_text
        )

        d = re.search(
            r'(?<![A-Za-z0-9])(\d+(?:/\d+)?)\s*(mg|ml|mcg|g|tablet|tab|capsule|cap)?',
            dosage_text
        )

        if d:
            dosage = d.group(1)

            if d.group(2):
                dosage += " " + d.group(2)

        # ---------------- Frequency ----------------

        frequency = "As directed"

        if ("once daily" in line_lower or
            "once per day" in line_lower or
            "once a day" in line_lower or
            "1 per day" in line_lower):

            frequency = "Once daily"

        elif ("twice daily" in line_lower or
              "twice a day" in line_lower or
              "twice per day" in line_lower or
              "2 per day" in line_lower):

            frequency = "Twice daily"

        elif ("thrice daily" in line_lower or
              "thrice a day" in line_lower or
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
            r'for\s+(\d+)\s+(days|day|weeks|week|months|month)',
            line_lower
        )

        if dur:
            duration = f"{dur.group(1)} {dur.group(2)}"

        instructions = line_lower
        instructions = re.sub(r'^[A-Za-z]+', '', instructions, count=1)
        instructions = re.sub(
            r'\b(?:once|twice|thrice)\s+(?:daily|a day|per day|weekly|a week|per week)\b',
            ' ',
            instructions,
        )
        instructions = re.sub(
            r'\b\d+\s*(?:times?\s+(?:daily|a day|per day)|per day)\b',
            ' ',
            instructions,
        )
        instructions = re.sub(
            r'\bfor\s+\d+\s+(?:day|days|week|weeks|month|months)\b',
            ' ',
            instructions,
        )
        instructions = re.sub(
            r'(?<![A-Za-z0-9])\d+(?:/\d+)?\s*(?:mg|ml|mcg|g|tablet|tab|capsule|cap)?\b',
            ' ',
            instructions,
            count=1,
        )
        instructions = re.sub(r'\b(?:take|please)\b', ' ', instructions)
        instructions = re.sub(r'[\s,;:-]+', ' ', instructions).strip()

        medicines.append({
            "name": medicine,
            "dosage": dosage,
            "frequency": frequency,
            "duration": duration,
            "instructions": instructions,
        })

    return {
        "name": "Patient",
        "age": "Not set",
        "gender": "Not set",
        "doctor": "Dr. XYZ",
        "clinic": "XYZ Clinic",
        "address": "xyzabc",
        "phone": "+91 **********",
        "email": "xyz@gmail.com",
        "medicines": medicines
    }


def create_prescription_filename(patient_name, visit_id):
    safe_name = re.sub(r'[^A-Za-z0-9_]+', '_', patient_name)
    safe_visit_id = re.sub(r'[^A-Za-z0-9_-]+', '_', visit_id)
    return f'prescription_{safe_name}_{safe_visit_id}.pdf'


def generate_prescription_pdf(data, download_url, filepath):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(False)

    pdf.set_font('Arial', 'B', 14)
    pdf.set_text_color(0, 0, 128)
    pdf.cell(0, 6, 'XYZ CLINIC', 0, 1, 'C')
    pdf.set_font('Arial', '', 9)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 5, 'Serving Health Since 1990', 0, 1, 'C')
    pdf.set_font('Arial', '', 8)
    pdf.cell(0, 4, data['address'], 0, 1, 'C')
    pdf.cell(0, 4, f"Phone: {data['phone']} | Email: {data['email']}", 0, 1, "C")
    pdf.ln(3)
    # ===================== DATE =====================
    pdf.set_font("Arial", "", 9)
    pdf.set_xy(165, 28)
    pdf.cell(
        30,
        6,
        f"Date: {datetime.now(doctor_db.INDIA_TIMEZONE).strftime('%d/%m/%Y')}",
        0,
        0,
        "R",
    )

    # ===================== DETAILS =====================

    left_x = 15
    right_x = 110

    row1 = 42
    row2 = 50
    row3 = 58

    label_w = 35
    value_w = 50

    # -------- LEFT SIDE --------
    pdf.set_font("Arial", "B", 9)
# Row positions
    row1 = 42
    row2 = 50
    row3 = 58
    row4 = 66
    row5 = 74

# -------- LEFT SIDE --------

    # Patient Name
    pdf.set_xy(left_x, row1)
    pdf.set_font("Arial", "B", 9)
    pdf.cell(label_w, 6, "Patient Name:", 0, 0)
    pdf.set_font("Arial", "", 9)
    pdf.cell(value_w, 6, data["name"], 0, 0)

    # Mobile Number
    pdf.set_xy(left_x, row2)
    pdf.set_font("Arial", "B", 9)
    pdf.cell(label_w, 6, "Mobile No:", 0, 0)
    pdf.set_font("Arial", "", 9)
    pdf.cell(value_w, 6, data["phone_number"], 0, 0)

    # Age
    pdf.set_xy(left_x, row3)
    pdf.set_font("Arial", "B", 9)
    pdf.cell(label_w, 6, "Age:", 0, 0)
    pdf.set_font("Arial", "", 9)
    pdf.cell(value_w, 6, data["age"], 0, 0)

    # Gender
    pdf.set_xy(left_x, row4)
    pdf.set_font("Arial", "B", 9)
    pdf.cell(label_w, 6, "Gender:", 0, 0)
    pdf.set_font("Arial", "", 9)
    pdf.cell(value_w, 6, data["gender"], 0, 0)

    # Patient ID
    pdf.set_xy(left_x, row5)
    pdf.set_font("Arial", "B", 9)
    pdf.cell(label_w, 6, "Patient ID:", 0, 0)
    pdf.set_font("Arial", "", 9)
    pdf.cell(value_w, 6, data["patient_id"], 0, 0)

    # -------- RIGHT SIDE --------

    # Doctor ID
    pdf.set_xy(right_x, row1)
    pdf.set_font("Arial", "B", 9)
    pdf.cell(label_w, 6, "Doctor ID:", 0, 0)
    pdf.set_font("Arial", "", 9)
    pdf.cell(0, 6, data["doctor"], 0, 0)

    # Clinic
    pdf.set_xy(right_x, row2)
    pdf.set_font("Arial", "B", 9)
    pdf.cell(label_w, 6, "Clinic:", 0, 0)
    pdf.set_font("Arial", "", 9)
    pdf.cell(0, 6, data["clinic"], 0, 0)

    # Visit ID
    pdf.set_xy(right_x, row3)
    pdf.set_font("Arial", "B", 9)
    pdf.cell(label_w, 6, "Visit ID:", 0, 0)
    pdf.set_font("Arial", "", 9)
    pdf.cell(0, 6, data["visit_id"], 0, 0)

    pdf.set_y(82)
    pdf.set_font('Arial', 'B', 8)
    pdf.set_fill_color(200, 220, 240)

    # ── Four-column layout matching the printed prescription format ──
    col_w = [52, 35, 50, 43]
    headers = ['Medicine Name', 'Dosage', 'Frequency', 'Duration']

    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 8, h, 1, 0, 'C', 1)
    pdf.ln()

    pdf.set_font('Arial', '', 7)
    for med in data['medicines']:
        # Build display strings (truncate to fit the cell)
        name_str = str(med.get('name', ''))[:32]
        dose_str = str(med.get('dosage', ''))[:20]
        freq_str = str(med.get('frequency', ''))[:26]
        timing_val = med.get('timing', [])
        if isinstance(timing_val, list) and timing_val:
            timing_str = ', '.join(timing_val)
        else:
            timing_str = '--'
        # Break timing into two lines if long (Morning, Afternoon → two rows)
        if len(timing_str) > 18:
            parts = timing_val if isinstance(timing_val, list) else [timing_str]
            mid   = (len(parts) + 1) // 2
            timing_str = ', '.join(parts[:mid]) + '\n' + ', '.join(parts[mid:])
        dur_str = str(med.get('duration', ''))[:18]

        # Row height: use 7 for single-line, 12 if timing wraps
        row_h = 12 if '\n' in timing_str else 7

        # Save cursor Y before row so we can draw all cells at same height
        row_y = pdf.get_y()
        x_start = 15  # left margin

        def draw_cell(col_idx, text, multiline=False):
            pdf.set_xy(x_start + sum(col_w[:col_idx]), row_y)
            if multiline and '\n' in text:
                lines = text.split('\n')
                pdf.set_xy(x_start + sum(col_w[:col_idx]), row_y)
                pdf.rect(x_start + sum(col_w[:col_idx]), row_y, col_w[col_idx], row_h)
                for li, line in enumerate(lines):
                    pdf.set_xy(x_start + sum(col_w[:col_idx]) + 1,
                               row_y + 1 + li * 5.5)
                    pdf.cell(col_w[col_idx] - 2, 5, line.strip(), 0, 0, 'C')
            else:
                pdf.cell(col_w[col_idx], row_h, text, 1, 0, 'C')

        draw_cell(0, name_str)
        draw_cell(1, dose_str)
        draw_cell(2, freq_str)
        draw_cell(3, dur_str)

        pdf.set_xy(x_start, row_y + row_h)

        # Keep omitted administration details below the compact table row.
        notes = []
        if timing_str != '--':
            notes.append('Timing: ' + timing_str.replace('\n', ', '))
        food = (med.get('food_instruction') or '').strip()
        if food:
            notes.append('Food: ' + food)
        special = (med.get('special_instructions') or '').strip()
        if special:
            notes.append('Note: ' + special)
        if notes:
            pdf.set_font('Arial', 'I', 6)
            pdf.set_fill_color(245, 245, 245)
            note_text = ' | '.join(notes)[:145]
            pdf.cell(sum(col_w), 5, note_text, 1, 1, 'L', 1)
            pdf.set_fill_color(255, 255, 255)
            pdf.set_font('Arial', '', 7)

    pdf.ln(5)

    # ================= DIGITAL SIGNATURE =================

    # Create signature image
    # ================= DIGITAL SIGNATURE =================

    box_x = 15
    box_y = 220
    box_w = 60
    box_h = 18

    # Heading
    pdf.set_xy(box_x, box_y - 7)
    pdf.set_font("Arial", "B", 9)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 5, "Digital Signature:")

    # Signature Box
    pdf.rect(box_x, box_y, box_w, box_h)

    # Signature Text
    pdf.set_text_color(0, 102, 204)
    pdf.set_font("Arial", "", 9)

    pdf.set_xy(box_x + 2, box_y + 2)
    pdf.cell(0, 4, "Digitally Signed", ln=1)

    pdf.set_x(box_x + 2)
    pdf.cell(0, 4, data["doctor"], ln=1)

    pdf.set_x(box_x + 2)
    pdf.cell(0, 4, datetime.now().strftime("%d/%m/%y %H:%M"), ln=1)

    # Reset text color
    pdf.set_text_color(0, 0, 0)


    qr_x = 155
    qr_y = 220

    pdf.set_xy(qr_x, qr_y - 6)
    pdf.set_font("Arial", "B", 8)
    pdf.cell(35, 5, "Scan to Download", 0, 1, "C")

    # ================= CREATE QR CODE =================

    qr = qrcode.QRCode(
        version=2,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=4,
        border=2
    )

    qr.add_data(download_url)
    qr.make(fit=True)

    qr_img = qr.make_image(fill_color="black", back_color="white")

    qr_path = os.path.join(
        GENERATED_FOLDER,
        f"qr_{uuid.uuid4().hex[:8]}.png"
    )

    qr_img.save(qr_path)

    pdf.image(qr_path, x=qr_x, y=qr_y, w=35, h=35)

    pdf.set_y(278)
    pdf.set_font('Arial', 'I', 7)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 4, 'This is a system-generated prescription. Valid with digital signature.', 0, 0, 'C')

    pdf.output(filepath)



@app.route('/generate-prescription', methods=['POST'])
@role_required("doctor", api=True)
def generate_prescription():
    try:
        if request.is_json:
            payload = request.get_json(silent=True)
        else:
            payload = request.form.to_dict()

        if not isinstance(payload, dict):
            return jsonify({
                "error": "Prescription data must be provided as an object.",
                "missing_fields": [],
                "field_errors": {},
            }), 400

        def text_value(value):
            return value.strip() if isinstance(value, str) else ""

        patient_id = text_value(payload.get("patient_id"))
        if not patient_id:
            return jsonify({"error": "Select or register a patient before prescribing."}), 400
        patient = doctor_db.get_patient(patient_id)
        if not patient:
            return jsonify({"error": "Patient not found."}), 404

        patient_name = patient["patient_name"]
        age = str(patient["age"])
        gender = patient["gender"]
        phone_number = patient["mobile_number"]
        field_errors = {}
        prescription_text = text_value(payload.get("text"))

        # ── PATH A: Structured medicines[] ──────────────────────────────────
        medicines_raw = payload.get("medicines")
        if "medicines" in payload and not isinstance(medicines_raw, list):
            field_errors["medicines"] = "Medicines must be provided as a list."
            medicines_raw = []

        if isinstance(medicines_raw, list) and medicines_raw:
            medicines_list = []
            for idx, m in enumerate(medicines_raw):
                if not isinstance(m, dict):
                    field_errors[f"medicines[{idx}]"] = (
                        f"Medicine #{idx + 1} has invalid information."
                    )
                    continue

                name = text_value(m.get("name"))
                dosage = text_value(m.get("dosage"))
                frequency = text_value(m.get("frequency"))
                food_instruction = text_value(m.get("food_instruction"))
                duration = text_value(m.get("duration"))
                timing  = m.get("timing", [])
                special = text_value(m.get("special_instructions"))
                instructions = text_value(m.get("instructions")) or special

                if not name:
                    field_errors[f"medicines[{idx}].name"] = (
                        f"Medicine #{idx + 1}: name is required."
                    )
                if not dosage:
                    field_errors[f"medicines[{idx}].dosage"] = (
                        f"Medicine #{idx + 1}: dosage is required."
                    )
                if not isinstance(timing, list):
                    timing = []
                timing = [value.strip() for value in timing if isinstance(value, str) and value.strip()]

                medicines_list.append({
                    "name":                name,
                    "dosage":              dosage,
                    "frequency":           frequency,
                    "timing":              timing,
                    "food_instruction":    food_instruction,
                    "duration":            duration,
                    "instructions":        instructions,
                    "special_instructions": special,
                })

            data = {
                "name":         patient_name,
                "age":          f"{age} years" if age else "",
                "gender":       gender,
                "phone_number": "+91" + phone_number,
                "doctor":       session["user_id"],
                "clinic":       "Shri XYZ Clinic",
                "address":      "xyzabc",
                "phone":        "+91 **********",
                "email":        "xyz@gmail.com",
                "medicines":    medicines_list,
            }

        # ── PATH B: Existing free-text prescription form ─────────────────────
        else:
            if not prescription_text:
                field_errors["medicines"] = (
                    "Record a prescription before generating the prescription."
                )
                data = None
            else:
                cleaned = clean_prescription_text(prescription_text)
                medicine_lines = [
                    line.strip()
                    for line in re.split(r'[\n\.]+', cleaned)
                    if line.strip()
                ]

                if not validate_prescription_text(cleaned):
                    field_errors["medicines"] = (
                        "Enter at least one valid medicine in the prescription."
                    )

                parsed_medicines = []
                for idx, line in enumerate(medicine_lines):
                    line_data = parse_prescription(line)["medicines"]
                    if not line_data:
                        field_errors[f"medicines[{idx}].name"] = (
                            f"Medicine #{idx + 1}: enter a medicine name."
                        )
                        continue

                    medicine = line_data[0]
                    if medicine["dosage"] == "As directed":
                        field_errors[f"medicines[{idx}].dosage"] = (
                            f"Medicine #{idx + 1}: enter dosage information."
                        )
                    parsed_medicines.extend(line_data)

                data = parse_prescription(cleaned)
                data["medicines"] = parsed_medicines
                data["name"] = patient_name
                data["age"] = f"{age} years" if age else ""
                data["gender"] = gender
                data["phone_number"] = "+91" + phone_number

        if not medicines_raw and not prescription_text:
            field_errors.setdefault(
                "medicines",
                "Record a prescription before generating the prescription."
            )

        if field_errors:
            return jsonify({
                "error": "Missing required information. Please complete the highlighted fields.",
                "missing_fields": list(field_errors),
                "field_errors": field_errors,
            }), 400

        data["doctor"] = session["user_id"]
        for medicine in data["medicines"]:
            medicine.setdefault("frequency", "")
            medicine.setdefault("duration", "")
            medicine.setdefault("timing", [])
            medicine.setdefault("food_instruction", "")
            medicine.setdefault("special_instructions", "")
            medicine.setdefault(
                "instructions",
                medicine.get("special_instructions", ""),
            )

        visit_id = f"VIS-{uuid.uuid4().hex[:16].upper()}"
        data["patient_id"] = patient_id
        data["visit_id"] = visit_id

        diagnosis = text_value(payload.get("diagnosis"))
        notes = prescription_text or text_value(payload.get("notes"))
        if not isinstance(payload.get("diagnosis", ""), str) or not isinstance(
            payload.get("notes", ""), str
        ):
            return jsonify({"error": "Diagnosis and notes must be text values."}), 400

        # Generate the existing PDF first; only persist its reference when it exists.
        filename = create_prescription_filename(data["name"], visit_id)
        filepath          = os.path.join(GENERATED_FOLDER, filename)
        local_download_url = url_for(
            "download_patient_visit_pdf",
            patient_id=patient_id,
            visit_id=visit_id,
            _external=True,
        )

        try:
            generate_prescription_pdf(data, local_download_url, filepath)
            if not os.path.exists(filepath):
                raise FileNotFoundError(
                    f"Generated prescription PDF not found at: {filepath}"
                )
            if os.path.getsize(filepath) <= 0:
                raise ValueError(f"Generated prescription PDF is empty: {filepath}")

            doctor_db.save_visit(
                patient_id,
                session["user_id"],
                diagnosis,
                notes,
                filename,
                data["medicines"],
                visit_id=visit_id,
            )
        except Exception:
            if os.path.exists(filepath):
                os.remove(filepath)
            raise

        # ── Keep local download available when Google Drive is not configured ─
        drive_url = None
        try:
            drive_url = upload_pdf_to_drive(filepath)
        except Exception as exc:
            logger.warning("Google Drive upload skipped for %s: %s", filepath, exc)

        # ── Send SMS ─────────────────────────────────────────────────────────
        try:
            if data.get("name") and data.get("phone_number") and drive_url:
                send_sms(
                    patient_name=data["name"],
                    phone_number=data["phone_number"],
                    download_url=drive_url
                )
        except Exception as e:
            logger.error(f"SMS send failed: {e}")

        return jsonify({
            "success":            True,
            "download_url":       local_download_url,
            "local_download_url": local_download_url,
            "drive_url":          drive_url,
            "filename":           filename,
            "patient":            data["name"],
            "patient_id":         patient_id,
            "visit_id":           visit_id,
            "doctor_id":          session["user_id"],
            "phone_number":       data["phone_number"],
            "age":                data["age"],
            "gender":             data["gender"],
            "medicines":          data["medicines"],
        })

    except Exception as e:
        logger.exception("Prescription generation failed")
        return jsonify({
            'error': 'Prescription generation failed. ' + str(e)
        }), 500


@app.route('/generated/<path:filename>')
@role_required("doctor")
def serve_generated_file(filename):
    return send_from_directory(GENERATED_FOLDER, filename, as_attachment=True)

@app.route("/download/<filename>")
@role_required("doctor")
def download_file(filename):
    return send_from_directory(
        GENERATED_FOLDER,
        filename,
        as_attachment=True
    )


def get_medicine_info_gemini(
    medicine_ocr,
    expiry_ocr="",
    language='English',
    generic_name="",
    brand_name="",
    strength="",
    dosage_form=""
):
    """Get medicine information and cautious suggestions from Gemini."""
    if not medicine_ocr or client is None:
        return None

    unavailable = "Information not available"

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

IDENTIFIED GENERIC NAME, IF AVAILABLE:
{generic_name or unavailable}

SCANNED BRAND NAME, IF AVAILABLE:
{brand_name or unavailable}

EXTRACTED STRENGTH, IF AVAILABLE:
{strength or unavailable}

EXTRACTED DOSAGE FORM, IF AVAILABLE:
{dosage_form or unavailable}

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
8. Same-ingredient brand suggestions
9. Other medicines a doctor might consider for the same condition or
   therapeutic purpose

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

Suggestion safety requirements:
- Never invent medicine brands, ingredients, strengths or dosage forms.
- Only report information you can identify with reasonable confidence.
- Same-ingredient brand suggestions must contain the same active
  ingredient(s) as the scanned medicine. Do not assume similar brand
  names have the same composition.
- Exclude the scanned brand from same-ingredient suggestions.
- Report each suggested brand's strength independently. Never infer it
  from the scanned medicine's strength or append the scanned strength.
- For an unknown strength, dosage form, generic name or reason, use
  "Information not available".
- If you cannot confidently identify the active ingredient(s), return
  empty arrays for both suggestion categories.
- Other drug options are not equivalent or interchangeable medicines.
  Do not include dosage or strength information for them.
- Do not claim suggestions are verified or clinically interchangeable.

Do not invent any other information. If a medicine detail cannot be
identified reliably, return "Information not available".

Return ONLY valid JSON in exactly this format:

{{
    "generic_name": "",
    "brand_name": "",
    "strength": "",
    "dosage_form": "",
    "expiry_date": "",
    "uses": [],
    "side_effects": [],
    "same_ingredient_alternatives": [
        {{
            "brand_name": "",
            "generic_name": "",
            "strength": "",
            "dosage_form": ""
        }}
    ],
    "other_drug_options": [
        {{
            "medicine_name": "",
            "reason": ""
        }}
    ]
}}

Keep each list concise (max 5 items per list). Return empty arrays when
reliable suggestions cannot be provided.
"""

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )

        text = response.text
        if not isinstance(text, str) or not text.strip():
            logger.warning("Gemini returned an empty or non-text response")
            return None
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        data = json.loads(text)

        if not isinstance(data, dict):
            logger.warning("Gemini returned non-dict JSON")
            return None

        def clean_value(value):
            if not isinstance(value, str) or not value.strip():
                return unavailable
            cleaned = value.strip()
            if cleaned.casefold() in {
                "unknown", "uncertain", "not sure", "n/a", "na"
            }:
                return unavailable
            return cleaned

        def has_information(value):
            return value != unavailable

        def identity_key(value):
            return "".join(re.findall(r"[a-z0-9]+", value.casefold()))

        def clean_string_list(value):
            if not isinstance(value, list):
                return []
            cleaned = []
            seen = set()
            for item in value:
                text_item = clean_value(item)
                key = text_item.casefold()
                if has_information(text_item) and key not in seen:
                    cleaned.append(text_item)
                    seen.add(key)
            return cleaned[:5]

        result = {
            'generic_name': clean_value(data.get('generic_name')),
            'brand_name': clean_value(data.get('brand_name')),
            'strength': clean_value(data.get('strength')),
            'dosage_form': clean_value(data.get('dosage_form')),
            'expiry_date': clean_value(data.get('expiry_date')),
            'uses': [],
            'side_effects': [],
            'same_ingredient_alternatives': [],
            'other_drug_options': [],
            'source': 'Gemini'
        }

        result['uses'] = clean_string_list(data.get('uses'))
        result['side_effects'] = clean_string_list(data.get('side_effects'))

        # If the ingredient is uncertain, neither suggestion category is safe.
        if has_information(result['generic_name']):
            scanned_brand_keys = {
                identity_key(value)
                for value in (brand_name, result['brand_name'])
                if isinstance(value, str) and has_information(clean_value(value))
            }
            scanned_generic_key = identity_key(result['generic_name'])
            seen_brands = set()
            suggestions = data.get('same_ingredient_alternatives')
            if isinstance(suggestions, list):
                for suggestion in suggestions:
                    if not isinstance(suggestion, dict):
                        continue
                    cleaned = {
                        'brand_name': clean_value(suggestion.get('brand_name')),
                        'generic_name': clean_value(suggestion.get('generic_name')),
                        'strength': clean_value(suggestion.get('strength')),
                        'dosage_form': clean_value(suggestion.get('dosage_form'))
                    }
                    brand_key = identity_key(cleaned['brand_name'])
                    generic_key = identity_key(cleaned['generic_name'])
                    if (
                        not has_information(cleaned['brand_name'])
                        or not has_information(cleaned['generic_name'])
                        or not brand_key
                        or generic_key != scanned_generic_key
                        or brand_key in scanned_brand_keys
                        or brand_key in seen_brands
                    ):
                        continue
                    result['same_ingredient_alternatives'].append(cleaned)
                    seen_brands.add(brand_key)
                    if len(result['same_ingredient_alternatives']) == 5:
                        break

            other_options = data.get('other_drug_options')
            seen_medicines = set()
            if isinstance(other_options, list):
                for option in other_options:
                    if not isinstance(option, dict):
                        continue
                    cleaned = {
                        'medicine_name': clean_value(option.get('medicine_name')),
                        'reason': clean_value(option.get('reason'))
                    }
                    medicine_key = identity_key(cleaned['medicine_name'])
                    if (
                        not has_information(cleaned['medicine_name'])
                        or not medicine_key
                        or medicine_key in seen_medicines
                    ):
                        continue
                    result['other_drug_options'].append(cleaned)
                    seen_medicines.add(medicine_key)
                    if len(result['other_drug_options']) == 5:
                        break

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
    return render_template(
        'index.html',
        user_role="public",
        initial_section="dashboardSection",
    )


def render_login(role, error=None, status=200):
    role_name = "Doctor" if role == "doctor" else "Medical Staff"
    return render_template(
        "login.html",
        role=role,
        role_name=role_name,
        id_label="Doctor ID" if role == "doctor" else "Staff ID",
        error=error,
    ), status


def authenticate_role(role):
    if session.get("role") == role:
        return redirect(
            url_for("doctor_dashboard" if role == "doctor" else "staff_dashboard")
        )

    if request.method == "GET":
        return render_login(role)

    credentials = app.config["AUTH_USERS"][role]
    configured_id = credentials["user_id"]
    configured_password = credentials["password"]
    if not configured_id or not configured_password:
        logger.error("%s login attempted before credentials were configured.", role)
        return render_login(
            role,
            "Login is not configured. Set this account's ID and password in the environment.",
            503,
        )

    submitted_id = request.form.get("user_id", "").strip()
    submitted_password = request.form.get("password", "")
    if not (
        hmac.compare_digest(submitted_id, configured_id)
        and hmac.compare_digest(submitted_password, configured_password)
    ):
        return render_login(role, "The ID or password is incorrect.", 401)

    session.clear()
    session.permanent = True
    session["role"] = role
    session["user_id"] = configured_id
    return redirect(
        url_for("doctor_dashboard" if role == "doctor" else "staff_dashboard")
    )


@app.route("/doctor/login", methods=["GET", "POST"])
def doctor_login():
    return authenticate_role("doctor")


@app.route("/staff/login", methods=["GET", "POST"])
def staff_login():
    return authenticate_role("medical_staff")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/doctor/dashboard")
@role_required("doctor")
def doctor_dashboard():
    return render_template(
        "index.html",
        user_role="doctor",
        initial_section="generatorTab",
        user_id=session.get("user_id"),
    )


@app.route("/staff/dashboard")
@role_required("medical_staff")
def staff_dashboard():
    return render_template(
        "index.html",
        user_role="medical_staff",
        initial_section="inventorySection",
        user_id=session.get("user_id"),
    )


def _patient_response(patient):
    fields = (
        "patient_id",
        "patient_name",
        "mobile_number",
        "age",
        "gender",
        "address",
        "created_at",
    )
    return {field: patient[field] for field in fields}


def _medicine_names_for_analysis(payload):
    medicines = payload.get("medicines")
    if isinstance(medicines, list):
        names = [
            item.strip() if isinstance(item, str) else
            item.get("name", "").strip() if isinstance(item, dict)
            and isinstance(item.get("name"), str) else ""
            for item in medicines
        ]
    else:
        text = payload.get("text", "")
        if not isinstance(text, str) or not text.strip():
            return []
        parsed = parse_prescription(text)
        names = [medicine["name"].strip() for medicine in parsed["medicines"]]
    return [name for name in names if name]


def _interaction_fingerprint(current_medicines, new_medicines):
    normalized = {
        "current": sorted(name.casefold() for name in current_medicines),
        "new": sorted(name.casefold() for name in new_medicines),
    }
    return hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _interaction_review_is_valid(payload, current_medicines, new_medicines):
    review = session.get("interaction_review", {})
    submitted_token = payload.get("interaction_review_token", "")
    if not isinstance(submitted_token, str) or not submitted_token:
        return False
    expected_token_hash = hashlib.sha256(submitted_token.encode("utf-8")).hexdigest()
    return (
        isinstance(review, dict)
        and hmac.compare_digest(review.get("token_hash", ""), expected_token_hash)
        and hmac.compare_digest(
            review.get("fingerprint", ""),
            _interaction_fingerprint(current_medicines, new_medicines),
        )
    )


@app.route("/doctor/patients/search", methods=["GET"])
@role_required("doctor", api=True)
def search_doctor_patients():
    patient_id = request.args.get("patient_id", "").strip()
    mobile_number = request.args.get("mobile_number", "").strip()
    if bool(patient_id) == bool(mobile_number):
        return jsonify({"error": "Search using either Patient ID or mobile number."}), 400
    try:
        patients = doctor_db.search_patients(
            patient_id=patient_id or None,
            mobile_number=mobile_number or None,
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify({"patients": [_patient_response(patient) for patient in patients]})


@app.route("/doctor/patients", methods=["POST"])
@role_required("doctor", api=True)
def create_doctor_patient():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Patient data must be provided as an object."}), 400

    patient_name = payload.get("patient_name", "")
    gender = payload.get("gender", "")
    address = payload.get("address", "")
    age_value = payload.get("age", "")
    mobile_value = payload.get("mobile_number", "")
    if not all(isinstance(value, str) for value in (patient_name, gender, address)):
        return jsonify({"error": "Patient fields must be text values."}), 400

    errors = {}
    patient_name = patient_name.strip()
    gender = gender.strip()
    if not patient_name:
        errors["patient_name"] = "Patient name is required."
    elif len(patient_name) > 120:
        errors["patient_name"] = "Patient name cannot exceed 120 characters."
    if (
        isinstance(age_value, bool)
        or not isinstance(age_value, (str, int))
        or not re.fullmatch(r"\d+", str(age_value))
    ):
        errors["age"] = "Age must be a valid whole number."
        age = None
    else:
        age = int(age_value)
        if age < 1 or age > 150:
            errors["age"] = "Age must be between 1 and 150."
    if gender not in {"Male", "Female", "Other"}:
        errors["gender"] = "Select a valid gender."
    try:
        mobile_number = doctor_db.normalize_mobile_number(mobile_value)
    except ValueError as error:
        errors["mobile_number"] = str(error)
    if errors:
        return jsonify({"error": "Please correct the patient details.", "field_errors": errors}), 400

    try:
        patient = doctor_db.register_patient(
            patient_name,
            age,
            gender,
            mobile_number,
            address,
            session["user_id"],
        )
    except doctor_db.DuplicatePatientError as error:
        return jsonify({
            "error": str(error),
            "existing_patients": [
                _patient_response(existing_patient)
                for existing_patient in error.patients
            ],
        }), 409
    return jsonify({"success": True, "patient": _patient_response(patient)}), 201


@app.route("/doctor/patients/<patient_id>", methods=["PUT"])
@role_required("doctor", api=True)
def update_doctor_patient(patient_id):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(
        payload.get("mobile_number"), str
    ):
        return jsonify({"error": "A mobile_number text value is required."}), 400
    if not doctor_db.get_patient(patient_id):
        return jsonify({"error": "Patient not found."}), 404
    try:
        mobile_number = doctor_db.normalize_mobile_number(payload["mobile_number"])
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    doctor_db.update_patient_mobile(patient_id, mobile_number)
    patient = doctor_db.get_patient(patient_id)
    return jsonify({"success": True, "patient": _patient_response(patient)})


@app.route("/doctor/patients/<patient_id>/history", methods=["GET"])
@role_required("doctor", api=True)
def get_doctor_patient_history(patient_id):
    patient = doctor_db.get_patient(patient_id)
    if not patient:
        return jsonify({"error": "Patient not found."}), 404
    visits = doctor_db.get_patient_history(patient_id)
    for visit in visits:
        visit["pdf_url"] = url_for(
            "download_patient_visit_pdf",
            patient_id=patient_id,
            visit_id=visit["visit_id"],
        )
    return jsonify({
        "patient": _patient_response(patient),
        "visits": visits,
    })


@app.route("/doctor/patients/<patient_id>/visits/<visit_id>", methods=["GET"])
@role_required("doctor", api=True)
def get_doctor_patient_visit(patient_id, visit_id):
    visit = doctor_db.get_patient_visit(patient_id, visit_id)
    if not visit:
        return jsonify({"error": "Visit not found for this patient."}), 404
    visit["pdf_url"] = url_for(
        "download_patient_visit_pdf",
        patient_id=patient_id,
        visit_id=visit_id,
    )
    return jsonify({"visit": visit})


@app.route(
    "/doctor/patients/<patient_id>/visits/<visit_id>/pdf",
    methods=["GET"],
)
@role_required("doctor")
def download_patient_visit_pdf(patient_id, visit_id):
    visit = doctor_db.get_patient_visit(patient_id, visit_id)
    if not visit:
        return jsonify({"error": "Visit not found for this patient."}), 404
    filename = visit["pdf_path"]
    if not filename or os.path.basename(filename) != filename:
        return jsonify({"error": "Prescription PDF is unavailable."}), 404
    return send_from_directory(GENERATED_FOLDER, filename, as_attachment=True)


@app.route("/doctor/interactions/analyze", methods=["POST"])
@role_required("doctor", api=True)
def analyze_doctor_medicine_interactions():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Interaction data must be provided as an object."}), 400
    current_medicines = payload.get("current_medicines", [])
    if (
        not isinstance(current_medicines, list)
        or any(not isinstance(name, str) or not name.strip() for name in current_medicines)
    ):
        return jsonify({
            "error": "Confirmed current medicines must be provided as a list of names."
        }), 400
    if payload.get("current_medicines_confirmed") is not True:
        return jsonify({
            "error": "Confirm that the patient's medication history was reviewed."
        }), 400
    current_medicines = [name.strip() for name in current_medicines]
    new_medicines = _medicine_names_for_analysis(payload)
    if not new_medicines:
        return jsonify({"error": "Enter at least one new medicine to analyze."}), 400

    if isinstance(payload.get("medicines"), list):
        prescription_preview = []
        for item in payload["medicines"]:
            if isinstance(item, str):
                prescription_preview.append({
                    "name": item.strip(),
                    "dosage": "",
                    "frequency": "",
                    "duration": "",
                    "instructions": "",
                })
            elif isinstance(item, dict):
                prescription_preview.append({
                    field: item.get(field, "") if isinstance(item.get(field, ""), str) else ""
                    for field in ("name", "dosage", "frequency", "duration", "instructions")
                })
    else:
        prescription_text = payload.get("text", "")
        prescription_preview = parse_prescription(prescription_text)["medicines"]

    result = analyze_medicine_interactions(current_medicines, new_medicines)
    review_token = secrets.token_urlsafe(32)
    session["interaction_review"] = {
        "token_hash": hashlib.sha256(review_token.encode("utf-8")).hexdigest(),
        "fingerprint": _interaction_fingerprint(
            current_medicines,
            new_medicines,
        ),
    }
    return jsonify({
        "analysis": result,
        "prescription_preview": prescription_preview,
        "interaction_review_token": review_token,
    })


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
            training_image_id = None
            processing_status = "failed"
            medicine_ocr = ""
            try:
                file.save(filepath)
                try:
                    training_image_id = archive_uploaded_training_image(
                        filepath,
                        filename,
                    )
                except Exception as archive_error:
                    logger.exception("Could not archive uploaded image for training")
                    raise RuntimeError(
                        "Could not save uploaded image for future training."
                    ) from archive_error

                logger.info(f"Processing: {filename}")

                image = cv2.imread(filepath)
                if image is None:
                    raise ValueError('Could not read image')

                medicine_name = None
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

                # =====================================================
                # GEMINI: Send OCR text (not just medicine name)
                # =====================================================
                if medicine_ocr:
                    gemini_language = 'Kannada' if language == 'kn' else 'English'
                    medicine_info = get_medicine_info_gemini(
                        medicine_ocr,
                        expiry_ocr,
                        gemini_language,
                        brand_name=medicine_name or ""
                    )

                    if not medicine_info:
                        medicine_info = {
                            'brand_name': medicine_name or 'Not detected',
                            'generic_name': 'Information not available',
                            'strength': 'Information not available',
                            'dosage_form': 'Information not available',
                            'expiry_date': expiry_date,
                            'uses': ['Information not available'],
                            'side_effects': ['Information not available'],
                            'same_ingredient_alternatives': [],
                            'other_drug_options': [],
                            'source': 'Gemini (error)'
                        }

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
                    same_ingredient_alternatives = medicine_info.get(
                        'same_ingredient_alternatives', []
                    )
                    other_drug_options = medicine_info.get('other_drug_options', [])

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
                    print("\n🔄 SAME-INGREDIENT BRAND SUGGESTIONS:")
                    if same_ingredient_alternatives:
                        for i, suggestion in enumerate(same_ingredient_alternatives, 1):
                            print(f"  {i}. {suggestion.get('brand_name', 'Information not available')}")
                    else:
                        print("  No reliable suggestions available")
                    print("\n💊 OTHER DRUG OPTIONS A DOCTOR MAY CONSIDER:")
                    if other_drug_options:
                        for i, option in enumerate(other_drug_options, 1):
                            print(f"  {i}. {option.get('medicine_name', 'Information not available')}")
                    else:
                        print("  No reliable suggestions available")
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

                        'same_ingredient_alternatives': same_ingredient_alternatives,

                        'other_drug_options': other_drug_options

                    })
                else:
                    logger.info(f"No medicine OCR detected in {filename}")
                    results.append({
                        'filename': filename,
                        'brand_name': 'Not detected',
                        'generic_name': 'Information not available',
                        'expiry_date': expiry_date,
                        'same_ingredient_alternatives': [],
                        'other_drug_options': [],
                        'error': 'Could not extract medicine information'
                    })
                processing_status = "processed"
            except Exception as file_error:
                logger.exception("❌ PROCESSING ERROR for %s", filename)
                results.append({
                    'filename': filename,
                    'medicine_name': 'Not detected',
                    'expiry_date': 'NOT FOUND',
                    'same_ingredient_alternatives': [],
                    'other_drug_options': [],
                    'error': str(file_error)
                })

            result = results[-1]
            if training_image_id:
                result["training_image_id"] = training_image_id
                result["training_archive_status"] = "saved"
                try:
                    update_training_image(
                        training_image_id,
                        processing_status=processing_status,
                        extracted_text=medicine_ocr,
                        medicine_name=result.get("medicine_name"),
                        brand_name=result.get("brand_name"),
                        generic_name=result.get("generic_name"),
                        strength=result.get("strength"),
                        dosage_form=result.get("dosage_form"),
                        expiry_date=result.get("expiry_date"),
                    )
                except Exception:
                    logger.exception(
                        "Could not update metadata for archived image %s",
                        training_image_id,
                    )
                    result["training_archive_status"] = "metadata_error"
                    result["training_archive_error"] = (
                        "Image was saved, but its training metadata could not be updated."
                    )
            else:
                result["training_archive_status"] = "failed"
                result["training_archive_error"] = (
                    "Image could not be saved for future training."
                )

        return jsonify(results)

    except Exception as e:
        logger.exception("❌ PROCESSING ERROR")
        return jsonify({
            "error": str(e),
            "message": "Medicine image processing failed."
        }), 500
# ==================== MEDICINE INVENTORY API ====================

@app.route('/add-medicine', methods=['POST'])
@role_required("medical_staff", api=True)
def add_medicine_api():
    data = request.get_json()

    if not data or not data.get('medicine_name'):
        return jsonify({"error": "medicine_name is required"}), 400

    try:
        expiry_date = normalize_expiry(data.get("expiry_date"))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

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
            "expiry_date": expiry_date,
            "quantity": quantity,
            "row_number": data.get("row_number"),
            "column_number": data.get("column_number")
        })

        return jsonify({
            "message": "Medicine added successfully",
            "medicine_id": medicine_id
        }), 201

    except (TypeError, ValueError):
        return jsonify({"error": "quantity must be a number"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/medicines', methods=['GET'])
@role_required("medical_staff", api=True)
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
@role_required("medical_staff", api=True)
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
@role_required("medical_staff", api=True)
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
@role_required("medical_staff", api=True)
def update_medicine_api(medicine_id):
    data = request.get_json()

    if not data or not data.get('medicine_name'):
        return jsonify({"error": "medicine_name is required"}), 400

    try:
        expiry_date = normalize_expiry(data.get("expiry_date"))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    try:
        medicine_data = {
            "medicine_name": data["medicine_name"],
            "brand_name": data.get("brand_name"),
            "generic_name": data.get("generic_name"),
            "strength": data.get("strength"),
            "dosage_form": data.get("dosage_form"),
            "expiry_date": expiry_date,
            "row_number": data.get("row_number"),
            "column_number": data.get("column_number")
        }
        if "quantity" in data:
            quantity = int(data["quantity"])
            if quantity < 0:
                return jsonify({"error": "quantity cannot be negative"}), 400
            medicine_data["quantity"] = quantity

        updated = update_medicine(medicine_id, medicine_data)

        if not updated:
            return jsonify({
                "error": "Medicine not found"
            }), 404

        return jsonify({
            "message": "Medicine updated successfully"
        }), 200

    except (TypeError, ValueError):
        return jsonify({"error": "quantity must be a number"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/medicine/<int:medicine_id>/quantity', methods=['PUT'])
@role_required("medical_staff", api=True)
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
@role_required("medical_staff", api=True)
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

# ==================== SALES API ====================

@app.route('/sales', methods=['POST'])
@role_required("medical_staff", api=True)
def create_sale_api():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "A JSON body is required."}), 400
    if "medicine_id" not in data:
        return jsonify({"error": "medicine_id is required."}), 400
    if "quantity" not in data:
        return jsonify({"error": "quantity is required."}), 400

    medicine_id = data["medicine_id"]
    if isinstance(medicine_id, str) and medicine_id.strip().isdigit():
        medicine_id = int(medicine_id)

    request_id = data.get("request_id")
    if request_id is not None and (
        not isinstance(request_id, str) or not 0 < len(request_id) <= 100
    ):
        return jsonify({"error": "request_id must be a short text value."}), 400

    try:
        sale = sell_medicine(
            medicine_id,
            data["quantity"],
            sold_by=session.get("user_id"),
            request_id=request_id,
        )
    except SaleError as error:
        return jsonify({"error": error.message}), error.status
    except Exception:
        logger.exception("Sale failed unexpectedly")
        return jsonify({"error": "The sale could not be completed. No stock was changed."}), 500

    if sale["duplicate"]:
        message = (
            "This sale was already recorded, so stock was not reduced again. "
            f"Remaining stock: {sale['remaining_stock']}."
        )
    else:
        message = f"Sale completed successfully. Remaining stock: {sale['remaining_stock']}."
    return jsonify({"message": message, **sale}), 200 if sale["duplicate"] else 201


@app.route('/sales', methods=['GET'])
@role_required("medical_staff", api=True)
def get_sales_api():
    try:
        sales = get_sales_history()
        return jsonify({"count": len(sales), "sales": sales}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


        # ==================== INVENTORY ALERT API ====================

@app.route('/medicines/expiring', methods=['GET'])
@role_required("medical_staff", api=True)
def expiring_medicines_api():
    try:
        days = int(request.args.get('days', app.config["EXPIRY_WARNING_DAYS"]))

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
@role_required("medical_staff", api=True)
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
@role_required("medical_staff", api=True)
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
@role_required("medical_staff", api=True)
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
    print("🚀 Medicine Detection API Started")
    print("="*60)
    print("\n📤 Upload medicine images to extract:")
    print("   • Medicine name (YOLO + OCR)")
    print("   • Expiry date (YOLO + OCR)")
    print("   • Generic name (Gemini)")
    print("   • Uses (Gemini)")
    print("   • Side effects (Gemini)")
    print("   • Alternatives (Gemini)")
    print("\n📡 DATA SOURCE: Gemini + YOLO + OCR")
    print("\n🌐 Web interface: http://localhost:5000")
    print("📡 API endpoint: http://localhost:5000/process")
    print("\n" + "="*60 + "\n")
    
    # Use environment variables for debug mode and host
    debug_mode = os.getenv("FLASK_DEBUG", "False").lower() == "true"
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", "5000"))
    
    app.run(debug=debug_mode, host=host, port=port)