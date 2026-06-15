import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from .convert_native import convert as convert_native
from .convert_ocr import OCRDispatcher
from .frontmatter import build_frontmatter, prepend_frontmatter
from .router import classify


def _iter_files(input_dir: Path):
    for p in sorted(input_dir.rglob("*")):
        if p.is_file():
            yield p


def _is_up_to_date(src: Path, md: Path) -> bool:
    return md.exists() and md.stat().st_mtime >= src.stat().st_mtime


def _write_output(out_md: Path, result, source_rel: str, source_type: str):
    out_md.parent.mkdir(parents=True, exist_ok=True)
    fm = build_frontmatter(
        source=source_rel,
        source_type=source_type,
        engine=result.engine,
        pages=result.pages,
        converted_at=datetime.now().isoformat(timespec="seconds"),
    )
    out_md.write_text(prepend_frontmatter(result.text, fm), encoding="utf-8")
    for rel, data in result.assets.items():
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
) -> dict:
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    dispatcher = OCRDispatcher(
        engine=ocr_engine, model=ocr_model, token=cloud_token
    )

    report = {
        "succeeded": 0,
        "failed": 0,
        "skipped_existing": 0,
        "skipped_unsupported": 0,
        "failures": [],
    }

    def handle(src: Path):
        rel = src.relative_to(input_dir)
        out_md = output_dir / rel.with_suffix(".md")
        route = classify(src, text_threshold=text_threshold)
        if route == "unsupported":
            return ("skipped_unsupported", rel, None)
        if skip_existing and _is_up_to_date(src, out_md):
            return ("skipped_existing", rel, None)
        try:
            if route == "native":
                result = convert_native(src)
            else:
                result = dispatcher.convert(src)
            _write_output(out_md, result, str(rel).replace("\\", "/"), src.suffix.lstrip("."))
            return ("succeeded", rel, None)
        except Exception as e:  # never abort the batch
            return ("failed", rel, f"{type(e).__name__}: {e}")

    files = list(_iter_files(input_dir))
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for status, rel, err in pool.map(handle, files):
            report[status] += 1
            if status == "failed":
                report["failures"].append({"file": str(rel).replace("\\", "/"), "error": err})

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
