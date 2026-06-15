import importlib.util
import threading
from pathlib import Path

from .models import ConversionResult


class LocalOCR:
    """Wrapper over a local PaddleOCR PP-StructureV3 / PaddleOCR-VL pipeline.

    The heavy paddleocr import is deferred until the first conversion.

    A PaddleOCR pipeline object is not safe to call from several threads at
    once, so both lazy construction and prediction are serialized behind an
    instance lock. The dispatcher caches one LocalOCR for the whole run, so
    local OCR effectively processes one document at a time even when
    ``--workers > 1``; native (markitdown) conversions still run in parallel.
    """

    def __init__(self, model: str | None = None):
        self.model = model or "PP-StructureV3"
        self._engine = None
        self._lock = threading.Lock()

    @staticmethod
    def is_available() -> bool:
        try:
            return importlib.util.find_spec("paddleocr") is not None
        except Exception:
            return False

    @property
    def engine_label(self) -> str:
        return f"local:{self.model.lower()}"

    def _ensure_engine(self):
        if self._engine is None:
            from paddleocr import PPStructureV3  # noqa: PLC0415

            self._engine = PPStructureV3()
        return self._engine

    def convert(self, path: Path) -> ConversionResult:
        with self._lock:
            engine = self._ensure_engine()
            results = engine.predict(str(path))
            parts = [r["markdown"]["text"] for r in results]
        return ConversionResult(text="\n\n".join(parts), engine=self.engine_label, pages=len(parts))
