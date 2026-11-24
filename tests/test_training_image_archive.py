import hashlib
import io
import os
import time

import app as medicine_app
import database


def test_process_archives_image_and_metadata_beyond_temp_cleanup(monkeypatch, tmp_path):
    upload_folder = tmp_path / "uploads"
    archive_folder = tmp_path / "training_data" / "images"
    upload_folder.mkdir()
    monkeypatch.setattr(medicine_app, "UPLOAD_FOLDER", str(upload_folder))
    monkeypatch.setattr(medicine_app, "TRAINING_IMAGES_FOLDER", str(archive_folder))
    monkeypatch.setattr(database, "DATABASE", tmp_path / "inventory.db")
    database.init_database()

    monkeypatch.setattr(medicine_app.cv2, "imread", lambda _path: object())
    monkeypatch.setattr(medicine_app, "process_with_yolo", lambda _path: (None, None))
    monkeypatch.setattr(
        medicine_app,
        "extract_text_with_ocr",
        lambda _image: "Paracetamol 500 mg EXP AUG 2027",
    )
    monkeypatch.setattr(
        medicine_app,
        "extract_expiry_with_rotations",
        lambda _image: ("NOT FOUND", None, ""),
    )
    monkeypatch.setattr(medicine_app, "extract_medicine_name", lambda _text: "Paracetamol")
    monkeypatch.setattr(medicine_app, "get_medicine_info_gemini", lambda *args, **kwargs: None)

    image_bytes = b"original uploaded image"
    response = medicine_app.app.test_client().post(
        "/process",
        data={"images": (io.BytesIO(image_bytes), "medicine.jpg")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    result = response.get_json()[0]
    assert result["training_archive_status"] == "saved"
    record = database.get_training_image(result["training_image_id"])
    archived_file = archive_folder / record["stored_filename"]
    assert archived_file.read_bytes() == image_bytes
    assert record["original_filename"] == "medicine.jpg"
    assert record["sha256"] == hashlib.sha256(image_bytes).hexdigest()
    assert record["processing_status"] == "processed"
    assert record["extracted_text"] == "Paracetamol 500 mg EXP AUG 2027"
    assert record["brand_name"] == "Paracetamol"
    assert record["verified_label"] is None

    old_timestamp = time.time() - 3 * 24 * 60 * 60
    temporary_file = next(upload_folder.iterdir())
    os.utime(temporary_file, (old_timestamp, old_timestamp))
    os.utime(archived_file, (old_timestamp, old_timestamp))
    medicine_app.cleanup_old_files()

    assert not temporary_file.exists()
    assert archived_file.exists()


def test_archive_failure_is_reported_in_scan_result(monkeypatch, tmp_path):
    upload_folder = tmp_path / "uploads"
    upload_folder.mkdir()
    monkeypatch.setattr(medicine_app, "UPLOAD_FOLDER", str(upload_folder))

    def fail_archive(*_args):
        raise OSError("disk unavailable")

    monkeypatch.setattr(medicine_app, "archive_uploaded_training_image", fail_archive)
    response = medicine_app.app.test_client().post(
        "/process",
        data={"images": (io.BytesIO(b"image bytes"), "medicine.jpg")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    result = response.get_json()[0]
    assert result["training_archive_status"] == "failed"
    assert "could not be saved" in result["training_archive_error"].lower()
