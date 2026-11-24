from pathlib import Path
from urllib.parse import urlsplit
from types import SimpleNamespace

import pytest

import doctor_database
import app as app_module
import sms as sms_module


@pytest.fixture
def doctor_client(tmp_path, monkeypatch):
    database_path = tmp_path / "doctor-test.db"
    monkeypatch.setattr(doctor_database, "DATABASE", database_path)
    doctor_database.init_database()

    generated_folder = tmp_path / "generated"
    generated_folder.mkdir()
    monkeypatch.setattr(app_module, "GENERATED_FOLDER", str(generated_folder))

    def write_test_pdf(data, filepath):
        Path(filepath).write_bytes(b"%PDF-1.4 test prescription")

    monkeypatch.setattr(app_module, "generate_prescription_pdf", write_test_pdf)
    monkeypatch.setattr(app_module, "upload_pdf_to_drive", lambda filepath: None)
    monkeypatch.setattr(app_module, "send_sms", lambda **kwargs: None)

    client = app_module.app.test_client()
    with client.session_transaction() as app_session:
        app_session["role"] = "doctor"
        app_session["user_id"] = "DOC-TEST"
    return client, generated_folder


def register_patient(client, name="Asha Rao", mobile="9876543210"):
    response = client.post(
        "/doctor/patients",
        json={
            "patient_name": name,
            "age": 38,
            "gender": "Female",
            "mobile_number": mobile,
            "address": "Bengaluru",
        },
    )
    assert response.status_code == 201
    return response.get_json()["patient"]


def create_visit(client, patient_id, medicines, **extra):
    payload = {"patient_id": patient_id, "medicines": medicines}
    payload.update(extra)
    return client.post("/generate-prescription", json=payload)


def test_search_patient_by_id_mobile_and_missing_result(doctor_client):
    client, _ = doctor_client
    patient = register_patient(client)

    by_id = client.get(
        f"/doctor/patients/search?patient_id={patient['patient_id']}"
    )
    by_mobile = client.get(
        "/doctor/patients/search?mobile_number=%2B91%209876543210"
    )
    missing = client.get("/doctor/patients/search?patient_id=PT-MISSING")

    assert by_id.get_json()["patients"][0]["patient_id"] == patient["patient_id"]
    assert by_mobile.get_json()["patients"][0]["patient_id"] == patient["patient_id"]
    assert missing.get_json()["patients"] == []
    patient_history = client.get(
        f"/doctor/patients/{patient['patient_id']}/history"
    ).get_json()["visits"]
    assert patient_history == []


def test_duplicate_registration_returns_existing_patient_instead_of_creating_one(doctor_client):
    client, _ = doctor_client
    patient = register_patient(client)

    duplicate = client.post(
        "/doctor/patients",
        json={
            "patient_name": "asha rao",
            "age": 38,
            "gender": "Female",
            "mobile_number": "9876543210",
            "address": "",
        },
    )

    assert duplicate.status_code == 409
    assert duplicate.get_json()["existing_patients"][0]["patient_id"] == patient["patient_id"]
    assert len(doctor_database.search_patients(patient_id=patient["patient_id"])) == 1


def test_new_patient_starts_without_history_and_can_be_retrieved(doctor_client):
    client, _ = doctor_client
    patient = register_patient(client, name="New Patient", mobile="9876500000")
    history = client.get(f"/doctor/patients/{patient['patient_id']}/history")

    assert patient["patient_id"].startswith("PT-")
    assert history.status_code == 200
    assert history.get_json()["visits"] == []


def test_patient_registration_rejects_invalid_age_and_mobile(doctor_client):
    client, _ = doctor_client
    response = client.post(
        "/doctor/patients",
        json={
            "patient_name": "Invalid Patient",
            "age": 20.5,
            "gender": "Other",
            "mobile_number": "not-a-number",
            "address": "",
        },
    )

    assert response.status_code == 400
    assert "age" in response.get_json()["field_errors"]
    assert "mobile_number" in response.get_json()["field_errors"]


def test_visits_keep_patient_doctor_and_pdf_links_and_old_medicines_are_not_copied(
    doctor_client,
):
    client, generated_folder = doctor_client
    patient = register_patient(client)
    first_response = create_visit(
        client,
        patient["patient_id"],
        [{"name": "Medicine A", "dosage": "10 mg", "frequency": "Daily"}],
        diagnosis="Initial visit",
    )
    assert first_response.status_code == 200
    first_visit = first_response.get_json()

    second_response = create_visit(
        client,
        patient["patient_id"],
        [{"name": "Medicine B", "dosage": "20 mg", "frequency": "Twice daily"}],
        diagnosis="Follow-up",
    )
    assert second_response.status_code == 200
    second_visit = second_response.get_json()
    another_patient = register_patient(
        client,
        name="Another Patient",
        mobile="9876500002",
    )

    history = client.get(f"/doctor/patients/{patient['patient_id']}/history")
    visits = history.get_json()["visits"]
    pdf_response = client.get(urlsplit(second_visit["download_url"]).path)
    wrong_patient_pdf = client.get(
        f"/doctor/patients/{another_patient['patient_id']}/visits/{second_visit['visit_id']}/pdf"
    )
    wrong_patient_visit = client.get(
        f"/doctor/patients/{another_patient['patient_id']}/visits/{second_visit['visit_id']}"
    )

    assert len(visits) == 2
    assert visits[0]["visit_id"] == second_visit["visit_id"]
    assert visits[1]["visit_id"] == first_visit["visit_id"]
    assert visits[0]["doctor_id"] == "DOC-TEST"
    assert [medicine["medicine_name"] for medicine in visits[0]["medicines"]] == [
        "Medicine B"
    ]
    assert [medicine["medicine_name"] for medicine in visits[1]["medicines"]] == [
        "Medicine A"
    ]
    assert pdf_response.status_code == 200
    assert pdf_response.data.startswith(b"%PDF")
    assert wrong_patient_pdf.status_code == 404
    assert wrong_patient_visit.status_code == 404
    assert len(list(generated_folder.glob("*.pdf"))) == 2


def test_qr_url_returns_saved_prescription_pdf(doctor_client):
    client, _ = doctor_client
    patient = register_patient(client)

    response = create_visit(
        client,
        patient["patient_id"],
        [{"name": "QR Medicine", "dosage": "10 mg"}],
    )

    assert response.status_code == 200
    qr_url = response.get_json()["qr_url"]
    qr_path = urlsplit(qr_url).path
    qr_response = client.get(qr_path)

    assert qr_path.startswith("/prescription/view/")
    assert "127.0.0.1" not in qr_url
    assert "localhost" not in qr_url
    assert qr_response.status_code == 200
    assert qr_response.mimetype == "application/pdf"
    assert qr_response.data.startswith(b"%PDF")


def test_free_text_generation_passes_dose_schedule_to_pdf(doctor_client, monkeypatch):
    client, _ = doctor_client
    patient = register_patient(client)
    captured = {}

    def capture_pdf_data(data, filepath):
        captured["medicines"] = data["medicines"]
        Path(filepath).write_bytes(b"%PDF-1.4 test prescription")

    monkeypatch.setattr(app_module, "generate_prescription_pdf", capture_pdf_data)
    response = client.post(
        "/generate-prescription",
        json={
            "patient_id": patient["patient_id"],
            "text": (
                "Paracetamol 500 mg one zero one zero for 5 days "
                "after food Morning Evening"
            ),
        },
    )

    assert response.status_code == 200
    assert captured["medicines"][0]["dose_schedule"] == "1-0-1-0"


def test_sms_sends_google_drive_link_to_patient(doctor_client, monkeypatch):
    client, _ = doctor_client
    patient = register_patient(client, name="SMS Patient", mobile="9876500010")
    drive_url = "https://drive.google.com/file/d/test-file/view"
    sent_messages = []
    monkeypatch.setattr(app_module, "upload_pdf_to_drive", lambda filepath: drive_url)
    monkeypatch.setattr(
        app_module,
        "send_sms",
        lambda **kwargs: sent_messages.append(kwargs),
    )

    response = create_visit(
        client,
        patient["patient_id"],
        [{"name": "Medicine SMS", "dosage": "10 mg"}],
    )
    assert response.status_code == 200
    response_data = response.get_json()

    assert response_data["drive_url"] == drive_url
    assert sent_messages[0]["download_url"] == drive_url
    assert response_data["sms_sent"] is True
    assert response_data["sms_error"] is None


def test_sms_failure_is_reported_without_losing_saved_prescription(
    doctor_client,
    monkeypatch,
):
    client, _ = doctor_client
    patient = register_patient(client)
    monkeypatch.setattr(
        app_module,
        "upload_pdf_to_drive",
        lambda filepath: "https://drive.google.com/file/d/test-file/view",
    )

    def fail_to_send_sms(**kwargs):
        raise RuntimeError("SMS provider unavailable")

    monkeypatch.setattr(app_module, "send_sms", fail_to_send_sms)
    response = create_visit(
        client,
        patient["patient_id"],
        [{"name": "Medicine SMS", "dosage": "10 mg"}],
    )

    assert response.status_code == 200
    assert response.get_json()["sms_sent"] is False
    assert "SMS could not be sent" in response.get_json()["sms_error"]
    history = client.get(
        f"/doctor/patients/{patient['patient_id']}/history"
    ).get_json()["visits"]
    assert len(history) == 1


def test_sms_is_not_sent_when_drive_upload_fails(doctor_client, monkeypatch):
    client, _ = doctor_client
    patient = register_patient(client)
    sent_messages = []
    monkeypatch.setattr(app_module, "send_sms", lambda **kwargs: sent_messages.append(kwargs))

    response = create_visit(
        client,
        patient["patient_id"],
        [{"name": "Medicine SMS", "dosage": "10 mg"}],
    )

    assert response.status_code == 200
    assert response.get_json()["sms_sent"] is False
    assert "Google Drive link is unavailable" in response.get_json()["sms_error"]
    assert sent_messages == []


def test_sms_uses_configured_twilio_sender_and_includes_drive_link(monkeypatch):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "test-account")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("TWILIO_PHONE_NUMBER", "+15005550006")
    sent = {}

    class FakeMessages:
        def create(self, **kwargs):
            sent.update(kwargs)
            return SimpleNamespace(sid="SM-test")

    class FakeClient:
        def __init__(self, account_sid, auth_token):
            assert account_sid == "test-account"
            assert auth_token == "test-token"
            self.messages = FakeMessages()

    monkeypatch.setattr(sms_module, "Client", FakeClient)
    link = "https://drive.google.com/file/d/test-file/view"

    message_sid = sms_module.send_sms(
        "Test Patient",
        "+919876543210",
        link,
    )

    assert message_sid == "SM-test"
    assert sent["from_"] == "+15005550006"
    assert sent["to"] == "+919876543210"
    assert link in sent["body"]


def test_mobile_change_keeps_history_attached_to_patient_id(doctor_client):
    client, _ = doctor_client
    patient = register_patient(client)
    saved = create_visit(
        client,
        patient["patient_id"],
        [{"name": "Medicine A", "dosage": "10 mg"}],
    )
    changed = client.put(
        f"/doctor/patients/{patient['patient_id']}",
        json={"mobile_number": "9876500001"},
    )
    history = client.get(f"/doctor/patients/{patient['patient_id']}/history")

    assert changed.status_code == 200
    assert changed.get_json()["patient"]["mobile_number"] == "9876500001"
    assert history.get_json()["patient"]["patient_id"] == patient["patient_id"]
    assert history.get_json()["visits"][0]["visit_id"] == saved.get_json()["visit_id"]


def test_saving_transcription_does_not_run_interaction_analysis(doctor_client, monkeypatch):
    client, generated_folder = doctor_client
    patient = register_patient(client)
    prescription_text = "Paracetamol 500 mg twice daily for 5 days after food"
    monkeypatch.setattr(
        app_module,
        "analyze_medicine_interactions",
        lambda *args: pytest.fail("Prescription saving must not run interaction analysis."),
    )

    response = client.post(
        "/generate-prescription",
        json={"patient_id": patient["patient_id"], "text": prescription_text},
    )

    assert response.status_code == 200
    result = response.get_json()
    assert result["patient_id"] == patient["patient_id"]
    assert result["doctor_id"] == "DOC-TEST"
    assert result["visit_id"]
    assert list(generated_folder.glob("*.pdf"))
    visit = doctor_database.get_patient_history(patient["patient_id"])[0]
    assert visit["patient_id"] == patient["patient_id"]
    assert visit["doctor_id"] == "DOC-TEST"
    assert visit["visit_date"]
    assert visit["pdf_path"] == result["filename"]
    assert visit["notes"] == prescription_text


def test_interaction_analysis_requires_explicit_history_review(doctor_client):
    client, _ = doctor_client
    response = client.post(
        "/doctor/interactions/analyze",
        json={
            "current_medicines": [],
            "medicines": [{"name": "Medicine A"}],
        },
    )

    assert response.status_code == 400
    assert "medication history was reviewed" in response.get_json()["error"]


def test_shared_clinic_doctor_access_is_role_guarded(doctor_client):
    client, _ = doctor_client
    patient = register_patient(client)
    with client.session_transaction() as app_session:
        app_session["user_id"] = "DOC-SECOND"
    assert client.get(
        f"/doctor/patients/{patient['patient_id']}/history"
    ).status_code == 200

    with client.session_transaction() as app_session:
        app_session["role"] = "medical_staff"
    assert client.get("/doctor/patients/search?patient_id=PT-1").status_code == 403
    assert client.post("/doctor/patients", json={}).status_code == 403


def test_unauthenticated_patient_endpoints_are_denied(doctor_client):
    client, _ = doctor_client
    with client.session_transaction() as app_session:
        app_session.clear()

    assert client.get("/doctor/patients/search?patient_id=PT-1").status_code == 401
    assert client.post("/doctor/patients", json={}).status_code == 401


def test_doctor_dashboard_renders_patient_workflow(doctor_client):
    client, _ = doctor_client
    response = client.get("/doctor/dashboard")

    assert response.status_code == 200
    assert b"Search patient" in response.data
    assert b"Register new patient" in response.data
    assert b"Voice-to-text prescription" in response.data
    assert b"Analyze interactions" not in response.data
    assert b"Current medication confirmation" not in response.data
    assert b"diagnosisInput" not in response.data
    assert b"visitNotesInput" not in response.data
