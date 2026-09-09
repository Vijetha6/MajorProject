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