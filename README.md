# Customs Document AI

A fully local, self-hosted platform for processing customs documents. It performs OCR, classifies the document type, extracts structured data into JSON, lets you export that data to CSV/Excel, and answers questions through a multilingual chatbot — including a Retrieval-Augmented Generation (RAG) assistant over the Customs Code of the Republic of Uzbekistan.

Everything runs on the local machine. No cloud APIs, no external services — document data stays in-house.

## Features

- **Smart OCR** — extracts text from PDFs and images. For PDFs it first tries direct text extraction (fast, exact) and only falls back to image-based OCR for scanned pages.
- **Document classification** — a local Qwen model labels each document as `invoice`, `awb`, `cmr`, `packing_list`, or `unknown`.
- **Structured extraction** — a specialized prompt per document type extracts the mandatory fields into validated JSON (validated with Pydantic, so the shape is guaranteed and missing fields are explicit `null`s rather than invented values).
- **Data export** — download the extracted data as CSV or Excel, one row per line item.
- **Multilingual chatbot (English / Russian / Uzbek)** with two modes:
  - **Document Q&A** — answers questions about the uploaded document from its extracted JSON (and falls back to the raw OCR text when no structured fields are available).
  - **General customs law (RAG)** — answers questions about Uzbek customs law, grounded in the Customs Code, and shows which articles it used.

## Architecture

The system is a linear pipeline with clear separation between the UI, OCR, LLM logic, and the RAG knowledge base.

```
Upload (PDF / JPG / PNG)
        |
   ocr_service.py        -> raw text (direct PDF text, or PaddleOCR on scanned pages)
        |
   llm_service.py        -> classify document type
        |                 -> extract mandatory fields as validated JSON
        |
   Streamlit UI (app.py) -> show JSON, export CSV/Excel, chat
        |
   Chatbot:
     - Document Q&A   (llm_service.answer_about_document)  -> answers from JSON / raw text
     - Customs law    (rag_service.answer_general)         -> answers from ChromaDB + Customs Code
```

### Files

| File | Responsibility |
|------|----------------|
| `config.py` | Central settings (model names, URLs, DB path) — change once, applies everywhere. |
| `ocr_service.py` | Smart OCR: direct PDF text with a fallback to PaddleOCR image OCR. |
| `llm_service.py` | Classification, structured extraction (Pydantic-validated), and Document Q&A. |
| `rag_loader.py` | Loads the Customs Code `.docx` and splits it into one chunk per article. |
| `rag_build.py` | One-time script: embeds the articles and stores them in ChromaDB. |
| `rag_service.py` | RAG answering: retrieve relevant articles, then answer grounded in them. |
| `app.py` | The Streamlit user interface tying everything together. |
| `field_requirements.md` | The "source of truth" for which fields to extract per document type. |

## Technology stack

- **OCR:** PaddleOCR (PP-OCRv5 mobile, with a Cyrillic recognizer for Uzbek/Russian)
- **LLM:** Qwen (`qwen3:1.7b`) running locally via Ollama
- **Embeddings:** `nomic-embed-text` via Ollama
- **Vector database:** ChromaDB (local, persists to `./chroma_db`)
- **UI:** Streamlit
- **Validation:** Pydantic

## Setup

### Prerequisites

- macOS or Linux, Python 3.11
- ~8 GB RAM (the project was built and tested on a MacBook Air M3, 8 GB)
- [Ollama](https://ollama.com) installed

> **Apple Silicon note:** install Ollama using the **cask** (`brew install --cask ollama`), not the Homebrew formula — the formula has shipped without the server binary on Apple Silicon. Launch it with `open -a Ollama` so the menu-bar app runs the server.

### 1. Clone and create the environment

```bash
git clone https://github.com/YOUR_USERNAME/customs-doc-ai.git
cd customs-doc-ai
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> **NumPy note:** PaddleOCR on Apple Silicon requires NumPy 1.x. If you hit a segfault, run `pip install "numpy<2"` (1.26.4 is known to work).

### 2. Pull the local models

```bash
ollama pull qwen3:1.7b
ollama pull nomic-embed-text
```

### 3. Get the Customs Code and build the knowledge base

The RAG assistant needs the Customs Code of the Republic of Uzbekistan. Obtain the official document as a `.docx` from the legislation portal (https://lex.uz, document 5535133 — English version) and place it in the project root as `customs_code.docx`. Then build the vector store (runs once):

```bash
python rag_build.py
```

This embeds all ~419 articles into `./chroma_db`. It takes a couple of minutes and only needs to be run once.

> **Why a `.docx` instead of scraping:** the assignment suggests scraping lex.uz, but the site renders article text via JavaScript, so a plain HTTP scrape returns only the table of contents. The official `.docx` provides the same source text completely and reliably, so it is loaded directly. This is a deliberate, documented deviation.

### 4. Run the app

Make sure Ollama is running, then:

```bash
streamlit run app.py
```

Open the local URL it prints (usually http://localhost:8501).

## Usage

1. Drag a customs document (PDF, JPG, or PNG) onto the upload box and click **Process document**.
2. The **Extracted Data** tab shows the document type, the structured JSON, and CSV/Excel download buttons.
3. The **Chatbot** tab offers two modes:
   - *About this document* — ask things like "What is the total?" or "Кто продавец?"
   - *General customs law* — ask things like "What documents are needed to import goods?" and see the source articles cited.

## Known limitations

These are honest constraints of running entirely locally on 8 GB RAM, documented as engineering trade-offs rather than hidden.

- **OCR speed on scanned pages.** Image-based OCR of scanned pages is CPU-bound and slow on 8 GB RAM (tens of seconds per page). This is a hardware ceiling, not a code issue — confirmed by testing different model sizes with no change in throughput. Searchable PDFs are near-instant via the direct-text path.
- **Long multi-page invoices.** Extraction processes up to ~12,000 characters of OCR text per document, a context-window limit of the small local model. Single-page documents are fully covered; very long invoices (e.g. 40+ line items across many pages) may have later items truncated or imperfectly separated.
- **Uzbek answer fluency.** RAG retrieval works across English, Russian, and Uzbek (non-English questions are translated to English before retrieval, since the corpus is English). Answer fluency is strong in English and Russian but degrades in Uzbek, where the 1.7B model can produce repetitive phrasing. This is a capacity limit of a model small enough to run on 8 GB RAM; a larger model would resolve it.
- **One file, one document.** Each uploaded file is treated as a single document. A file containing several merged documents is extracted as one combined record.

## Design notes

- **No invented numbers.** The extraction prompt instructs the model to use `null` for any field not present in the text and never to calculate or sum values. Pydantic validation enforces the output shape.
- **Grounded answers.** Both chatbot modes are instructed to answer only from the provided context (the document's JSON, or the retrieved Customs Code articles) and to say plainly when something is not covered, rather than guessing.
- **Centralized configuration.** All model names, endpoints, and paths live in `config.py`, so switching models (e.g. to a larger Qwen for better fluency) is a one-line change.

## Possible future improvements

- A larger LLM (14B+) for better extraction on long documents and fluent Uzbek output — requires more than 8 GB RAM.
- A multilingual embedding model so Russian/Uzbek questions retrieve without the English translation step.
- A document splitter to handle multi-document files.
