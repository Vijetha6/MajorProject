# Medicine Inventory API

Base URL:
http://127.0.0.1:5000

## 1. Add Medicine

POST /add-medicine

Example JSON:
{
    "medicine_name": "Paracetamol",
    "brand_name": "Crocin",
    "generic_name": "Paracetamol",
    "strength": "500mg",
    "dosage_form": "Tablet",
    "expiry_date": "2027-12-31",
    "quantity": 75,
    "row_number": 2,
    "column_number": 5
}

## 2. Get All Medicines

GET /medicines

## 3. Get One Medicine

GET /medicine/<id>

Example:
GET /medicine/1

## 4. Search Medicine

GET /search-medicine?q=Paracetamol

## 5. Update Medicine

PUT /medicine/<id>

## 6. Update Quantity

PUT /medicine/<id>/quantity

Example JSON:
{
    "quantity": 50
}

## 7. Delete Medicine

DELETE /medicine/<id>

## 8. Get Medicine Location

GET /medicine/<id>/location

Example:
GET /medicine/1/location

Response:
{
    "medicine_id": 1,
    "medicine_name": "Paracetamol",
    "row_number": 2,
    "column_number": 5
}

## 9. Low Stock Medicines

GET /medicines/low-stock

Optional:
GET /medicines/low-stock?threshold=10

## 10. Expiring Medicines

GET /medicines/expiring?days=30

## 11. Expired Medicines

GET /medicines/expired

## 12. Generate a Doctor Prescription

POST `/generate-prescription` with `Content-Type: application/json`.
Structured requests require the doctor to review the medicine list and send
`review_confirmed: true`. Reuse the same `Idempotency-Key` header when retrying
the same request; a reused key with changed prescription details returns 409.

```json
{
  "patient_name": "Patient name",
  "age": "35",
  "gender": "Other",
  "phone_number": "9876543210",
  "review_confirmed": true,
  "medicines": [
    {
      "name": "Medicine name",
      "dosage": "As prescribed",
      "dose_schedule": "1-0-0-1",
      "frequency": "Once daily",
      "timing": ["Morning"],
      "food_instruction": "After food",
      "duration": "As prescribed",
      "special_instructions": ""
    }
  ]
}
```

Frequency, dosage, dose schedule, and duration are supplied and approved by
the doctor; the server does not infer or alter them. `dose_schedule` is
optional and, when provided, uses four hyphen-separated values in
Morning-Afternoon-Evening-Bedtime order. Hyphens or spaces are accepted
(for example, `1-0-0-1` or `1 0 0 1`). The server never fills it
automatically. Required clinic identity/contact settings
(`DOCTOR_NAME` and `CLINIC_NAME`) must be configured in `.env`. Tagline,
address, phone, and email are optional; blank values are omitted from the PDF.
Missing required identities return HTTP 503 rather than using placeholder
details.

On success, the response contains one tokenized `download_url` and a
`prescription_id`. Download the PDF with `GET` on that URL. The PDF and its
prescription details are stored locally and in SQLite. Google Drive is
optional (`GOOGLE_DRIVE_UPLOAD_ENABLED=True`); Twilio SMS requires its
environment settings and a public `PUBLIC_BASE_URL` or an available Drive
link. An external integration failure does not invalidate local generation.

For legacy clients, a `text` field is still accepted if each line has an
explicit name, dosage with units, recognized frequency, and duration, for
example `Medicine name 500 mg once daily for 1 week`. Incomplete or ambiguous
lines are rejected rather than filled in with guessed prescription details.