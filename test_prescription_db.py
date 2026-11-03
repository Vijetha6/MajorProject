"""Synthetic functional test for prescription DB functions. Uses a test DB."""
import sqlite3, os, tempfile, sys
from pathlib import Path

# Point DATABASE at a temp file for isolation
import database as db_mod
_orig_db = db_mod.DATABASE
db_mod.DATABASE = Path(tempfile.mktemp(suffix=".db"))

try:
    db_mod.init_database()
    db_mod.init_prescription_database()

    # save_prescription
    pid, token = db_mod.save_prescription({
        "patient_name": "TEST_PATIENT",
        "phone_number": "+91TEST0000",
        "age": "30 years",
        "gender": "Male",
        "filename": "prescription_TEST_PATIENT_20260101_120000.pdf",
    })
    assert isinstance(pid, int) and pid > 0, f"Bad prescription_id: {pid}"
    assert len(token) == 32, f"Bad token length: {len(token)}"
    print(f"save_prescription OK  -> id={pid}, token={token}")

    # get_prescription_by_token
    rec = db_mod.get_prescription_by_token(token)
    assert rec is not None, "Token lookup returned None"
    assert rec["patient_name"] == "TEST_PATIENT"
    assert rec["download_token"] == token
    print("get_prescription_by_token OK ->", rec["patient_name"])

    # get_patient_prescriptions
    records = db_mod.get_patient_prescriptions("+91TEST0000")
    assert len(records) == 1
    assert records[0]["id"] == pid
    print("get_patient_prescriptions OK -> count =", len(records))

    # invalid token returns None
    missing = db_mod.get_prescription_by_token("a" * 32)
    assert missing is None
    print("Missing token returns None OK")

    print("\nAll DB function tests PASSED.")
finally:
    try:
        os.unlink(db_mod.DATABASE)
    except Exception:
        pass
    db_mod.DATABASE = _orig_db
