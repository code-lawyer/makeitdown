# makeitdown 异常警告与质检设计

日期：2026-06-15
状态：已确认，待实现

## 背景与目标

makeitdown 把整个文件夹的文档批量转成 Markdown，作为 LLM 知识库原材料。
当前对**硬失败**（PaddleOCR 抛异常、云端 job failed、文件打不开）已做文件级隔离：
单文件出错不中断整批，错误记入 `report.json` 的 `failures`。

但有两个缺口，且在实际使用中**两类失败都常发生**：

1. **软失败完全没检测**——OCR/转换跑完了但结果是垃圾（整页空白、乱码、内容异常重复、
   每页字符数异常少），当前被当作 `succeeded` 写出，下游无从察觉。
2. **警告不醒目、且不跟着文件走**——硬失败只进 `report.json`，文件一旦进入下游知识库
   就和警告脱钩。

目标：增加**异常警告**能力，让可疑产出被显式标记。

## 范围（明确边界）

经确认的三条范围约束：

- **容错粒度：文件级**。不做客户端拆页 / 逐页 salvage。崩在第 60 页的 100 页 PDF，
  整文件计入失败、不产出 .md；不试图保住前 59 页。
- **响应方式：警告 + 隔离，永不修改内容**。不自动重试、不引擎降级、不接 LLM 清洗。
  最坏情况是误报一个标记，用户忽略即可。
- **检测范围：硬失败 + 软失败都要**。

非目标（明确不做）：进度显示、页级 salvage、自动纠错/重试、LLM 二次加工、
OCR 置信度透传、语言检测。

## 架构

新增一个**纯函数质检模块**，其余皆为把它接入现有流程：

```
src/makeitdown/quality.py

assess(text: str, *, source_type: str, pages: int | None,
       thresholds: QualityThresholds) -> list[str]
```

- 输入转换后的 markdown 正文，返回**人类可读的警告原因列表**；空列表 = 正常。
- 纯函数、无 I/O、可独立测试。
- `pipeline` 在转换成功后调用一次。
- **不触碰 OCR 引擎、不拆页、不改 ConversionResult 的转换语义**。

`QualityThresholds` 为一个简单 dataclass，承载可调阈值，默认值见下。

## 检测规则

`assess()` 跑 4 条规则，全部保守（默认偏向少误报）。每条触发返回**带实测数值**的原因串。

| 规则 | 触发条件（默认阈值，可调） | 示例原因串 |
|---|---|---|
| 近乎空白 | 有意义字符总数 < `min_chars`（默认 20） | `near-empty output (8 chars)` |
| 每页字符过低 | 仅当 `pages` 已知且 **≥ 2**：总字符 / 页数 < `min_chars_per_page`（默认 50） | `avg 12 chars/page over 30 pages` |
| 乱码比例高 | 替换符(U+FFFD)+控制符+异常符号 占非空白字符 > `garbled_ratio`（默认 0.02） | `garbled-char ratio 7.3%` |
| 异常重复 | 某条长度 > 10 的非空行重复 > `repeat_count`（默认 30）次 | `line repeated 142x (possible OCR loop)` |

字符计数口径（统一）：前两条规则的"字符数"均指**非空白字符数**
（`len("".join(text.split()))`），不剥离 markdown 语法符号；保持简单、可预测。

设计决定：

- **故意不做语言检测**（如"中文文档却没中文就报警"）。法律场景有大量纯英文合同、
  纯数字财务表，语言检测会狂误报；"乱码比例"已能抓真正的乱码，更稳。
- **重复阈值调高到 30**：判决书/合同的页眉页脚、表格本就重复，低了会误报。
- **每页字符规则要求 pages ≥ 2**：单页文档可能本就很短（封面、单页通知），只在
  多页文档上判"每页几乎没字"才有意义，否则会误报短的单页件。
- "异常符号"定义：非空白且不属于 {CJK、字母、数字、常见标点} 的字符。

## 数据落地

### report.json（不破坏现有结构，加两项）

```jsonc
{
  "succeeded": 120,     // 产出且干净
  "warned": 8,          // 新增：产出了但质检可疑
  "failed": 3,          // 硬失败，无产出（已有）
  "skipped_existing": 0,
  "skipped_unsupported": 2,
  "failures": [ { "file": "...", "error": "..." } ],   // 已有
  "warnings": [                                          // 新增
    { "file": "合同/扫描件03.pdf",
      "reasons": ["avg 12 chars/page over 30 pages", "garbled-char ratio 7.3%"] }
  ]
}
```

语义：**`succeeded` 与 `warned` 互斥**。succeeded = 产出且干净，warned = 产出但可疑。
"有多少份输出信不过"一眼可见。两者之和 = 成功产出 .md 的文件数。

### frontmatter（仅可疑文件追加；干净文件完全不变）

```yaml
---
source: 合同/扫描件03.pdf
source_type: pdf
engine: cloud:paddleocr-vl-1.6
pages: 30
converted_at: 2026-06-15T10:30:00
quality: suspect          # 仅可疑文件才有
warnings:                 # YAML 列表
  - "avg 12 chars/page over 30 pages"
  - "garbled-char ratio 7.3%"
---
```

价值：警告**跟着文件进知识库**——Obsidian 肉眼可见、Dataview 可 `WHERE quality = "suspect"`
过滤、喂给 LLM 时可对可疑文档降权。`build_frontmatter` 需小改以支持输出 YAML 列表
（当前仅支持标量）。

### 硬失败

文件级、不产出 .md，**不写空壳**（避免污染知识库）。只进 `report.failures` +
stderr 即时醒目提示。

## 错误处理

核心原则：**质检自己绝不能拖垮转换**。

- `pipeline` 调 `assess()` 时包一层 try/except：质检自身抛异常则当作"无警告"，
  文件照常写出。转换已成功，绝不能因质检器 bug 反而丢结果。
- 硬失败沿用现有"每文件 catch → `report.failures`"，额外在 stderr 即时打一行提示。
- 线程安全：`handle()` 返回值扩成 `(status, rel, detail)`，`detail` 为
  `None` / 错误串(failed) / 原因列表(warned)。汇总仍只在主循环单线程做（现有不变量），
  worker 不碰共享 `report`。
- 可疑文件流程：转换成功 → `assess` → 有原因则带警告写 .md + 返回 `warned`；
  无原因则写干净 .md + `succeeded`。

## CLI

新增开关：

- `--warn-min-chars N`（默认 20）
- `--warn-min-chars-per-page N`（默认 50）
- `--warn-garbled-ratio F`（默认 0.02）
- `--warn-repeat-count N`（默认 30）
- `--no-quality-check`：一键关闭质检（所有产出按 succeeded 处理）

总览行加入 warned 计数，例如：
`Done. succeeded=120 warned=8 failed=3 skipped_existing=0 skipped_unsupported=2`
并在有 warned/failed 时提示查看 report.json。

## 测试（按 TDD，先写测试）

- `test_quality.py`（新）：逐规则用例表——空白 / 每页低字符（含 pages 未知分支）/
  乱码 / 重复各自命中；干净文本返回 `[]`；阈值边界；**反误报样本**：正常中文段落、
  纯英文合同、纯数字表格、重复次数低于阈值的页眉，均不应报。
- `test_frontmatter.py`：warnings 渲染成 YAML 列表 + 引号转义；干净文件不出现
  `quality`/`warnings`。
- `test_pipeline.py`：①转换器吐垃圾 → 写出 + `warned` + report.warnings +
  frontmatter 带 `quality: suspect`；②转换器抛异常 → `failed`、无 .md；
  ③`assess` 抛异常 → 当干净处理、文件照写、不崩；④succeeded/warned 计数互斥。
- `test_cli.py`：总览行含 warned 计数；`--no-quality-check` 生效。

## 受影响文件

- 新增：`src/makeitdown/quality.py`、`tests/test_quality.py`
- 修改：`src/makeitdown/pipeline.py`（接入 assess、扩展 report 与 handle 返回）、
  `src/makeitdown/frontmatter.py`（支持 YAML 列表、新增可选字段）、
  `src/makeitdown/cli.py`（新增阈值开关、总览行）、
  `tests/test_pipeline.py`、`tests/test_frontmatter.py`、`tests/test_cli.py`
- 文档：`README.md`（说明质检与开关）
