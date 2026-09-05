import argparse
import os

from drive_upload import upload_pdf_to_drive


def upload_one_pdf(pdf_path=None):
    project_root = os.path.dirname(os.path.abspath(__file__))
    generated_dir = os.path.join(project_root, "generated")

    if pdf_path is None:
        pdf_files = [
            os.path.join(generated_dir, name)
            for name in sorted(os.listdir(generated_dir))
            if name.lower().endswith(".pdf")
        ]
        if not pdf_files:
            raise FileNotFoundError("No PDF files found in the generated folder.")
        pdf_path = pdf_files[0]
    else:
        pdf_path = os.path.join(project_root, pdf_path) if not os.path.isabs(pdf_path) else pdf_path

    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    print(f"Uploading PDF: {pdf_path}")
    drive_url = upload_pdf_to_drive(pdf_path)
    print("Google Drive URL:", drive_url)
    return drive_url


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload one generated PDF to Google Drive.")
    parser.add_argument(
        "pdf_path",
        nargs="?",
        default=None,
        help="Optional relative or absolute path to a PDF file. Defaults to the newest PDF in generated/.",
    )
    args = parser.parse_args()
    upload_one_pdf(args.pdf_path)
