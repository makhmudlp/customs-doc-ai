"""
app.py — Streamlit UI for the customs document AI.
Stage 2: upload -> process -> show extracted JSON.
"""

import json
import tempfile
from pathlib import Path

import streamlit as st

from ocr_service import extract_from_text
from llm_service import classify_document, extract_fields, answer_about_document
from rag_service import answer_general
from config import MODEL

import io
import pandas as pd


def flatten_for_export(fields: dict) -> pd.DataFrame:
    """Turn the nested extracted fields into a flat table for CSV/Excel.

    Line items become one row each; the document-level fields (invoice number,
    seller, totals, ...) are repeated on every row so each row is self-contained.
    """
    if not fields:
        return pd.DataFrame()

    # Separate the repeating rows (line_items / packages) from everything else.
    row_key = "line_items" if "line_items" in fields else (
        "packages" if "packages" in fields else None
    )
    rows = fields.get(row_key) or [] if row_key else []

    # Flatten the top-level (non-list) fields into "key: value" pairs.
    base = {}
    for key, value in fields.items():
        if key == row_key:
            continue
        if isinstance(value, dict):                       # seller -> seller_name, seller_address
            for sub_key, sub_val in value.items():
                base[f"{key}_{sub_key}"] = sub_val
        elif isinstance(value, list):
            base[key] = "; ".join(str(v) for v in value)  # any other list -> joined text
        else:
            base[key] = value

    if not rows:                       # no line items -> a single row of the base fields
        return pd.DataFrame([base])

    # One row per line item, with the base fields repeated on each.
    out = []
    for item in rows:
        merged = dict(base)
        if isinstance(item, dict):
            merged.update(item)
        out.append(merged)
    return pd.DataFrame(out)

# --- Page setup (must be first) ---
st.set_page_config(page_title="Customs Doc AI", page_icon="📄", layout="wide")


# --- Load the heavy models ONCE and reuse across re-runs ---
@st.cache_resource
def warm_up():
    """Force PaddleOCR to load now, so it's warm for every document after."""
    from ocr_service import get_ocr_engine
    get_ocr_engine()
    return True


# --- The processing pipeline, wrapped for the UI ---
def process(file_path: str) -> dict:

    ocr_result = extract_from_text(file_path)
    text = ocr_result["full_text"]
    doc_type = classify_document(text)
    fields = extract_fields(text, doc_type)
    return {
        "source_file": ocr_result.get("source_file"),
        "method": ocr_result.get("method"),
        "document_type": doc_type,
        "fields": fields,
        "full_text": text,          # <-- keep the raw OCR text as a fallback
    }


# --- Remember the last result across re-runs ---
if "result" not in st.session_state:
    st.session_state.result = None

# --- UI ---
st.title("📄 Customs Document AI")
st.write("Upload a customs document (PDF, JPG, or PNG) to extract its data.")

warm_up()   # triggers the one-time model load (cached)

uploaded_file = st.file_uploader(
    "Drag and drop a file here, or click to browse",
    type=["pdf", "jpg", "jpeg", "png"],
)

if uploaded_file is not None:
    st.success(f"Received: **{uploaded_file.name}**")

    if st.button("Process document", type="primary"):
        # Bridge: the uploaded file lives in memory, but our pipeline needs a
        # path on disk. Write it to a temp file, then hand over the path.
        suffix = Path(uploaded_file.name).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = tmp.name

        with st.spinner("Reading and extracting… (this can take few minutes)"):
            try:
                st.write(f"Model being used: {MODEL}")
                st.session_state.result = process(tmp_path)
            except Exception as error:
                st.session_state.result = {"error": str(error)}

# --- Show whatever we last processed ---
# --- Show whatever we last processed ---
result = st.session_state.result
if result is not None and "error" in result:
    st.error(f"Processing failed: {result['error']}")

# --- Tabs: data + chat. Chat is always available (RAG needs no document). ---
tab_data, tab_chat = st.tabs(["📋 Extracted Data", "💬 Chatbot"])

# ---- TAB 1: extracted data + downloads ----
with tab_data:
    if result is None or "error" in result:
        st.info("Upload and process a document to see extracted data.")
    else:
        st.subheader("Result")
        col1, col2 = st.columns(2)
        col1.metric("Document type", result["document_type"])
        col2.metric("OCR method", result["method"])

        extraction = result["fields"]
        if extraction is None:
            st.warning("Unsupported document type — no fields extracted.")
        else:
            st.json(extraction)

            df = flatten_for_export(extraction)
            if not df.empty:
                st.subheader("Download")
                base_name = Path(result["source_file"] or "document").stem
                csv_bytes = df.to_csv(index=False).encode("utf-8")
                st.download_button("⬇️ Download CSV", csv_bytes,
                                   f"{base_name}.csv", "text/csv")
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                    df.to_excel(writer, index=False, sheet_name="extracted")
                st.download_button("⬇️ Download Excel", buffer.getvalue(),
                                   f"{base_name}.xlsx",
                                   "application/vnd.openpyxl-officedocument.spreadsheetml.sheet")

# ---- TAB 2: the chatbot (two modes) ----
with tab_chat:
    mode = st.radio(
        "Chat mode:",
        ["📄 About this document", "⚖️ General customs law"],
        horizontal=True,
    )

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for role, message in st.session_state.chat_history:
        with st.chat_message(role):
            st.markdown(message)

    question = st.chat_input("Ask in English, Russian, or Uzbek…")
    if question:
        st.session_state.chat_history.append(("user", question))
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                if mode == "📄 About this document":
                    if result is None or "error" in result:
                        answer = "Please upload and process a document first to ask about it."
                    elif result["fields"] is not None:
                        # We have structured JSON — answer from it (fast, precise).
                        answer = answer_about_document(question, result["fields"])
                    else:
                        # No structured fields (unsupported/unknown type) —
                        # fall back to answering from the raw OCR text.
                        answer = answer_about_document(
                            question, {"raw_text": result["full_text"][:8000]}
                        )
                else:  # ⚖️ General customs law (RAG)
                    rag = answer_general(question)
                    sources = ", ".join(rag["sources"])
                    answer = f"{rag['answer']}\n\n*Sources: {sources}*"
            st.markdown(answer)
        st.session_state.chat_history.append(("assistant", answer))