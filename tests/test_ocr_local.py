from pathlib import Path
import makeitdown.ocr_local as ol
from makeitdown.models import ConversionResult


def test_is_available_false_when_import_fails(monkeypatch):
    def boom(name, *a, **k):
        if name == "paddleocr":
            raise ImportError("no paddleocr")
        return _real_import(name, *a, **k)
    import builtins
    _real_import = builtins.__import__
    monkeypatch.setattr(builtins, "__import__", boom)
    assert ol.LocalOCR.is_available() is False


def test_convert_uses_injected_engine(tmp_path):
    f = tmp_path / "scan.pdf"
    f.write_bytes(b"%PDF-1.4")

    class _FakeEngine:
        def predict(self, src):
            return [{"markdown": {"text": "# local md"}}]

    client = ol.LocalOCR(model="PP-StructureV3")
    client._engine = _FakeEngine()  # inject, bypass lazy load
    result = client.convert(f)
    assert isinstance(result, ConversionResult)
    assert result.text == "# local md"
    assert result.engine == "local:pp-structurev3"
    assert result.pages == 1
    assert result.assets == {}


def test_convert_collects_image_assets(tmp_path):
    f = tmp_path / "scan.pdf"
    f.write_bytes(b"%PDF-1.4")

    class _FakeEngine:
        def predict(self, src):
            return [
                {"markdown": {"text": "# p1", "images": {"imgs/a.png": b"PNGBYTES"}}},
                {"markdown": {"text": "# p2"}},
            ]

    client = ol.LocalOCR()
    client._engine = _FakeEngine()
    result = client.convert(f)
    assert result.pages == 2
    assert result.assets == {"imgs/a.png": b"PNGBYTES"}


def test_vl_model_label(tmp_path):
    f = tmp_path / "scan.png"
    f.write_bytes(b"\x89PNG")

    class _FakeEngine:
        def predict(self, src):
            return [{"markdown": {"text": "vl"}}]

    client = ol.LocalOCR(model="PaddleOCR-VL")
    client._engine = _FakeEngine()
    result = client.convert(f)
    assert result.engine == "local:paddleocr-vl"
