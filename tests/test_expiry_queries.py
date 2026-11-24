import sqlite3
from datetime import date

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

    today = date(2027, 8, 1)
    monkeypatch.setattr(database, "_india_today", lambda: today)

    conn.executemany(
        """
        INSERT INTO medicines (
            medicine_name, brand_name, generic_name, strength, dosage_form,
            expiry_date, quantity, row_number, column_number
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("Expired yesterday", "Brand A", "Generic A", "10mg", "Tablet", "2027-07-31", 5, 1, 1),
            ("Expires today", "Brand B", "Generic B", "20mg", "Capsule", "2027-08-01", 3, 1, 2),
            ("Expires in 30 days", "Brand C", "Generic C", "30mg", "Syrup", "2027-08-31", 4, 1, 3),
            ("Expires in 31 days", "Brand D", "Generic D", "40mg", "Tablet", "2027-09-01", 20, 1, 4),
        ],
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(database, "DATABASE", db_path)

    expired = [item["medicine_name"] for item in database.get_expired_medicines()]
    expiring = [item["medicine_name"] for item in database.get_expiring_medicines(30)]
    expiring_today = [
        item["medicine_name"] for item in database.get_expiring_medicines(0)
    ]
    low_stock = [
        item["medicine_name"]
        for item in database.get_low_stock_medicines(threshold=10)
    ]

    assert expired == ["Expired yesterday"]
    assert expiring == ["Expires today", "Expires in 30 days"]
    assert expiring_today == ["Expires today"]
    assert low_stock == [
        "Expires today",
        "Expires in 30 days",
        "Expired yesterday",
    ]


def test_seven_day_expiry_window_reports_remaining_days(tmp_path, monkeypatch):
    db_path = tmp_path / "medicine_inventory.db"
    monkeypatch.setattr(database, "DATABASE", db_path)
    monkeypatch.setattr(database, "_india_today", lambda: date(2027, 8, 1))
    database.init_database()

    expiry_dates = {
        "Expired yesterday": "2027-07-31",
        "Expires today": "2027-08-01",
        "Expires tomorrow": "2027-08-02",
        "Expires in 2 days": "2027-08-03",
        "Expires in 7 days": "2027-08-08",
        "Expires in 8 days": "2027-08-09",
    }
    for medicine_name, expiry_date in expiry_dates.items():
        database.add_medicine({
            "medicine_name": medicine_name,
            "expiry_date": expiry_date,
        })

    upcoming = database.get_expiring_medicines(7)
    remaining_days = {
        medicine["medicine_name"]: medicine["days_remaining"]
        for medicine in upcoming
    }

    assert remaining_days == {
        "Expires today": 0,
        "Expires tomorrow": 1,
        "Expires in 2 days": 2,
        "Expires in 7 days": 7,
    }
    expired = database.get_expired_medicines()
    assert [medicine["medicine_name"] for medicine in expired] == ["Expired yesterday"]
    assert expired[0]["days_remaining"] == -1
