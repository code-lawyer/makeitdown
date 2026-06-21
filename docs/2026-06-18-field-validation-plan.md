# makeitdown 实战验证方案

日期：2026-06-18
目的：用真实案卷量出"它在你的场景里准到几成"，给"是否可实用"一个**实证**答案，并校准阈值。
适用：Windows / PowerShell；命令里的 `makeitdown` 若未在 PATH，用 `.venv\Scripts\makeitdown` 代替。

---

## 0. 这次要回答的 4 个问题

1. **正文有没有被损坏**（尤其金额/日期/案号/当事人）——法律红线，最高优先。
2. **质检准不准**：真坏的有没有被标 `quality: suspect`（召回）；干净的有没有被误标（误报）。
3. **标题层级对不对**（Phase 1，开 `--structure-headings` 时）。
4. **路由对不对**：扫描件有没有走 OCR、电子件有没有被错当扫描件、表格件成什么样。

---

## 1. 样本设计（分层，20 份左右）

按类型各取几份，**务必包含 3~5 份"你已知正确内容"的件**（能逐字核对金额/日期的）：

| 类别 | 份数 | 为什么要 |
|---|---|---|
| 电子版 PDF（有文字层） | 3 | 走 native，验证不被误判为扫描件 |
| 扫描 PDF（清晰） | 3 | OCR 主场，验证正文+标题 |
| 扫描 PDF（偏糊/复印件） | 3 | 触发质检/低置信，验证召回 |
| 表格密集件（财务/证据清单） | 3 | 已知弱区，量到底多差 |
| Word/.docx | 2 | native 基线 |
| 老 `.doc` / `.wps` | 2 | legacy 兜底链路 |
| 图片（png/jpg 的单据） | 2 | 图片 OCR |
| 无结构件（聊天记录/短通知） | 2 | 验证不被过度切分 |
| **已知答案件**（上面任意类型，含明确金额/日期） | 3~5 | **唯一能判"正文损坏"的依据** |

把它们放进一个目录，例如 `验证样本\`，**保留原件**用于人工比对。

---

## 2. 环境准备

```powershell
# 本地 OCR（离线、中文强）——需要 [local]
makeitdown --help    # 确认可用

# 若要一并验证标题层级（Phase 1），配一个 OpenAI 兼容端点（用你自己的，别用一次性 key）
$env:MAKEITDOWN_LLM_BASE_URL = "https://api.deepseek.com/v1"
$env:MAKEITDOWN_LLM_MODEL    = "deepseek-chat"
$env:MAKEITDOWN_LLM_API_KEY  = "你的key"
```

---

## 3. 执行

分两跑，便于隔离"转换本身"和"加了 LLM 标题"两件事。

```powershell
# 跑 A：纯转换 + 质检（本地 OCR），默认阈值
makeitdown 验证样本 -o 跑A_默认 --ocr-engine local

# 跑 B：在 A 基础上加 LLM 标题层级重建
makeitdown 验证样本 -o 跑B_含标题 --ocr-engine local --structure-headings
```

> 每跑一次看一次总览行：`Done. succeeded=.. warned=.. structured=.. failed=.. skipped_*`。

---

## 4. 自动初筛（用 report.json + frontmatter 快速定位可疑件）

```powershell
$r = Get-Content 跑A_默认\report.json -Raw -Encoding utf8 | ConvertFrom-Json
"OK=$($r.succeeded)  WARN=$($r.warned)  STRUCT=$($r.structured)  FAIL=$($r.failed)  UNSUP=$($r.skipped_unsupported)"

"`n== 被标记可疑（逐条看原因）=="
$r.warnings | ForEach-Object { "$($_.file)  ->  $($_.reasons -join ' | ')" }

"`n== 硬失败 =="
$r.failures | ForEach-Object { "$($_.file)  ->  $($_.error)" }

"`n== 干净跳过（老格式没转换器等）=="
$r.skipped  | ForEach-Object { "$($_.file)  ->  $($_.reason)" }
```

辅助：列出所有被标记的 .md，以及把某份件里所有"数字串"挑出来集中核对金额：

```powershell
# 所有 quality: suspect 的产出
Get-ChildItem 跑A_默认 -Recurse -Filter *.md | Select-String 'quality: suspect' | Select-Object Path

# 把某份 md 里的数字串列出来，对着原件逐个核对（金额/日期/案号最关键）
Select-String -Path '跑A_默认\某文件.md' -Pattern '[0-9][0-9,\.／/年月日-]{2,}' | ForEach-Object { $_.Line.Trim() }
```

---

## 5. 人工逐件评分（核心，自动化替代不了）

对每份样本填下表。**"正文损坏"一栏只要有一处未被标记的金额/日期错误，整个项目判不可实用。**

| 文件 | 路由对? | 正文损坏(金额/日期)? | 被正确标记? | 标题层级(跑B) | 表格可读? | 备注 |
|---|---|---|---|---|---|---|
| 例:借款合同_扫描.pdf | ✅OCR | ❌无 | —(干净) | ✅ | ⚠️错列 | 第3页表格串行 |
| … | | | | | | |

每栏判定口径：
- **路由对**：扫描件 engine 应是 `local:pp-structurev3`(或 vl)；电子件应是 `markitdown`。看 frontmatter 的 `engine`。
- **正文损坏**：对"已知答案件"逐个核对金额/日期/案号；其余件至少抽查最关键的 3~5 个数字。**这是红线栏。**
- **被正确标记**：坏件是否进了 `report.warnings` / frontmatter `quality: suspect`（召回）；干净件是否**没**被标（误报）。
- **标题层级**：跑 B 里 `#`/`##` 是否对应真实章节；无结构件应保持扁平。
- **表格可读**：能否看出行列对应关系（已知弱区，如实记录）。

---

## 6. 阈值校准循环

根据第 5 步结果调下面参数，**换新输出目录重跑**（或去掉 `--skip-existing`）：

| 现象 | 调什么 |
|---|---|
| 扫描件被当成电子件（没走 OCR） | 调高 `--text-threshold`（默认 50） |
| 电子件被误当扫描件 | 调低 `--text-threshold` |
| 干净件被误标乱码 | 调高 `--warn-garbled-ratio`（默认 0.02） |
| 真乱码漏标 | 调低 `--warn-garbled-ratio` |
| 低置信误报太多（本地 OCR） | 调低 `--warn-min-confidence`（默认 0.6） |
| 坏件漏标 | 调高 `--warn-min-confidence` |
| 正常短件被报"每页字数低" | 调低 `--warn-min-chars-per-page` |

目标：在你的语料上找到一组**召回优先、误报可接受**的阈值（法律场景宁多报不漏报），记进 README/启动脚本。

---

## 7. 判定标准（"可实用"的红线）

全部满足才算跨过"可试用 → 可实用"：

1. **零静默正文损坏**：样本中**没有任何**未被标记的金额/日期/案号错误。（出现一处即不可实用，优先修。）
2. **质检召回达标**：人工认定的坏件，≥ 90% 进了 `quality: suspect`。
3. **误报可控**：干净件被误标比例 ≤ 你能接受的复核成本（建议先定 ≤ 20%）。
4. **路由正确率** ≥ 95%。
5. **表格**：明确写下结论——是"可接受的降级"还是"表格密集件必须人工重做"。（不阻断，但必须知情。）
6. **批量稳定**：`failed` 都是真坏文件、不中断整批；老格式按预期进 `skipped` 且带可行建议。

---

## 8. 结论模板（跑完填这段）

```
样本：N 份（分布：…）
跑 A 总览：succeeded/warned/failed/…
跑 B 总览：…structured=…

红线①正文损坏：通过 / 不通过（列出每一处问题件）
质检召回：x/y  误报：a/b
路由正确：x/y
表格结论：可接受降级 / 需人工重做
校准后阈值：text-threshold=… garbled-ratio=… min-confidence=…

判定：可实用 / 仍可试用（欠缺：…）
下一步：…
```

---

> 一句话用法：**先跑 A/B → 用第 4 步初筛 → 第 5 步逐件评分（盯紧"正文损坏"红线）→ 第 6 步校准重跑 → 按第 7 步判定。** 跑完这套，你对"能不能真用"就有了证据，而不是猜。
