from dataclasses import dataclass, field


@dataclass
class ConversionResult:
    """Uniform output of every converter.

    text:   the Markdown body (no frontmatter)
    engine: label of the engine used, e.g. "markitdown",
            "local:pp-structurev3", "cloud:paddleocr-vl-1.6"
    pages:  page count when known (PDFs), else None
    assets: relative-path -> raw bytes for extracted images to write alongside the md
    """

    text: str
    engine: str
    pages: int | None = None
    assets: dict[str, bytes] = field(default_factory=dict)


class OCRUnavailableError(RuntimeError):
    """Raised when no usable OCR backend is configured/available."""
