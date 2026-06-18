import argparse
import os
import sys
from pathlib import Path

from .pipeline import convert_tree
from .quality import QualityThresholds
from .structure import HeadingStructurer


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
    p.add_argument("--keep-images", action="store_true",
                   help="keep images extracted from scans (default: text-only output)")
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
    # LLM heading-structure reconstruction (opt-in; OCR output only).
    p.add_argument("--structure-headings", action="store_true",
                   help="rebuild heading levels of OCR output via an LLM "
                        "(needs --llm-base-url/--llm-model/--llm-api-key)")
    p.add_argument("--llm-base-url", default=None,
                   help="OpenAI-compatible endpoint (default: env MAKEITDOWN_LLM_BASE_URL)")
    p.add_argument("--llm-model", default=None,
                   help="LLM model name (default: env MAKEITDOWN_LLM_MODEL)")
    p.add_argument("--llm-api-key", default=None,
                   help="LLM API key (default: env MAKEITDOWN_LLM_API_KEY)")
    p.add_argument("--llm-max-heading-len", type=int, default=80,
                   help="max length of a candidate heading line")
    p.add_argument("--llm-max-lines", type=int, default=1500,
                   help="skip structuring if candidate lines exceed this")
    p.add_argument("--llm-max-heading-ratio", type=float, default=0.35,
                   help="if headings exceed this fraction, treat doc as unstructured")
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

    structurer = None
    if args.structure_headings:
        base_url = args.llm_base_url or os.environ.get("MAKEITDOWN_LLM_BASE_URL")
        model = args.llm_model or os.environ.get("MAKEITDOWN_LLM_MODEL")
        api_key = args.llm_api_key or os.environ.get("MAKEITDOWN_LLM_API_KEY")
        if not (base_url and model and api_key):
            print(
                "error: --structure-headings requires --llm-base-url / --llm-model / "
                "--llm-api-key (or env MAKEITDOWN_LLM_BASE_URL / MAKEITDOWN_LLM_MODEL / "
                "MAKEITDOWN_LLM_API_KEY)",
                file=sys.stderr,
            )
            return 2
        structurer = HeadingStructurer(
            base_url, api_key, model,
            max_heading_len=args.llm_max_heading_len,
            max_input_lines=args.llm_max_lines,
            max_heading_ratio=args.llm_max_heading_ratio,
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
        keep_images=args.keep_images,
        structurer=structurer,
    )

    structured = (f"structured={report.get('structured', 0)} "
                  if args.structure_headings else "")
    print(
        f"Done. succeeded={report['succeeded']} warned={report['warned']} "
        f"{structured}failed={report['failed']} "
        f"skipped_existing={report['skipped_existing']} "
        f"skipped_unsupported={report['skipped_unsupported']}"
    )
    if report["warned"]:
        print(f"{report['warned']} file(s) flagged for quality. See {report_path}.",
              file=sys.stderr)
    if report.get("skipped"):
        print(f"{len(report['skipped'])} file(s) need an external converter "
              f"(see {report_path} for how to convert them).", file=sys.stderr)
    if report["failed"]:
        print(f"See {report_path} for {report['failed']} failure(s).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
