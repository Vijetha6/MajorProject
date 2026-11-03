# MedInfo
Developed an AI-based system to identify medicines from images and automatically extract the medicine name and expiry date using OCR and machine learning techniques. 
The system applies image preprocessing and object detection methods to handle variations in lighting, orientation, and packaging design, ensuring accurate recognition in real-world conditions. 
It also integrates information validation and provides bilingual output (English and Kannada) to enhance usability and accessibility for regional users. 
verall, the project focuses on improving healthcare safety by reducing manual errors in medicine verification and promoting safer medication practices.

## Doctor prescription setup

Before generating prescription PDFs, set the actual registered doctor and
clinic names in the local `.env` file: `DOCTOR_NAME` and `CLINIC_NAME`.
`CLINIC_TAGLINE`, `CLINIC_ADDRESS`, `CLINIC_PHONE`, and `CLINIC_EMAIL` are
optional and blank values are omitted from the PDF. Copy the variable names
from `.env.example`; do not commit real credentials. The generator reports
missing required identities instead of using fabricated doctor or clinic
details.

Doctors enter each medicine as structured data, review the complete list, and
confirm it before generating. The optional Indian-style dose schedule is
doctor-entered as Morning-Afternoon-Evening-Bedtime (for example,
`1-0-0-1`) and is never applied automatically. The PDF is stored locally and indexed in
SQLite, with a tokenized download link and QR code. It shows a blank doctor
signature line; it is not digitally signed. Google Drive upload is disabled by
default and can be enabled with `GOOGLE_DRIVE_UPLOAD_ENABLED=True`. SMS also
requires valid Twilio settings and either a public `PUBLIC_BASE_URL` or a
successful Drive link. Integration failures do not remove the local PDF.

The `/generate-prescription` endpoint continues to accept the legacy `text`
field for lines in the form `Medicine name 500 mg once daily for 1 week`.
Structured medicine requests must include `review_confirmed: true`.
