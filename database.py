import calendar
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

DATABASE = Path(__file__).parent / "medicine_inventory.db"
INDIA_TIMEZONE = timezone(timedelta(hours=5, minutes=30))
MONTH_NAMES = {
    name.casefold(): month
    for month in range(1, 13)
    for name in (calendar.month_abbr[month], calendar.month_name[month])
}


def normalize_expiry(value):
    """Return a supported medicine expiry date in canonical YYYY-MM-DD form."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Expiry date is required.")

    value = value.strip()

    iso_full_date = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", value)
    if iso_full_date:
        try:
            return date(*(int(part) for part in iso_full_date.groups())).isoformat()
        except ValueError as error:
            raise ValueError(
                "Invalid expiry date; expected a valid calendar date in YYYY-MM-DD format."
            ) from error

    iso_month = re.fullmatch(r"(\d{4})-(\d{1,2})", value)
    if iso_month:
        year, month = (int(part) for part in iso_month.groups())
        return _month_end_date(year, month)

    slash_month = re.fullmatch(r"(\d{1,2})/(\d{4})", value)
    if slash_month:
        month, year = (int(part) for part in slash_month.groups())
        return _month_end_date(year, month)

    day_first_date = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", value)
    if day_first_date:
        day, month, year = (int(part) for part in day_first_date.groups())
        try:
            return date(year, month, day).isoformat()
        except ValueError as error:
            raise ValueError(
                "Invalid expiry date; DD/MM/YYYY must be a valid calendar date."
            ) from error

    named_month = re.fullmatch(r"([A-Za-z]{3,9})\.?[\s-]+(\d{4})", value)
    if named_month:
        month_name, year_text = named_month.groups()
        month = MONTH_NAMES.get(month_name.casefold())
        if month is None:
            raise ValueError(f"Unrecognized expiry month: {month_name}.")
        return _month_end_date(int(year_text), month)

    raise ValueError(
        "Unrecognized expiry date. Use MM/YYYY, MON YYYY, YYYY-MM, "
        "YYYY-MM-DD, or DD/MM/YYYY."
    )


def _month_end_date(year, month):
    if not 1 <= month <= 12:
        raise ValueError("Expiry month must be between 1 and 12.")
    if not 1 <= year <= 9999:
        raise ValueError("Expiry year must be between 0001 and 9999.")
    return date(year, month, calendar.monthrange(year, month)[1]).isoformat()


def _india_today():
    return datetime.now(INDIA_TIMEZONE).date()


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
    expiry_date = normalize_expiry(data.get("expiry_date"))
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
        expiry_date,
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
    expiry_date = normalize_expiry(data.get("expiry_date"))
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
        expiry_date,
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
    if not isinstance(days, int) or isinstance(days, bool) or days < 0:
        raise ValueError("days must be a non-negative integer.")

    today = _india_today()
    last_included_day = today + timedelta(days=days)
    conn = get_connection()

    medicines = conn.execute("""
        SELECT *,
               CAST(julianday(date(expiry_date)) - julianday(date(?)) AS INTEGER)
                   AS days_remaining
        FROM medicines
        WHERE date(expiry_date) >= date(?)
        AND date(expiry_date) <= date(?)
        ORDER BY expiry_date
    """, (
        today.isoformat(),
        today.isoformat(),
        last_included_day.isoformat(),
    )).fetchall()

    conn.close()

    return [dict(medicine) for medicine in medicines]


# ==================== EXPIRED MEDICINES ====================

def get_expired_medicines():
    today = _india_today()
    conn = get_connection()

    medicines = conn.execute(
        "SELECT * FROM medicines"
    ).fetchall()

    conn.close()

    expired_medicines = []
    for row in medicines:
        medicine = dict(row)
        try:
            normalized_expiry = normalize_expiry(medicine.get("expiry_date"))
            expiry_date = date.fromisoformat(normalized_expiry)
        except ValueError:
            continue

        days_remaining = (expiry_date - today).days
        if days_remaining < 0:
            medicine["days_remaining"] = days_remaining
            expired_medicines.append((expiry_date, medicine))

    expired_medicines.sort(key=lambda item: item[0])
    return [medicine for _, medicine in expired_medicines]


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


# ==================== INITIALIZE DATABASE ====================

if __name__ == "__main__":
    init_database()
    print("Medicine inventory database initialized successfully.")