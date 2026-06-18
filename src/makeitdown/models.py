from dataclasses import dataclass, field


@dataclass
class ConversionResult:
    """Uniform output of every converter.

    text:   the Markdown body (no frontmatter)
    engine: label of the engine used, e.g. "markitdown",
            "local:pp-structurev3", "cloud:paddleocr-vl-1.6"
    pages:  page count when known (PDFs), else None
    assets: relative-path -> raw bytes for extracted images to write alongside the md
    confidences: per-region OCR recognition scores when the backend exposes them,
            else None; consumed by the quality check to flag low-confidence output.
    """

    text: str
    engine: str
    pages: int | None = None
    assets: dict[str, bytes] = field(default_factory=dict)
    confidences: list[float] | None = None


class OCRUnavailableError(RuntimeError):
    """Raised when no usable OCR backend is configured/available."""


class LegacyConversionUnavailable(RuntimeError):
    """Raised when a legacy binary (.doc/.wps) can't be converted because no
    backend is available. Carries an actionable hint for the user."""
