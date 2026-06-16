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

    def _engine_class(self):
        # Honour the requested model. PaddleOCR-VL is a separate pipeline class
        # from PP-StructureV3; both expose .predict() returning per-page results
        # whose .markdown dict has "markdown_texts" and "markdown_images".
        if "vl" in self.model.lower():
            from paddleocr import PaddleOCRVL  # noqa: PLC0415

            return PaddleOCRVL
        from paddleocr import PPStructureV3  # noqa: PLC0415

        return PPStructureV3

    def _ensure_engine(self):
        if self._engine is None:
            cls = self._engine_class()
            # Disable oneDNN/MKLDNN: paddle 3.x crashes in the oneDNN executor
            # on some models/CPUs ("ConvertPirAttribute2RuntimeAttribute not
            # support"). Reliability over speed. Fall back if a pipeline class
            # doesn't accept the kwarg.
            try:
                self._engine = cls(enable_mkldnn=False)
            except TypeError:
                self._engine = cls()
        return self._engine

    @staticmethod
    def _extract_assets(markdown: dict) -> dict[str, bytes]:
        """Serialize any in-memory images the pipeline attached to a page.

        Local pipelines hand back PIL images keyed by relative path; mirror the
        cloud backend by writing them alongside the .md. Defensive: a single
        unserializable image is skipped rather than failing the conversion.
        """
        import io

        assets: dict[str, bytes] = {}
        for rel, img in (markdown.get("markdown_images") or {}).items():
            try:
                if isinstance(img, (bytes, bytearray)):
                    assets[rel] = bytes(img)
                    continue
                buf = io.BytesIO()
                img.save(buf, format="PNG")  # PIL.Image
                assets[rel] = buf.getvalue()
            except Exception:
                continue
        return assets

    def convert(self, path: Path) -> ConversionResult:
        with self._lock:
            engine = self._ensure_engine()
            results = list(engine.predict(str(path)))
            parts: list[str] = []
            assets: dict[str, bytes] = {}
            for r in results:
                md = r.markdown  # paddlex result: dict with markdown_texts/images
                parts.append(md["markdown_texts"])
                assets.update(self._extract_assets(md))
        return ConversionResult(
            text="\n\n".join(parts),
            engine=self.engine_label,
            pages=len(results),
            assets=assets,
        )
