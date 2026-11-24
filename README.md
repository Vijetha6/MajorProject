# MedInfo
Developed an AI-based system to identify medicines from images and automatically extract the medicine name and expiry date using OCR and machine learning techniques. 
The system applies image preprocessing and object detection methods to handle variations in lighting, orientation, and packaging design, ensuring accurate recognition in real-world conditions. 
It also integrates information validation and provides bilingual output (English and Kannada) to enhance usability and accessibility for regional users. 
verall, the project focuses on improving healthcare safety by reducing manual errors in medicine verification and promoting safer medication practices.

## Medicine image archive for future training

Images submitted to the medicine scanner are copied to `training_data/images/`, separately from temporary uploads that are cleaned up. The original filename, SHA-256 hash, OCR text, scan status, and extracted medicine details are recorded in the `training_images` table in `medicine_inventory.db`. The `verified_label` field is left empty so OCR/AI suggestions are not mistaken for reviewed training labels. The archive is private (not served as static files) and ignored by Git; back up this folder and the database separately if you need to preserve the dataset. Do not upload patient-identifiable images.

## Role-based sign-in

The Doctor and Medical Staff dashboards use separate IDs and passwords read from the ignored `.env` file. Passwords are compared on the Flask backend and are never rendered into frontend code:

```text
FLASK_SECRET_KEY=<a random secret>
DOCTOR_ID=<doctor login ID>
DOCTOR_PASSWORD=<doctor development password>
STAFF_ID=<medical staff login ID>
STAFF_PASSWORD=<medical staff development password>
EXPIRY_WARNING_DAYS=7
TWILIO_ACCOUNT_SID=<Twilio account SID>
TWILIO_AUTH_TOKEN=<Twilio auth token>
TWILIO_PHONE_NUMBER=<Twilio sender number>
```

Use a unique random Flask secret, and use non-demo passwords outside local development. Set `SESSION_COOKIE_SECURE=true` when serving the application over HTTPS. Local HTTP development leaves this setting false. Start the application with `python app.py`.

Prescription PDFs do not contain QR codes. When Google Drive and Twilio are configured and the patient has a phone number, the app uploads the PDF to Drive and sends the Drive viewing link by SMS. Drive OAuth uses `credentials.json` and `token.pickle` in the project folder. SMS is sent only after the Drive upload succeeds, and the Doctor dashboard reports upload or SMS failures. Drive files are shared with anyone who has the link, so treat SMS links as private.

The Medical Staff expiry monitor warns about medicines expiring within `EXPIRY_WARNING_DAYS` days (default: 7). When the staff dashboard loads, it also checks the existing inventory for expired medicines and displays a dismissible alert with stock and location details. Dismissing the popup leaves expired entries available in Expiry Alerts. The staff-only expiring-medicines API also accepts a `days` query parameter to override the threshold for an individual request.

## Doctor patient records and e-prescriptions

Authenticated Doctors can search patients by Patient ID or mobile number, register a new patient, review visit history, confirm which historical medicines are currently being taken, and save a new visit with an e-prescription PDF. Each visit stores its own medicines and is linked to the permanent Patient ID and the authenticated Doctor ID. Updating a patient's mobile number does not change the Patient ID or detach prior visits. Medical Staff and public users cannot access these records.

Patient and prescription data is kept in the separate `doctor_records.db`; the medicine inventory remains in `medicine_inventory.db`. The Doctor database enforces SQLite foreign keys and transaction-scoped writes. It is local runtime data and is excluded from Git. Back up `doctor_records.db` before any future schema migration or database maintenance.

The project currently has no verified medicine-interaction knowledge base or RAG implementation. The Doctor workflow exposes an explicit integration point and reports interaction analysis as unavailable until a verified source is configured. An unavailable analysis is not a finding that no interaction exists; the Doctor must make the clinical decision.
