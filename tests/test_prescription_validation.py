import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ["GEMINI_API_KEY"] = "test-key"
os.environ["ROBOFLOW_API_KEY"] = ""

import dotenv

dotenv.load_dotenv = lambda *args, **kwargs: False

import database

_test_database_dir = tempfile.TemporaryDirectory()
database.DATABASE = Path(_test_database_dir.name) / "test.db"

import doctor_database
import app as app_module


class PrescriptionValidationTests(unittest.TestCase):
    def setUp(self):
        self.doctor_database_dir = tempfile.TemporaryDirectory()
        self.previous_doctor_database = doctor_database.DATABASE
        doctor_database.DATABASE = Path(self.doctor_database_dir.name) / "doctor.db"
        doctor_database.init_database()
        self.patient = doctor_database.register_patient(
            "Test Patient",
            22,
            "Other",
            "9876543210",
            "",
            "test-doctor",
        )
        self.client = app_module.app.test_client()
        with self.client.session_transaction() as app_session:
            app_session["role"] = "doctor"
            app_session["user_id"] = "test-doctor"
        self.output_dir = tempfile.TemporaryDirectory()
        self.previous_generated_folder = app_module.GENERATED_FOLDER
        app_module.GENERATED_FOLDER = self.output_dir.name

        def write_test_pdf(data, download_url, filepath):
            Path(filepath).write_bytes(b"%PDF-1.4 test")

        self.pdf_generator = patch.object(
            app_module,
            "generate_prescription_pdf",
            side_effect=write_test_pdf,
        )
        self.generate_pdf = self.pdf_generator.start()
        self.drive_upload = patch.object(
            app_module, "upload_pdf_to_drive", return_value=None
        )
        self.drive_upload.start()
        self.sms = patch.object(app_module, "send_sms")
        self.sms.start()

    def tearDown(self):
        self.sms.stop()
        self.drive_upload.stop()
        self.pdf_generator.stop()
        app_module.GENERATED_FOLDER = self.previous_generated_folder
        doctor_database.DATABASE = self.previous_doctor_database
        self.doctor_database_dir.cleanup()
        self.output_dir.cleanup()

    def request_structured(self, medicines=None, **extra):
        payload = {
            "patient_id": self.patient["patient_id"],
            "medicines": medicines if medicines is not None else [
                {"name": "Paracetamol", "dosage": "500 mg"}
            ],
        }
        payload.update(extra)
        return self.client.post("/generate-prescription", json=payload)

    def assert_rejected_without_pdf(self, response, expected_field):
        self.assertEqual(response.status_code, 400)
        self.assertIn(expected_field, response.get_json()["missing_fields"])
        self.generate_pdf.assert_not_called()
        self.assertEqual(list(Path(self.output_dir.name).iterdir()), [])

    def test_missing_patient_id_is_rejected(self):
        response = self.client.post(
            "/generate-prescription",
            json={"medicines": [{"name": "Paracetamol", "dosage": "500 mg"}]},
        )
        self.assertEqual(response.status_code, 400)
        self.generate_pdf.assert_not_called()
        self.assertEqual(list(Path(self.output_dir.name).iterdir()), [])

    def test_missing_medicine_name_is_rejected(self):
        response = self.request_structured(
            medicines=[{"name": "", "dosage": "500 mg"}]
        )
        self.assert_rejected_without_pdf(response, "medicines[0].name")

    def test_missing_medicine_dosage_is_rejected(self):
        response = self.request_structured(
            medicines=[{"name": "Paracetamol", "dosage": ""}]
        )
        self.assert_rejected_without_pdf(response, "medicines[0].dosage")

    def test_incomplete_entry_among_multiple_medicines_is_rejected(self):
        response = self.request_structured(
            medicines=[
                {"name": "Paracetamol", "dosage": "500 mg"},
                {"name": "Cetirizine", "dosage": ""},
            ]
        )
        self.assert_rejected_without_pdf(response, "medicines[1].dosage")

    def test_legacy_text_rejects_missing_dosage(self):
        response = self.client.post(
            "/generate-prescription",
            json={
                "patient_id": self.patient["patient_id"],
                "current_medicines": [],
                "current_medicines_confirmed": True,
                "text": "Paracetamol once daily for 7 days",
            },
        )
        self.assert_rejected_without_pdf(response, "medicines[0].dosage")

    def test_legacy_text_rejects_a_medicine_line_without_a_name(self):
        response = self.client.post(
            "/generate-prescription",
            json={
                "patient_id": self.patient["patient_id"],
                "current_medicines": [],
                "current_medicines_confirmed": True,
                "text": "Paracetamol 500 mg\n500 mg",
            },
        )
        self.assert_rejected_without_pdf(response, "medicines[1].name")

    def test_valid_prescription_generates_pdf_with_optional_fields_blank(self):
        response = self.request_structured(
            medicines=[
                {
                    "name": "Paracetamol",
                    "dosage": "500 mg",
                    "frequency": "",
                    "food_instruction": "",
                    "duration": "",
                }
            ],
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])
        self.generate_pdf.assert_called_once()
        self.assertTrue(list(Path(self.output_dir.name).glob("*.pdf")))

    def test_valid_prescription_generates_a_nonempty_pdf(self):
        self.pdf_generator.stop()
        response = self.request_structured()

        self.assertEqual(response.status_code, 200)
        pdf_path = Path(self.output_dir.name) / response.get_json()["filename"]
        self.assertTrue(pdf_path.is_file())
        self.assertGreater(pdf_path.stat().st_size, 0)
        self.assertTrue(pdf_path.read_bytes().startswith(b"%PDF"))

    def test_valid_legacy_text_generates_pdf(self):
        payload = {
            "patient_id": self.patient["patient_id"],
            "text": "Paracetamol 500 mg once daily for 7 days",
        }
        response = self.client.post("/generate-prescription", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])
        self.generate_pdf.assert_called_once()


if __name__ == "__main__":
    unittest.main()
