import argparse
import os
import sys
from pathlib import Path

from .pipeline import convert_tree


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
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    input_dir = Path(args.input)
    output_dir = Path(args.output) if args.output else Path(f"{input_dir}_md")
    token = args.cloud_token or os.environ.get("PADDLEOCR_AISTUDIO_TOKEN")
    report_path = Path(args.report) if args.report else output_dir / "report.json"

    report = convert_tree(
        input_dir, output_dir,
        ocr_engine=args.ocr_engine,
        ocr_model=args.ocr_model,
        cloud_token=token,
        workers=args.workers,
        skip_existing=args.skip_existing,
        text_threshold=args.text_threshold,
        report_path=report_path,
    )

    print(
        f"Done. succeeded={report['succeeded']} failed={report['failed']} "
        f"skipped_existing={report['skipped_existing']} "
        f"skipped_unsupported={report['skipped_unsupported']}"
    )
    if report["failed"]:
        print(f"See {report_path} for {report['failed']} failure(s).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
