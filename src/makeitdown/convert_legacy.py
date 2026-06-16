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

import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

from .convert_native import convert as convert_native
from .models import ConversionResult, LegacyConversionUnavailable

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


def _convert_via_com(src: Path, out_docx: Path) -> bool:
    """Use an already-installed Word/WPS via COM to save `src` as a .docx.

    Returns True on success. Windows-only; a no-op everywhere else. Never
    installs anything — it only drives an application the user already has.
    """
    if platform.system() != "Windows":
        return False
    try:
        import pythoncom  # noqa: PLC0415
        import win32com.client  # noqa: PLC0415
    except Exception:
        return False

    pythoncom.CoInitialize()  # COM must be initialized per worker thread
    try:
        for prog_id in ("Word.Application", "KWPS.Application", "WPS.Application"):
            try:
                app = win32com.client.Dispatch(prog_id)
            except Exception:
                continue
            try:
                try:
                    app.Visible = False
                except Exception:
                    pass
                doc = app.Documents.Open(str(src))
                doc.SaveAs2(str(out_docx), FileFormat=16)  # 16 = wdFormatDocumentDefault (.docx)
                doc.Close(False)
                return True
            except Exception:
                continue
            finally:
                try:
                    app.Quit()
                except Exception:
                    pass
        return False
    finally:
        pythoncom.CoUninitialize()


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
