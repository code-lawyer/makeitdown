from pathlib import Path

NATIVE_EXTS = {
    ".docx", ".xlsx", ".pptx", ".html", ".htm",
    ".csv", ".json", ".xml", ".txt", ".md", ".epub",
}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".gif", ".webp"}
# Legacy/ambiguous formats markitdown can't read directly. Routed to the legacy
# converter, which sniffs the real container (OOXML vs OLE2) and picks a backend.
LEGACY_BINARY_EXTS = {".doc", ".wps"}


def _pdf_avg_chars_per_page(path: Path) -> float:
    """Average extractable text characters per page; 0.0 if none/unreadable."""
    import fitz  # PyMuPDF

    try:
        doc = fitz.open(path)
    except Exception:
        return 0.0
    try:
        page_count = doc.page_count
        if page_count == 0:
            return 0.0
        total = sum(len(page.get_text("text").strip()) for page in doc)
        return total / page_count
    finally:
        doc.close()


def classify(path: Path, text_threshold: int = 50) -> str:
    """Return one of "native", "ocr", "legacy", "unsupported"."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        return "native" if _pdf_avg_chars_per_page(path) >= text_threshold else "ocr"
    if ext in NATIVE_EXTS:
        return "native"
    if ext in IMAGE_EXTS:
        return "ocr"
    if ext in LEGACY_BINARY_EXTS:
        return "legacy"
    return "unsupported"
