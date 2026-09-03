# 更新日志（CHANGELOG）

> 所有对项目有"读者可见"意义的更新，都记录在这里。
> 格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。
> 章节正文（`chapters/Chapter_NN.md`）和追踪表（`OUTLINE.md` / `CLUES_TRACKER.md` / `CAST.md`）的详细变更，见对应文件的 git diff；本文件只做高阶摘要。

## [Unreleased · 2026/9/3] — README 改造 + 双语

> 一次性合并推送 4 个任务（不修改任何 chapter 正文；只改 README/CHANGELOG）。

### 修改
- `README.md`：
  - **任务 1**：版权声明二元化（小说内容禁 / 工程代码可）
  - **任务 2**：新增「项目背景与致谢」节，致谢 Open Souls fork 来源
  - **任务 3**：新增「技术亮点（Highlights for AI Engineering）」节，6 个 AI 工程能力关键词
  - 当前进度同步至第 14 章《老槐树》定稿
- `README.en.md`：**新建**（双语 README，9 个二级标题；**任务 5**）
- `CHANGELOG.md`：本节

### 新增
- `README.en.md`：英文版 README，209 行；技术性章节（Highlights / Architecture / Workflow / Configuration）完整翻译；非技术性章节（剧情设定 / 写作规范速查 / 关键指标样例）简化或省略

### 不变
- `chapters/Chapter_*.md` 14 个：**未改动**
- `engine/` `tools/` 代码：**未改动**（本次为 README 层改造，不动工程代码）


---

## [Unreleased]

### 待写
- 第 15 章：副线案三·中段（蹲点调查 7:45 + 侧写锁定嫌疑人）
- 第 2-11 章扩写至 2500–3000 字区间（v3 旧章节回溯）
- `CAST.md`：骆一璇姑姑真身揭晓 / "上一级" 居所主人揭晓
- `CLUES_TRACKER.md`：T-4 "另一套代理人网络上层是谁" 揭晓（第 30 章后）

---

## [14] - 2026-09-03 — 老槐树

### 新增
- `chapters/Chapter_14.md`：第 14 章《老槐树》定稿正文
  - 副线案三·开场（顾星阑灰色中介抛出骆一璇案）
  - 涂黑母题 **M-4 第二轮**（监控截图里币面磨痕与"问"字笔帽同源）
  - 1987 年墨水长线再现
  - 港城西郊老槐树院落当晚首次亮灯（长线 **M-5 上一级居所** 推进）
- `prompts/Chapter_14_plan.md`：第 14 章策划 prompt
- `prompts/Chapter_14_draft.md`：第 14 章写手 prompt（含策划 JSON）

### 修改
- `CAST.md`：追加 2 个角色
  - **骆一璇**（港城家事法庭二庭法官助理·秦瑾同庭·副线案三受害人）
  - **骆一璇的姑姑**（戴鸭舌帽中年女人·功能性 NPC·不参与核心反派）
- `CLUES_TRACKER.md`：
  - T-1 "涂黑 = 同一双手"伏笔 → 状态更新为 **已部分回收（第 14 章第二轮）**
  - 新增 T-9 "港城西郊老槐树院落当晚亮灯疑问"（待下一章发现）
  - 第 7 节追踪表追加第 14 章行
  - 文件末尾注释更新到 2026/9/3
- `OUTLINE.md`：第 14 章状态从 ⏳ 待写 → ✅ 已定稿（保留所有 v3.1 硬约束说明）

### 校验
- `prose_lint.py --strict-editorial chapters/Chapter_14.md`：**0 ERR / 1 WARN**
- `safety_lint.py chapters/Chapter_14.md`：**✓ 安全门通过**
- `check_chapter_quality.ps1 -Chapter 14`：**[OK]** pure=2105
- `prescreen.py`：[OK]（无 AI 高频词、模板对话、强制精确数字告警）
- `validate_changed.py --paths chapters/Chapter_14.md`：**PASS**

### 写作铁律遵守
- ✅ 第三人称有限视角（POV = 轩宁）
- ✅ 纯正文连续叙事 + 章末自查段（**无小标题/序号/加粗**）
- ✅ 继承第 13 章"地点名 + 句号 + 单段"开篇（"港城西郊。"）
- ✅ 核心涉案 ≤ 3 人（轩宁 / 顾星阑 / 沈夜 + 骆一璇姑姑）
- ✅ 副线案 3 开场按 OUTLINE.md 节奏
- ✅ 霍爷爷本章不出场（大 Boss 暗线第 50 章前 0 暴露）
- ✅ 轩宁无凡人情绪波动（无眼眶红了/第一次哽咽/第一次带着颤等标签）
- ✅ 上一级姓名未揭晓（长线 M-5 钩子保留）
- ✅ 三个核心物证（"问"字笔帽 / VII 铜印 / 珠江路 17 号）以画面+内心型态呈现

---

## [13] - 2026-08-31 — 旧石灰号的根（第 2 次精修）

> 由历史 commit `18dd7d6`（"上传《天黑之前》全部文件·2026/9/1 第 2 次精修版本"）封存。
> 本次同步建立 v3.1 字数硬门 [1800, 2200] + 8 大 AI 通病禁令 + 大 Boss 暗线规则。

### 修改
- `chapters/Chapter_13.md`：em dash 24→7 / 0 err 0 warn / 第二案彻底闭环
- `chapters/Chapter_07-12.md`：第 2 次精修（em dash 清零 / 模板对话动作清零 / 加粗清零）
- `OUTLINE.md`：v3 项目级重大修订（70-80 章 / 2500-3000 字 / 纯正文 + 章末自查）
- `CLUES_TRACKER.md`：v3 同步章节状态追踪表
- `.clinerules`：v3.1 字数硬约束 1800-2200

---

## 版本号规则

- 章节号 = 主版本号（每章一次主版本号递增）
- 子版本号 = 同章内的精修（如 13.1、13.2）
- 主版本号 0.x = 草稿期；1.0 = 全本 70-80 章定稿
- 当前进度：**14 / 80 章（17.5%）**
