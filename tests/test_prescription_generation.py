import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
from pypdf import PdfReader

import app
import database


@pytest.fixture
def client(tmp_path, monkeypatch):
    database_path = tmp_path / "prescriptions.db"
    monkeypatch.setattr(database, "DATABASE", database_path)
    database.init_database()
    database.init_prescription_database()
    monkeypatch.setattr(app, "GENERATED_FOLDER", str(tmp_path / "generated"))
    monkeypatch.setattr(app, "is_sms_configured", lambda: False)
    monkeypatch.setattr(app, "upload_pdf_to_drive", lambda _path: None)
    for key, value in {
        "DOCTOR_NAME": "Dr. Test Clinician",
        "CLINIC_NAME": "Test Clinic",
        "CLINIC_TAGLINE": "Test clinic tagline",
        "CLINIC_ADDRESS": "10 Test Street",
        "CLINIC_PHONE": "0123456789",
        "CLINIC_EMAIL": "clinic@example.test",
        "PUBLIC_BASE_URL": "",
        "GOOGLE_DRIVE_UPLOAD_ENABLED": "",
    }.items():
        monkeypatch.setenv(key, value)
    return app.app.test_client()


def valid_payload(medicines=None):
    return {
        "patient_name": "Test Patient",
        "age": "42",
        "gender": "Other",
        "phone_number": "9876543210",
        "medicines": medicines or [{
            "name": "Medicine A",
            "dosage": "5 mg",
            "dose_schedule": "1-0-0-1",
            "frequency": "Once daily",
            "timing": ["Morning"],
            "food_instruction": "After food",
            "duration": "7 days",
            "special_instructions": "Test instructions",
        }],
        "review_confirmed": True,
    }


def post_prescription(client, payload=None, key="test-request-1"):
    return client.post(
        "/generate-prescription",
        json=payload or valid_payload(),
        headers={"Idempotency-Key": key},
    )


def test_generates_pdf_and_persists_full_prescription(client):
    response = post_prescription(client)

    assert response.status_code == 201
    result = response.get_json()
    assert result["success"] is True
    assert result["download_url"].endswith(
        "/patient/prescriptions/download/" + result["download_url"].rsplit("/", 1)[1]
    )
    assert "download_url" in result
    assert result["medicines"][0]["name"] == "Medicine A"

    download = client.get(result["download_url"].replace("http://localhost", ""))
    assert download.status_code == 200
    assert download.data.startswith(b"%PDF-")
    assert len(download.data) > 100

    filename = result["filename"]
    reader = PdfReader(str((__import__("pathlib").Path(app.GENERATED_FOLDER) / filename)))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert reader.pages[0].images
    for expected in (
        "Test Clinic",
        "Test clinic tagline",
        "10 Test Street",
        "0123456789",
        "clinic@example.test",
        "Test Patient",
        "9876543210",
        "42 years",
        "Other",
        "Dr. Test Clinician",
        "Medicine A",
        "5 mg",
        "1-0-0-1",
        "Dose M-A-E-B",
        "Once daily",
        "7 days",
        "Timing: Morning",
        "Food: After food",
        "Special instructions: Test instructions",
        "Doctor's signature:",
        "Generated for review",
    ):
        assert expected in text
    assert "digitally signed" not in text.casefold()

    records = database.get_patient_prescriptions("+91" + "9876543210")
    assert len(records) == 1
    stored = json.loads(records[0]["prescription_json"])
    assert stored["medicines"] == result["medicines"]
    assert records[0]["doctor_name"] == "Dr. Test Clinician"


def test_multiple_medicines_and_idempotency(client):
    payload = valid_payload([
        {
            "name": "Medicine A",
            "dosage": "5 mg",
            "dose_schedule": "",
            "frequency": "Once daily",
            "timing": ["Morning"],
            "food_instruction": "After food",
            "duration": "7 days",
            "special_instructions": "",
        },
        {
            "name": "Medicine B",
            "dosage": "10 ml",
            "dose_schedule": "",
            "frequency": "As needed",
            "timing": [],
            "food_instruction": "With food",
            "duration": "As directed",
            "special_instructions": "",
        },
    ])
    first = post_prescription(client, payload, "repeat-key")
    duplicate = post_prescription(client, payload, "repeat-key")

    assert first.status_code == 201
    assert duplicate.status_code == 200
    assert duplicate.get_json()["duplicate"] is True
    assert duplicate.get_json()["prescription_id"] == first.get_json()["prescription_id"]
    assert len(database.get_patient_prescriptions("+919876543210")) == 1
    pdf_path = __import__("pathlib").Path(app.GENERATED_FOLDER) / first.get_json()["filename"]
    text = "\n".join(page.extract_text() or "" for page in PdfReader(str(pdf_path)).pages)
    assert "Medicine A" in text
    assert "Medicine B" in text
    assert "10 ml" in text
    assert "As needed" in text


def test_dose_schedule_with_spaces_is_stored_and_printed_exactly(client):
    payload = valid_payload()
    payload["medicines"][0]["dose_schedule"] = "1 0 0 1"

    response = post_prescription(client, payload, "space-schedule")

    assert response.status_code == 201
    result = response.get_json()
    assert result["medicines"][0]["dose_schedule"] == "1 0 0 1"
    pdf_path = Path(app.GENERATED_FOLDER) / result["filename"]
    text = "\n".join(page.extract_text() or "" for page in PdfReader(str(pdf_path)).pages)
    assert "1 0 0 1" in text
    records = database.get_patient_prescriptions("+919876543210")
    assert json.loads(records[0]["prescription_json"])["medicines"][0]["dose_schedule"] == "1 0 0 1"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("patient_name", ""),
        ("age", ""),
        ("phone_number", ""),
        ("medicines", []),
    ],
)
def test_rejects_missing_required_fields(client, field, value):
    payload = valid_payload()
    payload[field] = value
    response = post_prescription(client, payload)

    assert response.status_code == 400
    assert response.get_json()["error"]
    assert database.get_patient_prescriptions("+919876543210") == []


def test_rejects_unconfirmed_or_invalid_medicine(client):
    payload = valid_payload()
    payload["review_confirmed"] = False
    assert post_prescription(client, payload).status_code == 400

    payload = valid_payload()
    payload["medicines"][0]["timing"] = ["Midnight"]
    response = post_prescription(client, payload, "invalid-timing")
    assert response.status_code == 400
    assert "timing" in response.get_json()["error"].casefold()

    payload = valid_payload()
    payload["medicines"][0]["dosage"] = ""
    response = post_prescription(client, payload, "invalid-dosage")
    assert response.status_code == 400
    assert "dosage" in response.get_json()["error"].casefold()

    payload = valid_payload()
    payload["medicines"][0]["dose_schedule"] = "1-0-1"
    response = post_prescription(client, payload, "invalid-dose-schedule")
    assert response.status_code == 400
    assert "dose schedule" in response.get_json()["error"].casefold()


def test_rejects_reuse_of_idempotency_key_for_changed_data(client):
    first = post_prescription(client, key="same-key")
    changed = valid_payload()
    changed["patient_name"] = "Another Patient"

    response = post_prescription(client, changed, "same-key")

    assert first.status_code == 201
    assert response.status_code == 409
    assert len(database.get_patient_prescriptions("+919876543210")) == 1


def test_idempotency_race_with_changed_data_returns_conflict(client, monkeypatch):
    lookups = iter([None, {"request_hash": "different-payload"}])
    monkeypatch.setattr(app, "get_prescription_by_request_id", lambda _key: next(lookups))
    monkeypatch.setattr(
        app,
        "save_prescription",
        lambda _data: (_ for _ in ()).throw(database.sqlite3.IntegrityError()),
    )

    response = post_prescription(client, key="racing-key")

    assert response.status_code == 409
    assert response.get_json()["error"]
    assert list(__import__("pathlib").Path(app.GENERATED_FOLDER).glob("*.pdf")) == []


def test_missing_clinic_configuration_is_reported(client, monkeypatch):
    monkeypatch.delenv("DOCTOR_NAME")
    response = post_prescription(client)

    assert response.status_code == 503
    assert "DOCTOR_NAME" in response.get_json()["error"]
    assert database.get_patient_prescriptions("+919876543210") == []


def test_optional_clinic_details_can_be_omitted(client, monkeypatch):
    for key in ("CLINIC_TAGLINE", "CLINIC_ADDRESS", "CLINIC_PHONE", "CLINIC_EMAIL"):
        monkeypatch.delenv(key)

    response = post_prescription(client, key="optional-clinic-details")

    assert response.status_code == 201
    pdf_path = Path(app.GENERATED_FOLDER) / response.get_json()["filename"]
    text = "\n".join(page.extract_text() or "" for page in PdfReader(str(pdf_path)).pages)
    assert "Dr. Test Clinician" in text
    assert "Test Clinic" in text
    assert "Phone:" not in text
    assert "Email:" not in text


def test_drive_and_sms_failures_do_not_prevent_local_download(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_DRIVE_UPLOAD_ENABLED", "true")
    monkeypatch.setattr(
        app,
        "upload_pdf_to_drive",
        lambda _path: (_ for _ in ()).throw(RuntimeError("Drive unavailable")),
    )
    monkeypatch.setattr(app, "is_sms_configured", lambda: True)
    monkeypatch.setattr(
        app,
        "send_sms",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("SMS unavailable")),
    )

    response = post_prescription(client, key="optional-services")

    assert response.status_code == 201
    download_url = response.get_json()["download_url"]
    download = client.get(download_url.replace("http://localhost", ""))
    assert download.status_code == 200
    assert download.data.startswith(b"%PDF-")


def test_generator_controls_are_present_for_all_script_references(client):
    class IdCollector(HTMLParser):
        def __init__(self):
            super().__init__()
            self.ids = set()

        def handle_starttag(self, _tag, attrs):
            self.ids.update(value for name, value in attrs if name == "id")

    response = client.get("/")
    assert response.status_code == 200
    parser = IdCollector()
    parser.feed(response.get_data(as_text=True))
    script = (Path(__file__).parents[1] / "static" / "script.js").read_text(
        encoding="utf-8"
    )
    referenced_ids = set(re.findall(
        r"getElementById\(['\"]([^'\"]+)['\"]\)", script
    ))

    assert referenced_ids - {"fileSummary"} <= parser.ids
    assert {
        "rxMedicineName",
        "rxDosage",
        "rxDoseSchedule",
        "rxFrequency",
        "rxFood",
        "rxDuration",
        "rxSpecial",
        "rxAddBtn",
        "rxMedicineList",
        "rxEmptyState",
        "rxMedicineCount",
        "rxFormError",
        "rxEntryPanel",
        "prescriptionReviewConfirmed",
    } <= parser.ids
