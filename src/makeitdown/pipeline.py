import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from .convert_legacy import convert as convert_legacy
from .convert_native import convert as convert_native
from .convert_ocr import OCRDispatcher
from .frontmatter import build_frontmatter, prepend_frontmatter
from .models import LegacyConversionUnavailable
from .quality import QualityThresholds, assess
from .router import classify


def _iter_files(input_dir: Path) -> list[Path]:
    return sorted(p for p in input_dir.rglob("*") if p.is_file())


def _is_up_to_date(src: Path, md: Path) -> bool:
    return md.exists() and md.stat().st_mtime >= src.stat().st_mtime


def _is_safe_asset_rel(rel: str) -> bool:
    """Reject asset paths that would escape the output directory.

    Asset keys come from the OCR engine (cloud API / paddle); an absolute path
    or one containing '..' could write outside the per-document folder.
    """
    p = Path(rel)
    return not p.is_absolute() and ".." not in p.parts


def _write_output(out_md: Path, result, source_rel: str, source_type: str,
                  warnings: list[str] | None = None):
    out_md.parent.mkdir(parents=True, exist_ok=True)
    fm = build_frontmatter(
        source=source_rel,
        source_type=source_type,
        engine=result.engine,
        pages=result.pages,
        converted_at=datetime.now().isoformat(timespec="seconds"),
        warnings=warnings,
    )
    out_md.write_text(prepend_frontmatter(result.text, fm), encoding="utf-8")
    for rel, data in result.assets.items():
        if not _is_safe_asset_rel(rel):
            continue  # skip path-escaping assets rather than write outside output
        asset_path = out_md.parent / rel
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_bytes(data)


def convert_tree(
    input_dir: Path,
    output_dir: Path,
    *,
    ocr_engine: str,
    ocr_model: str,
    cloud_token: str | None,
    workers: int,
    skip_existing: bool,
    text_threshold: int,
    report_path: Path,
    quality_check: bool = True,
    quality_thresholds: QualityThresholds | None = None,
) -> dict:
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    dispatcher = OCRDispatcher(
        engine=ocr_engine, model=ocr_model, token=cloud_token
    )

    report = {
        "succeeded": 0,
        "warned": 0,
        "failed": 0,
        "skipped_existing": 0,
        "skipped_unsupported": 0,
        "failures": [],
        "warnings": [],
        "skipped": [],
    }

    files = _iter_files(input_dir)
    # Two sources with the same stem but different extensions (e.g. report.pdf
    # and report.docx) would both map to report.md and overwrite each other.
    # Detect those collisions up front and disambiguate by keeping the original
    # extension (report.pdf.md); unique stems keep the clean name.
    md_counts = Counter(
        f.relative_to(input_dir).with_suffix(".md").as_posix() for f in files
    )

    def _out_md_for(rel: Path) -> Path:
        base = rel.with_suffix(".md")
        if md_counts[base.as_posix()] > 1:
            return output_dir / rel.parent / (rel.name + ".md")
        return output_dir / base

    def _quality_reasons(result, source_type: str) -> list[str]:
        # A buggy quality checker must never lose a successful conversion.
        if not quality_check:
            return []
        try:
            return assess(result.text, source_type=source_type,
                          pages=result.pages, thresholds=quality_thresholds)
        except Exception:
            return []

    def handle(src: Path):
        rel = src.relative_to(input_dir)
        out_md = _out_md_for(rel)
        # Cheap stat check first so re-runs don't open (and decode) files just to skip them.
        if skip_existing and _is_up_to_date(src, out_md):
            return ("skipped_existing", rel, None)
        route = classify(src, text_threshold=text_threshold)
        if route == "unsupported":
            return ("skipped_unsupported", rel, None)
        try:
            source_type = src.suffix.lstrip(".")
            if route == "native":
                result = convert_native(src)
            elif route == "legacy":
                result = convert_legacy(src)
            else:
                result = dispatcher.convert(src)
            reasons = _quality_reasons(result, source_type)
            _write_output(out_md, result, rel.as_posix(), source_type,
                          warnings=reasons)
            if reasons:
                return ("warned", rel, reasons)
            return ("succeeded", rel, None)
        except LegacyConversionUnavailable as e:
            # Recognized but no converter available: skip knowingly with a hint.
            return ("skipped_unsupported", rel, str(e))
        except Exception as e:  # never abort the batch
            return ("failed", rel, f"{type(e).__name__}: {e}")

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for future in as_completed(pool.submit(handle, src) for src in files):
            status, rel, detail = future.result()
            report[status] += 1
            if status == "failed":
                report["failures"].append({"file": rel.as_posix(), "error": detail})
            elif status == "warned":
                report["warnings"].append({"file": rel.as_posix(), "reasons": detail})
            elif status == "skipped_unsupported" and detail:
                report["skipped"].append({"file": rel.as_posix(), "reason": detail})

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
