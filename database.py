import sqlite3
from pathlib import Path

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
        "SELECT * FROM medicines ORDER BY medicine_name"
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
        WHERE date(expiry_date) <= date('now', '+' || ? || ' days')
        AND date(expiry_date) >= date('now')
        ORDER BY expiry_date
    """, (days,)).fetchall()

    conn.close()

    return [dict(medicine) for medicine in medicines]


# ==================== EXPIRED MEDICINES ====================

def get_expired_medicines():
    conn = get_connection()

    medicines = conn.execute("""
        SELECT * FROM medicines
        WHERE date(expiry_date) < date('now')
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


# ==================== INITIALIZE DATABASE ====================

if __name__ == "__main__":
    init_database()
    print("Medicine inventory database initialized successfully.")