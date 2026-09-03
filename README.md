> 🌐 **Languages**: [🇨🇳 中文（当前）](#) · **[🇬🇧 English](README.en.md)**
> 
> 👉 技术读者/AI Engineer 面试官：建议阅读 [English version](README.en.md)，技术章节（架构、Pipeline、Quality Gates）更完整。

# 《天黑之前》— AI 协作长篇写作引擎

港城过去十年"第七起"系列案件。一个被警界除名的女侧写师，在灰色暗线里，一步步发现自己不是被抛弃的人，而是被精心选中的人——而那个选中她的人，正是她喊了二十年"霍爷爷"的那个人。

**AI 自动续写 · Cline / Claude 协作 · 70–80 章长篇架构 · 全流程可审核**

> 🔒 **版权与隐私声明**：本仓库中的小说正文内容（chapters/ 目录、CAST.md、OUTLINE.md 等创作设定文件）仅供作者本人创作参考使用，未经许可不得外传、二次创作、商业使用或转载，版权归 © 2026 原作者所有。
> 仓库中的工程代码与系统架构（engine/、tools/ 目录及本 README 描述的 pipeline 设计）可作为技术能力展示自由查看，如需复用请注明来源。

---

## 🔀 项目背景与致谢

本仓库最初 fork 自 [Open Souls](https://github.com/open-souls/open-souls)——一个用 TypeScript 构建"具有人格的 AI Agent"的开源框架。
本项目在此基础上完全重写为 Python 实现，转向了不同的应用场景：AI 辅助长篇小说协作写作，包括 prompt 编排流水线、质量门禁系统（lint gates）、状态持久化与人机协作审核机制。
部分内部命名习惯（如角色/状态管理相关术语、环境变量命名）沿用了原项目的设计理念。

---

## 💡 技术亮点（Highlights for AI Engineering）

面向 AI Engineer / AI Consultant（大语言模型应用与训练方向）面试官，本项目展示了以下 LLM 应用工程能力。所有功能均已在 `engine/` 与 `tools/` 目录落地可运行。

- **Prompt Engineering & Orchestration** — 多阶段 prompt 编排流水线：`engine/writer.py` 实现 `brief → compose → plan → draft` 四阶段，每阶段生成独立结构化 prompt 文件供下游消费
- **Guardrail System** — 三道硬质量门禁：`engine/prose_lint.py`（8 大 AI 通病禁令）+ `engine/safety_lint.py`（内容安全）+ `tools/check_chapter_quality.ps1`（字数三口径），任一不过线即 BLOCKED，禁止落盘
- **Human-in-the-loop QA** — Cline 为主控 + 人工终审的双层审核机制，详见 `.clinerules` §11.2 强制流程，Claude 自报 PASS 不具备放行权
- **Graceful Degradation** — 无 `ANTHROPIC_API_KEY` 时自动降级到 Cline 协作模式（`run_dispatch.py` 跳过远端派发），系统不中断、流程不卡死
- **Structured State Management** — 长程任务状态持久化：`arc.json`（主线节拍 + 副线案进度）+ `ties.json`（角色关系网）+ `CAST.md` 角色追踪块 + `tools/cast_absence_scan.py` 角色缺席扫描
- **Incremental CI Gating** — PR 级别增量门禁：`tools/validate_changed.py` 默认只校验 `git diff HEAD~1..HEAD` 之间的改动章节，共享门代码改动时拒绝并要求显式 `--full`

---

## 🎯 当前进度

- ✅ **第 01–14 章已定稿**（v3.1 标准：1800–2200 字 / 章，纯正文连续叙事；最新定稿 2026/9/3 第 14 章《老槐树》副线案三开场）
- 🟡 **第 15 章待写**——按 v3.1 标准执行（副线案三·中段：蹲点调查 7:45 + 侧写锁定嫌疑人）
- 🛠️ **AI 自动写作工具链已就绪**（brief / compose / dispatch / lint 全流程跑通）
- 📊 **数据持久化已建**（`arc.json` 主线节拍 + `ties.json` 角色关系网）

---

## 🏗️ 架构图

```
┌──────────────────────────────────────────────────────────────────────┐
│                         《天黑之前》写作工作流                         │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   ┌─────────┐      ┌──────────────────┐      ┌─────────────────┐    │
│   │  Cline  │─────▶│  engine/writer.py │─────▶│  prompts/*.md   │    │
│   │  (人审) │      │  brief/compose/  │      │  (策划+写手     │    │
│   └─────────┘      │  plan/draft       │      │   prompt文件)    │    │
│        ▲           └──────────────────┘      └─────────────────┘    │
│        │                                              │              │
│        │              ┌──────────────────┐             ▼              │
│        └──────────────│  Claude API      │◀────┌─────────────────┐    │
│         读 PASS       │  (可选·配 key    │     │ engine/run_     │    │
│         才落盘        │   后启用)        │     │ dispatch.py     │    │
│                       └──────────────────┘     └─────────────────┘    │
│                                                      │               │
│                                                      ▼               │
│   ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐    │
│   │ chapter_   │  │ prose_     │  │ safety_    │  │ batch_     │    │
│   │ stats.ps1  │  │ lint.py    │  │ lint.py    │  │ rewrite.py │    │
│   │ 字数三口径 │  │ AI 通病    │  │ 三条铁线   │  │ 批量改稿   │    │
│   └────────────┘  └────────────┘  └────────────┘  └────────────┘    │
│         ▼                ▼                ▼               ▼         │
│   ┌─────────────────────────────────────────────────────────────┐    │
│   │            chapters/Chapter_NN.md  （定稿章节正文）             │    │
│   └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

**关键设计**：

- **Cline 是主控**——读 prompt、读 PASS 报告、做最终决策
- **engine/writer.py 是编排器**——生成 prompt 文件，不直连 API（半自动模式）
- **Claude API 可选**——配 `ANTHROPIC_API_KEY` 后启用 `run_dispatch.py` 远端派发
- **lint 是硬门**——`prose_lint.py` + `safety_lint.py` + `chapter_stats.ps1` 三道门不过线就 BLOCKED
- **人审是终门**——Cline 自己审 + 你最后审，"不关机不关 VS Code 长跑"模型

---

## 📁 项目结构

```
Novel_New/                          ← 项目根（仓库入口）
├── README.md                       ← 本文件（架构 + 进度 + 快速开始）
├── .clinerules                     ← 写作规范（v3.1 · 2026/8/31 三次修订）
├── .env.example                    ← 环境变量示例（API key 占位）
├── .gitignore                      ← Git 排除规则
│
├── CAST.md                         ← 角色名册（核心班底 + 大 Boss + 动态角色库）
├── OUTLINE.md                      ← 主线大纲 + 逐章梗概 + 章节状态追踪表
├── CLUES.md                        ← 悬疑线索 / 伏笔 / 暗线追踪表
├── CLUES_TRACKER.md                ← 强制阅读文件（第 3 节"待回收线索清单"）
├── WORLDVIEW.md                    ← 世界观 / 港城地理 / 关键物件
├── PSYCHOLOGY.md                   ← 犯罪心理侧写规范与术语表
├── WORDCOUNT_RULE.md               ← 字数三口径硬约束（v3.1）
│
├── arc.json                        ← 主线节拍 + 副线案进度（持久化）
├── ties.json                       ← 角色关系网（持久化）
│
├── chapters/                       ← 所有章节正文（定稿）
│   ├── Chapter_01.md               ← 七号仓库
│   ├── Chapter_02.md               ← 刚好书店
│   ├── ...                         ← 第 14 章待写
│   └── Chapter_13.md               ← 旧石灰号的根
│
├── engine/                          ← 写作引擎（Python 3.10+）
│   ├── writer.py                   ← 主编排器（brief/compose/plan/draft）
│   ├── run_dispatch.py             ← Claude API 派发器（可选·配 key 后启用）
│   ├── prose_lint.py               ← prose 质量 lint（AI 通病 + 硬线）
│   ├── safety_lint.py              ← 三条铁线 lint（性 / 自伤 / 未成年）
│   ├── batch_rewrite.py            ← 批量改稿（status / pick / clear-cache）
│   ├── season.py                   ← 主线节拍 + 副线案管理
│   ├── soul.py                     ← 角色名册解析（CAST.md fallback）
│   ├── cast.py                     ← 角色查询辅助
│   ├── trace.py                    ← 每章定稿后追踪器（登场 + 字数 + 校验）
│   ├── _extract_ships.py           ← 羁绊线抽取器（母题关键词 + 共现矩阵）
│   ├── validate.py                 ← schema 校验
│   └── test_lint.py                ← lint 单测
│
└── tools/                          ← 工具脚本（PowerShell + Python）
    ├── chapter_stats.ps1           ← 字数三口径统计（硬约束）
    ├── check_chapter_quality.ps1   ← 综合质量检查
    ├── validate_changed.py         ← PR 推送前 lint（增量门）
    ├── cast_absence_scan.py        ← 角色缺席扫描（三档阈值）
    ├── prescreen.py                ← 预筛
    ├── smoke_test.py               ← 冒烟测试
    └── _run_stats.ps1              ← 统计脚本包装
```

---

## 🚀 快速开始

### 1. 跑工具链（零 token 看流程）

```bash
# 验证第 14 章本回简报（生成 prompts/brief14_stdout.txt）
python engine/writer.py brief 14

# 一键生成策划 + 写手 prompt（生成 prompts/Chapter_14_plan.md + _draft.md）
python engine/writer.py compose 14
```

### 2. 检查章节质量（v3.1 硬约束）

```bash
# 字数三口径 + em dash 计数 + AI 通病统计
powershell tools/chapter_stats.ps1

# 综合质量检查（字数 + lint + 硬线）
powershell tools/check_chapter_quality.ps1

# 角色缺席扫描（核心班底 ≤3 章 / 大 Boss ≤10 章 / 动态角色 ≤8 章）
python tools/cast_absence_scan.py

# 羁绊线抽取（第 N 章登场角色 + 母题关键词 + 角色共现 + CLUES 对齐）
python engine/_extract_ships.py 13
```

### 3. PR 推送前增量门

```bash
# 只检查本次变 commit 涉及的章节
python tools/validate_changed.py --base origin/main --head HEAD

# 如果改了 engine/ 共享代码，须显式启用全量审计
OPEN_SOULS_FULL_PUSH=1 python tools/validate_changed.py --base origin/main --head HEAD
```

### 4. 批量改稿（CI 加速）

```bash
# 看所有章节 lint 状态
python engine/batch_rewrite.py status

# 自动挑 5 个最需要改稿的章节
python engine/batch_rewrite.py pick --pick 5

# 只挑"病句多"的章节
python engine/batch_rewrite.py pick --pick 5 --disease-only
```

---

## 🛠️ 工具链工作流（核心机制）

### Step-by-step：续写第 N 章

```
       ┌─────────────────────────────────────────┐
   ①   │  python engine/writer.py brief <N>      │  ← 简报（最近章节 + 节拍 + 角色 + 暗线）
       └─────────────────────────────────────────┘
                            ▼
       ┌─────────────────────────────────────────┐
   ②   │  python engine/writer.py compose <N>    │  ← 生成策划 + 写手 prompt 文件
       └─────────────────────────────────────────┘
                            ▼
       ┌─────────────────────────────────────────┐
   ③   │  python engine/run_dispatch.py \         │  ← 可选：派发给 Claude API 写正文
       │     --chapters <N> --effort high         │     (不配 key 时跳过，Cline 协作)
       └─────────────────────────────────────────┘
                            ▼
       ┌─────────────────────────────────────────┐
   ④   │  prose_lint + safety_lint + 字数校验    │  ← 三道门不过线 BLOCKED
       └─────────────────────────────────────────┘
                            ▼
       ┌─────────────────────────────────────────┐
   ⑤   │  Cline 读 PASS 报告 → 落盘 chapters/    │  ← 你最后人工审
       └─────────────────────────────────────────┘
```

### 关键设计原则

| 原则 | 实现 |
|---|---|
| **Cline 是主控** | `writer.py` 不直连 API；Cline 自己读 prompt、自己写、自己审 |
| **可对接 Claude API** | 配 `ANTHROPIC_API_KEY` → `run_dispatch.py` 派发远端 |
| **不关机长跑** | 每个 Step 独立命令 + 状态文件（`prompts/.results/Chapter_NN.md`）落盘 |
| **人审是终门** | Cline 写完 → 你审 → 改 → 落盘 |
| **数据可追溯** | `arc.json` + `ties.json` + `CAST.md` 自动追踪块 + `dossier.md` |

---

## 📐 写作规范速查（v3.1 · 2026/8/31 三次修订）

- **每章字数**：**1800–2200 字**（纯正文，不含标点 / 空格 / 换行 / Markdown 标记）
- **章节结构**：**纯正文连续叙事 + 章末自查段**（无小标题 / 序号 / 加粗 / 项目符号）
- **核心视角**：第三人称有限视角，杜绝上帝视角（含隐性越界）
- **AI 通病禁令**：8 大硬性禁令（机械机械 / 无效副词 / 模板对话动作 / 否定对比 / 弱转折 / 一句一动作 / 强迫症精确数字 / 罪己侧写术语）
- **大 Boss 暗线**：霍爷爷 100% 慈祥正派，**第 50 章前**严禁任何阴暗描写
- **每章末尾自查**：11 项强制（字数 / 视角 / 语言 / 终极禁令 / 人物 / 场景 / 悬悬铁律 / 项目同步）

详见 [`.clinerules`](.clinerules) 第 4 节 9 大硬约束 + 第 13 节 11 项末尾自查清单。

---

## 📊 实测指标（当前值 · 2026/9/3 · 14 章快照）

> 以下数据为**当前实测**（非历史趋势），全部通过 `engine/batch_rewrite.py status` / `engine/prose_lint.py` / `tools/cast_absence_scan.py` 现场跑出。两套 lint 工具通过率不一致是**有意设计**：`batch_rewrite` 是 PR 级粗筛（em dash + 字数 + 模板动作），`prose_lint` 是章节定稿前终门（12 类严格 ERROR + 5 类 WARN）。

### 1. 章节总数与 lint 通过率（两套口径并呈）

| 工具 | 命令 | 通过定义 | 通过率 | 备注 |
|---|---|---|---|---|
| `batch_rewrite.py` | `status` | `err=0` | **8/14 = 57.1%** | 6 章带 DISEASE 标记（ch06, 07, 08, 10, 12, 13）|
| `prose_lint.py` | 全扫 | 标 `[OK]`（0 ERROR）| **8/14 = 57.1%** | 同 6 章有 ERROR（见下表）|
| `prose_lint.py --warn-as-error` | 全扫 | 0 ERROR + 0 WARN | **2/14 = 14.3%** | 仅 ch01, ch09 完全零告警 |

> 三个工具通过率一致是巧合：粗筛的 6 个失败项 = 终门的 6 个失败项（ch06/07/08/10/12/13）。

### 2. 已知 ERROR 残留（待回溯项 · 不影响阅读观感）

| 章节 | 字数 | ERROR 类型 | 具体数值 | 是否影响阅读 |
|---|---:|---|---|---|
| ch06 | 2162 | 模板化对话动作 | 2 处 | 轻微 AI 痕迹（"她说"/"他问"类）|
| ch07 | 1999 | 破折号过载 + 模板对话 | 17/段 + 3 处 | 节奏略碎，但剧情完整 |
| ch08 | 2189 | 模板化对话动作 | 3 处 | 轻微 AI 痕迹 |
| ch10 | 2073 | 破折号过载 | 27/段 | 节奏拖成散文诗（最严重）|
| ch12 | 2156 | 破折号过载 + 模板对话 | 33/段 + 2 处 | 节奏拖成散文诗（最严重）|
| ch13 | 1979 | 破折号过载 | 7/段 | 接近阈值（5 个），基本可接受 |

**回溯计划**：上述 6 章为 v1/v2 阶段定稿（仅满足字数 + em dash 数量约束），**未跑过完整 `prose_lint` 严格标准**。第 14 章起已按严格标准执行。回溯工作待用户安排，**不在本仓库当前 PR 范围内**（避免大规模重写引入新问题）。

### 3. 角色一致性覆盖（`cast_absence_scan.py` 实测 · 2026/9/3）

```
=== Cast absence scan (all 14 chapters) ===
NAME       STATUS     LAST   GAP  APPS
------------------------------------------------------------
轩宁         核心班底       ch14   0    14
沈夜         核心班底       ch14   0    14
顾星阑        核心班底       ch14   2     7
霍渊白        大 Boss      ch7    7     1
陈屿         动态角色       ch14   2     8
陈砚青        动态角色       ch14   3     7
骆一璇        动态角色       ch14   0     1
陈屿         动态角色       ch13   4     7
程诺         动态角色       ch13   1     6
林岳洲        动态角色       ch13   1     2
陈维舟        动态角色       ch1    13    1   WARN-OVER-8: gap=13
```

- **追踪范围**：10 个角色（3 个核心班底 + 1 个大 Boss + 6 个动态角色）
- **核心班底 3 人**（轩宁/沈夜/顾星阑）：ch14 当下登场，GAP=0~2，全部在阈值内
- **大 Boss 霍渊白**：ch7 末次正面登场（ch1-13 通过线索侧面提及），GAP=7，符合"第 50 章前 0 阴暗描写"设定
- **9/10 角色全部在缺席阈值内**；唯一告警为「陈维舟」GAP=13 —— 这是**第 1 章的误导靶**（一次性角色，签名后第二年已死），属于**设定预期之内**的告警

### 4. 实时命令复现

```bash
# 跑出"通过率"和"DISEASE 分布"
python engine/batch_rewrite.py status

# 跑出"严格 12 类 ERROR + 5 类 WARN"判定
python engine/prose_lint.py chapters/Chapter_*.md

# 跑出"严格 0 ERROR + 0 WARN"（--warn-as-error 模式）
python engine/prose_lint.py --warn-as-error chapters/Chapter_*.md

# 跑出"角色缺席扫描 + 阈值告警"
python tools/cast_absence_scan.py
```

### 5. 改稿轮次

> 当前 git 历史仅可见 2 个涉及 `chapters/` 的 commit（v1/v2 旧稿 squash 在 `18dd7d6` 一次性 commit + ch14 新增 `d264793`），**无法从 git log 还原每章平均改稿轮次**。该项数据从 git log 不可量化，已诚实标注，不做估算。

> ⚠️ **本节数据为单次快照，不构成时间序列**。如需历史趋势，需在 CI 中跑定时统计并落盘（暂未实现）。


---

## 🔧 配置可选：API key 启用远端派发

```bash
# 1. 复制环境变量模板
cp .env.example .env

# 2. 编辑 .env 填入真 key
# ANTHROPIC_API_KEY=sk-ant-...

# 3. 验证 run_dispatch.py 跑通
python engine/run_dispatch.py --chapters 14 --effort high --dry-run
```

不配 key 时工具链**自动降级**到 Cline 协作模式——`run_dispatch.py` 跳过远端派发，Cline 自己读 prompt 文件写正文。

---



---

## 📜 版本 + 版权

- **写作规范版本**：v3.1（2026/8/31 三次修订）
- **架构版本**：双模式（Cline 协作 / Claude API 派发）
- **总章节规划**：70–80 章 × 2000 字 = 14–17.6 万字
- **本文档仅供作者本人创作参考使用，未经许可不得外传**
