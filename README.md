# makeitdown

把一整个文件夹的文档**批量转换为高保真 Markdown**，作为 LLM 知识库（参见 `llm-wiki.md` 模式）的原材料。中国大陆可用，无需海外服务。

基于 [microsoft/markitdown](https://github.com/microsoft/markitdown)（原生格式）与 [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR)（扫描件/图片）。

## 它做什么

- 递归扫描输入目录，按文件类型自动路由：
  - **原生文档**（Word/Excel/PPT、HTML、csv/json/xml、txt/md、epub、**有文字层的 PDF**）→ markitdown
  - **扫描件 / 图片型 PDF / 图片**（png/jpg/bmp/tiff…）→ PaddleOCR
- 输出**镜像输入目录结构**的 `.md`，每个文件带 YAML frontmatter（`source` / `source_type` / `engine` / `pages` / `converted_at`），便于溯源与 Obsidian Dataview。
- 单文件出错不中断整批，结果汇总到 `report.json`。

PDF 是否走 OCR：用 PyMuPDF 检测文字层——每页平均可提取字符数低于阈值（默认 50）即判为扫描件。

## 安装

需要 Python 3.11（PaddlePaddle 暂不支持更新的版本）。

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e .          # 核心：markitdown + 云端 OCR
# 可选：本地 OCR（体积较大）
.venv/Scripts/python -m pip install -e ".[local]" # 额外安装 paddleocr + paddlepaddle
```

> Windows 用 `.venv/Scripts/python`；macOS/Linux 用 `.venv/bin/python`。

## 使用

```bash
makeitdown <输入目录> -o <输出目录>
```

输出目录默认为 `<输入目录>_md`；`report.json` 默认写入输出目录。

### OCR 后端

| `--ocr-engine` | 说明 |
|---|---|
| `auto`（默认） | 本地 PaddleOCR 已安装则用本地，否则在配置了 token 时降级到云端 |
| `local` | 本地 PaddleOCR PP-StructureV3，需 `pip install -e ".[local]"` |
| `cloud` | PaddleOCR AI Studio 云端 API，需 token |

云端 token 从 `--cloud-token` 或环境变量 `PADDLEOCR_AISTUDIO_TOKEN` 读取，**绝不硬编码**：

```bash
# PowerShell
$env:PADDLEOCR_AISTUDIO_TOKEN = "你的token"
makeitdown docs --ocr-engine cloud
```

### 常用选项

| 选项 | 说明 |
|---|---|
| `-o, --output DIR` | 输出目录（默认 `<输入>_md`） |
| `--ocr-engine {auto,local,cloud}` | OCR 后端（默认 auto） |
| `--ocr-model NAME` | 本地模型（默认 `PP-StructureV3`，可选 `PaddleOCR-VL`） |
| `--cloud-token TOKEN` | 云端 token（默认读环境变量） |
| `--workers N` | 并发数（默认按 CPU 核数） |
| `--skip-existing` | 输出比源文件新则跳过（轻量增量） |
| `--text-threshold N` | PDF 判定为扫描件的每页平均字符数阈值（默认 50） |
| `--report PATH` | report.json 路径 |

## 输出示例

```markdown
---
source: 合同/2024采购框架.pdf
source_type: pdf
engine: cloud:paddleocr-vl-1.6
pages: 12
converted_at: 2026-06-15T10:30:00
---

# 采购框架协议
...
```

## 配合 LLM 知识库

转换完成后，把构建 wiki 的工作流指向 `<输出目录>`——干净的 Markdown + frontmatter 正适合 LLM 增量消化、交叉引用，详见 `llm-wiki.md`。仓库内也提供了一个薄 skill（`skill/makeitdown/SKILL.md`），让 agent 知道何时调用本工具。

## 开发

```bash
.venv/Scripts/python -m pytest -q
```

设计文档与实现计划见仓库提交历史。
