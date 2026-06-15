"""
rag_loader.py — load the Customs Code .docx and split it into per-article chunks.
Each chunk is one article: its title line plus the paragraphs beneath it.
"""

import re
from docx import Document


def load_paragraphs(path: str) -> list[str]:
    """Read the .docx and return its non-empty paragraphs as text."""
    doc = Document(path)
    return [p.text.strip() for p in doc.paragraphs if p.text.strip()]


def is_article_start(line: str) -> bool:
    """True if a paragraph begins a new article, e.g. 'Article 5. Customs territory'."""
    return bool(re.match(r"^Article\s+\d+", line))


def chunk_by_article(paragraphs: list[str]) -> list[dict]:
    """Group paragraphs into one chunk per article."""
    chunks = []
    current_title = None
    current_body = []

    for para in paragraphs:
        if is_article_start(para):
            # Starting a new article -> save the previous one first.
            if current_title is not None:
                chunks.append({
                    "title": current_title,
                    "text": current_title + "\n" + "\n".join(current_body),
                })
            current_title = para        # this line is the new article's title
            current_body = []
        else:
            if current_title is not None:   # skip the Section/Chapter lines before Article 1
                current_body.append(para)

    # Don't forget the final article.
    if current_title is not None:
        chunks.append({
            "title": current_title,
            "text": current_title + "\n" + "\n".join(current_body),
        })

    return chunks


if __name__ == "__main__":
    paragraphs = load_paragraphs("customs_code.docx")   # <-- your filename
    chunks = chunk_by_article(paragraphs)

    print(f"Total articles: {len(chunks)}\n")
    # Show the first 3 articles to confirm clean splitting.
    for chunk in chunks[:3]:
        print("=" * 60)
        print(chunk["text"][:400])
        print()
    for chunk in chunks[200:204]:
        print(chunk["title"])