import os

os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("ROBOFLOW_API_KEY", "")

import dotenv

dotenv.load_dotenv = lambda *args, **kwargs: False

import database
import app as medicine_app


def configure_auth(monkeypatch, tmp_path):
    database_path = tmp_path / "auth-test.db"
    monkeypatch.setattr(database, "DATABASE", database_path)
    database.init_database()
    monkeypatch.setitem(
        medicine_app.app.config,
        "AUTH_USERS",
        {
            "doctor": {
                "user_id": "doctor-test",
                "password": "doctor-password",
            },
            "medical_staff": {
                "user_id": "staff-test",
                "password": "staff-password",
            },
        },
    )
    return medicine_app.app.test_client()


def test_login_pages_and_direct_dashboard_access(monkeypatch, tmp_path):
    client = configure_auth(monkeypatch, tmp_path)

    doctor_login = client.get("/doctor/login")
    staff_login = client.get("/staff/login")
    assert doctor_login.status_code == 200
    assert b"Doctor ID" in doctor_login.data
    assert b'>Back</a>' in doctor_login.data
    assert staff_login.status_code == 200
    assert b"Staff ID" in staff_login.data
    assert b'>Back</a>' in staff_login.data
    assert client.get("/doctor/dashboard").headers["Location"].endswith("/doctor/login")
    assert client.get("/staff/dashboard").headers["Location"].endswith("/staff/login")


def test_homepage_has_only_three_role_choices_and_keeps_patient_route():
    response = medicine_app.app.test_client().get("/")

    assert response.status_code == 200
    assert response.data.count(b'class="role-button"') == 3
    assert b"Doctor Login" not in response.data
    assert b"Medical Staff Login" not in response.data
    assert b'data-section-target="scanSection">Patient</button>' in response.data
    assert b'href="/doctor/login">Doctor</a>' in response.data
    assert b'href="/staff/login">Medical Staff</a>' in response.data


def test_doctor_can_login_and_only_sees_doctor_dashboard(monkeypatch, tmp_path):
    client = configure_auth(monkeypatch, tmp_path)
    response = client.post(
        "/doctor/login",
        data={"user_id": "doctor-test", "password": "doctor-password"},
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/doctor/dashboard")
    dashboard = client.get("/doctor/dashboard")
    assert dashboard.status_code == 200
    assert b'id="generatorTab"' in dashboard.data
    assert b'id="inventorySection"' not in dashboard.data
    assert b'id="alertsSection"' not in dashboard.data
    assert client.get("/medicines").status_code == 403
    assert client.get("/medicines/expiring").status_code == 403
    assert client.get("/medicines/expired").status_code == 403
    assert client.post("/generate-prescription", json={}).status_code == 400


def test_staff_can_login_and_only_access_staff_resources(monkeypatch, tmp_path):
    client = configure_auth(monkeypatch, tmp_path)
    response = client.post(
        "/staff/login",
        data={"user_id": "staff-test", "password": "staff-password"},
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/staff/dashboard")
    dashboard = client.get("/staff/dashboard")
    assert dashboard.status_code == 200
    assert b'id="inventorySection"' in dashboard.data
    assert b'id="generatorTab"' not in dashboard.data
    assert b'id="alertsSection"' in dashboard.data
    assert client.get("/medicines").status_code == 200
    assert client.get("/medicines/expiring").status_code == 200
    assert client.get("/medicines/expired").status_code == 200
    assert client.post("/generate-prescription", json={}).status_code == 403


def test_patient_cannot_access_staff_expiry_notifications():
    client = medicine_app.app.test_client()

    assert client.get("/medicines/expiring").status_code == 401
    assert client.get("/medicines/expired").status_code == 401
    assert b'id="alertsSection"' not in client.get("/").data


def test_invalid_credentials_do_not_create_a_session(monkeypatch, tmp_path):
    client = configure_auth(monkeypatch, tmp_path)
    response = client.post(
        "/doctor/login",
        data={"user_id": "doctor-test", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert b"The ID or password is incorrect." in response.data
    assert client.get("/doctor/dashboard").status_code == 302


def test_logout_clears_the_role_session(monkeypatch, tmp_path):
    client = configure_auth(monkeypatch, tmp_path)
    client.post(
        "/staff/login",
        data={"user_id": "staff-test", "password": "staff-password"},
    )
    assert client.get("/staff/dashboard").status_code == 200

    assert client.post("/logout").status_code == 302
    assert client.get("/staff/dashboard").headers["Location"].endswith("/staff/login")


def test_unconfigured_credentials_fail_closed(monkeypatch, tmp_path):
    client = configure_auth(monkeypatch, tmp_path)
    monkeypatch.setitem(
        medicine_app.app.config["AUTH_USERS"],
        "doctor",
        {"user_id": "", "password": ""},
    )

    response = client.post(
        "/doctor/login",
        data={"user_id": "doctor-test", "password": "doctor-password"},
    )
    assert response.status_code == 503
    assert b"Login is not configured" in response.data
