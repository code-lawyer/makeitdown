# 参考项目学习汇总报告

日期：2026-06-18
范围：knowhere / liteparse / docling 三个外部项目，对照 makeitdown 现状（markitdown + PaddleOCR）
状态说明：本报告为调研记录；**引擎相关决策已被 `2026-06-18-next-steps-revision-plan.md` 收敛**（明确不采用 docling 版面模型与坐标还原表格）。

---

## 0. 层级：四者在同一条管线上的位置

```
原始文档 ──► [解析引擎] ──► 高保真 Markdown ──► [结构化：树/图谱] ──► [检索/消费]
              liteparse        makeitdown            knowhere(LLM)        knowhere
              docling          (你在这里)            docling(本地模型)     lawiki(你的下游)
              markitdown / PaddleOCR
```

- liteparse：上游纯解析引擎，出"文字 + 坐标"，不产 markdown、不做语义结构。
- docling：同层但更深，模型驱动，解析 + 阅读顺序 + 标题层级 + 表格，出 md/html/json。
- knowhere：下游，markdown → 树 + 图谱 + agentic 检索（重栈 + 云端 LLM）。
- makeitdown：不是解析器，是**"中国友好 + 法律域 + 批量"的工作流包装层**。

> 结论：这些项目强在"引擎中段（理解结构）"，makeitdown 强在"产品两端（采集/产出/本地化）"。组合关系，不是二选一。

## 1. 值得学习的点

优先级：🟢现在就做 / 🟡纳入路线 / 🔵借思想 / 下游=属于 lawiki

### 解析与结构
- **干净 md 不够，缺的是层级**（knowhere + docling）🟢 → 已立项 Phase 1。
- **LLM 只回"行号→级别"、绝不碰正文**（knowhere）🟡 → Phase 1 的安全约束。
- ~~本地版面模型重建层级（docling）~~ ❌ 已决定不采用。
- **非层级材料兜底**（本项目推演）🟢 → Phase 1 含密度闸门。
- ~~专用/坐标表格还原（docling TableFormer / liteparse）~~ ❌ 已决定不采用。

### 架构
- **统一结构化中间模型**（docling DoclingDocument）🔵→Phase 3 → md 与无损 JSON 同源，服务 lawiki。
- **可插拔引擎/后端架构**（docling / liteparse）🔵 → 你的 router + Dispatcher 已是轻量版，方向被验证。
- **slim 核心 + 重依赖全可选**（docling-slim）🟢 → 验证 `[local]`/`[com]` extras，保持核心轻。

### 质检与产品化
- **OCR 置信度入质检**🟡 → Phase 2，但**改用 PaddleOCR 自带置信度**（不依赖 docling）。
- **可溯源引用链**（knowhere）🔵 → frontmatter 溯源可细化到章节级。
- 轻量中文 OCR（RapidOCR）→ 已随"不换引擎"搁置。

### 下游（交给 lawiki）
- 树 + 图谱 + 混合检索（knowhere）→ Obsidian 原生：`#`大纲=树、`[[wikilink]]`=图谱、Dataview/Bases=检索；别上 Postgres/向量库。
- 跨文档实体链接（案号/当事人/法条）→ LLM 抽实体织 wikilink。

## 2. 明确"不抄"的东西
- knowhere 的重基础设施（PG/Redis/S3）+ 强制云端 LLM —— 与离线/隐私冲突。
- liteparse 的产出形态（只给文字 + 坐标、Tesseract 中文弱）—— 不如现状的平替。
- docling 版面模型、TableFormer、坐标表格、作为引擎的重装（torch + HF 下载）—— 已决定不采用。
- 放弃 makeitdown 改造 docling —— 会扔掉独有的国内适配/批量/质检/老格式，再重建包装层，更费劲。

## 3. 一句话索引
- knowhere → 学**结构化蓝图**（树/溯源/检索），别学重栈。
- liteparse → 整体不用。
- docling → 仅借**统一文档模型**思想（Phase 3）；版面模型/表格/引擎均不采用。
- makeitdown → 产品两端已更完整，要补的是"引擎中段：结构理解"——走 LLM 标题方案（Phase 1）。
