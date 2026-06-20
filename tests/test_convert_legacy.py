from pathlib import Path

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


def test_convert_passes_absolute_path_to_backend(tmp_path, monkeypatch):
    # External converters (Word COM, LibreOffice) resolve relative paths against
    # their own working dir, not ours — convert() must hand them an absolute path.
    monkeypatch.chdir(tmp_path)
    rel = Path("old.doc")
    rel.write_bytes(OLE2 + b"binary")

    seen = {}
    def fake_com(src, out_docx):
        seen["src"] = src
        out_docx.write_bytes(ZIP + b"converted")
        return True
    monkeypatch.setattr(cl, "_convert_via_com", fake_com)
    monkeypatch.setattr(cl, "_convert_via_libreoffice", lambda src, out_dir: None)
    monkeypatch.setattr(cl, "convert_native",
                        lambda p: ConversionResult(text="# ok", engine="markitdown"))

    cl.convert(rel)  # relative path in
    assert Path(seen["src"]).is_absolute()


class _FakeDoc:
    def SaveAs2(self, path, FileFormat=None):
        pass

    def Close(self, flag):
        pass


def test_word_session_reuses_one_app_and_quits_once():
    # The whole batch must share one Word instance (open once, convert N, quit
    # once) instead of cold-starting/quitting Word per file.
    state = {"dispatched": 0, "quits": 0}

    class _App:
        def __init__(self):
            self.Documents = type("D", (), {"Open": lambda self, p: _FakeDoc()})()

        def Quit(self):
            state["quits"] += 1

    def dispatch():
        state["dispatched"] += 1
        return _App()

    sess = cl._WordSession(dispatch)
    assert sess.convert("a.doc", "a.docx") is True
    assert sess.convert("b.doc", "b.docx") is True
    assert sess.convert("c.doc", "c.docx") is True
    assert state["dispatched"] == 1  # created once, reused
    sess.shutdown()
    assert state["quits"] == 1  # quit once, at shutdown


def test_word_session_serializes_concurrent_calls():
    # COM must never be driven from two threads at once (the RPC-crash cause).
    import threading
    import time

    active = {"now": 0, "max": 0}
    guard = threading.Lock()

    class _Docs:
        def Open(self, p):
            with guard:
                active["now"] += 1
                active["max"] = max(active["max"], active["now"])
            time.sleep(0.02)
            with guard:
                active["now"] -= 1
            return _FakeDoc()

    class _App:
        Documents = _Docs()

        def Quit(self):
            pass

    sess = cl._WordSession(lambda: _App())
    threads = [threading.Thread(target=lambda i=i: sess.convert(f"{i}.doc", f"{i}.docx"))
               for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert active["max"] == 1  # never two COM operations concurrently
    sess.shutdown()


def test_word_session_no_app_returns_false_without_retrying():
    # If Word/WPS isn't available, conclude once — don't re-attempt per file.
    state = {"n": 0}

    def dispatch():
        state["n"] += 1
        return None

    sess = cl._WordSession(dispatch)
    assert sess.convert("a.doc", "a.docx") is False
    assert sess.convert("b.doc", "b.docx") is False
    assert state["n"] == 1
    sess.shutdown()


def test_com_short_circuits_off_windows(tmp_path, monkeypatch):
    monkeypatch.setattr(cl.platform, "system", lambda: "Linux")
    assert cl._convert_via_com(tmp_path / "x.doc", tmp_path / "x.docx") is False


def test_libreoffice_short_circuits_without_soffice(tmp_path, monkeypatch):
    monkeypatch.setattr(cl.shutil, "which", lambda name: None)
    assert cl._convert_via_libreoffice(tmp_path / "x.doc", tmp_path) is None
