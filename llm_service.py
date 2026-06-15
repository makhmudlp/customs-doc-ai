"""
llm_service.py  —  the "brain".

Job 1: classify a document into a type.
Job 2: extract its mandatory fields as validated JSON.
"""

import json
import re
from typing import Optional

import requests
from pydantic import BaseModel, Field, ValidationError
from config import OLLAMA_URL, MODEL, DOC_TYPES



# ----------------------------------------------------------------------
# Low-level: talk to Qwen
# ----------------------------------------------------------------------
def _chat(messages: list[dict], force_json: bool = False) -> str:
    payload = {"model": MODEL, "messages": messages, "stream": False}
    if force_json:
        payload["format"] = "json"
    response = requests.post(OLLAMA_URL, json=payload, timeout=300)
    response.raise_for_status()
    return response.json()["message"]["content"]


def _extract_json(text: str) -> dict:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON found in model reply: {text!r}")
    return json.loads(text[start:end + 1])


# ----------------------------------------------------------------------
# The field "shapes" — these mirror field_requirements.md
# ----------------------------------------------------------------------
class Party(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None


class LineItem(BaseModel):
    description: Optional[str] = None
    hs_code: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    amount: Optional[float] = None


class Package(BaseModel):
    package_number: Optional[str] = None
    marks_and_numbers: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[float] = None
    net_weight: Optional[float] = None
    gross_weight: Optional[float] = None
    dimensions: Optional[str] = None


class Invoice(BaseModel):
    invoice_number: Optional[str] = Field(None, description="Invoice's unique reference number")
    invoice_date: Optional[str] = Field(None, description="Issue date, YYYY-MM-DD")
    seller: Optional[Party] = Field(None, description='Seller/exporter, object: {"name","address"}')
    buyer: Optional[Party] = Field(None, description='Buyer/importer, object: {"name","address"}')
    country_of_origin: Optional[str] = Field(None, description="Country goods were produced in")
    country_of_destination: Optional[str] = Field(None, description="Country goods ship to")
    incoterms: Optional[str] = Field(None, description="Delivery terms, e.g. FOB, CIF, EXW")
    currency: Optional[str] = Field(None, description="ISO currency code, e.g. USD")
    line_items: list[LineItem] = Field(default_factory=list,
        description='List of products; each: {"description","hs_code","quantity","unit","unit_price","amount"}')
    total_amount: Optional[float] = Field(None, description="Total invoice value, plain number")
    net_weight: Optional[float] = Field(None, description="Total net weight in kg")
    gross_weight: Optional[float] = Field(None, description="Total gross weight in kg")
    payment_terms: Optional[str] = Field(None, description="Agreed payment terms")


class PackingList(BaseModel):
    packing_list_number: Optional[str] = Field(None, description="Reference number")
    date: Optional[str] = Field(None, description="Issue date, YYYY-MM-DD")
    seller: Optional[Party] = Field(None, description='Shipper/seller: {"name","address"}')
    buyer: Optional[Party] = Field(None, description='Consignee/buyer: {"name","address"}')
    packages: list[Package] = Field(default_factory=list,
        description='List of packages; each: {"package_number","marks_and_numbers","description","quantity","net_weight","gross_weight","dimensions"}')
    total_packages: Optional[int] = Field(None, description="Total number of packages")
    total_net_weight: Optional[float] = Field(None, description="Sum of net weights, kg")
    total_gross_weight: Optional[float] = Field(None, description="Sum of gross weights, kg")


class AWB(BaseModel):
    awb_number: Optional[str] = Field(None, description="Air waybill number")
    shipper: Optional[Party] = Field(None, description='Sender: {"name","address"}')
    consignee: Optional[Party] = Field(None, description='Receiver: {"name","address"}')
    airport_of_departure: Optional[str] = Field(None, description="Origin airport (name or IATA code)")
    airport_of_destination: Optional[str] = Field(None, description="Destination airport (name or IATA code)")
    carrier: Optional[str] = Field(None, description="Issuing airline / carrier")
    flight_number: Optional[str] = Field(None, description="Flight number")
    flight_date: Optional[str] = Field(None, description="Flight date, YYYY-MM-DD")
    number_of_pieces: Optional[int] = Field(None, description="Number of pieces/packages")
    gross_weight: Optional[float] = Field(None, description="Gross weight, kg")
    chargeable_weight: Optional[float] = Field(None, description="Chargeable weight, kg")
    nature_of_goods: Optional[str] = Field(None, description="Description of goods")
    declared_value_for_carriage: Optional[str] = Field(None, description="Declared value for carriage")
    declared_value_for_customs: Optional[str] = Field(None, description="Declared value for customs")
    date_of_issue: Optional[str] = Field(None, description="Issue date, YYYY-MM-DD")


class CMR(BaseModel):
    cmr_number: Optional[str] = Field(None, description="CMR reference number")
    sender: Optional[Party] = Field(None, description='Box 1 sender: {"name","address"}')
    consignee: Optional[Party] = Field(None, description='Box 2 consignee: {"name","address"}')
    place_of_delivery: Optional[str] = Field(None, description="Box 3 place of delivery")
    place_and_date_of_taking_over: Optional[str] = Field(None, description="Box 4 where/when goods taken over")
    attached_documents: Optional[str] = Field(None, description="Box 5 attached documents")
    marks_and_numbers: Optional[str] = Field(None, description="Box 6 shipping marks")
    number_of_packages: Optional[int] = Field(None, description="Box 7 number of packages")
    method_of_packing: Optional[str] = Field(None, description="Box 8 packing method")
    nature_of_goods: Optional[str] = Field(None, description="Box 9 description of goods")
    gross_weight: Optional[float] = Field(None, description="Box 11 gross weight, kg")
    volume: Optional[float] = Field(None, description="Box 12 volume, m3")
    carrier: Optional[Party] = Field(None, description='Box 16 carrier: {"name","address"}')
    vehicle_registration_number: Optional[str] = Field(None, description="Truck/trailer plate number")
    place_and_date_of_completion: Optional[str] = Field(None, description="Box 21 where/when completed")


EXTRACTION_MODELS = {
    "invoice": Invoice,
    "packing_list": PackingList,
    "awb": AWB,
    "cmr": CMR,
}


# ----------------------------------------------------------------------
# Job 1: classification
# ----------------------------------------------------------------------
def classify_document(text: str) -> str:
    system = (
        "You are a customs document classifier. Identify the document type.\n"
        "- invoice: a bill listing goods, quantities, prices, and a total\n"
        "- awb: an Air Waybill, used for air freight\n"
        "- cmr: an international road transport consignment note\n"
        "- packing_list: a list of packed items and quantities\n"
        "- unknown: anything that fits none of the above\n"
        'Reply with ONLY this JSON: {"document_type": "<one of the labels>"}'
    )
    user = f"Document text:\n\n{text[:3000]}"
    reply = _chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        force_json=True,
    )
    data = _extract_json(reply)
    doc_type = str(data.get("document_type", "unknown")).strip().lower()
    return doc_type if doc_type in DOC_TYPES else "unknown"


# ----------------------------------------------------------------------
# Job 2: extraction
# ----------------------------------------------------------------------
def _field_guide(model_cls: type[BaseModel]) -> str:
    """Turn a model's fields into a readable list for the prompt."""
    lines = []
    for name, field in model_cls.model_fields.items():
        lines.append(f'  - "{name}": {field.description or ""}')
    return "\n".join(lines)


def _extraction_prompt(doc_type: str, model_cls: type[BaseModel]) -> str:
    return (
        f"You extract structured data from a {doc_type} document.\n"
        "Return ONE JSON object with EXACTLY these keys:\n"
        f"{_field_guide(model_cls)}\n\n"
        "Rules:\n"
        "- If a field is not in the text, set it to null. Never invent values.\n"
        "- Numbers must be plain: no currency symbols, no thousands separators.\n"
        "- Dates as YYYY-MM-DD.\n"
        "- Return ONLY the JSON object."
    )


def extract_fields(text: str, doc_type: str) -> Optional[dict]:
    """Extract the mandatory fields for a document, validated against its model."""
    model_cls = EXTRACTION_MODELS.get(doc_type)
    if model_cls is None:
        return None  # unknown type -> nothing to extract

    messages = [
        {"role": "system", "content": _extraction_prompt(doc_type, model_cls)},
        {"role": "user", "content": f"Document text:\n\n{text[:12000]}"},
    ]

    last_error = ""
    for _ in range(2):  # first attempt + one retry
        reply = _chat(messages, force_json=True)
        try:
            raw = _extract_json(reply)              # parse the JSON string
            validated = model_cls.model_validate(raw)  # check it against the shape
            return validated.model_dump()           # clean dict, every key present
        except (ValueError, ValidationError) as error:
            last_error = str(error)
            messages.append({"role": "assistant", "content": reply})
            messages.append({"role": "user", "content":
                f"Your previous answer was invalid: {last_error}\nReturn corrected JSON only."})

    raise ValueError(f"Extraction failed after retry. Last error:\n{last_error}")

def answer_about_document(question: str, extracted: dict) -> str:
    """Answer a question using ONLY the already-extracted JSON."""
    context = json.dumps(extracted, ensure_ascii=False, indent=2)
    system = (
        "You are a customs assistant. Answer the user's question using ONLY "
        "the structured document data below. Do not invent information. "
        "If the answer is not in the data, say so plainly.\n"
        "Reply in the SAME language the user asked in (Uzbek, Russian, or English).\n\n"
        f"Document data:\n{context}"
    )
    return _chat(
        [{"role": "system", "content": system},
         {"role": "user", "content": question}],
        force_json=False,   # a normal text answer, not JSON
    )


if __name__ == "__main__":
    from ocr_service import extract_from_text
    sample = (
        "COMMERCIAL INVOICE\n"
        "Invoice No: INV-2024-0042   Date: 12.03.2024\n"
        "Seller: Acme Trading LLC, Tashkent, Uzbekistan\n"
        "Buyer: Global Imports Co, Almaty, Kazakhstan\n"
        "Country of origin: Uzbekistan   Destination: Kazakhstan\n"
        "Terms: CIF   Currency: USD\n"
        "1. Ceramic tiles, HS 6907, 100 boxes, 25 USD each, 2500 USD\n"
        "2. Grout, HS 3214, 50 bags, 10 USD each, 500 USD\n"
        "Total: 3000 USD   Net weight: 1200 kg   Gross weight: 1300 kg\n"
    )
    #testing=extract_from_text("invoice.pdf")
    #doc_type = classify_document(testing["full_text"])
    #print("Type:", doc_type)
    #fields = extract_fields(testing["full_text"], doc_type)
    #print(json.dumps(fields, indent=2, ensure_ascii=False))
    sample = {"invoice_number": "1090130561", "total_amount": 13362.27, "currency": "EUR"}
    print(answer_about_document("What is the total?", sample))
    print(answer_about_document("Какая общая сумма?", sample))   # Russian — should reply in Russian