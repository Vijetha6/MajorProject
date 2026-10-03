import sqlite3
from datetime import date, timedelta

import database


def test_expiry_filters_for_today_and_future(tmp_path, monkeypatch):
    db_path = tmp_path / "medicine_inventory.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE medicines (
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
        """
    )

    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    in_10_days = (date.today() + timedelta(days=10)).isoformat()

    conn.executemany(
        """
        INSERT INTO medicines (
            medicine_name, brand_name, generic_name, strength, dosage_form,
            expiry_date, quantity, row_number, column_number
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("Expired today", "Brand A", "Generic A", "10mg", "Tablet", today, 5, 1, 1),
            ("Expiring soon", "Brand B", "Generic B", "20mg", "Capsule", tomorrow, 3, 1, 2),
            ("Later expiry", "Brand C", "Generic C", "30mg", "Syrup", in_10_days, 4, 1, 3),
        ],
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(database, "DATABASE", db_path)

    expired = [item["medicine_name"] for item in database.get_expired_medicines()]
    expiring = [item["medicine_name"] for item in database.get_expiring_medicines(30)]

    assert expired == ["Expired today"]
    assert expiring == ["Expiring soon", "Later expiry"]
