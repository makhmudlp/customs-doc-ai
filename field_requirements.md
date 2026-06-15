# Mandatory Fields — Extraction Source of Truth

**Status: DRAFT / PLACEHOLDER.** This document defines which fields the system
must extract from each customs document type. It stands in for the "separate
requirements document" referenced in the assignment. If the official version is
provided later, replace the field tables below and regenerate the matching code
(the Pydantic models in `llm_service.py`) to mirror them.

---

## How to read this file

Each document type lists its fields with four columns:

- **JSON key** — the exact key that must appear in the extracted JSON object
  (snake_case, machine-readable).
- **Description** — what the field means; this text feeds the "specialized
  prompt" given to Qwen.
- **Type** — the expected value type:
  - `string` — text
  - `number` — numeric value (no currency symbol, no thousands separators)
  - `date` — ISO format `YYYY-MM-DD`
  - `object` — a nested group of sub-fields
  - `array` — a list (used for repeating rows like line items / packages)
- **Required** — `yes` = mandatory; `no` = include if present, else `null`.

### Global rules (apply to every document type)

1. The output is always a **single JSON object**, nothing else.
2. Any field that cannot be found in the text is returned as `null`
   (never invented, never guessed).
3. Money is split: a numeric amount field **plus** a separate `currency`
   field (ISO code, e.g. `USD`, `EUR`, `UZS`).
4. Dates are normalized to `YYYY-MM-DD`.
5. Names/addresses are captured verbatim as written, in their original
   language (Uzbek, Russian, or English).

---

## 1. Invoice (`invoice`)

A commercial invoice: the binding record of the transaction used by customs to
assess value and duties.

| JSON key | Description | Type | Required |
|---|---|---|---|
| `invoice_number` | The invoice's unique reference number | string | yes |
| `invoice_date` | Date the invoice was issued | date | yes |
| `seller` | Exporter/seller: `{ "name", "address" }` | object | yes |
| `buyer` | Importer/buyer (consignee): `{ "name", "address" }` | object | yes |
| `country_of_origin` | Country where the goods were produced | string | yes |
| `country_of_destination` | Country the goods are shipped to | string | yes |
| `incoterms` | Delivery terms (e.g. FOB, CIF, EXW) | string | no |
| `currency` | ISO currency code of all amounts | string | yes |
| `line_items` | One entry per product row (see sub-fields) | array | yes |
| `total_amount` | Total invoice value as a number | number | yes |
| `net_weight` | Total net weight (kg) | number | no |
| `gross_weight` | Total gross weight (kg) | number | no |
| `payment_terms` | Agreed payment terms | string | no |

**`line_items` sub-fields** (each element of the array):

| JSON key | Description | Type | Required |
|---|---|---|---|
| `description` | Description of the goods | string | yes |
| `hs_code` | Harmonized System tariff code | string | no |
| `quantity` | Number of units | number | yes |
| `unit` | Unit of measure (pcs, kg, box, etc.) | string | no |
| `unit_price` | Price per unit | number | no |
| `amount` | Line total (quantity × unit_price) | number | yes |

---

## 2. Packing List (`packing_list`)

A physical inventory of the shipment: what is in each package, with weights and
counts. Carries no pricing.

| JSON key | Description | Type | Required |
|---|---|---|---|
| `packing_list_number` | Reference number of the packing list | string | no |
| `date` | Date the packing list was issued | date | no |
| `seller` | Shipper/seller: `{ "name", "address" }` | object | yes |
| `buyer` | Consignee/buyer: `{ "name", "address" }` | object | yes |
| `packages` | One entry per package (see sub-fields) | array | yes |
| `total_packages` | Total number of packages | number | yes |
| `total_net_weight` | Sum of net weights (kg) | number | no |
| `total_gross_weight` | Sum of gross weights (kg) | number | no |

**`packages` sub-fields** (each element of the array):

| JSON key | Description | Type | Required |
|---|---|---|---|
| `package_number` | Package or carton number | string | no |
| `marks_and_numbers` | Shipping marks / labels on the package | string | no |
| `description` | Description of contents | string | yes |
| `quantity` | Number of units in the package | number | yes |
| `net_weight` | Net weight of the package (kg) | number | no |
| `gross_weight` | Gross weight of the package (kg) | number | no |
| `dimensions` | Package dimensions (e.g. 40×30×20 cm) | string | no |

---

## 3. Air Waybill (`awb`)

The transport contract for air freight, in IATA-standard format. The AWB number
is an 11-digit code: a 3-digit airline prefix followed by an 8-digit serial.

| JSON key | Description | Type | Required |
|---|---|---|---|
| `awb_number` | Air waybill number (prefix + serial) | string | yes |
| `shipper` | Sender: `{ "name", "address" }` | object | yes |
| `consignee` | Receiver: `{ "name", "address" }` | object | yes |
| `airport_of_departure` | Origin airport (name or IATA code) | string | yes |
| `airport_of_destination` | Destination airport (name or IATA code) | string | yes |
| `carrier` | Issuing airline / carrier | string | no |
| `flight_number` | Flight number | string | no |
| `flight_date` | Scheduled flight date | date | no |
| `number_of_pieces` | Number of pieces / packages | number | yes |
| `gross_weight` | Gross weight (kg) | number | yes |
| `chargeable_weight` | Chargeable weight (kg) | number | no |
| `nature_of_goods` | Description / quantity of goods | string | yes |
| `declared_value_for_carriage` | Declared value for carriage | string | no |
| `declared_value_for_customs` | Declared value for customs | string | no |
| `date_of_issue` | Date the AWB was issued | date | no |

---

## 4. CMR Consignment Note (`cmr`)

The international road-transport consignment note (CMR Convention). The note is
laid out as numbered boxes; the box number for each field is shown in the
description. Box numbering can vary slightly between printed templates.

| JSON key | Description | Type | Required |
|---|---|---|---|
| `cmr_number` | CMR reference number | string | no |
| `sender` | Box 1 — Sender: `{ "name", "address" }` | object | yes |
| `consignee` | Box 2 — Consignee: `{ "name", "address" }` | object | yes |
| `place_of_delivery` | Box 3 — Place of delivery of the goods | string | yes |
| `place_and_date_of_taking_over` | Box 4 — Where/when goods were taken over | string | no |
| `attached_documents` | Box 5 — Documents attached (invoice, etc.) | string | no |
| `marks_and_numbers` | Box 6 — Shipping marks | string | no |
| `number_of_packages` | Box 7 — Number of packages | number | no |
| `method_of_packing` | Box 8 — Packing method | string | no |
| `nature_of_goods` | Box 9 — Description of the goods | string | yes |
| `gross_weight` | Box 11 — Gross weight (kg) | number | yes |
| `volume` | Box 12 — Volume (m³) | number | no |
| `carrier` | Box 16 — Carrier: `{ "name", "address" }` | object | yes |
| `vehicle_registration_number` | Truck / trailer plate number | string | yes |
| `place_and_date_of_completion` | Box 21 — Where/when the note was completed | string | no |

---

## 5. Unknown (`unknown`)

If classification returns `unknown`, no field extraction is attempted. The
system reports that the document type is not supported and returns:

```json
{ "document_type": "unknown", "fields": null }
```

---

## Extending this spec

To add a new document type (e.g. `certificate_of_origin`, `bill_of_lading`):

1. Add its label to `DOC_TYPES` in `llm_service.py`.
2. Add a section here with its field table.
3. Add a matching Pydantic model and specialized prompt in `llm_service.py`.

Keeping this file and the code in sync is what makes the official spec a simple
swap-in later.
