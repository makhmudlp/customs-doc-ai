"""
rag_service.py — Phase B: answer customs-law questions using the ChromaDB knowledge base.
retrieve relevant articles -> feed them to Qwen -> grounded answer.
"""

import re
import chromadb
import requests

from config import (
    MODEL,
    OLLAMA_URL,
    OLLAMA_EMBED_URL,
    EMBED_MODEL,
    DB_PATH,
    COLLECTION_NAME,
)


# --- Open the knowledge base once and reuse it ---
_collection = None


def get_collection():
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=DB_PATH)
        _collection = client.get_collection(COLLECTION_NAME)
    return _collection


def embed(text: str) -> list[float]:
    """Same embedding model used to build the DB — must match."""
    response = requests.post(
        OLLAMA_EMBED_URL,
        json={"model": EMBED_MODEL, "prompt": text},
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["embedding"]


def translate_to_english(question: str) -> str:
    """Translate a question to English for retrieval (corpus is English)."""
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content":
                    "Translate the user's text to English. Reply with ONLY the "
                    "translation, nothing else. If it is already English, repeat it."},
                {"role": "user", "content": question},
            ],
            "stream": False,
        },
        timeout=300,
    )
    response.raise_for_status()
    out = response.json()["message"]["content"]
    return re.sub(r"<think>.*?</think>", "", out, flags=re.DOTALL).strip()


def retrieve(question: str, k: int = 3) -> list[dict]:
    """Find the k most relevant articles. Search in English since the corpus is English."""
    search_query = translate_to_english(question)   # <-- the fix
    question_vector = embed(search_query)
    results = get_collection().query(
        query_embeddings=[question_vector],
        n_results=k,
    )
    docs = results["documents"][0]
    metas = results["metadatas"][0]
    return [{"title": m["title"], "text": d} for d, m in zip(docs, metas)]


def answer_general(question: str) -> dict:
    """Answer a customs-law question, grounded in retrieved articles."""
    articles = retrieve(question, k=3)

    # Build the context block from the retrieved articles.
    context = "\n\n".join(a["text"] for a in articles)

    system = (
        "You are a customs law assistant for Uzbekistan. Answer the user's "
        "question using ONLY the Customs Code articles provided below. "
        "Do not invent legal provisions. If the answer is not in the articles, "
        "say the provided articles do not cover it.\n"
        "Reply in the SAME language the user asked in (Uzbek, Russian, or English).\n\n"
        f"Customs Code articles:\n{context}"
    )

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": question},
            ],
            "stream": False,
        },
        timeout=600,
    )
    response.raise_for_status()
    answer = response.json()["message"]["content"]

    # Strip Qwen's <think> blocks if present.
    import re
    answer = re.sub(r"<think>.*?</think>", "", answer, flags=re.DOTALL).strip()

    return {
        "answer": answer,
        "sources": [a["title"] for a in articles],   # which articles we used
    }


if __name__ == "__main__":
    result = answer_general("Какие документы нужны для импорта товаров?")
    print("ANSWER:\n", result["answer"])
    print("\nSOURCES:", result["sources"])