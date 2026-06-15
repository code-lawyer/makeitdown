from pathlib import Path
import makeitdown.router as router


def test_native_extensions(tmp_path):
    for name in ["a.docx", "b.xlsx", "c.pptx", "d.html", "e.csv", "f.json", "g.txt", "h.epub"]:
        p = tmp_path / name
        p.write_text("x", encoding="utf-8")
        assert router.classify(p) == "native"


def test_image_extensions(tmp_path):
    for name in ["a.png", "b.jpg", "c.jpeg", "d.bmp", "e.tiff"]:
        p = tmp_path / name
        p.write_bytes(b"\x00")
        assert router.classify(p) == "ocr"


def test_unsupported_extension(tmp_path):
    p = tmp_path / "a.zip.unknownext"
    p.write_bytes(b"\x00")
    assert router.classify(p) == "unsupported"


def test_pdf_with_text_layer_is_native(tmp_path, monkeypatch):
    p = tmp_path / "doc.pdf"
    p.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(router, "_pdf_avg_chars_per_page", lambda path: 500.0)
    assert router.classify(p, text_threshold=50) == "native"


def test_pdf_without_text_layer_is_ocr(tmp_path, monkeypatch):
    p = tmp_path / "scan.pdf"
    p.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(router, "_pdf_avg_chars_per_page", lambda path: 3.0)
    assert router.classify(p, text_threshold=50) == "ocr"
