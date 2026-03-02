from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.rag.repository import add_material_text


SUPPORTED_EXTENSIONS = {
    ".txt",
    ".md",
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tiff",
}


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "gbk", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def _extract_pdf_pages(data: bytes) -> List[Tuple[Optional[int], str]]:
    try:
        import pdfplumber  # type: ignore
    except ImportError as exc:
        raise RuntimeError("pdfplumber is required for PDF ingestion.") from exc

    pages: List[Tuple[Optional[int], str]] = []
    with pdfplumber.open(BytesIO(data)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            text = text.strip()
            if text:
                pages.append((i, text))
    return pages


def _extract_image_text(data: bytes) -> str:
    try:
        from PIL import Image  # type: ignore
    except ImportError as exc:
        raise RuntimeError("Pillow is required for image OCR.") from exc

    try:
        import pytesseract  # type: ignore
    except ImportError as exc:
        raise RuntimeError("pytesseract is required for image OCR.") from exc

    image = Image.open(BytesIO(data))
    return pytesseract.image_to_string(image, lang="chi_sim+eng").strip()


def _extract_by_extension(extension: str, data: bytes) -> List[Tuple[Optional[int], str]]:
    if extension in {".txt", ".md"}:
        text = _decode_text(data).strip()
        return [(None, text)] if text else []

    if extension == ".pdf":
        return _extract_pdf_pages(data)

    if extension in {".png", ".jpg", ".jpeg", ".bmp", ".tiff"}:
        text = _extract_image_text(data)
        return [(None, text)] if text else []

    text = _decode_text(data).strip()
    return [(None, text)] if text else []


def ingest_uploaded_material(
    conn: Any,
    course_id: int,
    filename: str,
    file_bytes: bytes,
    source_name: Optional[str] = None,
) -> Dict[str, Any]:
    ext = Path(filename).suffix.lower()
    if ext and ext not in SUPPORTED_EXTENSIONS:
        raise RuntimeError(f"unsupported file extension: {ext}")

    source = (source_name or filename or "uploaded_file").strip()
    pages = _extract_by_extension(ext, file_bytes)
    if not pages:
        raise RuntimeError("no readable content found in uploaded file")

    inserted_chunks = 0
    page_count = 0
    total_chars = 0
    for page_number, text in pages:
        clean_text = text.strip()
        if not clean_text:
            continue
        inserted_chunks += add_material_text(
            conn=conn,
            course_id=course_id,
            source_name=source,
            text=clean_text,
            page_number=page_number,
        )
        page_count += 1
        total_chars += len(clean_text)

    if inserted_chunks <= 0:
        raise RuntimeError("content extracted but no chunks were inserted")

    return {
        "course_id": course_id,
        "source_name": source,
        "filename": filename,
        "inserted_chunks": inserted_chunks,
        "ingested_pages": page_count,
        "total_chars": total_chars,
        "file_type": ext or "text",
    }

