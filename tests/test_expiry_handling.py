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


def test_expiry_warning_api_uses_seven_day_default_and_allows_override(inventory_db):
    for medicine_name, expiry_date in (
        ("Expired yesterday", "2027-07-31"),
        ("Expires today", "2027-08-01"),
        ("Expires tomorrow", "2027-08-02"),
        ("Expires in 2 days", "2027-08-03"),
        ("Expires in 7 days", "2027-08-08"),
        ("Expires in 8 days", "2027-08-09"),
    ):
        database.add_medicine({
            "medicine_name": medicine_name,
            "expiry_date": expiry_date,
        })

    client = staff_client()
    response = client.get("/medicines/expiring")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["days"] == 7
    assert {
        medicine["medicine_name"]: medicine["days_remaining"]
        for medicine in payload["medicines"]
    } == {
        "Expires today": 0,
        "Expires tomorrow": 1,
        "Expires in 2 days": 2,
        "Expires in 7 days": 7,
    }

    overridden = client.get("/medicines/expiring?days=2")
    assert overridden.status_code == 200
    assert overridden.get_json()["days"] == 2
    assert [
        medicine["medicine_name"]
        for medicine in overridden.get_json()["medicines"]
    ] == ["Expires today", "Expires tomorrow", "Expires in 2 days"]

    expired = client.get("/medicines/expired")
    expired_medicines = expired.get_json()["medicines"]
    assert [medicine["medicine_name"] for medicine in expired_medicines] == [
        "Expired yesterday"
    ]
    assert expired_medicines[0]["days_remaining"] == -1


def test_expiry_alerts_are_combined_and_sorted_by_actual_expiry_date(inventory_db):
    for medicine_name, expiry_date in (
        ("Expires next week", "2027-08-08"),
        ("Expired yesterday", "2027-07-31"),
        ("Expired first", "2027-06-30"),
        ("Expires today", "2027-08-01"),
        ("Expires tomorrow", "2027-08-02"),
    ):
        database.add_medicine({
            "medicine_name": medicine_name,
            "expiry_date": expiry_date,
        })

    response = staff_client().get("/medicines/expiry-alerts")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["expired_count"] == 2
    assert payload["expiring_count"] == 3
    assert [medicine["medicine_name"] for medicine in payload["medicines"]] == [
        "Expired first",
        "Expired yesterday",
        "Expires today",
        "Expires tomorrow",
        "Expires next week",
    ]


def test_expired_medicines_include_details_and_skip_today_future_or_invalid_dates(inventory_db):
    with sqlite3.connect(inventory_db) as connection:
        connection.executemany(
            """
            INSERT INTO medicines (
                medicine_name, brand_name, generic_name, strength, dosage_form,
                expiry_date, quantity, row_number, column_number
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("Expired ISO", "Brand A", None, None, None, "2027-07-30", 5, 2, 4),
                ("Expired alternate", "Brand B", None, None, None, "31/07/2027", 3, 1, 8),
                ("Expires today", None, None, None, None, "2027-08-01", 2, None, None),
                ("Expires tomorrow", None, None, None, None, "2027-08-02", 1, None, None),
                ("Invalid expiry", None, None, None, None, "not-a-date", 7, None, None),
                ("Missing expiry", None, None, None, None, "", 4, None, None),
            ],
        )

    response = staff_client().get("/medicines/expired")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["count"] == 2
    assert [medicine["medicine_name"] for medicine in payload["medicines"]] == [
        "Expired ISO",
        "Expired alternate",
    ]
    assert payload["medicines"][0]["brand_name"] == "Brand A"
    assert payload["medicines"][0]["expiry_date"] == "2027-07-30"
    assert payload["medicines"][0]["quantity"] == 5
    assert payload["medicines"][0]["row_number"] == 2
    assert payload["medicines"][0]["column_number"] == 4
    assert [medicine["days_remaining"] for medicine in payload["medicines"]] == [-2, -1]


def test_expired_medicines_empty_when_inventory_has_no_valid_past_expiry(inventory_db):
    with sqlite3.connect(inventory_db) as connection:
        connection.executemany(
            """
            INSERT INTO medicines (
                medicine_name, expiry_date, quantity
            ) VALUES (?, ?, ?)
            """,
            [
                ("Expires today", "2027-08-01", 1),
                ("Expires future", "2027-08-02", 1),
                ("Invalid expiry", "not-a-date", 1),
                ("Missing expiry", "", 1),
            ],
        )

    response = staff_client().get("/medicines/expired")

    assert response.status_code == 200
    assert response.get_json() == {"count": 0, "medicines": []}


def test_expired_medicine_results_reflect_inventory_updates_and_removals(inventory_db):
    medicine_id = database.add_medicine({
        "medicine_name": "Expired medicine",
        "expiry_date": "2027-07-31",
        "quantity": 3,
    })
    assert [item["id"] for item in database.get_expired_medicines()] == [medicine_id]

    assert database.update_medicine(
        medicine_id,
        {"medicine_name": "Updated medicine", "expiry_date": "2027-08-02", "quantity": 3},
    )
    assert database.get_expired_medicines() == []

    removed_id = database.add_medicine({
        "medicine_name": "Removed expired medicine",
        "expiry_date": "2027-07-30",
    })
    assert database.delete_medicine(removed_id)
    assert database.get_expired_medicines() == []


def test_staff_can_remove_only_the_selected_expired_medicine(inventory_db):
    expired_id = database.add_medicine({
        "medicine_name": "Same medicine",
        "expiry_date": "2027-07-31",
        "quantity": 3,
    })
    current_id = database.add_medicine({
        "medicine_name": "Same medicine",
        "expiry_date": "2027-08-08",
        "quantity": 8,
    })
    client = staff_client()

    response = client.delete(f"/medicine/{expired_id}/expired")

    assert response.status_code == 200
    assert response.get_json()["message"] == "Expired medicine removed successfully."
    assert database.get_medicine(expired_id) is None
    assert database.get_medicine(current_id)["quantity"] == 8
    assert [medicine["id"] for medicine in client.get("/medicines").get_json()["medicines"]] == [
        current_id
    ]
    assert client.get("/medicines/expiry-alerts").get_json()["expired_count"] == 0

    not_expired = client.delete(f"/medicine/{current_id}/expired")
    assert not_expired.status_code == 409
    assert database.get_medicine(current_id) is not None


def test_removing_expired_medicines_requires_medical_staff(inventory_db):
    medicine_id = database.add_medicine({
        "medicine_name": "Expired medicine",
        "expiry_date": "2027-07-31",
    })

    assert medicine_app.app.test_client().delete(
        f"/medicine/{medicine_id}/expired"
    ).status_code == 401

    doctor_client = medicine_app.app.test_client()
    with doctor_client.session_transaction() as session:
        session["role"] = "doctor"
    assert doctor_client.delete(
        f"/medicine/{medicine_id}/expired"
    ).status_code == 403
    assert database.get_medicine(medicine_id) is not None


def test_expired_medicine_modal_is_only_rendered_for_medical_staff(inventory_db):
    staff_dashboard = staff_client().get("/staff/dashboard")
    assert b'id="expiredMedicineModal"' in staff_dashboard.data
    assert b"EXPIRY ALERT" in staff_dashboard.data
    assert b'id="closeExpiredMedicineModal"' in staff_dashboard.data

    public_dashboard = medicine_app.app.test_client().get("/")
    assert b'id="expiredMedicineModal"' not in public_dashboard.data

    doctor_client = medicine_app.app.test_client()
    with doctor_client.session_transaction() as session:
        session["role"] = "doctor"
    doctor_dashboard = doctor_client.get("/doctor/dashboard")
    assert b'id="expiredMedicineModal"' not in doctor_dashboard.data


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


def test_update_medicine_preserves_quantity_when_quantity_is_omitted(inventory_db):
    medicine_id = database.add_medicine({
        "medicine_name": "Test Medicine",
        "expiry_date": "03/2027",
        "quantity": 42,
    })

    assert database.update_medicine(
        medicine_id,
        {"medicine_name": "Updated Medicine", "expiry_date": "2027-03-15"},
    )
    assert database.get_medicine(medicine_id)["quantity"] == 42


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

    update_without_quantity = client.put(
        f"/medicine/{medicine_id}",
        json={"medicine_name": "Manual Medicine", "expiry_date": "2027-08-20"},
    )
    assert update_without_quantity.status_code == 200
    assert database.get_medicine(medicine_id)["quantity"] == 5

    empty_expiry = client.put(
        f"/medicine/{medicine_id}",
        json={"medicine_name": "Manual Medicine", "expiry_date": ""},
    )
    assert empty_expiry.status_code == 400
    assert "expiry date is required" in empty_expiry.get_json()["error"].lower()
    assert database.get_medicine(medicine_id)["expiry_date"] == "2027-08-20"


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
