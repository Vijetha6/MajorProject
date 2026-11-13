import io
import os
import sqlite3
from datetime import date

import pytest

import database

os.environ.setdefault("GEMINI_API_KEY", "test-key")
import app as medicine_app


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("03/2027", "2027-03-31"),
        ("08/2027", "2027-08-31"),
        ("AUG 2027", "2027-08-31"),
        ("2027-08", "2027-08-31"),
        ("02/2028", "2028-02-29"),
        ("2027-08-15", "2027-08-15"),
        ("15/08/2027", "2027-08-15"),
    ],
)
def test_normalize_expiry_supported_formats(value, expected):
    assert database.normalize_expiry(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "13/2027",
        "2027-13",
        "31/02/2027",
        "2027-02-29",
        "",
        "   ",
        None,
        "08/27",
        "03/04/27",
    ],
)
def test_normalize_expiry_rejects_invalid_or_ambiguous_values(value):
    with pytest.raises(ValueError):
        database.normalize_expiry(value)


@pytest.fixture
def inventory_db(tmp_path, monkeypatch):
    db_path = tmp_path / "medicine_inventory.db"
    monkeypatch.setattr(database, "DATABASE", db_path)
    database.init_database()
    monkeypatch.setattr(database, "_india_today", lambda: date(2027, 8, 1))
    return db_path


def staff_client():
    client = medicine_app.app.test_client()
    with client.session_transaction() as session:
        session["role"] = "medical_staff"
        session["user_id"] = "test-staff"
    return client


def test_add_and_update_medicine_normalize_without_partial_overwrite(inventory_db):
    medicine_id = database.add_medicine(
        {"medicine_name": "Test Medicine", "expiry_date": "03/2027", "quantity": 4}
    )
    assert database.get_medicine(medicine_id)["expiry_date"] == "2027-03-31"

    assert database.update_medicine(
        medicine_id,
        {"medicine_name": "Updated Medicine", "expiry_date": "15/08/2027", "quantity": 6},
    )
    before_invalid_update = database.get_medicine(medicine_id)
    with pytest.raises(ValueError, match="DD/MM/YYYY"):
        database.update_medicine(
            medicine_id,
            {"medicine_name": "Must Not Replace", "expiry_date": "31/02/2027"},
        )

    assert database.get_medicine(medicine_id) == before_invalid_update
    with sqlite3.connect(inventory_db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM medicines").fetchone()[0] == 1


def test_api_validates_expiry_before_quantity_and_updates_existing_record(inventory_db):
    client = staff_client()
    created = client.post(
        "/add-medicine",
        json={"medicine_name": "Manual Medicine", "expiry_date": "08/2027", "quantity": 3},
    )
    assert created.status_code == 201
    medicine_id = created.get_json()["medicine_id"]
    assert database.get_medicine(medicine_id)["expiry_date"] == "2027-08-31"

    invalid = client.post(
        "/add-medicine",
        json={
            "medicine_name": "Invalid Medicine",
            "expiry_date": "13/2027",
            "quantity": "not a number",
        },
    )
    assert invalid.status_code == 400
    assert "expiry month" in invalid.get_json()["error"].lower()
    assert "quantity" not in invalid.get_json()["error"].lower()

    updated = client.put(
        f"/medicine/{medicine_id}",
        json={
            "medicine_name": "Manual Medicine",
            "expiry_date": "2027-08-15",
            "quantity": 5,
        },
    )
    assert updated.status_code == 200
    assert database.get_medicine(medicine_id)["expiry_date"] == "2027-08-15"

    empty_expiry = client.put(
        f"/medicine/{medicine_id}",
        json={"medicine_name": "Manual Medicine", "expiry_date": ""},
    )
    assert empty_expiry.status_code == 400
    assert "expiry date is required" in empty_expiry.get_json()["error"].lower()
    assert database.get_medicine(medicine_id)["expiry_date"] == "2027-08-15"


def test_ocr_result_can_be_saved_with_normalized_expiry(inventory_db, tmp_path, monkeypatch):
    upload_folder = tmp_path / "uploads"
    upload_folder.mkdir()
    monkeypatch.setattr(medicine_app, "UPLOAD_FOLDER", str(upload_folder))
    monkeypatch.setattr(medicine_app, "cleanup_old_files", lambda: None)
    monkeypatch.setattr(medicine_app.cv2, "imread", lambda _path: object())
    monkeypatch.setattr(medicine_app, "process_with_yolo", lambda _path: (None, None))
    monkeypatch.setattr(
        medicine_app,
        "extract_text_with_ocr",
        lambda _image: "Paracetamol 500 mg EXP AUG 2027",
    )
    monkeypatch.setattr(medicine_app, "extract_medicine_name", lambda _text: "Paracetamol")
    monkeypatch.setattr(
        medicine_app,
        "extract_expiry_with_rotations",
        lambda _image: ("AUG 2027", None, "EXP AUG 2027"),
    )
    monkeypatch.setattr(
        medicine_app,
        "get_medicine_info_gemini",
        lambda *args, **kwargs: {
            "brand_name": "Paracetamol",
            "generic_name": "Paracetamol",
            "strength": "500 mg",
            "dosage_form": "Tablet",
            "expiry_date": "Information not available",
            "uses": [],
            "side_effects": [],
        },
    )

    client = staff_client()
    response = client.post(
        "/process",
        data={"images": (io.BytesIO(b"image bytes"), "medicine.jpg")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    extracted = response.get_json()[0]
    assert extracted["expiry_date"] == "AUG 2027"

    saved = client.post(
        "/add-medicine",
        json={
            "medicine_name": extracted["medicine_name"],
            "expiry_date": extracted["expiry_date"],
            "quantity": 2,
        },
    )
    assert saved.status_code == 201
    assert database.get_medicine(saved.get_json()["medicine_id"])["expiry_date"] == "2027-08-31"
