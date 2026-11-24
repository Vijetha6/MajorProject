import os
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
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

        def write_test_pdf(data, filepath):
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

    def test_free_text_parser_keeps_dose_schedule_food_and_timing(self):
        parsed = app_module.parse_prescription(
            "Paracetamol 500 mg 1-0-1-0 for 5 days after food Morning Evening\n"
            "Cetirizine 10 mg 0-0-0-1 for 3 days Bedtime"
        )

        self.assertEqual(
            [medicine["dose_schedule"] for medicine in parsed["medicines"]],
            ["1-0-1-0", "0-0-0-1"],
        )
        self.assertEqual(
            parsed["medicines"][0]["food_instruction"],
            "After food",
        )
        self.assertEqual(
            parsed["medicines"][0]["timing"],
            ["Morning", "Evening"],
        )
        self.assertEqual(
            parsed["medicines"][1]["timing"],
            ["Bedtime"],
        )
        self.assertEqual(
            app_module.parse_prescription(
                "Paracetamol 500 mg one zero one zero for 5 days"
            )["medicines"][0]["dose_schedule"],
            "1-0-1-0",
        )
        fallback_medicine = app_module.parse_medicine_segment(
            "Paracetamol 500 mg one-zero-one-zero for 5 days after food Morning Evening"
        )
        self.assertEqual(fallback_medicine["dose_schedule"], "1-0-1-0")
        self.assertEqual(
            app_module.parse_prescription(
                "Paracetamol 1-0-1-0 for 5 days"
            )["medicines"][0]["dosage"],
            "As directed",
        )

    def test_pdf_renders_schedule_and_instruction_rows(self):
        self.pdf_generator.stop()
        parsed = app_module.parse_prescription(
            "Paracetamol 500 mg 1-0-1-0 for 5 days after food Morning Evening\n"
            "Cetirizine 10 mg 0-0-0-1 for 3 days Bedtime"
        )
        data = {
            **parsed,
            "name": "Test Patient",
            "phone_number": "9876543210",
            "age": "22 years",
            "gender": "Other",
            "patient_id": self.patient["patient_id"],
            "visit_id": "VIS-PDF-TEST",
            "doctor": "test-doctor",
        }
        pdf_path = Path(self.output_dir.name) / "layout-test.pdf"

        original_fpdf = app_module.FPDF

        class UncompressedFPDF(original_fpdf):
            def __init__(self):
                super().__init__()
                self.set_compression(False)

        with patch.object(app_module, "FPDF", UncompressedFPDF):
            app_module.generate_prescription_pdf(data, str(pdf_path))
        pdf_contents = pdf_path.read_bytes().decode("latin-1")

        self.assertIn("Dose M-A-E-B", pdf_contents)
        self.assertIn("1-0-1-0", pdf_contents)
        self.assertIn("Food: After food | Timing: Morning, Evening", pdf_contents)
        self.assertIn("0-0-0-1", pdf_contents)
        self.assertNotIn("Frequency: As directed", pdf_contents)

    def test_ai_preview_reconciles_schedule_with_source_and_filters_formulations(self):
        response_data = {
            "medicines": [
                {
                    "name": "Gastro-resistant",
                    "dosage": "Dose not specified",
                    "frequency": "As directed",
                },
                {
                    "name": "Paracetamol",
                    "dosage": "500 mg",
                    "dose_schedule": "",
                    "frequency": "Once weekly",
                },
            ],
            "general_advice": [],
        }
        fake_client = SimpleNamespace(
            models=SimpleNamespace(
                generate_content=lambda **kwargs: SimpleNamespace(
                    text=json.dumps(response_data)
                )
            )
        )

        with patch.object(app_module, "client", fake_client), patch.object(
            app_module, "GEMINI_API_KEY", "test-key"
        ):
            result = app_module.extract_prescription_with_gemini(
                "Pantoprazole 40 mg 1-0-1-0 for 1 week before food\n"
                "Paracetamol 500 mg 0-0-1-0 for 3 days"
            )

        self.assertEqual(len(result["medicines"]), 1)
        self.assertEqual(result["medicines"][0]["name"], "Paracetamol")
        self.assertEqual(result["medicines"][0]["dose_schedule"], "0-0-1-0")
        self.assertEqual(result["medicines"][0]["frequency"], "As directed")

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
