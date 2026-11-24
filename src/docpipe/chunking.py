from __future__ import annotations

import re
from dataclasses import dataclass

from .extract import Page


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    path: str
    page: int
    position: int
    text: str


_SENTENCE_END = re.compile(r"(?<=[.!?;:])\s+")


def _pieces(text: str, size: int) -> list[str]:
    """Paragraphs first; a paragraph longer than `size` is cut on sentence ends,
    and a sentence longer than `size` is cut on words."""
    out = []
    for para in [p.strip() for p in text.split("\n\n") if p.strip()]:
        para = " ".join(para.split())
        if len(para) <= size:
            out.append(para)
            continue
        for sent in _SENTENCE_END.split(para):
            if len(sent) <= size:
                out.append(sent)
            else:
                words, buf = sent.split(), ""
                for w in words:
                    if len(buf) + len(w) + 1 > size and buf:
                        out.append(buf)
                        buf = w
                    else:
                        buf = f"{buf} {w}".strip()
                if buf:
                    out.append(buf)
    return out


def chunk_pages(pages: list[Page], doc_id: str, path: str, size: int = 900, overlap: int = 150) -> list[Chunk]:
    chunks: list[Chunk] = []
    for page in pages:
        buf = ""
        for piece in _pieces(page.text, size):
            if buf and len(buf) + len(piece) + 1 > size:
                chunks.append(_make(doc_id, path, page.number, len(chunks), buf))
                # carry the end of the previous chunk so a fact split in two is still retrievable
                tail = buf[-overlap:]
                tail = tail[tail.find(" ") + 1:] if " " in tail else tail
                buf = f"{tail} {piece}" if overlap else piece
            else:
                buf = f"{buf} {piece}".strip() if buf else piece
        if buf:
            chunks.append(_make(doc_id, path, page.number, len(chunks), buf))
    return chunks


def _make(doc_id: str, path: str, page: int, position: int, text: str) -> Chunk:
    return Chunk(f"{doc_id}-{position:04d}", doc_id, path, page, position, text.strip())
