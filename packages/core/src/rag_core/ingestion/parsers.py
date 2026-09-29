"""Multi-format document parsing and structural metadata extraction."""

import io
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict, Field
from pypdf import PdfReader

from rag_core.errors import DocumentParsingError

logger = structlog.get_logger(__name__)


class ParsedPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    page_number: int = Field(ge=1)
    text: str
    char_count: int


class ParsedDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str = Field(min_length=1)
    pages: tuple[ParsedPage, ...] = ()
    file_type: str
    total_pages: int = Field(ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentParser:
    """Parses raw document bytes (PDF, Plaintext, Markdown) into normalized textual content."""

    @classmethod
    def parse(
        cls,
        data: bytes,
        file_type: str = "text/plain",
        *,
        metadata: dict[str, Any] | None = None,
    ) -> ParsedDocument:
        """Parse raw binary data into a structured ParsedDocument."""
        normalized_mime = file_type.lower().split(";")[0].strip()
        doc_metadata = metadata or {}

        if not data:
            raise DocumentParsingError("Document payload is empty")

        if normalized_mime in ("text/plain", "text/markdown", "text/csv"):
            return cls._parse_text(data, normalized_mime, doc_metadata)
        elif normalized_mime == "application/pdf":
            return cls._parse_pdf(data, doc_metadata)
        else:
            raise DocumentParsingError(
                f"Unsupported document format '{file_type}'. "
                "Supported formats: text/plain, text/markdown, text/csv, application/pdf"
            )

    @staticmethod
    def _parse_text(data: bytes, mime_type: str, metadata: dict[str, Any]) -> ParsedDocument:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("latin-1", errors="replace")

        cleaned = text.replace("\x00", "").strip()
        if not cleaned:
            raise DocumentParsingError("Text document contains no readable text content")

        page = ParsedPage(page_number=1, text=cleaned, char_count=len(cleaned))
        return ParsedDocument(
            text=cleaned,
            pages=(page,),
            file_type=mime_type,
            total_pages=1,
            metadata=metadata,
        )

    @staticmethod
    def _parse_pdf(data: bytes, metadata: dict[str, Any]) -> ParsedDocument:
        try:
            stream = io.BytesIO(data)
            reader = PdfReader(stream)
            num_pages = len(reader.pages)
            if num_pages == 0:
                raise DocumentParsingError("PDF file contains 0 pages")

            pages: list[ParsedPage] = []
            extracted_text_parts: list[str] = []

            for idx, page in enumerate(reader.pages, start=1):
                page_text = (page.extract_text() or "").replace("\x00", "").strip()
                if page_text:
                    pages.append(
                        ParsedPage(
                            page_number=idx,
                            text=page_text,
                            char_count=len(page_text),
                        )
                    )
                    extracted_text_parts.append(f"--- Page {idx} ---\n{page_text}")

            full_text = "\n\n".join(extracted_text_parts).strip()
            if not full_text:
                raise DocumentParsingError(
                    "No extractable text found in PDF (document may be scanned images without OCR)"
                )

            return ParsedDocument(
                text=full_text,
                pages=tuple(pages),
                file_type="application/pdf",
                total_pages=num_pages,
                metadata={
                    **metadata,
                    "pdf_page_count": num_pages,
                },
            )
        except DocumentParsingError:
            raise
        except Exception as exc:
            logger.error("pdf_parsing_failed", error=str(exc))
            raise DocumentParsingError(f"Failed to parse PDF document: {exc}") from exc
