from pathlib import Path
import makeitdown.convert_ocr as co
from makeitdown.models import ConversionResult, OCRUnavailableError


class _FakeBackend:
    def __init__(self, label):
        self._label = label

    def convert(self, path):
        return ConversionResult(text=f"md from {self._label}", engine=self._label)


def test_auto_prefers_local_when_available(monkeypatch):
    monkeypatch.setattr(co.LocalOCR, "is_available", staticmethod(lambda: True))
    monkeypatch.setattr(co, "LocalOCR", lambda **k: _FakeBackend("local:pp-structurev3"))
    d = co.OCRDispatcher(engine="auto", token=None)
    r = d.convert(Path("x.png"))
    assert r.engine == "local:pp-structurev3"


def test_auto_falls_back_to_cloud_when_local_missing(monkeypatch):
    monkeypatch.setattr(co.LocalOCR, "is_available", staticmethod(lambda: False))
    monkeypatch.setattr(co, "CloudOCR", lambda **k: _FakeBackend("cloud:paddleocr-vl-1.6"))
    d = co.OCRDispatcher(engine="auto", token="TKN")
    r = d.convert(Path("x.png"))
    assert r.engine == "cloud:paddleocr-vl-1.6"


def test_auto_raises_clear_error_when_neither(monkeypatch):
    monkeypatch.setattr(co.LocalOCR, "is_available", staticmethod(lambda: False))
    d = co.OCRDispatcher(engine="auto", token=None)
    try:
        d.convert(Path("x.png"))
        assert False, "expected OCRUnavailableError"
    except OCRUnavailableError as e:
        msg = str(e)
        assert "makeitdown[local]" in msg
        assert "PADDLEOCR_AISTUDIO_TOKEN" in msg


def test_explicit_cloud_without_token_raises(monkeypatch):
    d = co.OCRDispatcher(engine="cloud", token=None)
    try:
        d.convert(Path("x.png"))
        assert False, "expected OCRUnavailableError"
    except OCRUnavailableError as e:
        assert "PADDLEOCR_AISTUDIO_TOKEN" in str(e)
