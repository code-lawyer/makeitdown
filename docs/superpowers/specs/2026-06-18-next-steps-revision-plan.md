# makeitdown 下一步修订计划

日期：2026-06-18
前提：已排除 docling 版面模型、坐标还原表格、引擎替换、bake-off

## 决策确认（本轮锁定）

| 状态 | 项 |
|---|---|
| ✅ 采纳 | LLM 标题层级重建（只回级别、不碰正文）+ 非层级材料兜底 |
| ✅ 采纳 | OCR 置信度并入质检（用 **PaddleOCR 自带的** per-line 置信度，**非** docling） |
| 🔵 借思想/中期 | 统一结构化中间模型（轻量，服务 lawiki 的无损 JSON） |
| ❌ 移除 | docling 引擎、版面识别模型、TableFormer、坐标还原表格、引擎 bake-off |

> 关键：置信度这一项**不依赖 docling**——PaddleOCR 本身每行就返回置信度，现在的 `ConversionResult` 把它丢掉了。捡回来即可，正打"OCR 局部数字损坏漏检"的法律盲点。

## 路线总览（按优先级）

```
Phase 1  LLM 标题层级重建    ← 核心缺口，最高价值，现在就做
Phase 2  OCR 置信度入质检    ← 补法律盲点，本地零外部依赖
Phase 3  统一结构化中间模型  ← 可选/中期，Phase 1 若被字符串方案卡住才上
```

## Phase 1 — LLM 标题层级重建（核心）

详见 `2026-06-18-llm-heading-structure-design.md`。要点：
- 新增 `structure.py`：候选行 → LLM 要回 `{行号:级别}` → 本地加 `#`，正文逐字节拷贝。
- 安全约束：LLM 只输出整数级别，绝不经手正文。
- 非层级兜底：提示「无结构则全判 0」+ 标题密度闸门（>0.35 回退扁平）。
- opt-in、provider 无关、零新依赖、失败回退原文。

**触碰文件**：新增 `structure.py` + `test_structure.py`；改 `pipeline.py`、`cli.py`、`README.md` + 对应测试。

## Phase 2 — OCR 置信度入质检

- `ConversionResult` 增可选 `confidences`；本地 + 云端 OCR 路径填充。
- `quality.assess` 增规则：低置信片段/低置信占比过高 → 警告（带实测数值）。
- 新增 `--warn-min-confidence`。

**触碰文件**：`models.py`、`ocr_local.py`、`ocr_cloud.py`、`quality.py`、`cli.py` + 测试 + `README.md`。

**风险**：阈值保守标定（法律件宁多报不漏报），先用真实样本校准。

## Phase 3 — 统一结构化中间模型（可选/中期）

仅当 Phase 1 发现"直接操作 markdown 字符串"太别扭才上；否则推迟。在 `ConversionResult` 之上加轻量结构模型（标题树/段落/表格/置信度），使 `.md` 与无损 JSON 同源产出、直接喂 lawiki。

## 建议立即顺序

1. 落地两份文档（本计划 + LLM 标题设计文档）。✅
2. 按 TDD 开 Phase 1：先 `test_structure.py`，再 `structure.py`，再接 pipeline/cli。
3. Phase 1 完成、测试通过后再启 Phase 2。
