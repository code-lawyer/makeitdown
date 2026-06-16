import makeitdown.convert_legacy as cl
from makeitdown.models import ConversionResult, LegacyConversionUnavailable

OLE2 = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
ZIP = b"PK\x03\x04"


def test_ooxml_under_wrong_extension_goes_through_markitdown(tmp_path, monkeypatch):
    # A .wps that is really a .docx (OOXML/ZIP) — T1, zero dependencies.
    f = tmp_path / "really_docx.wps"
    f.write_bytes(ZIP + b"rest-of-zip")

    seen = {}
    def fake_native(p):
        seen["path"] = str(p)
        return ConversionResult(text="# from docx", engine="markitdown", pages=2)
    monkeypatch.setattr(cl, "convert_native", fake_native)

    result = cl.convert(f)
    assert result.text == "# from docx"
    assert result.engine == "markitdown"
    assert seen["path"].endswith(".docx")  # handed to markitdown as a docx


def test_ole2_via_com(tmp_path, monkeypatch):
    f = tmp_path / "old.doc"
    f.write_bytes(OLE2 + b"binary")

    def fake_com(src, out_docx):
        out_docx.write_bytes(ZIP + b"converted")
        return True
    monkeypatch.setattr(cl, "_convert_via_com", fake_com)
    monkeypatch.setattr(cl, "_convert_via_libreoffice", lambda src, out_dir: None)
    monkeypatch.setattr(cl, "convert_native",
                        lambda p: ConversionResult(text="# ok", engine="markitdown", pages=5))

    result = cl.convert(f)
    assert result.text == "# ok"
    assert result.pages == 5
    assert result.engine == "legacy:com->markitdown"


def test_ole2_via_libreoffice_when_com_unavailable(tmp_path, monkeypatch):
    f = tmp_path / "old.doc"
    f.write_bytes(OLE2 + b"binary")

    monkeypatch.setattr(cl, "_convert_via_com", lambda src, out_docx: False)

    def fake_lo(src, out_dir):
        produced = out_dir / "old.docx"
        produced.write_bytes(ZIP + b"converted")
        return produced
    monkeypatch.setattr(cl, "_convert_via_libreoffice", fake_lo)
    monkeypatch.setattr(cl, "convert_native",
                        lambda p: ConversionResult(text="# lo", engine="markitdown"))

    result = cl.convert(f)
    assert result.text == "# lo"
    assert result.engine == "legacy:libreoffice->markitdown"


def test_ole2_no_backend_raises_with_actionable_hint(tmp_path, monkeypatch):
    f = tmp_path / "old.doc"
    f.write_bytes(OLE2 + b"binary")
    monkeypatch.setattr(cl, "_convert_via_com", lambda src, out_docx: False)
    monkeypatch.setattr(cl, "_convert_via_libreoffice", lambda src, out_dir: None)

    try:
        cl.convert(f)
        assert False, "expected LegacyConversionUnavailable"
    except LegacyConversionUnavailable as e:
        msg = str(e)
        assert "WPS" in msg or "Office" in msg or "LibreOffice" in msg


def test_com_short_circuits_off_windows(tmp_path, monkeypatch):
    monkeypatch.setattr(cl.platform, "system", lambda: "Linux")
    assert cl._convert_via_com(tmp_path / "x.doc", tmp_path / "x.docx") is False


def test_libreoffice_short_circuits_without_soffice(tmp_path, monkeypatch):
    monkeypatch.setattr(cl.shutil, "which", lambda name: None)
    assert cl._convert_via_libreoffice(tmp_path / "x.doc", tmp_path) is None
