"""Tests for the Sell Medicine / Sales History feature.

Every test uses a temporary database (pytest's tmp_path), never your real
medicine_inventory.db.
"""
import os
import sqlite3
from datetime import date, timedelta
from pathlib import Path

os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("ROBOFLOW_API_KEY", "")

import dotenv

dotenv.load_dotenv = lambda *args, **kwargs: False

import pytest

import database
import app as medicine_app
import backup_database

FUTURE = (date.today() + timedelta(days=400)).isoformat()
LATER = (date.today() + timedelta(days=800)).isoformat()
PAST = (date.today() - timedelta(days=400)).isoformat()


# ---------------------------------------------------------------- helpers

def use_temp_database(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DATABASE", tmp_path / "sales-test.db")
    database.init_database()


def add_batch(name="Paracetamol", expiry=FUTURE, quantity=100, strength="500 mg"):
    return database.add_medicine({
        "medicine_name": name,
        "strength": strength,
        "dosage_form": "Tablet",
        "expiry_date": expiry,
        "quantity": quantity,
    })


def stock(medicine_id):
    return database.get_medicine(medicine_id)["quantity"]


def sales_rows():
    conn = database.get_connection()
    rows = conn.execute("SELECT * FROM sales ORDER BY id").fetchall()
    conn.close()
    return rows


def make_client(monkeypatch, tmp_path, login_as=None):
    use_temp_database(monkeypatch, tmp_path)
    monkeypatch.setitem(
        medicine_app.app.config,
        "AUTH_USERS",
        {
            "doctor": {"user_id": "doctor-test", "password": "doctor-password"},
            "medical_staff": {"user_id": "staff-test", "password": "staff-password"},
        },
    )
    client = medicine_app.app.test_client()
    if login_as == "staff":
        client.post("/staff/login", data={"user_id": "staff-test", "password": "staff-password"})
    elif login_as == "doctor":
        client.post("/doctor/login", data={"user_id": "doctor-test", "password": "doctor-password"})
    return client


# ------------------------------------------------------- database: success

def test_successful_sale_reduces_stock_and_records_history(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    medicine_id = add_batch(quantity=100)

    result = database.sell_medicine(medicine_id, 5, sold_by="staff-test", request_id="r1")

    assert result["remaining_stock"] == 95
    assert result["quantity_sold"] == 5
    assert result["duplicate"] is False
    assert stock(medicine_id) == 95
    rows = sales_rows()
    assert len(rows) == 1
    assert rows[0]["medicine_name"] == "Paracetamol"
    assert rows[0]["quantity_sold"] == 5
    assert rows[0]["sold_by"] == "staff-test"
    assert rows[0]["sold_at"]


def test_selling_exact_remaining_stock_is_allowed(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    medicine_id = add_batch(quantity=7)

    result = database.sell_medicine(medicine_id, 7, request_id="exact")

    assert result["remaining_stock"] == 0
    assert stock(medicine_id) == 0


def test_insufficient_stock_is_refused_and_nothing_changes(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    medicine_id = add_batch(quantity=3)

    with pytest.raises(database.SaleError) as error:
        database.sell_medicine(medicine_id, 4, request_id="too-many")

    assert error.value.status == 409
    assert "Insufficient stock" in error.value.message
    assert stock(medicine_id) == 3
    assert sales_rows() == []


@pytest.mark.parametrize("bad_quantity", [0, -1, -50])
def test_zero_and_negative_quantities_are_refused(monkeypatch, tmp_path, bad_quantity):
    use_temp_database(monkeypatch, tmp_path)
    medicine_id = add_batch(quantity=10)

    with pytest.raises(database.SaleError):
        database.sell_medicine(medicine_id, bad_quantity)

    assert stock(medicine_id) == 10
    assert sales_rows() == []


@pytest.mark.parametrize("bad_quantity", [2.5, 2.0, "2.5", "abc", "", None, True, [1], "-3"])
def test_decimal_and_invalid_text_quantities_are_refused(monkeypatch, tmp_path, bad_quantity):
    use_temp_database(monkeypatch, tmp_path)
    medicine_id = add_batch(quantity=10)

    with pytest.raises(database.SaleError):
        database.sell_medicine(medicine_id, bad_quantity)

    assert stock(medicine_id) == 10
    assert sales_rows() == []


def test_unknown_medicine_is_refused(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)

    with pytest.raises(database.SaleError) as error:
        database.sell_medicine(9999, 1)

    assert error.value.status == 404
    assert sales_rows() == []


# ------------------------------------------------------ expiry and batches

def test_expired_batch_cannot_be_sold(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    medicine_id = add_batch(expiry=PAST, quantity=50)

    with pytest.raises(database.SaleError) as error:
        database.sell_medicine(medicine_id, 1)

    assert error.value.status == 409
    assert "expired" in error.value.message
    assert stock(medicine_id) == 50
    assert sales_rows() == []


def test_batch_expiring_today_can_still_be_sold(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    monkeypatch.setattr(database, "_india_today", lambda: date(2030, 6, 15))
    medicine_id = add_batch(expiry="2030-06-15", quantity=5)

    assert database.sell_medicine(medicine_id, 2)["remaining_stock"] == 3


def test_different_expiry_dates_stay_separate_batches(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    expired = add_batch(expiry=PAST, quantity=20)
    soon = add_batch(expiry=FUTURE, quantity=30)
    later = add_batch(expiry=LATER, quantity=40)

    assert len({expired, soon, later}) == 3

    database.sell_medicine(soon, 10, request_id="soon")

    assert stock(expired) == 20      # untouched
    assert stock(soon) == 20         # only this batch reduced
    assert stock(later) == 40        # untouched
    with pytest.raises(database.SaleError):
        database.sell_medicine(expired, 1)
    assert [row["expiry_date"] for row in sales_rows()] == [FUTURE]


# --------------------------------------------- duplicates / transactions

def test_simultaneous_sales_never_make_stock_negative(monkeypatch, tmp_path):
    import threading

    use_temp_database(monkeypatch, tmp_path)
    medicine_id = add_batch(quantity=5)
    outcomes = []

    def sell_one(number):
        try:
            database.sell_medicine(medicine_id, 1, request_id=f"thread-{number}")
            outcomes.append("sold")
        except database.SaleError:
            outcomes.append("refused")

    threads = [threading.Thread(target=sell_one, args=(n,)) for n in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert outcomes.count("sold") == 5
    assert outcomes.count("refused") == 7
    assert stock(medicine_id) == 0
    assert len(sales_rows()) == 5


def test_duplicate_request_does_not_sell_twice(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    medicine_id = add_batch(quantity=100)

    first = database.sell_medicine(medicine_id, 5, request_id="same-click")
    second = database.sell_medicine(medicine_id, 5, request_id="same-click")

    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert second["sale_id"] == first["sale_id"]
    assert stock(medicine_id) == 95
    assert len(sales_rows()) == 1


def test_failed_history_insert_rolls_back_stock_change(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    medicine_id = add_batch(quantity=100)
    conn = database.get_connection()
    conn.execute(
        "CREATE TRIGGER block_sales BEFORE INSERT ON sales "
        "BEGIN SELECT RAISE(ABORT, 'simulated failure'); END"
    )
    conn.commit()
    conn.close()

    with pytest.raises(sqlite3.Error):
        database.sell_medicine(medicine_id, 5, request_id="will-fail")

    assert stock(medicine_id) == 100
    assert sales_rows() == []


def test_sale_and_history_persist_after_reconnecting(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    medicine_id = add_batch(quantity=100)
    database.sell_medicine(medicine_id, 5, request_id="persist")

    fresh = sqlite3.connect(database.DATABASE)
    quantity = fresh.execute("SELECT quantity FROM medicines WHERE id = ?", (medicine_id,)).fetchone()[0]
    sold = fresh.execute("SELECT quantity_sold FROM sales").fetchone()[0]
    fresh.close()

    assert quantity == 95
    assert sold == 5


def test_sales_history_lists_newest_first_with_required_fields(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    first_id = add_batch(name="Aspirin", quantity=10)
    second_id = add_batch(name="Cetirizine", quantity=10)
    database.sell_medicine(first_id, 1, request_id="a")
    database.sell_medicine(second_id, 2, request_id="b")

    history = database.get_sales_history()

    assert [sale["medicine_name"] for sale in history] == ["Cetirizine", "Aspirin"]
    assert history[0]["quantity_sold"] == 2
    assert len(history[0]["sold_at"]) == 19  # YYYY-MM-DD HH:MM:SS


def test_existing_data_survives_adding_the_sales_table(tmp_path, monkeypatch):
    """Simulates a user's old database that has no sales table yet."""
    old_db = tmp_path / "old.db"
    conn = sqlite3.connect(old_db)
    conn.execute(
        "CREATE TABLE medicines (id INTEGER PRIMARY KEY AUTOINCREMENT, medicine_name TEXT NOT NULL, "
        "brand_name TEXT, generic_name TEXT, strength TEXT, dosage_form TEXT, expiry_date TEXT NOT NULL, "
        "quantity INTEGER DEFAULT 0, row_number INTEGER, column_number INTEGER)"
    )
    conn.execute(
        "INSERT INTO medicines (medicine_name, expiry_date, quantity) VALUES ('Old medicine', ?, 12)",
        (FUTURE,),
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(database, "DATABASE", old_db)

    database.init_database()
    database.init_database()  # running twice must be harmless

    assert database.get_all_medicines()[0]["medicine_name"] == "Old medicine"
    assert database.get_all_medicines()[0]["quantity"] == 12
    assert database.get_sales_history() == []


# ---------------------------------------------------------------- the API

def test_api_sale_returns_success_message_and_updated_quantity(monkeypatch, tmp_path):
    client = make_client(monkeypatch, tmp_path, login_as="staff")
    medicine_id = add_batch(quantity=100)

    response = client.post("/sales", json={"medicine_id": medicine_id, "quantity": 5, "request_id": "api-1"})

    assert response.status_code == 201
    body = response.get_json()
    assert body["message"] == "Sale completed successfully. Remaining stock: 95."
    assert body["remaining_stock"] == 95
    assert client.get(f"/medicine/{medicine_id}").get_json()["quantity"] == 95
    history = client.get("/sales").get_json()
    assert history["count"] == 1
    assert history["sales"][0]["medicine_name"] == "Paracetamol"
    assert history["sales"][0]["sold_by"] == "staff-test"


def test_api_error_responses(monkeypatch, tmp_path):
    client = make_client(monkeypatch, tmp_path, login_as="staff")
    ok_id = add_batch(quantity=3)
    expired_id = add_batch(expiry=PAST, quantity=3)

    assert client.post("/sales", json={"medicine_id": ok_id, "quantity": 9}).status_code == 409
    assert client.post("/sales", json={"medicine_id": expired_id, "quantity": 1}).status_code == 409
    assert client.post("/sales", json={"medicine_id": 9999, "quantity": 1}).status_code == 404
    assert client.post("/sales", json={"medicine_id": ok_id, "quantity": 0}).status_code == 400
    assert client.post("/sales", json={"medicine_id": ok_id, "quantity": -2}).status_code == 400
    assert client.post("/sales", json={"medicine_id": ok_id, "quantity": 1.5}).status_code == 400
    assert client.post("/sales", json={"medicine_id": ok_id, "quantity": "abc"}).status_code == 400
    assert client.post("/sales", json={"medicine_id": ok_id}).status_code == 400
    assert client.post("/sales", json={"quantity": 1}).status_code == 400
    assert client.post("/sales", data="not json", content_type="text/plain").status_code == 400
    assert stock(ok_id) == 3
    assert stock(expired_id) == 3
    assert client.get("/sales").get_json()["count"] == 0


def test_api_duplicate_request_is_not_sold_twice(monkeypatch, tmp_path):
    client = make_client(monkeypatch, tmp_path, login_as="staff")
    medicine_id = add_batch(quantity=100)
    payload = {"medicine_id": medicine_id, "quantity": 5, "request_id": "double-click"}

    first = client.post("/sales", json=payload)
    second = client.post("/sales", json=payload)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.get_json()["duplicate"] is True
    assert stock(medicine_id) == 95
    assert client.get("/sales").get_json()["count"] == 1


def test_sales_endpoints_are_staff_only(monkeypatch, tmp_path):
    anonymous = make_client(monkeypatch, tmp_path)
    medicine_id = add_batch(quantity=10)
    payload = {"medicine_id": medicine_id, "quantity": 1}

    assert anonymous.post("/sales", json=payload).status_code == 401
    assert anonymous.get("/sales").status_code == 401

    doctor = make_client(monkeypatch, tmp_path, login_as="doctor")
    assert doctor.post("/sales", json=payload).status_code == 403
    assert doctor.get("/sales").status_code == 403

    assert stock(medicine_id) == 10
    assert sales_rows() == []


def test_existing_add_medicine_endpoint_still_keeps_batches_separate(monkeypatch, tmp_path):
    client = make_client(monkeypatch, tmp_path, login_as="staff")
    base = {"medicine_name": "Amoxicillin", "strength": "250 mg", "quantity": 10}

    first = client.post("/add-medicine", json={**base, "expiry_date": FUTURE})
    second = client.post("/add-medicine", json={**base, "expiry_date": LATER})

    assert first.status_code == second.status_code == 201
    assert first.get_json()["medicine_id"] != second.get_json()["medicine_id"]
    assert client.get("/medicines").get_json()["count"] == 2


def test_staff_dashboard_has_sell_and_history_sections_but_doctor_does_not(monkeypatch, tmp_path):
    staff = make_client(monkeypatch, tmp_path, login_as="staff")
    page = staff.get("/staff/dashboard").data
    assert b'id="sellMedicineSection"' in page
    assert b'id="salesHistorySection"' in page
    assert b"<th>Quantity</th>" in page
    # existing sections are still there
    for existing in (b'id="inventorySection"', b'id="addMedicineSection"', b'id="alertsSection"', b'id="scanSection"'):
        assert existing in page

    doctor = make_client(monkeypatch, tmp_path, login_as="doctor")
    doctor_page = doctor.get("/doctor/dashboard").data
    assert b'id="sellMedicineSection"' not in doctor_page
    assert b'id="salesHistorySection"' not in doctor_page


# ----------------------------------------------------------- backup script

def test_backup_script_copies_database_without_changing_original(monkeypatch, tmp_path):
    use_temp_database(monkeypatch, tmp_path)
    add_batch(quantity=42)
    original = Path(database.DATABASE)
    before = original.read_bytes()

    backup = backup_database.backup_database(original, tmp_path / "backups")

    assert backup.exists() and backup != original
    copy = sqlite3.connect(backup)
    assert copy.execute("SELECT quantity FROM medicines").fetchone()[0] == 42
    copy.close()
    assert original.read_bytes() == before
