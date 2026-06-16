# makeitdown

把一整个文件夹的文档**批量转换为高保真 Markdown**，作为 LLM 知识库的原材料。中国大陆可用，无需海外服务。

基于 [microsoft/markitdown](https://github.com/microsoft/markitdown)（原生格式）与 [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR)（扫描件/图片）。

## 它做什么

- 递归扫描输入目录，按文件类型自动路由：
  - **原生文档**（Word/Excel/PPT、HTML、csv/json/xml、txt/md、epub、**有文字层的 PDF**）→ markitdown
  - **扫描件 / 图片型 PDF / 图片**（png/jpg/bmp/tiff…）→ PaddleOCR
  - **老式 .doc / .wps** → 先嗅探内核：实为 .docx 的直接转；真二进制用已装的 Word/WPS 或
    LibreOffice（见下文「老式 .doc / .wps」）
- 输出**镜像输入目录结构**的 `.md`，每个文件带 YAML frontmatter（`source` / `source_type` / `engine` / `pages` / `converted_at`），便于溯源与 Obsidian Dataview。
- 单文件出错不中断整批，结果汇总到 `report.json`。

PDF 是否走 OCR：用 PyMuPDF 检测文字层——每页平均可提取字符数低于阈值（默认 50）即判为扫描件。

## 安装（国内网络优化）

需要 **Python 3.11 或 3.12**；用本地版的话建议 **3.11**（PaddlePaddle 对 3.11 支持最稳）。先有 Python 再装 uv：

```bash
pip install uv -i https://pypi.tuna.tsinghua.edu.cn/simple
```

然后**二选一**——两个版本的区别：

| | 本地版 | 云端版 |
|---|---|---|
| 联网 | 转换时**不需要** | 需要 |
| 账号 / token | **不需要**，装完即用 | 需去[百度 AI Studio](https://aistudio.baidu.com/)拿 token |
| 隐私 | 文档**不出本机** | 文档上传到百度服务器 |
| 费用 | 免费 | 可能按量计费 |
| 体积 / 速度 | 大（几百 MB），转换较慢 | 小、装得快、转换较快 |

```bash
# 本地版（离线、免费、私密；体积大）
uv tool install --python 3.11 --index https://pypi.tuna.tsinghua.edu.cn/simple \
  "makeitdown[local] @ git+https://gitee.com/code-lawyer/makeitdown.git"

# 云端版（轻快；需联网 + token）
uv tool install --python 3.11 --index https://pypi.tuna.tsinghua.edu.cn/simple \
  "makeitdown @ git+https://gitee.com/code-lawyer/makeitdown.git"
```

装完执行 `makeitdown --help` 验证。命令找不到时运行 `uv tool update-shell` 后开新终端。

说明：
- 代码走 **Gitee 镜像**、依赖走**清华 PyPI 源**，避开 GitHub/PyPI 在国内的卡顿；PaddleOCR 模型由百度托管，国内下载很快。
- uv 自动下载 Python 是从 GitHub 拉的，国内可能慢——所以请先备好 Python 3.11；若 uv 仍有问题，用纯 pip 后备：
  ```bash
  pip install "makeitdown @ git+https://gitee.com/code-lawyer/makeitdown.git" \
    -i https://pypi.tuna.tsinghua.edu.cn/simple
  ```
- **海外用户**：去掉 `--index`/`-i` 参数，并把 `gitee.com` 换成 `github.com`。

## 使用

```bash
makeitdown <输入目录> -o <输出目录>
```

输出目录默认为 `<输入目录>_md`；`report.json` 默认写入输出目录。

### OCR 后端

| `--ocr-engine` | 说明 |
|---|---|
| `auto`（默认） | 本地 PaddleOCR 已安装则用本地，否则在配置了 token 时降级到云端 |
| `local` | 本地 PaddleOCR PP-StructureV3，需装“本地版”（见上） |
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
| `--no-quality-check` | 关闭输出质检（所有产出按正常处理） |
| `--warn-min-chars N` | 非空白字符数低于此值则警告（默认 20） |
| `--warn-min-chars-per-page N` | 多页文档每页平均字符数低于此值则警告（默认 50） |
| `--warn-garbled-ratio F` | 乱码字符比例超过此值则警告（默认 0.02） |
| `--warn-repeat-count N` | 某行重复超过此次数则警告（默认 30） |

### 质检与异常警告

转换**成功但结果可疑**的文件（整页空白、乱码、内容异常重复、多页却几乎没字），不会被
当作正常结果悄悄写出，而是会被**标记**——既进 `report.json` 的 `warnings`，也写进该 `.md`
的 frontmatter（`quality: suspect` + `warnings` 列表），警告随文件进入下游知识库。

- **只警告、不改内容**：质检永不修改或删除你的转换结果，最坏只是误报一个标记。
- **硬失败**（转换直接报错）仍按原样隔离：不产出 `.md`，记入 `report.json` 的 `failures`，
  单文件出错不中断整批。
- 阈值都可用上面的 `--warn-*` 选项调整；`--no-quality-check` 可整体关闭。

`report.json` 中 `succeeded` 与 `warned` 互斥：前者是产出且干净，后者是产出但可疑。

### 老式 .doc / .wps

`.doc`（老 Word 二进制）和 `.wps`（金山）markitdown 读不了，makeitdown 会分层处理：

1. **内容嗅探（零依赖）**：很多"`.doc`/`.wps`"其实是改了后缀的 `.docx`（OOXML）——直接当
   `.docx` 转，无需任何外部工具。
2. **已装的 Word / WPS（Windows）**：真二进制文件，调用本机**已安装**的 Word 或金山 WPS
   转换。需装可选依赖 `makeitdown[com]`（只装 COM 桥，不装 Office）：
   ```bash
   uv tool install --python 3.11 --index https://pypi.tuna.tsinghua.edu.cn/simple \
     "makeitdown[com] @ git+https://gitee.com/code-lawyer/makeitdown.git"
   ```
3. **LibreOffice（可选）**：若 `soffice` 已在 PATH，则用它转换（跨平台）。makeitdown
   **不会自动安装 LibreOffice**；需要的话请自行安装（国内走清华/中科大镜像）。
4. **都没有**：该文件不会被硬转成垃圾，而是**干净跳过**并记入 `report.json` 的 `skipped`，
   附上"怎样才能转成功"的说明。

> makeitdown 自身从不静默安装任何外部程序；要不要装 LibreOffice 完全由你决定。

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

转换完成后，把构建 wiki 的工作流指向 `<输出目录>`——干净的 Markdown + frontmatter 正适合 LLM 增量消化、交叉引用。仓库内也提供了一个薄 skill（`skill/makeitdown/SKILL.md`），让 agent 知道何时调用本工具。

## 开发（从源码）

```bash
git clone https://gitee.com/code-lawyer/makeitdown.git   # 海外用 github.com
cd makeitdown
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple
.venv/Scripts/python -m pytest -q
```

> Windows 用 `.venv/Scripts/python`；macOS/Linux 用 `.venv/bin/python`。
