"""Convert legacy/ambiguous office formats (.doc, .wps) to Markdown.

Strategy, in order of preference and cost:

  T1  content sniff  — a .doc/.wps that is really OOXML (a renamed .docx) is
                       handed straight to markitdown. Zero dependencies.
  T2  COM            — drive an *already-installed* Word / Kingsoft WPS on
                       Windows to produce a .docx, then markitdown it.
  T4  LibreOffice    — if `soffice` is already on PATH, convert via headless
                       LibreOffice. This module never *installs* anything.
  T3  skip + hint    — none available: raise LegacyConversionUnavailable with
                       an actionable message so the file is skipped knowingly.
"""

import atexit
import platform
import shutil
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .convert_native import convert as convert_native
from .models import ConversionResult, LegacyConversionUnavailable

# A single Word/WPS COM operation can take seconds; cap it so one hung document
# can't block a worker forever.
_COM_CALL_TIMEOUT = 300.0
_WD_FORMAT_DOCX = 16  # wdFormatDocumentDefault

_HINT = (
    "legacy .doc/.wps needs Microsoft Word or WPS Office installed (Windows), "
    "or LibreOffice on PATH; none found — skipped."
)

_OOXML_MAGIC = b"PK\x03\x04"
_OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def _sniff(path: Path) -> str:
    """Return 'ooxml', 'ole2', or 'unknown' from the file's magic bytes."""
    with open(path, "rb") as fh:
        head = fh.read(8)
    if head.startswith(_OOXML_MAGIC):
        return "ooxml"
    if head.startswith(_OLE2_MAGIC):
        return "ole2"
    return "unknown"


def _default_dispatch():
    """Attach to an already-installed Word/WPS via COM (Windows only).

    Runs on the session's dedicated thread, so CoInitialize happens on the same
    thread that will drive the app. Returns the app, or None if unavailable.
    """
    try:
        import pythoncom  # noqa: PLC0415
        import win32com.client  # noqa: PLC0415
    except Exception:
        return None
    try:
        pythoncom.CoInitialize()
    except Exception:
        pass
    for prog_id in ("Word.Application", "KWPS.Application", "WPS.Application"):
        try:
            app = win32com.client.Dispatch(prog_id)
        except Exception:
            continue
        try:
            app.Visible = False
        except Exception:
            pass
        return app
    return None


class _WordSession:
    """Owns one Word/WPS COM instance on a single dedicated thread.

    All COM work (attach, open, save, quit) runs on that one thread, which keeps
    the STA object on its creating thread and serializes access — so many worker
    threads can call ``convert`` without driving COM concurrently (the cause of
    "RPC server unavailable" crashes) and without cold-starting Word per file.
    The app is created lazily, reused across the whole batch, and quit once at
    shutdown. If no app is available it's concluded once, not retried per file.
    """

    def __init__(self, dispatch_fn=_default_dispatch):
        self._dispatch = dispatch_fn
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._app = None
        self._resolved = False

    def convert(self, src, out_docx) -> bool:
        try:
            return self._executor.submit(self._run, str(src), str(out_docx)).result(
                timeout=_COM_CALL_TIMEOUT
            )
        except Exception:
            return False

    def _app_or_none(self):
        if not self._resolved:
            self._resolved = True
            self._app = self._dispatch()
        return self._app

    def _run(self, src: str, out_docx: str) -> bool:
        app = self._app_or_none()
        if app is None:
            return False
        doc = None
        try:
            doc = app.Documents.Open(src)
            doc.SaveAs2(out_docx, FileFormat=_WD_FORMAT_DOCX)
            return True
        except Exception:
            return False
        finally:
            if doc is not None:
                try:
                    doc.Close(False)
                except Exception:
                    pass

    def shutdown(self):
        def _quit():
            if self._app is not None:
                try:
                    self._app.Quit()
                except Exception:
                    pass
                self._app = None
            try:
                import pythoncom  # noqa: PLC0415

                pythoncom.CoUninitialize()
            except Exception:
                pass

        try:
            self._executor.submit(_quit).result(timeout=30)
        except Exception:
            pass
        self._executor.shutdown(wait=True)


_session = None
_session_lock = threading.Lock()


def _get_session() -> _WordSession:
    global _session
    if _session is None:
        with _session_lock:
            if _session is None:
                _session = _WordSession()
                atexit.register(_session.shutdown)
    return _session


def _convert_via_com(src: Path, out_docx: Path) -> bool:
    """Use an already-installed Word/WPS via COM to save `src` as a .docx.

    Returns True on success. Windows-only; a no-op everywhere else. Delegates to
    a shared, serialized, instance-reusing session. Never installs anything — it
    only drives an application the user already has.
    """
    if platform.system() != "Windows":
        return False
    return _get_session().convert(src, out_docx)


def _convert_via_libreoffice(src: Path, out_dir: Path) -> Path | None:
    """Convert `src` to .docx via headless LibreOffice if `soffice` is on PATH.

    Returns the produced .docx path, or None if LibreOffice is absent/fails.
    Never installs LibreOffice — only uses it when already present.
    """
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return None
    try:
        subprocess.run(
            [soffice, "--headless", "--convert-to", "docx",
             "--outdir", str(out_dir), str(src)],
            check=True, capture_output=True, timeout=120,
        )
    except Exception:
        return None
    produced = out_dir / (src.stem + ".docx")
    return produced if produced.exists() else None


def _relabel(result: ConversionResult, engine: str) -> ConversionResult:
    return ConversionResult(text=result.text, engine=engine,
                            pages=result.pages, assets=result.assets)


def convert(path: Path) -> ConversionResult:
    # Resolve to absolute: Word COM and LibreOffice resolve relative paths against
    # their own working directory, not ours, so a relative path would not be found.
    src = Path(path).resolve()
    kind = _sniff(src)
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        if kind == "ooxml":
            # Really a .docx under the wrong extension — let markitdown read it.
            docx = td_path / (src.stem + ".docx")
            shutil.copyfile(src, docx)
            return convert_native(docx)

        if kind == "ole2":
            out_docx = td_path / (src.stem + ".docx")
            if _convert_via_com(src, out_docx) and out_docx.exists():
                return _relabel(convert_native(out_docx), "legacy:com->markitdown")
            produced = _convert_via_libreoffice(src, td_path)
            if produced and produced.exists():
                return _relabel(convert_native(produced), "legacy:libreoffice->markitdown")

        raise LegacyConversionUnavailable(_HINT)
