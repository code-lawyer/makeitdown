from pathlib import Path
import makeitdown.ocr_local as ol
from makeitdown.models import ConversionResult


class _FakeRes:
    """Mimics paddlex LayoutParsingResultV2: a `.markdown` dict with
    `markdown_texts` (str) and `markdown_images` (dict)."""

    def __init__(self, text, images=None):
        self.markdown = {"markdown_texts": text, "markdown_images": images or {}}


class _FakeEngine:
    def __init__(self, results):
        self._results = results

    def predict(self, src):
        return self._results


def test_is_available_false_when_spec_missing(monkeypatch):
    monkeypatch.setattr(ol.importlib.util, "find_spec", lambda name: None)
    assert ol.LocalOCR.is_available() is False


def test_is_available_true_when_spec_present(monkeypatch):
    monkeypatch.setattr(ol.importlib.util, "find_spec", lambda name: object())
    assert ol.LocalOCR.is_available() is True


def test_convert_uses_injected_engine(tmp_path):
    f = tmp_path / "scan.pdf"
    f.write_bytes(b"%PDF-1.4")

    client = ol.LocalOCR(model="PP-StructureV3")
    client._engine = _FakeEngine([_FakeRes("# local md")])  # inject, bypass lazy load
    result = client.convert(f)
    assert isinstance(result, ConversionResult)
    assert result.text == "# local md"
    assert result.engine == "local:pp-structurev3"
    assert result.pages == 1
    assert result.assets == {}


def test_convert_collects_image_assets(tmp_path):
    f = tmp_path / "scan.pdf"
    f.write_bytes(b"%PDF-1.4")

    client = ol.LocalOCR()
    client._engine = _FakeEngine([
        _FakeRes("# p1", images={"imgs/a.png": b"PNGBYTES"}),
        _FakeRes("# p2"),
    ])
    result = client.convert(f)
    assert result.pages == 2
    assert result.text == "# p1\n\n# p2"
    assert result.assets == {"imgs/a.png": b"PNGBYTES"}


class _ScoredRes:
    """Mimics a PP-StructureV3 page: `.markdown` plus subscriptable
    `["overall_ocr_res"]["rec_scores"]`."""

    def __init__(self, text, scores):
        self.markdown = {"markdown_texts": text, "markdown_images": {}}
        self._d = {"overall_ocr_res": {"rec_scores": scores}}

    def __getitem__(self, key):
        return self._d[key]


def test_convert_collects_rec_scores_across_pages(tmp_path):
    f = tmp_path / "scan.pdf"
    f.write_bytes(b"%PDF-1.4")
    client = ol.LocalOCR()
    client._engine = _FakeEngine([_ScoredRes("# p1", [0.99, 0.4]),
                                  _ScoredRes("# p2", [0.95])])
    result = client.convert(f)
    assert result.confidences == [0.99, 0.4, 0.95]


def test_convert_without_scores_leaves_confidences_none(tmp_path):
    f = tmp_path / "scan.pdf"
    f.write_bytes(b"%PDF-1.4")
    client = ol.LocalOCR()
    client._engine = _FakeEngine([_FakeRes("# p1")])  # no overall_ocr_res
    result = client.convert(f)
    assert result.confidences is None


def test_vl_model_label(tmp_path):
    f = tmp_path / "scan.png"
    f.write_bytes(b"\x89PNG")

    client = ol.LocalOCR(model="PaddleOCR-VL")
    client._engine = _FakeEngine([_FakeRes("vl")])
    result = client.convert(f)
    assert result.engine == "local:paddleocr-vl"
