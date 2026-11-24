import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from docpipe.extract import ExtractionError, extract


def _pdf(tmp_path, pages):
    path = tmp_path / "doc.pdf"
    c = canvas.Canvas(str(path), pagesize=A4)
    for text in pages:
        c.drawString(72, 750, text)
        c.showPage()
    c.save()
    return path.read_bytes()


def test_pdf_pages_are_numbered(tmp_path):
    pages = extract(_pdf(tmp_path, ["premiere page", "deuxieme page"]), ".pdf")
    assert [p.number for p in pages] == [1, 2]
    assert "deuxieme" in pages[1].text


def test_invalid_pdf_raises():
    with pytest.raises(ExtractionError):
        extract(b"garbage", ".pdf")


def test_unsupported_extension():
    with pytest.raises(ExtractionError):
        extract(b"x", ".docx")
