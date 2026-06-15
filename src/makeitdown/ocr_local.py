import importlib.util
from pathlib import Path

from .models import ConversionResult


class LocalOCR:
    """Wrapper over a local PaddleOCR PP-StructureV3 / PaddleOCR-VL pipeline.

    The heavy paddleocr import is deferred until the first conversion.
    """

    def __init__(self, model: str = "PP-StructureV3"):
        self.model = model
        self._engine = None

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
        engine = self._ensure_engine()
        results = engine.predict(str(path))
        parts = [r["markdown"]["text"] for r in results]
        return ConversionResult(text="\n\n".join(parts), engine=self.engine_label, pages=len(parts))
