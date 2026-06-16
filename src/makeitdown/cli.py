import argparse
import os
import sys
from pathlib import Path

from .pipeline import convert_tree
from .quality import QualityThresholds


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="makeitdown",
        description="Batch convert documents to high-fidelity Markdown for LLM knowledge bases.",
    )
    p.add_argument("input", help="input directory to scan recursively")
    p.add_argument("-o", "--output", help="output directory (default: <input>_md)")
    p.add_argument("--ocr-engine", choices=["local", "cloud", "auto"], default="auto",
                   help="OCR backend (default: auto = local first, fall back to cloud)")
    p.add_argument("--ocr-model", default=None,
                   help="OCR model; applies to whichever backend runs "
                        "(local default PP-StructureV3, cloud default PaddleOCR-VL-1.6)")
    p.add_argument("--cloud-token", default=None,
                   help="AI Studio token (default: env PADDLEOCR_AISTUDIO_TOKEN)")
    p.add_argument("--workers", type=int, default=os.cpu_count() or 4,
                   help="number of concurrent workers")
    p.add_argument("--skip-existing", action="store_true",
                   help="skip files whose .md output is newer than the source")
    p.add_argument("--text-threshold", type=int, default=50,
                   help="avg chars/page below which a PDF is treated as scanned")
    p.add_argument("--report", default=None, help="path to report.json")
    p.add_argument("--no-quality-check", dest="quality_check", action="store_false",
                   help="disable output quality checks (treat all output as clean)")
    # Defaults sourced from QualityThresholds so there is one source of truth.
    qt = QualityThresholds()
    p.add_argument("--warn-min-chars", type=int, default=qt.min_chars,
                   help="warn if non-whitespace char count is below this")
    p.add_argument("--warn-min-chars-per-page", type=int, default=qt.min_chars_per_page,
                   help="warn if avg chars/page (multi-page docs) is below this")
    p.add_argument("--warn-garbled-ratio", type=float, default=qt.garbled_ratio,
                   help="warn if garbled-character ratio exceeds this (0-1)")
    p.add_argument("--warn-repeat-count", type=int, default=qt.repeat_count,
                   help="warn if a line repeats more than this many times")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    input_dir = Path(args.input)
    output_dir = Path(args.output) if args.output else Path(f"{input_dir}_md")
    token = args.cloud_token or os.environ.get("PADDLEOCR_AISTUDIO_TOKEN")
    report_path = Path(args.report) if args.report else output_dir / "report.json"

    thresholds = QualityThresholds(
        min_chars=args.warn_min_chars,
        min_chars_per_page=args.warn_min_chars_per_page,
        garbled_ratio=args.warn_garbled_ratio,
        repeat_count=args.warn_repeat_count,
    )

    report = convert_tree(
        input_dir, output_dir,
        ocr_engine=args.ocr_engine,
        ocr_model=args.ocr_model,
        cloud_token=token,
        workers=args.workers,
        skip_existing=args.skip_existing,
        text_threshold=args.text_threshold,
        report_path=report_path,
        quality_check=args.quality_check,
        quality_thresholds=thresholds,
    )

    print(
        f"Done. succeeded={report['succeeded']} warned={report['warned']} "
        f"failed={report['failed']} skipped_existing={report['skipped_existing']} "
        f"skipped_unsupported={report['skipped_unsupported']}"
    )
    if report["warned"]:
        print(f"{report['warned']} file(s) flagged for quality. See {report_path}.",
              file=sys.stderr)
    if report["failed"]:
        print(f"See {report_path} for {report['failed']} failure(s).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
