# makeitdown 老式 .doc / .wps 格式支持设计

日期：2026-06-15
状态：已确认，待实现

> **2026-06-18 补充（COM 并发与冷启动修复）**：原实现对每个真二进制 `.doc/.wps` 都
> `Dispatch` 一次 Word/WPS、转完即 `Quit`；在 `--workers>1` 下多个 worker 线程并发驱动同一
> 个 COM 单例，会触发 "RPC server unavailable" 崩溃，且逐文件冷启动 Word 极慢。现改为
> `_WordSession`：所有 COM 操作跑在**单个专用线程**上（STA 对象不跨线程、天然串行），**全批
> 复用一个 Word 实例**（开一次、转 N 个、`atexit` 时 Quit 一次），无可用应用时只判定一次、
> 不逐文件重试。`_convert_via_com(src, out_docx)` 签名不变（仍是 mock 接缝）。

## 背景与目标

markitdown 只认 `.docx`，不认老式 `.doc`（OLE2 二进制）和 `.wps`（金山）。
当前这些文件被 router 判 `unsupported` 直接跳过。中国法律实务里 `.doc`/`.wps` 极常见，
这是把工具从"能处理干净文档"推到"能处理真实律所文件夹"的关键缺口。

核心约束（用户明确要求）：

1. **绝不让用户在不知情下安装额外工具。** 默认零额外下载；任何需要下载的操作
   （如 LibreOffice）必须由 agent 用大白话解释清楚、拿到明确同意后才执行。
2. **照顾国内网络。** pip 依赖走清华源；任何可选下载给国内镜像指引。

## 关键事实

- `.wps` 不是单一格式：常是 ① OOXML 内核只是后缀叫 .wps；② .doc 二进制内核；
  ③ 老金山/Works 私有二进制（少见）。`.doc` 同理——很多"`.doc`"其实是改了后缀的 .docx。
- **没有靠谱的纯 Python 库**能把真二进制 .doc 转成像样文本；自己解析 FIB/piece-table
  极脆且常产出垃圾。因此放弃"纯 Python 兜底"，改为诚实的"跳过 + 可操作提示"。

## 分层方案

| 层 | 做法 | 额外下载 | 平台 |
|---|---|---|---|
| **T1 内容嗅探** | 按魔数识别：假后缀的 OOXML（实为 .docx）→ 复制为 .docx 走 markitdown | 无，零依赖 | 全 |
| **T2 COM** | 调用**本机已装的** Word / 金山 WPS 转成 docx 再走 markitdown（`pywin32`） | 无（已装为前提） | Windows |
| **T4 LibreOffice** | `soffice --headless --convert-to docx`；**仅当 soffice 已在 PATH** 才用 | 安装与否由用户知情决定（见 SKILL 规矩） | 全 |
| **T3 跳过+提示** | 真二进制且无任何可用后端：干净跳过，报告里说清怎么办 | 无 | 全 |

说明：T4 在**代码层面**只是"若 `soffice` 已在 PATH 就用它"，**绝不自动安装**；
"是否安装 LibreOffice"完全是 SKILL.md 里 agent 与用户的知情同意流程，不在工具代码内。

## 架构

- **router**：新增 `LEGACY_BINARY_EXTS = {".doc", ".wps"}`，这些后缀一律路由到新的
  `"legacy"` 类别。router 不读内容，保持简单；格式细分交给转换器（高内聚）。
- **新模块 `convert_legacy.py`**：拥有全部老格式逻辑。
  - `convert(path) -> ConversionResult`：先嗅探魔数：
    - **OOXML**（`PK\x03\x04`）→ 复制为临时 `.docx` → `convert_native()`（T1，引擎标 `markitdown`）。
    - **OLE2**（`\xD0\xCF\x11\xE0...`）→ 依次尝试可用后端：COM → LibreOffice；
      产出临时 `.docx` 后走 `convert_native()`，引擎标 `legacy:com->markitdown`
      / `legacy:libreoffice->markitdown`。
    - 都不可用 → 抛 `LegacyConversionUnavailable(hint)`。
  - 后端探测：COM 仅 Windows + 能 `import win32com`；LibreOffice 仅 `shutil.which("soffice"/"libreoffice")` 命中。
  - **COM 并发**：转换在 ThreadPoolExecutor 的 worker 线程里跑，COM 必须**每线程**
    `pythoncom.CoInitialize()/CoUninitialize()` 包裹。ProgID 依次试
    `Word.Application` → `KWPS.Application` → `WPS.Application`，`SaveAs2(FileFormat=16)`，
    用完 `Quit()`，临时文件用 `tempfile.TemporaryDirectory()` 自动清理。
- **pipeline**：
  - `route == "legacy"` → `convert_legacy.convert(src)`，结果与 native 一样走质检/frontmatter。
  - 专门捕获 `LegacyConversionUnavailable`（在通用 `except Exception` 之前），
    记为 `skipped_unsupported` 并把 hint 写进新的 `report["skipped"]` 列表。
  - 其它异常仍按既有 `failed` 隔离。

## report.json 变化

新增 `skipped`（可操作跳过的明细，仅老格式无后端时填充）：

```jsonc
{
  "succeeded": 0, "warned": 0, "failed": 0,
  "skipped_existing": 0, "skipped_unsupported": 1,
  "failures": [], "warnings": [],
  "skipped": [
    { "file": "卷宗/起诉状.doc",
      "reason": "legacy .doc/.wps needs Word or WPS Office installed (Windows), or LibreOffice on PATH; none found — skipped." }
  ]
}
```

真正未知的后缀仍只计入 `skipped_unsupported`，不进 `skipped` 列表（无可操作信息）。

## SKILL.md 安装透明规矩（给 agent 的硬约束）

在 `skill/makeitdown/SKILL.md` 新增"处理老式 .doc/.wps"小节，明确：

- **永不静默安装任何东西。** T2 只使用**已经装好的** Word/WPS；用了要在对话里说明
  "用了你本机已装的 WPS/Office 来转换"。
- **LibreOffice（T4）属于要下载几百 MB 的操作**：agent 必须先用大白话解释
  （装什么、约多大、为什么需要、从哪下），**拿到用户明确同意后才安装**，绝不替用户决定。
  - 国内镜像指引：从清华/中科大等国内 LibreOffice 镜像下载，不走官网。
- 遇到 `report["skipped"]` 里的文件，agent 要把"怎样才能转成功"原样转达给用户，让其自行选择。
- pip 依赖（含 `pywin32`）统一走清华源 `https://pypi.tuna.tsinghua.edu.cn/simple`，
  延续"代码走 Gitee、依赖走清华"的既有基调。

## pyproject 变化

- 新增可选依赖组：`com = ["pywin32 ; platform_system=='Windows'"]`（仅 Windows 装）。
  默认安装不带；需要 COM 的 Windows 用户装 `makeitdown[com]`。
  （`olefile` 等纯 Python 解析不再需要，因放弃纯 Python 兜底。）

## 错误处理

- `convert_legacy` 内每个后端各自 try/except，单个后端失败则降级到下一个，不冒泡。
- COM 资源（app/doc/临时目录）务必清理，即使中途异常。
- 后端全不可用 → `LegacyConversionUnavailable`（携带 hint），pipeline 归为可操作跳过。
- 与既有"单文件出错不中断整批"一致。

## 测试（按 TDD，先写测试）

- `test_router.py`：`.doc`、`.wps` → `"legacy"`；未知后缀仍 `"unsupported"`。
- `test_convert_legacy.py`（新）：
  - OOXML 魔数文件 → 走 T1：`convert_native` 收到的是 `.docx` 路径，返回其结果。
  - OLE2 文件 + mock COM 成功 → 返回结果，引擎标 `legacy:com->markitdown`。
  - OLE2 文件 + COM 不可用、mock soffice 成功 → 引擎标 `legacy:libreoffice->markitdown`。
  - OLE2 文件 + 所有后端不可用 → 抛 `LegacyConversionUnavailable`，hint 含可操作信息。
  - 后端探测：非 Windows 时 COM 短路；`soffice` 不在 PATH 时 LibreOffice 短路。
- `test_pipeline.py`：
  - `"legacy"` 路由成功 → 与 native 同样产出 + 质检。
  - `LegacyConversionUnavailable` → `skipped_unsupported` 计数 +1 且 `report["skipped"]`
    含该文件与 hint；不计入 `failed`。
- 真实 COM / LibreOffice 路径**无法在本环境运行验证**（云端 venv 无 pywin32、无 soffice）；
  代码用依赖注入/可 mock 设计，COM 与 soffice 调用须在装了对应工具的真机上人工验证。

## 受影响文件

- 新增：`src/makeitdown/convert_legacy.py`、`tests/test_convert_legacy.py`
- 修改：`src/makeitdown/router.py`（LEGACY_BINARY_EXTS + legacy 路由）、
  `src/makeitdown/pipeline.py`（legacy 路由、LegacyConversionUnavailable→skipped、report["skipped"]）、
  `src/makeitdown/models.py`（`LegacyConversionUnavailable` 异常）、
  `pyproject.toml`（`com` 可选依赖）、
  `skill/makeitdown/SKILL.md`（安装透明规矩 + 国内镜像）、`README.md`、
  `tests/test_router.py`、`tests/test_pipeline.py`

## 已知缺口 / 后续（.wps 真二进制）

真机验证了 `.doc`（OLE2 → Word COM）和 OOXML 假后缀两条路；`.wps` 的真二进制路径还没验。
记录一条关键结论备忘：

- 国内绝大多数 `.wps` 是**金山 WPS** 存的，内核就是 MS 兼容格式（OLE2 的 .doc 或 OOXML 的
  .docx）。用户常用的"把 `.wps` 改名成 `.doc` 就能打开"之所以成立，**是因为 Word/WPS 按内容
  嗅探、不只看后缀**——不是后缀本身的魔力。
- 例外：真·微软 Works 的 `.wps`（很老、国内少见）是另一种格式，改名打不开，需 Works 转换器。
- 对本工具的影响：`convert_legacy` 已按文件头嗅探分流，等于自动化了"改名"。**唯一要补的点**：
  T2 现在把原始 `.wps` 路径直接交给 `Documents.Open()`，而 Word 可能因扩展名是 `.wps` 而
  拒绝打开（即便内容是 OLE2）。实现 `.wps` 时的稳妥做法——**OLE2 内核的 `.wps` 先复制成临时
  `.doc` 再交给 Word**（OOXML 内核已复制成临时 `.docx`，即 T1）。即把用户的手动改名自动化。

## 非目标

纯 Python .doc 解析、老 `.xls`/`.ppt`/`.rtf`、自动安装任何外部程序、为 COM/LibreOffice
做重试框架。
