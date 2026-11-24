"""Text extraction, page by page so that answers can cite a page number."""
from __future__ import annotations

import io
from dataclasses import dataclass


@dataclass
class Page:
    number: int
    text: str


class ExtractionError(Exception):
    pass


def _clean(text: str) -> str:
    lines = [ln.strip() for ln in text.replace("\r", "").split("\n")]
    out, blank = [], False
    for ln in lines:
        if not ln:
            if not blank:
                out.append("")
            blank = True
            continue
        # join words split by a hyphen at the end of a line
        if out and out[-1].endswith("-") and ln[:1].islower():
            out[-1] = out[-1][:-1] + ln
        else:
            out.append(ln)
        blank = False
    return "\n".join(out).strip()


def extract_pdf(data: bytes) -> list[Page]:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [Page(i + 1, _clean(p.extract_text() or "")) for i, p in enumerate(reader.pages)]
    except PdfReadError as e:
        raise ExtractionError(str(e)) from e
    if not any(p.text for p in pages):
        raise ExtractionError("no text layer (scanned PDF?), use Document Intelligence")
    return pages


def extract_text(data: bytes) -> list[Page]:
    return [Page(1, _clean(data.decode("utf-8", errors="replace")))]


def extract_with_document_intelligence(data: bytes, endpoint: str, key: str) -> list[Page]:
    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.core.credentials import AzureKeyCredential

    client = DocumentIntelligenceClient(endpoint, AzureKeyCredential(key))
    poller = client.begin_analyze_document("prebuilt-read", body=data, content_type="application/octet-stream")
    result = poller.result()
    return [Page(p.page_number, _clean("\n".join(ln.content for ln in (p.lines or [])))) for p in result.pages]


def extract(data: bytes, extension: str, docintel: tuple[str, str] | None = None) -> list[Page]:
    if extension == ".pdf":
        try:
            return extract_pdf(data)
        except ExtractionError:
            if docintel and docintel[0]:
                return extract_with_document_intelligence(data, *docintel)
            raise
    if extension in (".txt", ".md"):
        return extract_text(data)
    raise ExtractionError(f"unsupported file type {extension}")
