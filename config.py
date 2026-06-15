# config.py — central settings for the whole project.
# Change something here once, and every file that imports it updates.

MODEL = "qwen3:1.7b"                              # the local Qwen model (chat + extraction)
OLLAMA_URL = "http://localhost:11434/api/chat"   # the local Qwen server

DOC_TYPES = ["invoice", "awb", "cmr", "packing_list", "unknown"]

# --- RAG settings (customs-law knowledge base) ---
OLLAMA_EMBED_URL = "http://localhost:11434/api/embeddings"  # embedding endpoint
EMBED_MODEL = "nomic-embed-text"                            # turns text into vectors
DB_PATH = "./chroma_db"                                     # where the vector DB lives
COLLECTION_NAME = "customs_code"                            # the collection name
DOCX_PATH="customs_code"                                    