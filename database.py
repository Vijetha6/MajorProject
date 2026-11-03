import sqlite3
import json
import uuid
from pathlib import Path
from datetime import datetime

DATABASE = Path(__file__).parent / "medicine_inventory.db"


# ==================== DATABASE CONNECTION ====================

def get_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


# ==================== CREATE DATABASE ====================

def init_database():
    conn = get_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS medicines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            medicine_name TEXT NOT NULL,
            brand_name TEXT,
            generic_name TEXT,
            strength TEXT,
            dosage_form TEXT,
            expiry_date TEXT NOT NULL,
            quantity INTEGER DEFAULT 0,
            row_number INTEGER,
            column_number INTEGER
        )
    """)

    conn.commit()
    conn.close()


# ==================== ADD MEDICINE ====================

def add_medicine(data):
    conn = get_connection()

    cursor = conn.execute("""
        INSERT INTO medicines (
            medicine_name,
            brand_name,
            generic_name,
            strength,
            dosage_form,
            expiry_date,
            quantity,
            row_number,
            column_number
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data["medicine_name"],
        data.get("brand_name"),
        data.get("generic_name"),
        data.get("strength"),
        data.get("dosage_form"),
        data["expiry_date"],
        data.get("quantity", 0),
        data.get("row_number"),
        data.get("column_number")
    ))

    conn.commit()
    medicine_id = cursor.lastrowid
    conn.close()

    return medicine_id


# ==================== GET ALL MEDICINES ====================

def get_all_medicines():
    conn = get_connection()

    medicines = conn.execute(
        "SELECT * FROM medicines ORDER BY medicine_name COLLATE NOCASE ASC, id ASC"
    ).fetchall()

    conn.close()

    return [dict(medicine) for medicine in medicines]


# ==================== GET SINGLE MEDICINE ====================

def get_medicine(medicine_id):
    conn = get_connection()

    medicine = conn.execute(
        "SELECT * FROM medicines WHERE id = ?",
        (medicine_id,)
    ).fetchone()

    conn.close()

    return dict(medicine) if medicine else None


# ==================== SEARCH MEDICINES ====================

def search_medicines(search_text):
    conn = get_connection()

    medicines = conn.execute("""
        SELECT * FROM medicines
        WHERE medicine_name LIKE ?
           OR brand_name LIKE ?
           OR generic_name LIKE ?
    """, (
        f"%{search_text}%",
        f"%{search_text}%",
        f"%{search_text}%"
    )).fetchall()

    conn.close()

    return [dict(medicine) for medicine in medicines]


# ==================== UPDATE MEDICINE ====================

def update_medicine(medicine_id, data):
    conn = get_connection()

    conn.execute("""
        UPDATE medicines
        SET medicine_name = ?,
            brand_name = ?,
            generic_name = ?,
            strength = ?,
            dosage_form = ?,
            expiry_date = ?,
            quantity = ?,
            row_number = ?,
            column_number = ?
        WHERE id = ?
    """, (
        data["medicine_name"],
        data.get("brand_name"),
        data.get("generic_name"),
        data.get("strength"),
        data.get("dosage_form"),
        data["expiry_date"],
        data.get("quantity", 0),
        data.get("row_number"),
        data.get("column_number"),
        medicine_id
    ))

    conn.commit()
    changed = conn.total_changes
    conn.close()

    return changed > 0


# ==================== UPDATE QUANTITY ====================

def update_quantity(medicine_id, quantity):
    conn = get_connection()

    conn.execute("""
        UPDATE medicines
        SET quantity = ?
        WHERE id = ?
    """, (quantity, medicine_id))

    conn.commit()
    changed = conn.total_changes
    conn.close()

    return changed > 0


# ==================== DELETE MEDICINE ====================

def delete_medicine(medicine_id):
    conn = get_connection()

    conn.execute(
        "DELETE FROM medicines WHERE id = ?",
        (medicine_id,)
    )

    conn.commit()
    changed = conn.total_changes
    conn.close()

    return changed > 0


# ==================== EXPIRING MEDICINES ====================

def get_expiring_medicines(days=30):
    conn = get_connection()

    medicines = conn.execute("""
        SELECT * FROM medicines
        WHERE date(expiry_date) > date('now')
        AND date(expiry_date) <= date('now', '+' || ? || ' days')
        ORDER BY expiry_date
    """, (days,)).fetchall()

    conn.close()

    return [dict(medicine) for medicine in medicines]


# ==================== EXPIRED MEDICINES ====================

def get_expired_medicines():
    conn = get_connection()

    medicines = conn.execute("""
        SELECT * FROM medicines
        WHERE date(expiry_date) <= date('now')
        ORDER BY expiry_date
    """).fetchall()

    conn.close()

    return [dict(medicine) for medicine in medicines]


# ==================== LOW STOCK MEDICINES ====================

def get_low_stock_medicines(threshold=10):
    conn = get_connection()

    medicines = conn.execute("""
        SELECT * FROM medicines
        WHERE quantity <= ?
        ORDER BY quantity ASC
    """, (threshold,)).fetchall()

    conn.close()

    return [dict(medicine) for medicine in medicines]



# ==================== PRESCRIPTION HISTORY ====================

def init_prescription_database():
    conn = get_connection()

    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS prescriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_name TEXT NOT NULL,
                phone_number TEXT NOT NULL,
                age TEXT,
                gender TEXT,
                filename TEXT NOT NULL UNIQUE,
                download_token TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                doctor_name TEXT,
                clinic_name TEXT,
                prescription_json TEXT NOT NULL DEFAULT '{}',
                request_id TEXT,
                request_hash TEXT
            )
        """)

        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(prescriptions)")
        }
        migrations = {
            "doctor_name": "TEXT",
            "clinic_name": "TEXT",
            "prescription_json": "TEXT NOT NULL DEFAULT '{}'",
            "request_id": "TEXT",
            "request_hash": "TEXT",
        }
        for column, definition in migrations.items():
            if column not in columns:
                conn.execute(f"ALTER TABLE prescriptions ADD COLUMN {column} {definition}")

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_prescription_phone
            ON prescriptions(phone_number)
        """)
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_prescription_request_id
            ON prescriptions(request_id)
            WHERE request_id IS NOT NULL
        """)
        conn.commit()
    finally:
        conn.close()


def save_prescription(data):
    token = data.get("download_token") or uuid.uuid4().hex
    prescription_data = data.get("prescription_data") or {}
    conn = get_connection()
    try:
        cursor = conn.execute("""
            INSERT INTO prescriptions (
                patient_name, phone_number, age, gender, filename,
                download_token, created_at, doctor_name, clinic_name,
                prescription_json, request_id, request_hash
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["patient_name"],
            data["phone_number"],
            data.get("age", ""),
            data.get("gender", ""),
            data["filename"],
            token,
            datetime.now().isoformat(timespec="seconds"),
            data.get("doctor_name"),
            data.get("clinic_name"),
            json.dumps(prescription_data, ensure_ascii=False),
            data.get("request_id"),
            data.get("request_hash"),
        ))
        conn.commit()
        return cursor.lastrowid, token
    finally:
        conn.close()


def get_patient_prescriptions(phone_number):
    conn = get_connection()

    rows = conn.execute("""
        SELECT id, patient_name, age, gender, filename,
               download_token, created_at, doctor_name, clinic_name,
               prescription_json
        FROM prescriptions
        WHERE phone_number = ?
        ORDER BY created_at DESC
    """, (phone_number,)).fetchall()

    conn.close()
    return [dict(row) for row in rows]


def get_prescription_by_token(token):
    conn = get_connection()

    row = conn.execute("""
        SELECT id, patient_name, phone_number, age, gender,
               filename, download_token, created_at, doctor_name, clinic_name,
               prescription_json, request_id, request_hash
        FROM prescriptions
        WHERE download_token = ?
    """, (token,)).fetchone()

    conn.close()
    return dict(row) if row else None


def get_prescription_by_request_id(request_id):
    conn = get_connection()
    try:
        row = conn.execute("""
            SELECT id, patient_name, phone_number, age, gender, filename,
                   download_token, created_at, doctor_name, clinic_name,
                   prescription_json, request_id, request_hash
            FROM prescriptions
            WHERE request_id = ?
        """, (request_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ==================== INITIALIZE DATABASE ====================

if __name__ == "__main__":
    init_database()
    init_prescription_database()
    print("Medicine inventory database initialized successfully.")