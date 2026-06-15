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

### Step 2 — Make sure `uv` is installed

`uv` is the installer; it also auto-provisions the required Python (3.11). Check first:

```bash
uv --version
```

If not found, install it (pick the user's OS):

- **macOS:** `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Windows (PowerShell):** `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`

After installing uv, you may need a new shell for it to be on PATH; if `uv` still isn't found, restart the shell or run `uv tool update-shell`.

### Step 3 — Install the chosen edition

Run **one** of these (uv fetches Python 3.11 automatically if missing):

- **本地版 (Local):**
  ```bash
  uv tool install --python 3.11 "makeitdown[local] @ git+https://github.com/code-lawyer/makeitdown.git"
  ```
  This pulls PaddleOCR + PaddlePaddle (a large download) — tell the user it may take several minutes. PaddleOCR models download on first conversion.

- **云端版 (Cloud):**
  ```bash
  uv tool install --python 3.11 "makeitdown @ git+https://github.com/code-lawyer/makeitdown.git"
  ```

Confirm it worked: `makeitdown --help`. If the command isn't on PATH yet, either run `uv tool update-shell` (then new shell) or invoke it via `uv tool run --from makeitdown makeitdown ...`.

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
- `--workers N` — concurrency.
- `--text-threshold N` — avg chars/page below which a PDF is treated as scanned.

## When to use

The user wants to turn a directory of documents/case files/papers/reports into
Markdown to feed an LLM knowledge base (see the `llm-wiki.md` pattern). Install if
needed (see First run), run the CLI, then point the wiki-building workflow at
`<output_dir>`.
