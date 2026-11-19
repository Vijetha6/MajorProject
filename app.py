
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
    print("Gemini Loaded")


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


def normalize_duration_value(value):
    if not value:
        return "As directed"
    value = value.strip().lower()
    replacements = {
        "one": "1",
        "two": "2",
        "three": "3",
        "four": "4",
        "five": "5",
        "six": "6",
        "seven": "7",
        "eight": "8",
        "nine": "9",
        "ten": "10",
    }
    for word, number in replacements.items():
        value = re.sub(rf"\b{word}\b", number, value)
    value = re.sub(r"\s+", " ", value)
    value = value.replace("day ", "day ")
    return value


def extract_timing_values(text):
    timing = []
    for slot in ["Morning", "Afternoon", "Evening", "Bedtime"]:
        if re.search(rf"\b{slot.lower()}\b", text, re.IGNORECASE):
            timing.append(slot)
    return timing


def is_likely_medicine_name(text):
    """Check if text is likely a medicine name vs conversation/advice"""
    if not text or len(text.strip()) < 2:
        return False
    
    text_lower = text.lower().strip()
    
    # Exclude common conversation phrases
    conversation_phrases = [
        'hello', 'hi', 'doctor speaking', 'i am', 'the patient', 'should', 
        'take', 'adequate', 'rest', 'drink', 'water', 'plenty', 'recording',
        'completed', 'prescribe', 'also prescribe', 'for the patient',
        'good morning', 'good afternoon', 'good evening', 'thank you',
        'please', 'kindly', 'avoid', 'continue', 'stop', 'follow up'
    ]
    
    for phrase in conversation_phrases:
        if phrase in text_lower:
            return False
    
    # Exclude general advice patterns
    advice_patterns = [
        r'^(take|drink|avoid|continue|stop|get|do|don\'t)\s+',
        r'\b(rest|water|exercise|sleep|diet|food)\b',
        r'^(the patient|patient should|you should)',
        r'(recording|transcript|completed|finished)'
    ]
    
    for pattern in advice_patterns:
        if re.search(pattern, text_lower):
            return False
    
    # Check if it looks like a medicine name (contains known medicine or has medicine-like pattern)
    known_medicine = any(med in text_lower for med in COMMON_MEDICINES)
    has_dosage = bool(re.search(r'\d+\s*(?:mg|ml|mcg|g)\b', text_lower))
    has_frequency = bool(re.search(r'\b(once|twice|thrice|daily|weekly)\b', text_lower))
    
    # If it has both a known medicine pattern and dosage/frequency info, likely a medicine
    if known_medicine or (has_dosage and has_frequency):
        return True
    
    # Check for medicine-like structure: word + number + unit
    if re.search(r'^[A-Za-z]{3,}(?:in|ol|ne|zine|cillin|mycin|pam|lol|pine|pril|sartan|tide|mine|dine|lone)\b', text_lower):
        return True
    
    return False


def extract_medicines_from_voice_transcript(text):
    """
    Intelligently extract medicine prescriptions from voice transcript.
    Separates actual medicines from conversation and general advice.
    """
    if not text:
        return []
    
    text = clean_prescription_text(word_to_number(text))
    
    # Split by common separators but keep context
    segments = re.split(r'(?:\.|\.|also prescribe|and prescribe|prescribe)\s+', text, flags=re.IGNORECASE)
    
    medicines = []
    general_advice = []
    
    for segment in segments:
        segment = segment.strip()
        if not segment or len(segment) < 5:
            continue
        
        segment_lower = segment.lower()
        
        # Check if this segment contains medicine-like information
        has_medicine_indicator = (
            any(med in segment_lower for med in COMMON_MEDICINES) or
            re.search(r'\d+\s*(?:mg|ml|mcg|g)\b', segment_lower) or
            re.search(r'\b(tablet|capsule|syrup|injection)\b', segment_lower)
        )
        
        # Check if it's general advice
        is_advice = (
            re.search(r'^(take|drink|avoid|get|do)\s+(adequate|plenty|rest|water|exercise)', segment_lower) or
            re.search(r'(should rest|should drink|should avoid|should take care)', segment_lower) or
            'recording completed' in segment_lower or
            'hello doctor' in segment_lower
        )
        
        if is_advice:
            general_advice.append(segment)
            continue
        
        if not has_medicine_indicator:
            continue
        
        # Extract medicine details from this segment
        medicine_data = parse_medicine_segment(segment)
        if medicine_data and is_likely_medicine_name(medicine_data['name']):
            medicines.append(medicine_data)
    
    return medicines


def parse_medicine_segment(segment):
    """Parse a single segment that likely contains a medicine prescription"""
    line = segment.strip()
    line_lower = line.lower()
    
    # Extract medicine name - look for word before dosage or frequency
    med_match = re.match(
        r'^(?:prescribe\s+)?([A-Za-z][A-Za-z .()-]+?)(?=\s+(?:\d+(?:/\d+)?\s*(?:mg|ml|mcg|g)|once|twice|thrice|daily|weekly))',
        line,
        re.IGNORECASE
    )
    
    if not med_match:
        # Try to find known medicine names
        for known_med in COMMON_MEDICINES:
            if known_med in line_lower:
                med_match = re.search(rf'\b({known_med})\b', line, re.IGNORECASE)
                if med_match:
                    break
    
    if not med_match:
        return None
    
    medicine = med_match.group(1).strip()
    
    # Clean up medicine name
    medicine = re.sub(r'\b(prescribe|prescribed|tablet|capsule|syrup)\b', '', medicine, flags=re.IGNORECASE).strip()
    
    if not medicine or len(medicine) < 2:
        return None
    
    # Extract dosage
    dosage_match = re.search(r'(\d+(?:/\d+)?\s*(?:mg|ml|mcg|g|milligram|milligrams|mill))', line, re.IGNORECASE)
    dosage = dosage_match.group(1).strip() if dosage_match else "Dose not specified"
    
    # Normalize dosage
    dosage = re.sub(r'\bmilligram(?:s)?\b', 'mg', dosage, flags=re.IGNORECASE)
    dosage = re.sub(r'\bmill\b', 'mg', dosage, flags=re.IGNORECASE)
    
    # Extract frequency
    frequency = "As directed"
    if re.search(r'\b(?:once|1|one)\s+(?:daily|a day|per day|in a day)\b', line_lower):
        frequency = "Once daily"
    elif re.search(r'\b(?:twice|2|two)\s+(?:daily|a day|per day|in a day)\b', line_lower):
        frequency = "Twice daily"
    elif re.search(r'\b(?:thrice|3|three)\s+(?:daily|a day|per day|in a day)\b', line_lower):
        frequency = "Thrice daily"
    elif re.search(r'\b(?:four times|4 times)\s+(?:daily|a day|per day)\b', line_lower):
        frequency = "Four times daily"
    
    # Extract duration
    duration = "As directed"
    dur_match = re.search(
        r'for\s+((?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s*(?:day|days|week|weeks|month|months))',
        line_lower
    )
    if dur_match:
        duration = normalize_duration_value(dur_match.group(1))
    
    # Extract timing
    timing = extract_timing_values(line)
    
    # Extract food instruction
    food_instruction = ''
    food_match = re.search(r'(after food|before food|with food|empty stomach|before meal|after meal)', line_lower)
    if food_match:
        food_instruction = food_match.group(1).strip().title()
    
    # Extract special instructions (excluding medicine name, dosage, frequency, etc.)
    instructions = line
    instructions = re.sub(rf'^{re.escape(medicine)}', '', instructions, flags=re.IGNORECASE)
    instructions = re.sub(re.escape(dosage), '', instructions, flags=re.IGNORECASE)
    instructions = re.sub(rf'\b{re.escape(frequency.lower())}\b', '', instructions, flags=re.IGNORECASE)
    instructions = re.sub(r'\bfor\s+.*?\b(?:day|days|week|weeks|month|months)\b', '', instructions, flags=re.IGNORECASE)
    instructions = re.sub(
        r'\b(?:prescribe|prescribed|morning|afternoon|evening|bedtime|after food|before food|with food|empty stomach|take|tablet|tab|capsule|cap|daily|weekly)\b',
        ' ',
        instructions,
        flags=re.IGNORECASE
    )
    instructions = re.sub(r'[\s,;:-]+', ' ', instructions).strip()
    
    if not instructions or len(instructions) < 3:
        instructions = ''
    
    return {
        "name": medicine.title(),
        "dosage": dosage,
        "frequency": frequency,
        "duration": duration,
        "timing": timing,
        "food_instruction": food_instruction,
        "special_instructions": instructions,
        "instructions": instructions,
    }


def extract_prescription_with_gemini(prescription_text):
    """
    Use Gemini to intelligently extract structured medicine data from free-form prescription text.
    Handles natural doctor speech patterns, multiple medicines, context across sentences,
    corrections, and separates medicines from general advice.
    
    Returns:
        dict: {
            "medicines": [...],
            "general_advice": [...],
            "extraction_source": "gemini" or "fallback"
        }
    """
    if not prescription_text or not prescription_text.strip():
        return {
            "medicines": [],
            "general_advice": [],
            "extraction_source": "fallback",
            "error": "Empty prescription text"
        }
    
    # Check if Gemini is available
    if client is None or not GEMINI_API_KEY:
        logger.warning("Gemini not available, using fallback parser")
        fallback_medicines = extract_medicines_from_voice_transcript(prescription_text)
        return {
            "medicines": fallback_medicines,
            "general_advice": [],
            "extraction_source": "fallback",
            "note": "Intelligent extraction unavailable. Using pattern-based fallback."
        }
    
    # Prepare Gemini prompt for intelligent extraction
    prompt = f"""You are a medical prescription extraction assistant. Your task is to extract structured medicine information from natural doctor speech or typed prescription text.

PRESCRIPTION TEXT:
{prescription_text}

IMPORTANT INSTRUCTIONS:

1. UNDERSTAND CONTEXT ACROSS SENTENCES:
   - When a doctor says "Prescribe Paracetamol 500 mg. Take one tablet morning and evening. Continue for five days. After food."
   - ALL these sentences refer to ONE medicine (Paracetamol).
   - Do NOT create separate medicines for each sentence.
   - Combine information from multiple sentences that refer to the same medicine.

2. HANDLE CORRECTIONS:
   - If the doctor says "for five days. Actually, make that three days", use THREE days (latest value).
   - The most recent explicit correction overrides earlier values.

3. DISTINGUISH MEDICINES FROM CONVERSATION:
   - Extract ONLY actual medicine prescriptions.
   - DO NOT treat these as medicines:
     * Greetings: "Hello", "Good morning", "Doctor speaking"
     * Closing statements: "Thank you", "That completes the prescription", "Recording completed"
     * General advice: "Drink plenty of water", "Get adequate rest", "Maintain a healthy diet"
     * Instructions without medicine: "Take adequate rest"

4. GENERAL PATIENT ADVICE:
   - Extract general health advice separately (not as medicines).
   - Examples: "Drink plenty of water", "Get adequate rest", "Avoid spicy food"

5. REQUIRED FIELDS FOR EACH MEDICINE:
   {{
     "name": "Medicine name (required)",
     "dosage": "Strength with unit (e.g., 500 mg)",
     "frequency": "How often (e.g., Once daily, Twice daily, As directed)",
     "duration": "How long (e.g., 5 days, 1 week, As directed)",
     "timing": ["Morning", "Afternoon", "Evening", "Bedtime"],
     "food_instruction": "After food, Before food, With food, or empty string",
     "special_instructions": "Any additional notes"
   }}

6. MEDICAL SAFETY RULES:
   - NEVER invent medicine names, dosages, or durations.
   - If information is missing or uncertain, use empty string "" or "As directed".
   - NEVER assume frequency from timing alone (if only "morning" is mentioned, frequency is "As directed", not "once daily" unless explicitly stated).
   - NEVER convert uncertain medicine names to different medicines.
   - Extract only what is explicitly stated or strongly implied.

7. TIMING VALUES:
   - Use exactly these values: "Morning", "Afternoon", "Evening", "Bedtime"
   - Return as a JSON array: ["Morning", "Evening"]

8. FREQUENCY NORMALIZATION:
   - "once a day", "one per day", "once daily" → "Once daily"
   - "twice a day", "two per day", "twice daily" → "Twice daily"
   - "thrice a day", "three times a day" → "Thrice daily"
   - "four times a day" → "Four times daily"
   - If not specified → "As directed"

9. DURATION NORMALIZATION:
   - Convert words to numbers: "five days" → "5 days"
   - "one week" → "1 week"
   - If not specified → "As directed"

10. DOSAGE NORMALIZATION:
    - "500 milligrams" → "500 mg"
    - "10 milligram" → "10 mg"
    - Keep format: number + space + unit (e.g., "500 mg", "10 ml")

RESPONSE FORMAT:
Return ONLY valid JSON in this exact structure:

{{
  "medicines": [
    {{
      "name": "Paracetamol",
      "dosage": "500 mg",
      "frequency": "Twice daily",
      "duration": "5 days",
      "timing": ["Morning", "Evening"],
      "food_instruction": "After food",
      "special_instructions": ""
    }}
  ],
  "general_advice": [
    "Drink plenty of water",
    "Get adequate rest"
  ]
}}

CRITICAL: Return ONLY the JSON object. No markdown code blocks, no explanations, no additional text.
"""
    
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )
        
        response_text = response.text
        if not isinstance(response_text, str) or not response_text.strip():
            logger.warning("Gemini returned empty response for prescription extraction")
            fallback_medicines = extract_medicines_from_voice_transcript(prescription_text)
            return {
                "medicines": fallback_medicines,
                "general_advice": [],
                "extraction_source": "fallback",
                "note": "Gemini returned empty response. Using fallback."
            }
        
        # Clean response text
        response_text = response_text.strip()
        
        # Remove markdown code blocks if present
        if response_text.startswith("```"):
            response_text = re.sub(r"^```(?:json)?\s*", "", response_text, flags=re.IGNORECASE)
            response_text = re.sub(r"\s*```$", "", response_text)
        
        # Parse JSON
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.warning(f"Gemini returned invalid JSON: {e}")
            fallback_medicines = extract_medicines_from_voice_transcript(prescription_text)
            return {
                "medicines": fallback_medicines,
                "general_advice": [],
                "extraction_source": "fallback",
                "note": "Invalid JSON from Gemini. Using fallback."
            }
        
        # Validate structure
        if not isinstance(data, dict):
            logger.warning("Gemini returned non-dict JSON")
            fallback_medicines = extract_medicines_from_voice_transcript(prescription_text)
            return {
                "medicines": fallback_medicines,
                "general_advice": [],
                "extraction_source": "fallback",
                "note": "Invalid structure from Gemini. Using fallback."
            }
        
        # Extract and validate medicines
        medicines = data.get("medicines", [])
        if not isinstance(medicines, list):
            medicines = []
        
        # Validate and clean each medicine
        validated_medicines = []
        for med in medicines:
            if not isinstance(med, dict):
                continue
            
            name = str(med.get("name", "")).strip()
            if not name or len(name) < 2:
                continue
            
            # Skip if it's likely not a medicine (general advice mistaken as medicine)
            if not is_likely_medicine_name(name):
                continue
            
            dosage = str(med.get("dosage", "")).strip() or "Dose not specified"
            frequency = str(med.get("frequency", "")).strip() or "As directed"
            duration = str(med.get("duration", "")).strip() or "As directed"
            food_instruction = str(med.get("food_instruction", "")).strip()
            special_instructions = str(med.get("special_instructions", "")).strip()
            
            # Validate timing array
            timing = med.get("timing", [])
            if not isinstance(timing, list):
                timing = []
            
            valid_timing_slots = {"Morning", "Afternoon", "Evening", "Bedtime"}
            timing = [str(t).strip() for t in timing if str(t).strip() in valid_timing_slots]
            
            validated_medicines.append({
                "name": name,
                "dosage": dosage,
                "frequency": frequency,
                "duration": duration,
                "timing": timing,
                "food_instruction": food_instruction,
                "special_instructions": special_instructions,
                "instructions": special_instructions,
            })
        
        # Extract general advice
        general_advice = data.get("general_advice", [])
        if not isinstance(general_advice, list):
            general_advice = []
        general_advice = [str(advice).strip() for advice in general_advice if isinstance(advice, str) and str(advice).strip()]
        
        # If no medicines extracted and text looks like it should have medicines, try fallback
        if not validated_medicines and any(med in prescription_text.lower() for med in COMMON_MEDICINES):
            logger.warning("Gemini extracted no medicines but text contains known medicine names. Using fallback.")
            fallback_medicines = extract_medicines_from_voice_transcript(prescription_text)
            return {
                "medicines": fallback_medicines,
                "general_advice": general_advice,
                "extraction_source": "fallback",
                "note": "Gemini extracted no medicines. Using fallback."
            }
        
        return {
            "medicines": validated_medicines,
            "general_advice": general_advice,
            "extraction_source": "gemini"
        }
        
    except Exception as e:
        logger.exception("Gemini prescription extraction failed")
        fallback_medicines = extract_medicines_from_voice_transcript(prescription_text)
        return {
            "medicines": fallback_medicines,
            "general_advice": [],
            "extraction_source": "fallback",
            "note": f"Gemini error: {str(e)}. Using fallback."
        }


def parse_prescription(text):
    """
    Parse prescription text - use intelligent extraction for voice transcripts
    """
    # First try intelligent extraction with Gemini
    extraction_result = extract_prescription_with_gemini(text)
    medicines = extraction_result.get("medicines", [])
    
    # If no medicines found, try fallback
    if not medicines:
        medicines = extract_medicines_from_voice_transcript(text)
    
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
    """
    Generate professional prescription PDF matching reference design.
    Features:
    - Clean clinic header with centered alignment
    - Two-column patient/doctor info layout
    - Professional medicine table with proper spacing
    - Separate food/special instructions (not mixed in medicine names)
    - Digital signature and QR code
    - Professional footer
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(15, 10, 15)

    # Extract data
    clinic_name = str(data.get('clinic') or data.get('clinic_name') or 'SHRI XYZ CLINIC')
    clinic_tagline = str(data.get('clinic_tagline') or 'HEALTH IS WEALTH')
    clinic_address = str(data.get('address') or 'xyzabc')
    clinic_phone = str(data.get('phone') or data.get('clinic_phone') or '+91 **********')
    clinic_email = str(data.get('email') or 'xyz@gmail.com')
    
    patient_name = str(data.get('name') or data.get('patient_name') or 'Patient')
    patient_mobile = str(data.get('phone_number') or data.get('mobile_number') or '')
    patient_age = str(data.get('age') or 'Not set')
    patient_gender = str(data.get('gender') or 'Not set')
    patient_id = str(data.get('patient_id') or '')
    
    doctor_name = str(data.get('doctor_name') or data.get('doctor') or 'Dr. XYZ')
    if doctor_name and not doctor_name.lower().startswith('dr'):
        doctor_name = f'Dr. {doctor_name}'
    visit_id = str(data.get('visit_id') or '')
    
    today = datetime.now(doctor_db.INDIA_TIMEZONE).strftime('%d/%m/%Y')

    # ═══════════════════════════════════════════════════════════════
    # CLINIC HEADER (Centered)
    # ═══════════════════════════════════════════════════════════════
    pdf.set_font('Arial', 'B', 16)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 8, clinic_name.upper(), 0, 1, 'C')
    
    pdf.set_font('Arial', '', 9)
    pdf.cell(0, 5, clinic_tagline.upper(), 0, 1, 'C')
    
    pdf.set_font('Arial', '', 8)
    pdf.cell(0, 4, clinic_address, 0, 1, 'C')
    pdf.cell(0, 4, f"Phone: {clinic_phone} | Email: {clinic_email}", 0, 1, 'C')
    
    pdf.ln(3)

    # ═══════════════════════════════════════════════════════════════
    # PRESCRIPTION HEADING WITH DATE
    # ═══════════════════════════════════════════════════════════════
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 7, 'PRESCRIPTION', 0, 1, 'C')
    
    # Date on the right side
    pdf.set_font('Arial', '', 9)
    pdf.set_xy(pdf.w - 55, pdf.get_y() - 7)
    pdf.cell(40, 7, f'Date: {today}', 0, 0, 'R')
    
    pdf.ln(10)

    # ═══════════════════════════════════════════════════════════════
    # PATIENT & DOCTOR INFO (Two Columns)
    # ═══════════════════════════════════════════════════════════════
    info_start_y = pdf.get_y()
    left_col_x = 15
    right_col_x = 105
    line_height = 6
    
    # LEFT COLUMN: Patient Info
    pdf.set_xy(left_col_x, info_start_y)
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(35, line_height, 'Patient Name:', 0, 0)
    pdf.set_font('Arial', '', 9)
    pdf.cell(55, line_height, patient_name, 0, 1)
    
    pdf.set_x(left_col_x)
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(35, line_height, 'Mobile No:', 0, 0)
    pdf.set_font('Arial', '', 9)
    pdf.cell(55, line_height, patient_mobile, 0, 1)
    
    pdf.set_x(left_col_x)
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(35, line_height, 'Age:', 0, 0)
    pdf.set_font('Arial', '', 9)
    pdf.cell(55, line_height, patient_age, 0, 1)
    
    pdf.set_x(left_col_x)
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(35, line_height, 'Gender:', 0, 0)
    pdf.set_font('Arial', '', 9)
    pdf.cell(55, line_height, patient_gender, 0, 1)
    
    # RIGHT COLUMN: Doctor Info
    pdf.set_xy(right_col_x, info_start_y)
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(35, line_height, 'Doctor Name:', 0, 0)
    pdf.set_font('Arial', '', 9)
    pdf.cell(55, line_height, doctor_name, 0, 1)
    
    pdf.set_xy(right_col_x, info_start_y + line_height)
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(35, line_height, 'Clinic:', 0, 0)
    pdf.set_font('Arial', '', 9)
    pdf.cell(55, line_height, clinic_name, 0, 1)
    
    pdf.set_xy(right_col_x, info_start_y + line_height * 2)
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(35, line_height, 'Visit ID:', 0, 0)
    pdf.set_font('Arial', '', 9)
    pdf.cell(55, line_height, visit_id, 0, 1)
    
    if patient_id:
        pdf.set_xy(right_col_x, info_start_y + line_height * 3)
        pdf.set_font('Arial', 'B', 9)
        pdf.cell(35, line_height, 'Patient ID:', 0, 0)
        pdf.set_font('Arial', '', 9)
        pdf.cell(55, line_height, patient_id, 0, 1)
    
    pdf.ln(8)

    # ═══════════════════════════════════════════════════════════════
    # MEDICINE TABLE
    # ═══════════════════════════════════════════════════════════════
    table_start_y = pdf.get_y()
    
    # Table column widths: Medicine Name | Dosage | Dose M-A-E-B | Duration
    col_widths = [55, 28, 45, 32]  # Adjusted for new column structure
    total_width = sum(col_widths)
    
    # Table header
    pdf.set_font('Arial', 'B', 9)
    pdf.set_fill_color(205, 220, 235)  # Light blue header
    pdf.set_text_color(0, 0, 0)
    
    headers = ['Medicine Name', 'Dosage', 'Dose M-A-E-B', 'Duration']
    for i, header in enumerate(headers):
        pdf.cell(col_widths[i], 8, header, 1, 0, 'C', True)
    pdf.ln()
    
    # Table rows
    pdf.set_font('Arial', '', 8)
    pdf.set_fill_color(255, 255, 255)
    
    medicines = data.get('medicines', [])
    for med in medicines:
        name = str(med.get('name') or 'Medicine name missing')
        dosage = str(med.get('dosage') or 'Dose not specified')
        duration = str(med.get('duration') or 'As directed')
        
        # Build M-A-E-B (Morning-Afternoon-Evening-Bedtime) dose string
        timing = med.get('timing', [])
        if isinstance(timing, list):
            # Convert timing list to M-A-E-B format
            m = '1' if 'Morning' in timing else '0'
            a = '1' if 'Afternoon' in timing else '0'
            e = '1' if 'Evening' in timing else '0'
            b = '1' if 'Bedtime' in timing else '0'
            dose_maeb = f"{m}-{a}-{e}-{b}"
        else:
            dose_maeb = '0-0-0-0'
        
        # Truncate if too long
        if len(name) > 32:
            name = name[:29] + '...'
        if len(dosage) > 16:
            dosage = dosage[:13] + '...'
        if len(duration) > 18:
            duration = duration[:15] + '...'
        
        # Medicine row: Medicine Name | Dosage | Dose M-A-E-B | Duration
        pdf.cell(col_widths[0], 7, name, 1, 0, 'L')
        pdf.cell(col_widths[1], 7, dosage, 1, 0, 'C')
        pdf.cell(col_widths[2], 7, dose_maeb, 1, 0, 'C')
        pdf.cell(col_widths[3], 7, duration, 1, 0, 'C')
        pdf.ln()
        
        # Food & special instructions (if present) - compact format
        instructions_parts = []
        
        food_instruction = str(med.get('food_instruction') or '').strip()
        if food_instruction and food_instruction.lower() not in ['', 'none']:
            instructions_parts.append(f"Food: {food_instruction}")
        
        timing_values = med.get('timing', [])
        if isinstance(timing_values, list) and timing_values:
            instructions_parts.append(f"Timing: {', '.join(timing_values)}")
        
        special_instructions = str(med.get('special_instructions') or med.get('instructions') or '').strip()
        if special_instructions and special_instructions.lower() not in ['', 'none', 'no additional instructions']:
            instructions_parts.append(f"Note: {special_instructions}")
        
        if instructions_parts:
            instruction_text = ' | '.join(instructions_parts)
            # Truncate if too long
            if len(instruction_text) > 90:
                instruction_text = instruction_text[:87] + '...'
            
            pdf.set_font('Arial', 'I', 7)
            pdf.set_fill_color(240, 245, 250)
            pdf.cell(total_width, 5, instruction_text, 1, 1, 'L', True)
            pdf.set_font('Arial', '', 8)
            pdf.set_fill_color(255, 255, 255)
    
    pdf.ln(8)

    # ═══════════════════════════════════════════════════════════════
    # DIGITAL SIGNATURE & QR CODE
    # ═══════════════════════════════════════════════════════════════
    signature_y = pdf.get_y()
    
    # Ensure enough space for signature section
    if signature_y > 240:
        pdf.add_page()
        signature_y = pdf.get_y()
    
    # LEFT: Digital Signature
    pdf.set_xy(15, signature_y)
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(70, 6, "Doctor's signature:", 0, 1)
    
    # Signature box
    pdf.set_xy(15, pdf.get_y())
    pdf.rect(15, pdf.get_y(), 70, 25)
    
    pdf.set_xy(20, pdf.get_y() + 3)
    pdf.set_font('Arial', '', 8)
    pdf.cell(60, 5, 'Digitally Signed', 0, 1)
    pdf.set_x(20)
    pdf.cell(60, 5, doctor_name, 0, 1)
    pdf.set_x(20)
    pdf.cell(60, 5, today, 0, 1)
    
    # RIGHT: QR Code
    qr = qrcode.QRCode(
        version=2,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=4,
        border=2
    )
    qr.add_data(download_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color='black', back_color='white')
    qr_path = os.path.join(GENERATED_FOLDER, f'qr_{uuid.uuid4().hex[:8]}.png')
    qr_img.save(qr_path)
    
    qr_x = 145
    qr_y = signature_y
    
    pdf.set_xy(qr_x, qr_y)
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(40, 6, 'Scan to Download', 0, 1, 'C')
    
    pdf.image(qr_path, x=qr_x, y=qr_y + 8, w=40, h=40)
    
    # ═══════════════════════════════════════════════════════════════
    # FOOTER
    # ═══════════════════════════════════════════════════════════════
    pdf.set_y(-20)
    pdf.set_font('Arial', 'I', 7)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 5, 'This is a system-generated prescription. Valid with digital signature.', 0, 0, 'C')
    
    pdf.output(filepath)



@app.route('/extract-prescription', methods=['POST'])
@role_required("doctor", api=True)
def extract_prescription():
    """
    Extract structured medicine data from free-form prescription text using intelligent NLP.
    This endpoint uses Gemini AI to understand natural doctor speech and convert it to structured data.
    """
    try:
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "Request must be JSON object."}), 400
        
        prescription_text = payload.get("text", "").strip()
        if not prescription_text:
            return jsonify({"error": "Prescription text is required."}), 400
        
        # Use intelligent extraction
        result = extract_prescription_with_gemini(prescription_text)
        
        return jsonify({
            "success": True,
            "medicines": result.get("medicines", []),
            "general_advice": result.get("general_advice", []),
            "extraction_source": result.get("extraction_source", "unknown"),
            "note": result.get("note", "")
        })
        
    except Exception as e:
        logger.exception("Prescription extraction failed")
        return jsonify({
            "error": f"Extraction failed: {str(e)}"
        }), 500


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
        
        # Generate QR code URL for patient access (public, no authentication required)
        # QR code should point to /prescription/<visit_id> for direct PDF viewing
        base_url = os.getenv("APPLICATION_BASE_URL", "").strip()
        if base_url:
            # Use configured base URL (for network access or production)
            # Remove trailing slash
            base_url = base_url.rstrip('/')
            # Use public prescription route for QR code
            qr_code_url = f"{base_url}/prescription/{visit_id}"
        else:
            # Use Flask's url_for (auto-detects from request)
            qr_code_url = url_for(
                "view_prescription_by_visit_id",
                visit_id=visit_id,
                _external=True,
            )

        try:
            # Generate PDF with QR code pointing to public prescription view
            generate_prescription_pdf(data, qr_code_url, filepath)
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

        # ── Send WhatsApp with PDF ───────────────────────────────────────────
        # Automatically send prescription PDF via WhatsApp immediately after generation
        try:
            from sms import send_whatsapp_with_pdf
            
            if data.get("name") and data.get("phone_number"):
                # Use the public prescription URL for WhatsApp PDF attachment
                # Note: For Twilio to download the PDF, this URL must be publicly accessible
                # For development: Use ngrok to expose local server
                # For production: Use cloud storage URL (S3, Cloudinary, etc.)
                
                whatsapp_result = send_whatsapp_with_pdf(
                    patient_name=data["name"],
                    phone_number=data["phone_number"],
                    pdf_url=qr_code_url  # Public prescription URL
                )
                
                if whatsapp_result:
                    logger.info(f"WhatsApp sent successfully to {data.get('phone_number')}, SID: {whatsapp_result}")
                else:
                    logger.warning(f"WhatsApp send failed for {data.get('phone_number')}")
                    
        except Exception as e:
            logger.error(f"WhatsApp send failed: {e}")
            logger.exception("Full WhatsApp error trace:")

        # Generate authenticated download URL for doctor dashboard
        doctor_download_url = url_for(
            "download_patient_visit_pdf",
            patient_id=patient_id,
            visit_id=visit_id,
            _external=False
        )

        return jsonify({
            "success":            True,
            "download_url":       doctor_download_url,  # For doctor to download
            "public_url":         qr_code_url,          # Public URL embedded in QR code
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
    """Doctor-authenticated route for downloading prescription PDFs."""
    visit = doctor_db.get_patient_visit(patient_id, visit_id)
    if not visit:
        return jsonify({"error": "Visit not found for this patient."}), 404
    filename = visit["pdf_path"]
    if not filename or os.path.basename(filename) != filename:
        return jsonify({"error": "Prescription PDF is unavailable."}), 404
    return send_from_directory(GENERATED_FOLDER, filename, as_attachment=True)


@app.route("/prescription/<visit_id>", methods=["GET"])
def view_prescription_by_visit_id(visit_id):
    """
    Public route for patients to view their prescription via QR code.
    Retrieves prescription using only Visit ID (no authentication required).
    Opens PDF inline in browser for immediate viewing.
    """
    try:
        # Validate visit_id format (basic security check)
        if not visit_id or not isinstance(visit_id, str):
            return jsonify({"error": "Invalid visit ID."}), 400
        
        # Get visit by visit_id only (without patient_id requirement)
        visit = doctor_db.get_visit_by_id(visit_id)
        
        if not visit:
            return render_template('prescription_not_found.html', visit_id=visit_id), 404
        
        # Get PDF filename
        filename = visit.get("pdf_path")
        if not filename:
            return jsonify({"error": "Prescription PDF not found."}), 404
        
        # Security: Ensure filename is safe (no path traversal)
        filename = os.path.basename(filename)
        filepath = os.path.join(GENERATED_FOLDER, filename)
        
        if not os.path.exists(filepath):
            return jsonify({"error": "Prescription PDF file does not exist."}), 404
        
        # Return PDF with inline display (opens in browser, not download)
        return send_from_directory(
            GENERATED_FOLDER,
            filename,
            mimetype='application/pdf',
            as_attachment=False  # Display inline in browser
        )
        
    except Exception as e:
        logger.error(f"Error viewing prescription for visit {visit_id}: {e}")
        return jsonify({"error": "Failed to retrieve prescription."}), 500


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
        quantity = int(data.get('quantity', 0))

        if quantity < 0:
            return jsonify({"error": "quantity cannot be negative"}), 400

        updated = update_medicine(medicine_id, {
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
        # ==================== INVENTORY ALERT API ====================

@app.route('/medicines/expiring', methods=['GET'])
@role_required("medical_staff", api=True)
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
    debug_mode = os.getenv("FLASK_DEBUG", "TRUE").lower() == "true"
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", "5000"))
    
    app.run(debug=debug_mode, host=host, port=port)