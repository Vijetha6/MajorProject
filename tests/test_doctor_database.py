import sqlite3

import pytest

import doctor_database


@pytest.fixture
def doctor_db(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor_database, "DATABASE", tmp_path / "doctor-test.db")
    doctor_database.init_database()
    return doctor_database.DATABASE


def register(doctor_id="doctor-1", name="Asha Rao", mobile="9876543210"):
    return doctor_database.register_patient(
        name, 38, "Female", mobile, "Bengaluru", doctor_id
    )


def test_patient_id_is_stable_and_searchable_by_id_and_mobile(doctor_db):
    patient = register()

    assert patient["patient_id"].startswith("PT-")
    assert doctor_database.search_patients(patient_id=patient["patient_id"]) == [patient]
    assert doctor_database.search_patients(mobile_number="+91 9876543210") == [patient]


def test_exact_name_and_mobile_duplicate_is_rejected(doctor_db):
    register()

    with pytest.raises(doctor_database.DuplicatePatientError) as error:
        register(name="asha rao")

    assert len(error.value.patients) == 1


def test_visit_and_medicines_are_saved_and_returned_newest_first(doctor_db):
    patient = register()
    older_visit = doctor_database.save_visit(
        patient["patient_id"],
        "doctor-1",
        "Headache",
        "",
        "generated/older.pdf",
        [{"name": "Medicine A", "dosage": "10 mg", "frequency": "Daily"}],
        visit_id="VIS-OLDER",
    )
    newer_visit = doctor_database.save_visit(
        patient["patient_id"],
        "doctor-2",
        "Follow-up",
        "Notes",
        "generated/newer.pdf",
        [
            {
                "name": "Medicine B",
                "dosage": "20 mg",
                "frequency": "Twice daily",
                "duration": "5 days",
                "instructions": "After food",
                "timing": ["Morning", "Evening"],
            },
            {"name": "Medicine C", "dosage": "1 tablet"},
        ],
        visit_id="VIS-NEWER",
    )

    history = doctor_database.get_patient_history(patient["patient_id"])

    assert [visit["visit_id"] for visit in history] == [newer_visit, older_visit]
    assert history[0]["doctor_id"] == "doctor-2"
    assert [medicine["medicine_name"] for medicine in history[0]["medicines"]] == [
        "Medicine B",
        "Medicine C",
    ]
    assert history[0]["medicines"][0]["timing"] == ["Morning", "Evening"]


def test_visit_lookup_requires_the_matching_patient_id(doctor_db):
    first_patient = register(name="First Patient", mobile="9876543210")
    second_patient = register(name="Second Patient", mobile="9876543211")
    visit_id = doctor_database.save_visit(
        first_patient["patient_id"],
        "doctor-1",
        "",
        "",
        "generated/test.pdf",
        [{"name": "Medicine A", "dosage": "10 mg"}],
    )

    assert doctor_database.get_patient_visit(
        second_patient["patient_id"], visit_id
    ) is None


def test_foreign_keys_are_enabled_and_invalid_patient_visit_rolls_back(doctor_db):
    connection = doctor_database.get_connection()
    try:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        connection.close()

    with pytest.raises(sqlite3.IntegrityError):
        doctor_database.save_visit(
            "missing-patient",
            "doctor-1",
            "",
            "",
            "generated/missing.pdf",
            [{"name": "Medicine A", "dosage": "10 mg"}],
        )

    connection = sqlite3.connect(doctor_db)
    try:
        assert connection.execute("SELECT COUNT(*) FROM visits").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM visit_medicines").fetchone()[0] == 0
    finally:
        connection.close()
