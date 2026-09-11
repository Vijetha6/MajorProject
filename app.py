
import os
import re
import time
import shutil
import json
import logging
import uuid
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
    from sms import send_sms
except Exception:
    def send_sms(patient_name, phone_number, download_url):
        return None
from flask import Flask, request, jsonify, render_template, send_from_directory
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
init_database()


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
        "name": "Patient",
        "age": "Not set",
        "gender": "Not set",
        "doctor": "Dr. XYZ",
        "clinic": "Shri XYZ Clinic",
        "address": "xyzabc",
        "phone": "+91 **********",
        "email": "xyz@gmail.com",
        "medicines": medicines
    }


def create_prescription_filename(patient_name):
    safe_name = re.sub(r'[^A-Za-z0-9_]+', '_', patient_name)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return f'prescription_{safe_name}_{timestamp}.pdf'


def generate_prescription_pdf(data, download_url, filepath):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(False)

    pdf.set_font('Arial', 'B', 14)
    pdf.set_text_color(0, 0, 128)
    pdf.cell(0, 6, 'SHRI XYZ CLINIC', 0, 1, 'C')
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
    pdf.cell(30, 6, f"Date: {datetime.now().strftime('%d/%m/%Y')}", 0, 0, "R")

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
        # -------- RIGHT SIDE --------

    # Doctor Name
    pdf.set_xy(right_x, row1)
    pdf.set_font("Arial", "B", 9)
    pdf.cell(label_w, 6, "Doctor Name:", 0, 0)
    pdf.set_font("Arial", "", 9)
    pdf.cell(0, 6, data["doctor"], 0, 0)

    # Clinic
    pdf.set_xy(right_x, row2)
    pdf.set_font("Arial", "B", 9)
    pdf.cell(label_w, 6, "Clinic:", 0, 0)
    pdf.set_font("Arial", "", 9)
    pdf.cell(0, 6, data["clinic"], 0, 0)

    pdf.set_y(82)
    pdf.set_font('Arial', 'B', 9)
    pdf.set_fill_color(200, 220, 240)
    pdf.cell(68, 8, 'Medicine Name', 1, 0, 'C', 1)
    pdf.cell(38, 8, 'Dosage', 1, 0, 'C', 1)
    pdf.cell(48, 8, 'Frequency', 1, 0, 'C', 1)
    pdf.cell(32, 8, 'Duration', 1, 1, 'C', 1)

    pdf.set_font('Arial', '', 8)
    for med in data['medicines']:
        pdf.cell(68, 7, med['name'][:32], 1, 0, 'L')
        pdf.cell(38, 7, med['dosage'], 1, 0, 'C')
        pdf.cell(48, 7, med['frequency'], 1, 0, 'L')
        pdf.cell(32, 7, med['duration'], 1, 1, 'C')
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
def generate_prescription():
    try:
        if request.is_json:
            payload = request.get_json()
        else:
            payload = request.form.to_dict()

        patient_name = (payload.get("patient_name") or "").strip()
        age = (payload.get("age") or "").strip()
        gender = (payload.get("gender") or "").strip()
        phone_number = (payload.get("phone_number") or "").strip()
        text = (payload.get("text") or "").strip()

        # Validate all required fields
        if not patient_name:
            return jsonify({'error': 'Patient name is required.'}), 400

        if not age:
            return jsonify({'error': 'Age is required.'}), 400

        if not gender:
            return jsonify({'error': 'Gender is required.'}), 400

        if not phone_number:
            return jsonify({'error': 'Phone number is required.'}), 400

        if not text:
            return jsonify({'error': 'Prescription text is required.'}), 400

        # Validate age
        try:
            age_int = int(age)
            if age_int < 1 or age_int > 150:
                return jsonify({'error': 'Age must be between 1 and 150.'}), 400
        except ValueError:
            return jsonify({'error': 'Age must be a valid number.'}), 400

        cleaned = clean_prescription_text(text)

        if not validate_prescription_text(cleaned):
            return jsonify({
                'error': 'Invalid prescription text. Please include at least one medicine.'
            }), 400

        data = parse_prescription(cleaned)

        # Override with manually entered patient details
        data["name"] = patient_name
        data["age"] = age + " years"
        data["gender"] = gender
        data["phone_number"] = "+91" + phone_number

        filename = create_prescription_filename(data["name"])
        filepath = os.path.join(GENERATED_FOLDER, filename)
        local_download_url = request.host_url.rstrip("/") + "/download/" + filename

        generate_prescription_pdf(
            data,
            local_download_url,
            filepath
        )

        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Generated prescription PDF not found at: {filepath}")

        if os.path.getsize(filepath) <= 0:
            raise ValueError(f"Generated prescription PDF is empty: {filepath}")

        try:
            drive_url = upload_pdf_to_drive(filepath)
        except Exception as exc:
            logger.exception("Google Drive upload failed for %s", filepath)
            return jsonify({
                "success": False,
                "error": f"Google Drive upload failed: {exc}"
            }), 500

        if not drive_url:
            return jsonify({
                "success": False,
                "error": "Google Drive upload failed: no URL returned."
            }), 500

        sms_sent = False
        sms_sid = None
        sms_error = None

        try:
            if data.get("name") and data.get("phone_number") and drive_url:
                sms_sid = send_sms(
                    patient_name=data["name"],
                    phone_number=data["phone_number"],
                    download_url=drive_url
                )
                sms_sent = bool(sms_sid)
        except Exception as e:
            logger.error(f"SMS send failed: {e}")
            sms_error = str(e)

        return jsonify({
            "success": True,
            "download_url": drive_url,
            "local_download_url": local_download_url,
            "filename": filename,
            "patient": data["name"],
            "phone_number": data["phone_number"],
            "age": data["age"],
            "gender": data["gender"],
            "medicines": data["medicines"],
            "sms_sent": sms_sent,
            "sms_sid": sms_sid,
            "sms_error": sms_error
        })
    except Exception as e:
        logger.exception("Prescription generation failed")
        return jsonify({
            'error': 'Prescription generation failed. ' + str(e)
        }), 500


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
            model="gemini-3.6-flash",
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
                # FALLBACK: Full image OCR if YOLO regions not found
                # =====================================================
                if not medicine_name:
                    logger.info("YOLO didn't find medicine, trying full image")
                    full_text = extract_text_with_ocr(image)
                    medicine_name = extract_medicine_name(full_text)
                    medicine_ocr = full_text

                    if expiry_date == "NOT FOUND":
                        # Try fallback expiry extraction
                        expiry_region_full = image
                        expiry_date, _, expiry_ocr = extract_expiry_with_rotations(
                            expiry_region_full
                        )

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
                        medicine_info = {
                            'brand_name': medicine_name or 'Not detected',
                            'generic_name': 'Information not available',
                            'strength': 'Information not available',
                            'dosage_form': 'Information not available',
                            'expiry_date': expiry_date,
                            'uses': ['Information not available'],
                            'side_effects': ['Information not available'],
                            'alternatives': ['Information not available'],
                            'source': 'Gemini (error)'
                        }

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
