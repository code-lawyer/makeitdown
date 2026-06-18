# makeitdown LLM 标题层级重建设计

日期：2026-06-18
状态：已确认，待实现（Phase 1）

## 背景与目标

参考 knowhere 与 docling 后的关键发现：**Obsidian 的层级树是白送的——只要 markdown 的标题级别（`#`/`##`/`###`）正确。**

- **原生文档**（走 markitdown）：标题层级通常已保留，无需处理。
- **扫描件 / 图片**（走 PaddleOCR）：输出是**扁平文本**，几乎无 `#` 层级，下游 lawiki 只能平铺。

knowhere 补这个缺口的真实手段不是"树算法"（建树只是个平凡的栈），而是**用 LLM 把丢失的标题级别补回来**（返回 `id→level` 映射）。本设计为 makeitdown 增加一个**可选的 LLM 标题层级重建 pass**。

（路线背景：已明确**不采用** docling 的本地版面模型、也**不采用**坐标还原表格；结构重建就走本 LLM 方案。见 `docs/reference-projects-learnings-2026-06-18.md` 与下一步修订计划。）

## 核心安全约束（不可协商）

法律场景下正文里的金额、日期、当事人、法条编号被悄悄改动是灾难性的且极难发现。因此：

> **LLM 只输出"行号 → 标题级别"的整数映射，绝不输出、绝不经手任何正文。**
> 加 `#` 前缀在本地完成，正文行**逐字节原样拷贝**。

由此得到数学保证：**本功能不可能改动正文内容**——LLM 的输出只是一组整数。这比"让 LLM 重写 markdown 再 diff 校验"严格更安全、更省 token、更简单。

## 范围（明确边界）

- **只处理 OCR 路由的产物**：`route` 不属于 {native, legacy, unsupported} 的文件。native（markitdown）输出本就带层级，不碰。
- **opt-in，默认关闭**：需联网 + LLM token，与"离线、文档不出本机"主线相悖，必须显式开启。
- **provider 无关**：走 OpenAI 兼容 `/chat/completions`，base_url / model / key 可配，指向任意国内端点（DeepSeek / 通义 / Moonshot / 智谱）。
- **零新依赖**：复用已有的 `requests`。

非目标：正文重写、OCR 纠错、摘要、实体 wikilink（lawiki 的活）、跨 chunk 拼接、表格还原、引擎替换。

## 架构

新增 `src/makeitdown/structure.py`：

```
extract_heading_candidates(text, *, max_len) -> list[Candidate]   # 纯逻辑，挑候选标题行（带行号）
apply_heading_levels(text, levels) -> str                         # 纯逻辑，按级别加 #，正文逐字节拷贝
class HeadingStructurer:                                           # 唯一网络副作用点
    restructure(text) -> tuple[str, str | None, str | None]       # (新文本, engine后缀|None, 警告原因|None)
```

数据流（在 `pipeline.handle` 内，OCR 转换成功后、质检前；仅当开启且 route==ocr）：

```
OCR 扁平 markdown
  → extract_heading_candidates（短行、非表格行、含已有 # 行；带行号）
  → 调 LLM：发编号候选行，要回 JSON {行号: 级别}
  → 密度闸门校验（见错误处理）
  → apply_heading_levels：按级别加 #，正文逐字节拷贝
  → engine 追加 "+llm-heads:<model>"
  → 质检 assess 照常跑（跑在结构化后的文本上）
```

### 候选行提取（省 token、控风险）

只发"可能是标题"的行：非空、去空白后长度 ≤ `max_len`（默认 80）、非表格行（不以 `|` 开头/不含多个 `|`）；已有 `#` 行也纳入（允许重新定级）。每行带原文行号。

### LLM 交互

- system 提示：「你是文档结构分析器，只判断每行的标题级别（1-6），0 表示正文；**只返回 JSON，绝不改写任何文字**。」
- **非层级材料硬要求**（关键）：「**若文档没有清晰的标题结构（如聊天记录、流水清单、表单、单页通知），全部返回 0，不要凭空制造结构。**」
- 强制 JSON 输出（不支持的端点用文本解析兜底）。
- 响应 `{"levels": {"<行号>": <1-6>}}`；缺失/0 视为正文。
- **白名单校验**：只接受键在候选行号集合内、值为 1-6 整数的项；其余丢弃。

### 重新加 #（本地、无损）

`apply_heading_levels`：逐行重建。命中行去掉原前导 `#`/空白后重新前缀 `"#"*level + " "`；其余行**原样拷贝**。可加断言：重建后各行"去掉前导 #"后与原行"去掉前导 #"后逐行相等，否则回退原文。

## 非层级材料的处理（聊天记录等）

三层防护，确保无结构材料不被破坏：

1. **提示层**：上述「无结构则全判 0」指令——理想情况下聊天记录原样返回。
2. **密度闸门**（兜底防过度切分）：若 LLM 标为标题的行数 / 候选（或总非空）行数 **超过 `max_heading_ratio`（默认 0.35）**，判定"此材料无层级"，**整份丢弃结构化结果、保持扁平**，并打 `quality: suspect` + 原因 `heading structuring skipped: too many headings (N%)`。
3. **底线**：即便前两层失灵，LLM 只能动 `#` 标记、碰不到正文 → 最坏只是多几个 `#`，**内容零损失且肉眼可见**。

## 数据落地

- **engine 标签**：`cloud:paddleocr-vl-1.6+llm-heads:deepseek-chat`（frontmatter 无需改）。
- **report.json**：新增 `structured` 计数（成功结构化的文件数）。
- **结构化失败但转换成功**：不算 failed，md 照常按原文写出，走既有警告通道补一条原因（`quality: suspect`）。

## 错误处理（与质检一致：绝不拖垮转换）

- `restructure` 全程 try/except：网络错误 / 超时 / 非法 JSON / 校验失败 / 密度闸门触发 → **返回原文**，文件照常写出 + 记 warning。
- **超大文档**：候选行 > `max_input_lines`（默认 1500）→ 跳过 + 警告，不发请求（v1 不分块）。
- 开启 `--structure-headings` 但缺 base_url/key → CLI 启动即 fail fast。

## CLI

| 选项 | 说明 | 默认 |
|---|---|---|
| `--structure-headings` | 开启 OCR 产物的 LLM 标题层级重建 | 关 |
| `--llm-base-url URL` | OpenAI 兼容端点 | env `MAKEITDOWN_LLM_BASE_URL` |
| `--llm-model NAME` | 模型名 | env `MAKEITDOWN_LLM_MODEL` |
| `--llm-api-key KEY` | API key | env `MAKEITDOWN_LLM_API_KEY` |
| `--llm-max-heading-len N` | 候选行最大长度 | 80 |
| `--llm-max-lines N` | 超过则跳过结构化 | 1500 |
| `--llm-max-heading-ratio F` | 标题占比超过则判无层级、回退扁平 | 0.35 |

总览行追加 `structured=N`（仅开启时）。

## 测试（TDD，先写测试）

- `test_structure.py`：
  - `extract_heading_candidates`：表格行/超长行被排除；短行、已有 `#` 行纳入；行号正确。
  - `apply_heading_levels`：目标行正确加 `#`、正文行逐字节不变；级别 0/缺失不动；已有 `#` 行重新定级而非叠加。
  - **无损断言**：随机正文 + 任意 levels，重建后"去掉前导 # 的逐行内容"恒等于原文。
  - `restructure`（mock LLM）：正常重标 + engine 后缀；LLM 报错/非 JSON/越界级别/越权行号 → 回退原文 + 标记；候选行超限 → 跳过；**密度超阈值 → 回退扁平 + 标记**；**安全用例**：mock LLM 响应里塞篡改正文，输出正文仍逐字节一致。
- `test_pipeline.py`：开启 + OCR 路由 → 调用 structurer；native/legacy → 不调用；失败仍写出（原文）+ 计 warned；关闭（默认）行为同现状。
- `test_cli.py`：开启但缺 base_url/key → fail fast；总览行含 `structured`。

## 受影响文件

- 新增：`src/makeitdown/structure.py`、`tests/test_structure.py`
- 修改：`pipeline.py`、`cli.py`、`tests/test_pipeline.py`、`tests/test_cli.py`、`README.md`
