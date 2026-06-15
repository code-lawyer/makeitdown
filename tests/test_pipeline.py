import json
from pathlib import Path
import makeitdown.pipeline as pl
from makeitdown.models import ConversionResult


def _setup_tree(tmp_path):
    src = tmp_path / "in"
    (src / "sub").mkdir(parents=True)
    (src / "a.docx").write_text("x", encoding="utf-8")
    (src / "sub" / "b.png").write_bytes(b"\x00")
    (src / "note.unknownext").write_bytes(b"\x00")
    return src


def test_convert_tree_writes_mirrored_md_and_report(tmp_path, monkeypatch):
    src = _setup_tree(tmp_path)
    out = tmp_path / "out"

    monkeypatch.setattr(pl, "classify",
                        lambda p, text_threshold=50: {"docx": "native", "png": "ocr"}.get(
                            p.suffix.lstrip("."), "unsupported"))
    monkeypatch.setattr(pl, "convert_native",
                        lambda p: ConversionResult(text="# native", engine="markitdown"))

    class _Disp:
        def __init__(self, **k): pass
        def convert(self, p): return ConversionResult(text="# ocr", engine="local:pp-structurev3")

    monkeypatch.setattr(pl, "OCRDispatcher", _Disp)

    report = pl.convert_tree(src, out, ocr_engine="auto", ocr_model="PP-StructureV3",
                             cloud_token=None, workers=2, skip_existing=False,
                             text_threshold=50, report_path=out / "report.json")

    a_md = (out / "a.md").read_text(encoding="utf-8")
    b_md = (out / "sub" / "b.md").read_text(encoding="utf-8")
    assert a_md.startswith("---\n") and "# native" in a_md
    assert "engine: markitdown" in a_md
    assert "# ocr" in b_md
    assert report["succeeded"] == 2
    assert report["skipped_unsupported"] == 1
    saved = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert saved["succeeded"] == 2


def test_convert_tree_records_failures_without_aborting(tmp_path, monkeypatch):
    src = tmp_path / "in"
    src.mkdir()
    (src / "a.docx").write_text("x", encoding="utf-8")
    (src / "c.docx").write_text("x", encoding="utf-8")
    out = tmp_path / "out"

    monkeypatch.setattr(pl, "classify", lambda p, text_threshold=50: "native")

    def flaky(p):
        if p.name == "a.docx":
            raise ValueError("broken file")
        return ConversionResult(text="# ok", engine="markitdown")

    monkeypatch.setattr(pl, "convert_native", flaky)

    report = pl.convert_tree(src, out, ocr_engine="auto", ocr_model="PP-StructureV3",
                             cloud_token=None, workers=1, skip_existing=False,
                             text_threshold=50, report_path=out / "report.json")
    assert report["succeeded"] == 1
    assert report["failed"] == 1
    assert (out / "c.md").exists()
    assert not (out / "a.md").exists()
    assert any("broken file" in f["error"] for f in report["failures"])


def test_skip_existing_skips_up_to_date_output(tmp_path, monkeypatch):
    src = tmp_path / "in"
    src.mkdir()
    f = src / "a.docx"
    f.write_text("x", encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    md = out / "a.md"
    md.write_text("old", encoding="utf-8")
    import os, time
    future = time.time() + 100
    os.utime(md, (future, future))  # output newer than source

    monkeypatch.setattr(pl, "classify", lambda p, text_threshold=50: "native")
    called = {"n": 0}
    def conv(p):
        called["n"] += 1
        return ConversionResult(text="# new", engine="markitdown")
    monkeypatch.setattr(pl, "convert_native", conv)

    report = pl.convert_tree(src, out, ocr_engine="auto", ocr_model="PP-StructureV3",
                             cloud_token=None, workers=1, skip_existing=True,
                             text_threshold=50, report_path=out / "report.json")
    assert called["n"] == 0
    assert report["skipped_existing"] == 1
    assert md.read_text(encoding="utf-8") == "old"
