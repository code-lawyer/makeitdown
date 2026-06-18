import json
from pathlib import Path
import makeitdown.pipeline as pl
from makeitdown.models import ConversionResult, LegacyConversionUnavailable


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
                        lambda p: ConversionResult(text="# native\n\n" + "正常的文档内容" * 5,
                                                   engine="markitdown"))

    class _Disp:
        def __init__(self, **k): pass
        def convert(self, p): return ConversionResult(text="# ocr\n\n" + "正常的文档内容" * 5,
                                                      engine="local:pp-structurev3")

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
        return ConversionResult(text="# ok\n\n" + "正常的文档内容" * 5, engine="markitdown")

    monkeypatch.setattr(pl, "convert_native", flaky)

    report = pl.convert_tree(src, out, ocr_engine="auto", ocr_model="PP-StructureV3",
                             cloud_token=None, workers=1, skip_existing=False,
                             text_threshold=50, report_path=out / "report.json")
    assert report["succeeded"] == 1
    assert report["failed"] == 1
    assert (out / "c.md").exists()
    assert not (out / "a.md").exists()
    assert any("broken file" in f["error"] for f in report["failures"])


def _single_docx(tmp_path):
    src = tmp_path / "in"
    src.mkdir()
    (src / "a.docx").write_text("x", encoding="utf-8")
    return src


def test_garbage_output_flagged_as_warned(tmp_path, monkeypatch):
    src = _single_docx(tmp_path)
    out = tmp_path / "out"
    monkeypatch.setattr(pl, "classify", lambda p, text_threshold=50: "native")
    monkeypatch.setattr(pl, "convert_native",
                        lambda p: ConversionResult(text="x", engine="markitdown"))

    report = pl.convert_tree(src, out, ocr_engine="auto", ocr_model="PP-StructureV3",
                             cloud_token=None, workers=1, skip_existing=False,
                             text_threshold=50, report_path=out / "report.json")

    assert report["succeeded"] == 0
    assert report["warned"] == 1
    assert (out / "a.md").exists()  # output is kept, not lost
    md = (out / "a.md").read_text(encoding="utf-8")
    assert "quality: suspect" in md
    assert report["warnings"][0]["file"] == "a.docx"
    assert any("near-empty" in r for r in report["warnings"][0]["reasons"])


def test_clean_output_not_warned(tmp_path, monkeypatch):
    src = _single_docx(tmp_path)
    out = tmp_path / "out"
    monkeypatch.setattr(pl, "classify", lambda p, text_threshold=50: "native")
    monkeypatch.setattr(pl, "convert_native",
                        lambda p: ConversionResult(text="正常的中文合同内容" * 5,
                                                   engine="markitdown"))

    report = pl.convert_tree(src, out, ocr_engine="auto", ocr_model="PP-StructureV3",
                             cloud_token=None, workers=1, skip_existing=False,
                             text_threshold=50, report_path=out / "report.json")
    assert report["succeeded"] == 1
    assert report["warned"] == 0
    assert "quality:" not in (out / "a.md").read_text(encoding="utf-8")


def test_quality_check_failure_is_non_fatal(tmp_path, monkeypatch):
    src = _single_docx(tmp_path)
    out = tmp_path / "out"
    monkeypatch.setattr(pl, "classify", lambda p, text_threshold=50: "native")
    monkeypatch.setattr(pl, "convert_native",
                        lambda p: ConversionResult(text="正常内容" * 10, engine="markitdown"))

    def boom(*a, **k):
        raise RuntimeError("quality checker bug")
    monkeypatch.setattr(pl, "assess", boom)

    report = pl.convert_tree(src, out, ocr_engine="auto", ocr_model="PP-StructureV3",
                             cloud_token=None, workers=1, skip_existing=False,
                             text_threshold=50, report_path=out / "report.json")
    # A buggy checker must never lose a successful conversion.
    assert report["succeeded"] == 1
    assert report["failed"] == 0
    assert (out / "a.md").exists()


def test_no_quality_check_disables_warnings(tmp_path, monkeypatch):
    src = _single_docx(tmp_path)
    out = tmp_path / "out"
    monkeypatch.setattr(pl, "classify", lambda p, text_threshold=50: "native")
    monkeypatch.setattr(pl, "convert_native",
                        lambda p: ConversionResult(text="x", engine="markitdown"))

    report = pl.convert_tree(src, out, ocr_engine="auto", ocr_model="PP-StructureV3",
                             cloud_token=None, workers=1, skip_existing=False,
                             text_threshold=50, report_path=out / "report.json",
                             quality_check=False)
    assert report["succeeded"] == 1
    assert report["warned"] == 0
    assert "quality:" not in (out / "a.md").read_text(encoding="utf-8")


def test_legacy_route_converts_like_native(tmp_path, monkeypatch):
    src = tmp_path / "in"
    src.mkdir()
    (src / "a.doc").write_bytes(b"\xd0\xcf\x11\xe0")
    out = tmp_path / "out"
    monkeypatch.setattr(pl, "classify", lambda p, text_threshold=50: "legacy")
    monkeypatch.setattr(pl, "convert_legacy",
                        lambda p: ConversionResult(text="正常的合同正文内容" * 5,
                                                   engine="legacy:com->markitdown"))

    report = pl.convert_tree(src, out, ocr_engine="auto", ocr_model="PP-StructureV3",
                             cloud_token=None, workers=1, skip_existing=False,
                             text_threshold=50, report_path=out / "report.json")
    assert report["succeeded"] == 1
    md = (out / "a.md").read_text(encoding="utf-8")
    assert "engine: legacy:com->markitdown" in md


def test_legacy_unavailable_is_skipped_with_hint(tmp_path, monkeypatch):
    src = tmp_path / "in"
    src.mkdir()
    (src / "a.doc").write_bytes(b"\xd0\xcf\x11\xe0")
    out = tmp_path / "out"
    monkeypatch.setattr(pl, "classify", lambda p, text_threshold=50: "legacy")

    def unavailable(p):
        raise LegacyConversionUnavailable("install WPS/Office or LibreOffice")
    monkeypatch.setattr(pl, "convert_legacy", unavailable)

    report = pl.convert_tree(src, out, ocr_engine="auto", ocr_model="PP-StructureV3",
                             cloud_token=None, workers=1, skip_existing=False,
                             text_threshold=50, report_path=out / "report.json")
    assert report["skipped_unsupported"] == 1
    assert report["failed"] == 0
    assert not (out / "a.md").exists()
    assert report["skipped"][0]["file"] == "a.doc"
    assert "LibreOffice" in report["skipped"][0]["reason"]


def test_same_stem_different_ext_do_not_collide(tmp_path, monkeypatch):
    src = tmp_path / "in"
    src.mkdir()
    (src / "report.docx").write_text("x", encoding="utf-8")
    (src / "report.txt").write_text("x", encoding="utf-8")
    out = tmp_path / "out"
    monkeypatch.setattr(pl, "classify", lambda p, text_threshold=50: "native")
    monkeypatch.setattr(pl, "convert_native",
                        lambda p: ConversionResult(text=f"内容来自 {p.name} " * 5,
                                                   engine="markitdown"))

    report = pl.convert_tree(src, out, ocr_engine="auto", ocr_model="PP-StructureV3",
                             cloud_token=None, workers=2, skip_existing=False,
                             text_threshold=50, report_path=out / "report.json")
    assert report["succeeded"] == 2
    # Colliding stems are disambiguated by keeping the original extension.
    assert (out / "report.docx.md").exists()
    assert (out / "report.txt.md").exists()
    assert "report.docx" in (out / "report.docx.md").read_text(encoding="utf-8")
    assert "report.txt" in (out / "report.txt.md").read_text(encoding="utf-8")


def test_unique_stem_keeps_clean_name(tmp_path, monkeypatch):
    src = tmp_path / "in"
    src.mkdir()
    (src / "report.docx").write_text("x", encoding="utf-8")
    out = tmp_path / "out"
    monkeypatch.setattr(pl, "classify", lambda p, text_threshold=50: "native")
    monkeypatch.setattr(pl, "convert_native",
                        lambda p: ConversionResult(text="正常的文档内容" * 5, engine="markitdown"))

    pl.convert_tree(src, out, ocr_engine="auto", ocr_model="PP-StructureV3",
                    cloud_token=None, workers=1, skip_existing=False,
                    text_threshold=50, report_path=out / "report.json")
    assert (out / "report.md").exists()
    assert not (out / "report.docx.md").exists()


def test_unsafe_asset_paths_are_skipped(tmp_path, monkeypatch):
    src = tmp_path / "in"
    src.mkdir()
    (src / "a.docx").write_text("x", encoding="utf-8")
    out = tmp_path / "out"
    monkeypatch.setattr(pl, "classify", lambda p, text_threshold=50: "native")
    monkeypatch.setattr(pl, "convert_native",
                        lambda p: ConversionResult(
                            text="正常的文档内容" * 5, engine="markitdown",
                            assets={"../evil.png": b"e", "sub/ok.png": b"o",
                                    "a/../../evil2.png": b"e2"}))

    pl.convert_tree(src, out, ocr_engine="auto", ocr_model="PP-StructureV3",
                    cloud_token=None, workers=1, skip_existing=False,
                    text_threshold=50, report_path=out / "report.json", keep_images=True)
    assert (out / "sub" / "ok.png").read_bytes() == b"o"          # safe asset written
    assert not (tmp_path / "evil.png").exists()                   # ../ escape blocked
    assert not (tmp_path / "evil2.png").exists()                  # a/../../ escape blocked


def test_strip_images_helper():
    from makeitdown.pipeline import _strip_images
    t = ('正文 <img src="imgs/seal.jpg" alt="Image"> 中间 ![cap](pic.png) 末尾 '
         '<div style="text-align: center;"><img src="z.png"></div> '
         '<div style="text-align: center;"><table>keep</table></div>')
    out = _strip_images(t)
    assert "<img" not in out
    assert "![" not in out
    assert "imgs/seal.jpg" not in out
    assert "<table>keep</table>" in out          # table preserved
    assert "text-align: center;\"></div>" not in out  # emptied seal div collapsed


def test_images_stripped_by_default(tmp_path, monkeypatch):
    src = tmp_path / "in"
    src.mkdir()
    (src / "a.docx").write_text("x", encoding="utf-8")
    out = tmp_path / "out"
    monkeypatch.setattr(pl, "classify", lambda p, text_threshold=50: "native")
    text = "正文内容很长很长很长" * 5 + '\n\n<div style="text-align: center;"><img src="imgs/seal.jpg"></div>'
    monkeypatch.setattr(pl, "convert_native",
                        lambda p: ConversionResult(text=text, engine="markitdown",
                                                   assets={"imgs/seal.jpg": b"JPG"}))

    pl.convert_tree(src, out, ocr_engine="auto", ocr_model="PP-StructureV3",
                    cloud_token=None, workers=1, skip_existing=False,
                    text_threshold=50, report_path=out / "report.json")
    md = (out / "a.md").read_text(encoding="utf-8")
    assert "<img" not in md and "imgs/seal.jpg" not in md
    assert not (out / "imgs" / "seal.jpg").exists()


def test_keep_images_preserves_assets(tmp_path, monkeypatch):
    src = tmp_path / "in"
    src.mkdir()
    (src / "a.docx").write_text("x", encoding="utf-8")
    out = tmp_path / "out"
    monkeypatch.setattr(pl, "classify", lambda p, text_threshold=50: "native")
    text = "正文内容很长很长很长" * 5 + '\n\n<div style="text-align: center;"><img src="imgs/seal.jpg"></div>'
    monkeypatch.setattr(pl, "convert_native",
                        lambda p: ConversionResult(text=text, engine="markitdown",
                                                   assets={"imgs/seal.jpg": b"JPG"}))

    pl.convert_tree(src, out, ocr_engine="auto", ocr_model="PP-StructureV3",
                    cloud_token=None, workers=1, skip_existing=False,
                    text_threshold=50, report_path=out / "report.json", keep_images=True)
    md = (out / "a.md").read_text(encoding="utf-8")
    assert "<img" in md
    assert (out / "imgs" / "seal.jpg").read_bytes() == b"JPG"


class _ApplyStruct:
    """Fake structurer that pretends to add a heading and label the engine."""

    def restructure(self, text):
        return ("# 标题\n" + text, "llm-heads:deepseek-chat", None)


class _SpyStruct:
    def __init__(self):
        self.calls = 0

    def restructure(self, text):
        self.calls += 1
        return text, None, None


class _WarnStruct:
    def restructure(self, text):
        return text, None, "heading structuring skipped: Timeout"


def _ocr_tree(tmp_path, monkeypatch):
    src = tmp_path / "in"
    src.mkdir()
    (src / "b.png").write_bytes(b"\x00")
    monkeypatch.setattr(pl, "classify", lambda p, text_threshold=50: "ocr")

    class _Disp:
        def __init__(self, **k):
            pass

        def convert(self, p):
            return ConversionResult(text="标题\n" + "正常的文档内容" * 5,
                                    engine="local:pp-structurev3")

    monkeypatch.setattr(pl, "OCRDispatcher", _Disp)
    return src


def test_structurer_applied_on_ocr_route(tmp_path, monkeypatch):
    src = _ocr_tree(tmp_path, monkeypatch)
    out = tmp_path / "out"
    report = pl.convert_tree(src, out, ocr_engine="auto", ocr_model="PP-StructureV3",
                             cloud_token=None, workers=1, skip_existing=False,
                             text_threshold=50, report_path=out / "report.json",
                             structurer=_ApplyStruct())
    md = (out / "b.md").read_text(encoding="utf-8")
    assert "engine: local:pp-structurev3+llm-heads:deepseek-chat" in md
    assert "# 标题" in md
    assert report["structured"] == 1
    assert report["succeeded"] == 1


def test_structurer_not_called_on_native_route(tmp_path, monkeypatch):
    src = _single_docx(tmp_path)
    out = tmp_path / "out"
    monkeypatch.setattr(pl, "classify", lambda p, text_threshold=50: "native")
    monkeypatch.setattr(pl, "convert_native",
                        lambda p: ConversionResult(text="正常的文档内容" * 5,
                                                   engine="markitdown"))
    spy = _SpyStruct()
    report = pl.convert_tree(src, out, ocr_engine="auto", ocr_model="PP-StructureV3",
                             cloud_token=None, workers=1, skip_existing=False,
                             text_threshold=50, report_path=out / "report.json",
                             structurer=spy)
    assert spy.calls == 0
    assert report["structured"] == 0
    assert report["succeeded"] == 1


def test_structurer_warning_marks_warned_but_keeps_output(tmp_path, monkeypatch):
    src = _ocr_tree(tmp_path, monkeypatch)
    out = tmp_path / "out"
    report = pl.convert_tree(src, out, ocr_engine="auto", ocr_model="PP-StructureV3",
                             cloud_token=None, workers=1, skip_existing=False,
                             text_threshold=50, report_path=out / "report.json",
                             structurer=_WarnStruct())
    assert report["warned"] == 1
    assert (out / "b.md").exists()
    md = (out / "b.md").read_text(encoding="utf-8")
    assert "quality: suspect" in md
    assert any("heading structuring skipped" in r
               for r in report["warnings"][0]["reasons"])


def test_low_confidence_ocr_flagged_as_warned(tmp_path, monkeypatch):
    src = tmp_path / "in"
    src.mkdir()
    (src / "b.png").write_bytes(b"\x00")
    out = tmp_path / "out"
    monkeypatch.setattr(pl, "classify", lambda p, text_threshold=50: "ocr")

    class _Disp:
        def __init__(self, **k):
            pass

        def convert(self, p):
            return ConversionResult(text="正常的文档内容" * 5,
                                    engine="local:pp-structurev3",
                                    confidences=[0.99, 0.30, 0.95])

    monkeypatch.setattr(pl, "OCRDispatcher", _Disp)
    report = pl.convert_tree(src, out, ocr_engine="auto", ocr_model="PP-StructureV3",
                             cloud_token=None, workers=1, skip_existing=False,
                             text_threshold=50, report_path=out / "report.json")
    assert report["warned"] == 1
    md = (out / "b.md").read_text(encoding="utf-8")
    assert "quality: suspect" in md
    assert any("low-confidence" in r for r in report["warnings"][0]["reasons"])


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
