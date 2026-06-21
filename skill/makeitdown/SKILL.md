---
name: makeitdown
description: Batch-convert a folder of documents (Office, PDF, scanned PDF, images) into high-fidelity Markdown for use as LLM knowledge-base raw material. Routes native formats through markitdown and scanned/image content through PaddleOCR (local PP-StructureV3, or the AI Studio cloud API). On first use, install the tool via this skill — it offers the user a Cloud edition vs a Local edition. Use whenever the user wants to convert, digitize, OCR, or batch-process a directory of documents into Markdown for an LLM wiki/knowledge base.
---

# makeitdown

Batch document → Markdown converter. Prefer this over hand-orchestrating markitdown/PaddleOCR per file: the CLI does the deterministic routing, concurrency, frontmatter, and error reporting.

The target users are **non-technical (Windows or macOS)**. Drive the install for them — don't hand them raw commands to run. Use the install commands below yourself via the shell, and explain choices in plain language.

---

## First run: install if needed

Before the first conversion, check whether the tool is already installed:

```bash
makeitdown --help
```

If that succeeds, skip ahead to **Usage**. If the command is not found, install it by following the steps below.

### Step 1 — Let the user choose an edition

There are two editions. **Do not pick for the user** — present both neutrally and ask which they want. Relay this comparison in plain language (Chinese if the user writes Chinese):

| | 本地版 (Local) | 云端版 (Cloud) |
|---|---|---|
| 是否需要联网 | 转换时**不需要**联网 | **需要**联网 |
| 是否需要账号/token | **不需要**，装完即用 | 需要去百度 AI Studio 注册账号、生成 token |
| 隐私 | 文档**不出本机** | 文档会上传到百度服务器 |
| 费用 | 免费 | 可能按量计费 |
| 安装体积/速度 | **大**（几百 MB），第一次下模型慢 | 小，装得快 |
| 转换速度 | 吃电脑性能，较慢 | 由服务器算，较快 |
| 一句话 | 省心、私密、免费，但占空间、较慢 | 轻快，但要联网、要弄 token、要上传文档 |

Tell the user honestly: **Local is usually the most hassle-free for a non-technical user** (no account, no token, works offline), at the cost of disk space and speed. Cloud is lighter to install but requires obtaining a token, which is itself a hurdle. Then let them decide.

### China network note (important — the target users are in mainland China)

GitHub and PyPI are slow/flaky from China; build the install around domestic mirrors:

- **Code** is installed from a **Gitee mirror**, not GitHub: `git+https://gitee.com/code-lawyer/makeitdown.git`. (Replace `code-lawyer` with the actual Gitee username if it differs.)
- **Python dependencies** are pulled from the **Tsinghua PyPI mirror**: `https://pypi.tuna.tsinghua.edu.cn/simple`.
- **PaddleOCR models** (Local edition) download from Baidu's domestic servers — these are fast in China, no mirror needed.
- **uv's own auto-download of Python comes from GitHub** and may stall in China. So prefer an already-installed Python 3.11; only fall back to uv-managed Python if the machine has none.

### Step 2 — Make sure Python 3.11 and uv are present

1. **Python 3.11** (the package needs ≥3.11, <3.13). Check `python --version`. If it's not 3.11/3.12, have the user install Python 3.11 via a domestic-friendly route (e.g. Miniconda from the Tsinghua mirror, or python.org). Relying on an existing interpreter avoids uv fetching Python from GitHub.
2. **uv** — install it from the Tsinghua mirror (avoids astral.sh):
   ```bash
   pip install uv -i https://pypi.tuna.tsinghua.edu.cn/simple
   ```

### Step 3 — Install the chosen edition

**If you were handed the agent bundle** (an unzipped `makeitdown-agent` folder that
contains `pyproject.toml` and `src/`), install directly from it — no Gitee/GitHub
fetch needed. From inside that folder:

```bash
# Local edition
pip install ".[local]" -i https://pypi.tuna.tsinghua.edu.cn/simple
# Cloud edition
pip install "." -i https://pypi.tuna.tsinghua.edu.cn/simple
```

**Otherwise, install from the remote** (Gitee source + Tsinghua mirror). Run **one** of these:

- **本地版 (Local):**
  ```bash
  uv tool install --python 3.11 --index https://pypi.tuna.tsinghua.edu.cn/simple "makeitdown[local] @ git+https://gitee.com/code-lawyer/makeitdown.git"
  ```
  This pulls PaddleOCR + PaddlePaddle (a large download) — tell the user it may take several minutes. PaddleOCR models download on first conversion (from Baidu, fast in China).

- **云端版 (Cloud):**
  ```bash
  uv tool install --python 3.11 --index https://pypi.tuna.tsinghua.edu.cn/simple "makeitdown @ git+https://gitee.com/code-lawyer/makeitdown.git"
  ```

If uv gives trouble, the plain-pip fallback (needs an existing Python 3.11) works the same way:
```bash
pip install "makeitdown @ git+https://gitee.com/code-lawyer/makeitdown.git" -i https://pypi.tuna.tsinghua.edu.cn/simple
```

Confirm it worked: `makeitdown --help`. If the command isn't on PATH yet, run `uv tool update-shell` (then open a new shell) or invoke it via `uv tool run --from makeitdown makeitdown ...`.

> Outside mainland China: drop `--index ...`/`-i ...` and use the GitHub URL `git+https://github.com/code-lawyer/makeitdown.git`.

### Step 4 — Cloud edition only: set the token

The Cloud edition needs a PaddleOCR AI Studio token. Walk the user through getting one at https://aistudio.baidu.com/ , then set it as an environment variable (never hardcode it, never put it on the command line where it lands in shell history):

- **macOS:** `export PADDLEOCR_AISTUDIO_TOKEN="<token>"` (add to `~/.zshrc` to persist)
- **Windows (PowerShell):** `setx PADDLEOCR_AISTUDIO_TOKEN "<token>"` (persists for new shells)

The Local edition needs no token — skip this step.

---

## Usage

```bash
makeitdown <input_dir> -o <output_dir>
```

Output mirrors the input directory structure; each `.md` carries YAML frontmatter
(`source`, `source_type`, `engine`, `pages`, `converted_at`). A `report.json` lists
succeeded/failed/skipped files. A single broken file never aborts the batch.

## OCR backend

`--ocr-engine` defaults to `auto`: use local PaddleOCR if the Local edition is
installed, else fall back to the cloud API when a token is set. Force a backend with
`--ocr-engine local` or `--ocr-engine cloud` if needed. The cloud token comes from
env `PADDLEOCR_AISTUDIO_TOKEN` (or `--cloud-token`).

## Common options

- `--skip-existing` — incremental: skip files whose `.md` is newer than the source.
- `--workers N` — concurrency (native conversions run in parallel; local OCR is
  serialized internally for thread-safety, so this mainly speeds up native files).
- `--text-threshold N` — avg chars/page below which a PDF is treated as scanned.
- `--keep-images` — keep images extracted from scans (default: text-only output).

## Quality flags (suspect output travels with the file)

Conversions that *succeed but look wrong* (near-empty, garbled, runaway repetition,
multi-page with almost no text, or **low OCR confidence**) are not silently emitted
as clean — they are flagged into `report.json` **and** the `.md` frontmatter
(`quality: suspect` + a `warnings` list). For legal/high-stakes use, surface these
to the user for manual review.

- `--no-quality-check` — disable all checks (treat every output as clean).
- `--warn-min-confidence F` — flag if any OCR region scores below this (0-1,
  default 0.6; **local PP-StructureV3 only** — cloud PaddleOCR-VL exposes no
  per-region scores, so the rule is simply inactive there).
- `--warn-min-chars N`, `--warn-min-chars-per-page N`, `--warn-garbled-ratio F`,
  `--warn-repeat-count N` — other thresholds; defaults are conservative.

Thresholds are not yet calibrated against a real corpus — for a new deployment,
run a small sample first and tune (see `docs/2026-06-18-field-validation-plan.md`).

## Optional: LLM heading reconstruction for OCR output

Scanned output is flat text with no `#` heading levels. `--structure-headings`
rebuilds heading levels **for OCR-routed files only**, using an LLM that returns
*only* a line→level map — body text is copied byte-for-byte and can never be
altered (safe for amounts/dates). Off by default; needs an OpenAI-compatible
endpoint (point it at a domestic provider: DeepSeek / Qwen / Moonshot / Zhipu).

```bash
# prefer env vars; a key on the command line lands in shell history
export MAKEITDOWN_LLM_BASE_URL="https://api.deepseek.com/v1"
export MAKEITDOWN_LLM_MODEL="deepseek-chat"
export MAKEITDOWN_LLM_API_KEY="<key>"
makeitdown <input_dir> --ocr-engine local --structure-headings
```

Successfully structured files get an engine suffix (`...+llm-heads:<model>`) and
count toward `report.json`'s `structured`. Non-hierarchical material (chat logs,
lists) stays flat; any failure falls back to the original text.

## Reading the results (machine-readable contract)

After a run, parse `<output_dir>/report.json`:

```jsonc
{
  "succeeded": 120,   // produced and clean
  "warned": 8,        // produced but quality: suspect (review these)
  "structured": 34,   // had LLM heading reconstruction applied
  "failed": 3,        // hard error, no .md produced
  "skipped_existing": 0,
  "skipped_unsupported": 2,
  "failures": [ { "file": "...", "error": "..." } ],
  "warnings": [ { "file": "...", "reasons": ["avg 12 chars/page over 30 pages"] } ],
  "skipped":  [ { "file": "a.doc", "reason": "needs WPS/Office or LibreOffice" } ]
}
```

`succeeded` and `warned` are mutually exclusive. An agent should report `warned`
(and `failures`/`skipped`) back to the user — never present output as trustworthy
without checking. Each suspect `.md` also carries `quality: suspect` + `warnings`
in frontmatter, so downstream (Obsidian/Dataview) can filter on it.

## Programmatic use (non-CLI agents)

```python
from pathlib import Path
from makeitdown.pipeline import convert_tree

report = convert_tree(
    Path("in"), Path("out"),
    ocr_engine="auto", ocr_model="PP-StructureV3", cloud_token=None,
    workers=4, skip_existing=True, text_threshold=50,
    report_path=Path("out/report.json"),
)
# report is the same dict written to report.json
```

## Installing this skill into another agent

This `skill/makeitdown/` directory *is* the package. Copy it into the target
agent's skills location (e.g. an agent's `.claude/skills/makeitdown/` or a plugin's
`skills/` dir). The skill drives installation of the `makeitdown` CLI itself on
first use (see First run). The CLI and the skill are distributed separately: the
PyPI/Gitee package ships the CLI; this folder ships the agent instructions.

## Legacy .doc / .wps files (install transparency — read before acting)

makeitdown handles old `.doc` and `.wps` by first sniffing the real container:
a file that is actually OOXML (a renamed `.docx`) is converted with zero extra
tooling. Only genuine legacy binaries need an external converter, and here you
MUST be transparent with the user:

- **Never silently install anything.** Conversion of true `.doc`/`.wps` binaries
  uses, in order: (1) an **already-installed** Microsoft Word or Kingsoft WPS on
  Windows (via the optional `makeitdown[com]` extra — the COM bridge drives an app
  the user already has, it installs no office suite); (2) **LibreOffice only if
  `soffice` is already on PATH**. makeitdown itself installs neither.
- **LibreOffice is a several-hundred-MB download.** If the user has no Word/WPS and
  wants those files converted, explain in plain language what LibreOffice is, the
  rough size, why it's needed, and where to get it — then install it **only after
  explicit consent**. Do not decide for them. In mainland China, point them at a
  domestic mirror (e.g. Tsinghua/USTC LibreOffice mirror), not the official site.
- **Relay the skip report.** Files that couldn't be converted appear in
  `report.json` under `skipped` with a `reason`. Read those reasons back to the
  user so they can choose how to proceed (install WPS/Office, or LibreOffice).
- The `makeitdown[com]` extra installs from the **Tsinghua PyPI mirror** like the
  rest (`-i https://pypi.tuna.tsinghua.edu.cn/simple`).

## When to use

The user wants to turn a directory of documents/case files/papers/reports into
Markdown to feed an LLM knowledge base (see the `llm-wiki.md` pattern). Install if
needed (see First run), run the CLI, then point the wiki-building workflow at
`<output_dir>`.
