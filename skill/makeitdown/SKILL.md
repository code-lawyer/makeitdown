---
name: makeitdown
description: Batch-convert a folder of documents (Office, PDF, scanned PDF, images) into high-fidelity Markdown for use as LLM knowledge-base raw material. Routes native formats through markitdown and scanned/image content through PaddleOCR (local PP-StructureV3 or AI Studio cloud API). Use whenever the user wants to convert, digitize, OCR, or batch-process a directory of documents into Markdown for an LLM wiki/knowledge base.
---

# makeitdown

Batch document → Markdown converter. Prefer this over hand-orchestrating markitdown/PaddleOCR per file: the CLI does the deterministic routing, concurrency, frontmatter, and error reporting.

## Usage

```bash
makeitdown <input_dir> -o <output_dir>
```

Output mirrors the input directory structure; each `.md` carries YAML frontmatter
(`source`, `source_type`, `engine`, `pages`, `converted_at`). A `report.json` lists
succeeded/failed/skipped files.

## OCR backend

- `--ocr-engine auto` (default): use local PaddleOCR if installed, else fall back to
  the cloud API when a token is set.
- `--ocr-engine local`: requires `pip install "makeitdown[local]"`.
- `--ocr-engine cloud`: requires a token — set env `PADDLEOCR_AISTUDIO_TOKEN`
  or pass `--cloud-token`. Never hardcode the token.

## Common options

- `--skip-existing` — incremental: skip files whose `.md` is newer than the source.
- `--workers N` — concurrency.
- `--text-threshold N` — avg chars/page below which a PDF is treated as scanned.

## When to use

The user wants to turn a directory of documents/case files/papers/reports into
Markdown to feed an LLM knowledge base (see the `llm-wiki.md` pattern). Run the CLI,
then point the wiki-building workflow at `<output_dir>`.
