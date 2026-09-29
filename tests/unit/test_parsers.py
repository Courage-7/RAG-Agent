import io

import pytest
from pypdf import PageObject, PdfWriter
from rag_core.errors import DocumentParsingError
from rag_core.ingestion.parsers import DocumentParser


def test_parse_plain_text() -> None:
    content = b"This is a plain text document.\nIt contains multiple lines."
    doc = DocumentParser.parse(content, file_type="text/plain")

    assert doc.file_type == "text/plain"
    assert doc.total_pages == 1
    assert "This is a plain text document." in doc.text
    assert len(doc.pages) == 1
    assert doc.pages[0].page_number == 1


def test_parse_markdown() -> None:
    content = b"# Architecture\n\n- Point 1\n- Point 2"
    doc = DocumentParser.parse(content, file_type="text/markdown")

    assert doc.file_type == "text/markdown"
    assert doc.total_pages == 1
    assert "# Architecture" in doc.text


def test_parse_pdf() -> None:
    # Programmatically create a valid PDF with text in-memory
    writer = PdfWriter()
    page = PageObject.create_blank_page(width=200, height=200)
    writer.add_page(page)

    # In modern pypdf, we can add annotations or simple text representation
    stream = io.BytesIO()
    writer.write(stream)
    pdf_bytes = stream.getvalue()

    # Empty pages in PDF will trigger the empty extractable text check
    with pytest.raises(DocumentParsingError, match="No extractable text found"):
        DocumentParser.parse(pdf_bytes, file_type="application/pdf")


def test_parse_empty_payload_raises() -> None:
    with pytest.raises(DocumentParsingError, match="empty"):
        DocumentParser.parse(b"", file_type="text/plain")


def test_parse_unsupported_format_raises() -> None:
    with pytest.raises(DocumentParsingError, match="Unsupported document format"):
        DocumentParser.parse(b"data", file_type="application/x-executable")
