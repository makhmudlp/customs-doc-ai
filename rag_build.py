"""
rag_build.py — Phase A: embed the Customs Code articles into ChromaDB.
Run ONCE. Produces a local ./chroma_db folder.
"""

import chromadb
import requests

from rag_loader import load_paragraphs, chunk_by_article

OLLAMA_EMBED_URL = "http://localhost:11434/api/embeddings"
EMBED_MODEL = "nomic-embed-text"
DOCX_PATH = "customs_code.docx"        # <-- your filename
DB_PATH = "./chroma_db"
COLLECTION_NAME = "customs_code"


def embed(text: str) -> list[float]:
    """Turn one piece of text into a vector using the local embedding model."""
    response = requests.post(
        OLLAMA_EMBED_URL,
        json={"model": EMBED_MODEL, "prompt": text},
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["embedding"]


def main():
    # 1. Load + chunk the document.
    paragraphs = load_paragraphs(DOCX_PATH)
    chunks = chunk_by_article(paragraphs)
    print(f"Loaded {len(chunks)} articles.")

    # 2. Open a local ChromaDB and a fresh collection.
    client = chromadb.PersistentClient(path=DB_PATH)
    # Start clean so re-running doesn't create duplicates.
    if COLLECTION_NAME in [c.name for c in client.list_collections()]:
        client.delete_collection(COLLECTION_NAME)
    collection = client.create_collection(COLLECTION_NAME)

    # 3. Embed each article and add it to the collection.
    for i, chunk in enumerate(chunks):
        vector = embed(chunk["text"])
        collection.add(
            ids=[f"article_{i}"],
            embeddings=[vector],
            documents=[chunk["text"]],
            metadatas=[{"title": chunk["title"]}],
        )
        if (i + 1) % 25 == 0:
            print(f"  embedded {i + 1}/{len(chunks)}…")

    print(f"\nDone. {collection.count()} articles stored in {DB_PATH}")


if __name__ == "__main__":
    main()