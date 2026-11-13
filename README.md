# MedInfo
Developed an AI-based system to identify medicines from images and automatically extract the medicine name and expiry date using OCR and machine learning techniques. 
The system applies image preprocessing and object detection methods to handle variations in lighting, orientation, and packaging design, ensuring accurate recognition in real-world conditions. 
It also integrates information validation and provides bilingual output (English and Kannada) to enhance usability and accessibility for regional users. 
verall, the project focuses on improving healthcare safety by reducing manual errors in medicine verification and promoting safer medication practices.

## Role-based sign-in

The Doctor and Medical Staff dashboards use separate IDs and passwords read from the ignored `.env` file. Passwords are compared on the Flask backend and are never rendered into frontend code:

```text
FLASK_SECRET_KEY=<a random secret>
DOCTOR_ID=<doctor login ID>
DOCTOR_PASSWORD=<doctor development password>
STAFF_ID=<medical staff login ID>
STAFF_PASSWORD=<medical staff development password>
```

Use a unique random Flask secret, and use non-demo passwords outside local development. Set `SESSION_COOKIE_SECURE=true` when serving the application over HTTPS. Local HTTP development leaves this setting false. Start the application with `python app.py`.

## Doctor patient records and e-prescriptions

Authenticated Doctors can search patients by Patient ID or mobile number, register a new patient, review visit history, confirm which historical medicines are currently being taken, and save a new visit with an e-prescription PDF. Each visit stores its own medicines and is linked to the permanent Patient ID and the authenticated Doctor ID. Updating a patient's mobile number does not change the Patient ID or detach prior visits. Medical Staff and public users cannot access these records.

Patient and prescription data is kept in the separate `doctor_records.db`; the medicine inventory remains in `medicine_inventory.db`. The Doctor database enforces SQLite foreign keys and transaction-scoped writes. It is local runtime data and is excluded from Git. Back up `doctor_records.db` before any future schema migration or database maintenance.

The project currently has no verified medicine-interaction knowledge base or RAG implementation. The Doctor workflow exposes an explicit integration point and reports interaction analysis as unavailable until a verified source is configured. An unavailable analysis is not a finding that no interaction exists; the Doctor must make the clinical decision.
