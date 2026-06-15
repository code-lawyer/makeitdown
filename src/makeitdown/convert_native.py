import threading
from pathlib import Path

from markitdown import MarkItDown

from .models import ConversionResult

_local = threading.local()


def _get_converter() -> MarkItDown:
    converter = getattr(_local, "converter", None)
    if converter is None:
        converter = MarkItDown()
        _local.converter = converter
    return converter


def convert(path: Path) -> ConversionResult:
    result = _get_converter().convert(str(path))
    return ConversionResult(text=result.text_content, engine="markitdown")
