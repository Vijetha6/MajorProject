import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


DATABASE = Path(__file__).parent / "doctor_records.db"
INDIA_TIMEZONE = timezone(timedelta(hours=5, minutes=30))


class DuplicatePatientError(ValueError):
    def __init__(self, patients):
        super().__init__("A patient with this name and mobile number already exists.")
        self.patients = patients


def get_connection():
    connection = sqlite3.connect(DATABASE, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_database():
    connection = get_connection()
    try:
        with connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS patients (
                    patient_id TEXT PRIMARY KEY,
                    patient_name TEXT NOT NULL,
                    age INTEGER NOT NULL,
                    gender TEXT NOT NULL,
                    mobile_number TEXT NOT NULL,
                    address TEXT,
                    created_by_doctor_id TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_patients_mobile
                    ON patients(mobile_number);

                CREATE INDEX IF NOT EXISTS idx_patients_name_mobile
                    ON patients(patient_name COLLATE NOCASE, mobile_number);

                CREATE TABLE IF NOT EXISTS visits (
                    visit_id TEXT PRIMARY KEY,
                    patient_id TEXT NOT NULL,
                    doctor_id TEXT NOT NULL,
                    visit_date TEXT NOT NULL,
                    diagnosis TEXT,
                    notes TEXT,
                    pdf_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
                        ON UPDATE RESTRICT ON DELETE RESTRICT
                );

                CREATE INDEX IF NOT EXISTS idx_visits_patient_date
                    ON visits(patient_id, visit_date DESC, created_at DESC);

                CREATE TABLE IF NOT EXISTS visit_medicines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    visit_id TEXT NOT NULL,
                    medicine_name TEXT NOT NULL,
                    dosage TEXT NOT NULL,
                    frequency TEXT,
                    duration TEXT,
                    instructions TEXT,
                    timing TEXT NOT NULL DEFAULT '[]',
                    food_instruction TEXT,
                    special_instructions TEXT,
                    FOREIGN KEY (visit_id) REFERENCES visits(visit_id)
                        ON UPDATE RESTRICT ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_visit_medicines_visit
                    ON visit_medicines(visit_id, id);
            """)
    finally:
        connection.close()


def normalize_mobile_number(value):
    if not isinstance(value, str):
        raise ValueError("Mobile number is required.")

    compact = "".join(value.strip().split()).replace("-", "")
    if compact.startswith("+91"):
        compact = compact[3:]
    elif compact.startswith("91") and len(compact) == 12:
        compact = compact[2:]

    if len(compact) != 10 or not compact.isdigit():
        raise ValueError("Enter a valid 10-digit mobile number.")
    return compact


def _now_india():
    return datetime.now(INDIA_TIMEZONE)


def _patient_dict(row):
    return dict(row) if row else None


def register_patient(patient_name, age, gender, mobile_number, address, doctor_id):
    patient_id = f"PT-{uuid.uuid4().hex[:12].upper()}"
    now = _now_india().isoformat(timespec="microseconds")
    connection = get_connection()
    try:
        with connection:
            matches = connection.execute(
                """
                SELECT * FROM patients
                WHERE patient_name = ? COLLATE NOCASE AND mobile_number = ?
                ORDER BY created_at DESC, patient_id
                """,
                (patient_name.strip(), mobile_number),
            ).fetchall()
            if matches:
                raise DuplicatePatientError([dict(row) for row in matches])

            connection.execute(
                """
                INSERT INTO patients (
                    patient_id, patient_name, age, gender, mobile_number,
                    address, created_by_doctor_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    patient_id,
                    patient_name.strip(),
                    age,
                    gender.strip(),
                    mobile_number,
                    address.strip() if address else "",
                    doctor_id,
                    now,
                ),
            )
            patient = connection.execute(
                "SELECT * FROM patients WHERE patient_id = ?",
                (patient_id,),
            ).fetchone()
            return _patient_dict(patient)
    finally:
        connection.close()


def get_patient(patient_id):
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT * FROM patients WHERE patient_id = ?",
            (patient_id,),
        ).fetchone()
        return _patient_dict(row)
    finally:
        connection.close()


def update_patient_mobile(patient_id, mobile_number):
    connection = get_connection()
    try:
        with connection:
            cursor = connection.execute(
                "UPDATE patients SET mobile_number = ? WHERE patient_id = ?",
                (mobile_number, patient_id),
            )
            return cursor.rowcount > 0
    finally:
        connection.close()


def search_patients(patient_id=None, mobile_number=None):
    if patient_id:
        patient = get_patient(patient_id.strip())
        return [patient] if patient else []
    if mobile_number:
        normalized_mobile = normalize_mobile_number(mobile_number)
        connection = get_connection()
        try:
            rows = connection.execute(
                """
                SELECT * FROM patients
                WHERE mobile_number = ?
                ORDER BY patient_name COLLATE NOCASE, created_at DESC
                """,
                (normalized_mobile,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            connection.close()
    raise ValueError("Search by Patient ID or mobile number.")


def get_patient_history(patient_id):
    connection = get_connection()
    try:
        visits = connection.execute(
            """
            SELECT visit_id, patient_id, doctor_id, visit_date, diagnosis,
                   notes, pdf_path, created_at
            FROM visits
            WHERE patient_id = ?
            ORDER BY visit_date DESC, created_at DESC, visit_id DESC
            """,
            (patient_id,),
        ).fetchall()
        results = []
        for visit_row in visits:
            visit = dict(visit_row)
            medicines = connection.execute(
                """
                SELECT id, medicine_name, dosage, frequency, duration,
                       instructions, timing, food_instruction,
                       special_instructions
                FROM visit_medicines
                WHERE visit_id = ?
                ORDER BY id
                """,
                (visit["visit_id"],),
            ).fetchall()
            for medicine in medicines:
                medicine_data = dict(medicine)
                medicine_data["timing"] = json.loads(medicine_data["timing"] or "[]")
                visit.setdefault("medicines", []).append(medicine_data)
            visit.setdefault("medicines", [])
            results.append(visit)
        return results
    finally:
        connection.close()


def get_patient_visit(patient_id, visit_id):
    connection = get_connection()
    try:
        visit = connection.execute(
            """
            SELECT visit_id, patient_id, doctor_id, visit_date, diagnosis,
                   notes, pdf_path, created_at
            FROM visits
            WHERE patient_id = ? AND visit_id = ?
            """,
            (patient_id, visit_id),
        ).fetchone()
        if not visit:
            return None

        result = dict(visit)
        medicines = connection.execute(
            """
            SELECT id, medicine_name, dosage, frequency, duration,
                   instructions, timing, food_instruction,
                   special_instructions
            FROM visit_medicines
            WHERE visit_id = ?
            ORDER BY id
            """,
            (visit_id,),
        ).fetchall()
        result["medicines"] = []
        for medicine in medicines:
            medicine_data = dict(medicine)
            medicine_data["timing"] = json.loads(medicine_data["timing"] or "[]")
            result["medicines"].append(medicine_data)
        return result
    finally:
        connection.close()


def get_visit_by_id(visit_id):
    """
    Get visit information by visit_id only (for public prescription access).
    Used by QR code scanning - does not require patient_id or authentication.
    """
    connection = get_connection()
    try:
        visit = connection.execute(
            """
            SELECT visit_id, patient_id, doctor_id, visit_date, diagnosis,
                   notes, pdf_path, created_at
            FROM visits
            WHERE visit_id = ?
            """,
            (visit_id,),
        ).fetchone()
        if not visit:
            return None

        result = dict(visit)
        medicines = connection.execute(
            """
            SELECT id, medicine_name, dosage, frequency, duration,
                   instructions, timing, food_instruction,
                   special_instructions
            FROM visit_medicines
            WHERE visit_id = ?
            ORDER BY id
            """,
            (visit_id,),
        ).fetchall()
        result["medicines"] = []
        for medicine in medicines:
            medicine_data = dict(medicine)
            medicine_data["timing"] = json.loads(medicine_data["timing"] or "[]")
            result["medicines"].append(medicine_data)
        return result
    finally:
        connection.close()


def save_visit(
    patient_id,
    doctor_id,
    diagnosis,
    notes,
    pdf_path,
    medicines,
    visit_id=None,
):
    now = _now_india()
    visit_id = visit_id or f"VIS-{uuid.uuid4().hex[:16].upper()}"
    connection = get_connection()
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO visits (
                    visit_id, patient_id, doctor_id, visit_date, diagnosis,
                    notes, pdf_path, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    visit_id,
                    patient_id,
                    doctor_id,
                    now.date().isoformat(),
                    diagnosis.strip() if diagnosis else "",
                    notes.strip() if notes else "",
                    pdf_path,
                    now.isoformat(timespec="microseconds"),
                ),
            )
            connection.executemany(
                """
                INSERT INTO visit_medicines (
                    visit_id, medicine_name, dosage, frequency, duration,
                    instructions, timing, food_instruction,
                    special_instructions
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        visit_id,
                        medicine["name"],
                        medicine["dosage"],
                        medicine.get("frequency", ""),
                        medicine.get("duration", ""),
                        medicine.get("instructions", ""),
                        json.dumps(medicine.get("timing", [])),
                        medicine.get("food_instruction", ""),
                        medicine.get("special_instructions", ""),
                    )
                    for medicine in medicines
                ],
            )
        return visit_id
    finally:
        connection.close()
