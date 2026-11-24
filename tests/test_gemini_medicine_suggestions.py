import io
import json

import app as medicine_app
import database


class FakeGeminiClient:
    def __init__(self, response_text=None, error=None):
        self.response_text = response_text
        self.error = error
        self.prompt = None
        self.models = self

    def generate_content(self, **kwargs):
        self.prompt = kwargs["contents"]
        if self.error:
            raise self.error

        class Response:
            text = self.response_text

        return Response()


def test_gemini_parses_distinct_suggestions_and_does_not_infer_strength(monkeypatch):
    response = {
        "generic_name": "ingredient alpha",
        "brand_name": "Scanned Brand",
        "strength": "500 mg",
        "dosage_form": "tablet",
        "expiry_date": "Information not available",
        "uses": ["Use one"],
        "side_effects": [],
        "same_ingredient_alternatives": [
            {
                "brand_name": "Scanned Brand",
                "generic_name": "ingredient alpha",
                "strength": "500 mg",
                "dosage_form": "tablet",
            },
            {
                "brand_name": "Other Brand",
                "generic_name": "ingredient alpha",
                "strength": "Information not available",
                "dosage_form": "capsule",
            },
            {
                "brand_name": "Other Brand",
                "generic_name": "ingredient alpha",
                "strength": "20 mg",
                "dosage_form": "capsule",
            },
            {
                "brand_name": "Wrong Ingredient Brand",
                "generic_name": "ingredient beta",
                "strength": "100 mg",
                "dosage_form": "tablet",
            },
        ],
        "other_drug_options": [
            {"medicine_name": "Option One", "reason": "Different option"},
            {"medicine_name": "Option One", "reason": "Duplicate"},
            {"medicine_name": "Option Two", "reason": ""},
        ],
    }
    fake_client = FakeGeminiClient(json.dumps(response))
    monkeypatch.setattr(medicine_app, "client", fake_client)

    result = medicine_app.get_medicine_info_gemini(
        "OCR text",
        "expiry OCR",
        "English",
        generic_name="ingredient alpha",
        brand_name="Scanned Brand",
        strength="500 mg",
        dosage_form="tablet",
    )

    assert result["same_ingredient_alternatives"] == [
        {
            "brand_name": "Other Brand",
            "generic_name": "ingredient alpha",
            "strength": "Information not available",
            "dosage_form": "capsule",
        }
    ]
    assert result["other_drug_options"] == [
        {"medicine_name": "Option One", "reason": "Different option"},
        {"medicine_name": "Option Two", "reason": "Information not available"},
    ]
    assert "OCR text" in fake_client.prompt
    assert "ingredient alpha" in fake_client.prompt
    assert "Scanned Brand" in fake_client.prompt
    assert "500 mg" in fake_client.prompt
    assert "dosage form" in fake_client.prompt.lower()
    assert "alternatives" not in result


def test_uncertain_ingredient_suppresses_both_suggestion_categories(monkeypatch):
    response = {
        "generic_name": "Information not available",
        "brand_name": "Scanned Brand",
        "same_ingredient_alternatives": [
            {
                "brand_name": "Other Brand",
                "generic_name": "ingredient alpha",
                "strength": "10 mg",
                "dosage_form": "tablet",
            }
        ],
        "other_drug_options": [{"medicine_name": "Option One", "reason": "Reason"}],
    }
    monkeypatch.setattr(medicine_app, "client", FakeGeminiClient(json.dumps(response)))

    result = medicine_app.get_medicine_info_gemini("OCR text")

    assert result["same_ingredient_alternatives"] == []
    assert result["other_drug_options"] == []


def test_malformed_gemini_json_and_api_errors_return_none(monkeypatch):
    monkeypatch.setattr(medicine_app, "client", FakeGeminiClient("not valid json"))
    assert medicine_app.get_medicine_info_gemini("OCR text") is None

    monkeypatch.setattr(
        medicine_app,
        "client",
        FakeGeminiClient(error=RuntimeError("Gemini unavailable")),
    )
    assert medicine_app.get_medicine_info_gemini("OCR text") is None


def test_process_returns_suggestion_fields_when_gemini_fails(monkeypatch, tmp_path):
    upload_folder = tmp_path / "uploads"
    upload_folder.mkdir()
    monkeypatch.setattr(database, "DATABASE", tmp_path / "medicine_inventory.db")
    database.init_database()
    monkeypatch.setattr(medicine_app, "UPLOAD_FOLDER", str(upload_folder))
    monkeypatch.setattr(
        medicine_app,
        "TRAINING_IMAGES_FOLDER",
        str(tmp_path / "training_data" / "images"),
    )
    monkeypatch.setattr(medicine_app, "cleanup_old_files", lambda: None)
    monkeypatch.setattr(medicine_app.cv2, "imread", lambda _path: object())
    monkeypatch.setattr(medicine_app, "process_with_yolo", lambda _path: (None, None))
    monkeypatch.setattr(medicine_app, "extract_text_with_ocr", lambda _image: "OCR medicine text")
    monkeypatch.setattr(
        medicine_app,
        "extract_expiry_with_rotations",
        lambda _image: ("NOT FOUND", None, ""),
    )
    monkeypatch.setattr(medicine_app, "extract_medicine_name", lambda _text: "Scanned Brand")
    monkeypatch.setattr(medicine_app, "get_medicine_info_gemini", lambda *args, **kwargs: None)

    response = medicine_app.app.test_client().post(
        "/process",
        data={"images": (io.BytesIO(b"image bytes"), "medicine.jpg")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    result = response.get_json()[0]
    assert result["same_ingredient_alternatives"] == []
    assert result["other_drug_options"] == []
    assert result["brand_name"] == "Scanned Brand"
    assert result["source"] == "Gemini (error)"
