# -*- coding: utf-8 -*-
"""天黑之前 · AI 自动续写编排器（Cline 协作版 · 半自动）。

移植自旧魂《众魂》engine/writer.py（plan/draft/critique 三阶段编排），
已按天黑之前的需求改造：

  · 不调用 Anthropic API（天黑之前用 Cline 协作，不需要直连）
  · 每个阶段生成一个独立的结构化 prompt 文件，可手动复制粘贴给 Cline
  · 可选自动调起 `claude --file <prompt>` 把 prompt 喂给 Cline（半自动模式）
  · 字段全部贴合天黑之前的硬门（.clinerules 第 4 节 9 大硬约束）

核心函数（按"策划→写手→审校"流水线）：
  brief(chapter)        → 输出"本回简报"（最近章节 + 节拍 + 角色卡 + 暗线状态）
  plan(brief)            → 输出 prompts/Chapter_NN_plan.md
  draft(brief, plan)     → 输出 prompts/Chapter_NN_draft.md
  critique(brief, draft) → 输出 prompts/Chapter_NN_review.md
  compose(chapter, auto=False)
                          → 一键跑 plan → draft → critique 三个 prompt 文件
                          → auto=True 时自动调起 Cline 处理每个 prompt

用法：
  python engine/writer.py brief 14                    # 输出本回简报
  python engine/writer.py compose 14                  # 生成三个 prompt
  python engine/writer.py compose 14 --auto            # 自动喂给 Cline
"""
import os
import sys
import json
import re
import subprocess
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))

import soul as SOUL
from season import load_arc, beat_line, open_side_cases
from trace import chapter_appearances, chapter_metrics

CHARACTERS_DIR = ROOT / "characters"
CHAPTERS_DIR = ROOT / "chapters"
CAST_FILE = ROOT / "CAST.md"
CLINES_FILE = ROOT / "CLUES_TRACKER.md"
PROMPTS_DIR = ROOT / "prompts"

# v3.1 字数配置（2026/8/31 用户最新决策）
# 降字以保证 Cline 输出质量：单章纯字 [1800, 2200]，中位 2000
TARGET_CHARS = 2000          # 中位值
MIN_CHARS = 1800
MAX_CHARS = 2200

# 系统级 register（天黑之前版）
REGISTER = """你是《天黑之前》的写作助手。这是一部港城过去十年"第七起"系列案件的悬疑爽剧。
主角是被警界除名的女侧写师轩宁，在灰色暗线里一步步发现自己不是被抛弃的人，而是被精心选中的人。
你的笔调克制、潜台词推进、多感官场景、刑侦专业——读者要"细思极恐"而不是"看破"。
所有判定对照 Novel_New/.clinerules 第 4 节 9 大硬约束。
"""


def _read(path: Path, n: Optional[int] = None) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    return text[:n] if n else text


def _chapter_path(n: int) -> Path:
    return CHAPTERS_DIR / f"Chapter_{n:02d}.md"


def _ensure_prompts_dir():
    PROMPTS_DIR.mkdir(exist_ok=True)


# ============================================================
# 阶段 0 · 本回简报
# ============================================================

def brief(chapter: int) -> str:
    """生成"本回简报"：最近章节 + 节拍 + 角色卡 + 暗线状态。

    这是策划/写手/审稿三阶段共用的输入。
    """
    arc = load_arc(ROOT)
    # 优先 characters/；不存在时 fallback 到 CAST.md（已由 SOUL.load_cast 自动判断）
    cast = SOUL.load_cast(str(CHARACTERS_DIR))

    recent = []
    for prev in range(max(1, chapter - 3), chapter):
        p = _chapter_path(prev)
        if p.exists():
            metrics = chapter_metrics(str(p))
            apps = chapter_appearances(str(p), list(cast.keys()))
            recent.append({
                "chapter": prev,
                "file": p.name,
                "pure_chars": metrics["chars"],
                "cast": [n for n, _ in apps],
            })

    candidates = []
    for name, meta in cast.items():
        candidates.append({
            "name": name,
            "role": meta.get("role", "—"),
            "status": meta.get("status", "—"),
            "one_line": meta.get("one_line", ""),
            "fracture": meta.get("fracture", {}),
            "under_pressure": meta.get("under_pressure", ""),
            "voice": meta.get("voice", ""),
            "boundaries": meta.get("boundaries", ""),
            "signature": meta.get("signature", ""),
            "current_state": meta.get("current_state", "—"),
        })

    brief_data = {
        "chapter": chapter,
        "target_chars": TARGET_CHARS,
        "min_chars": MIN_CHARS,
        "max_chars": MAX_CHARS,
        "main_beat": arc["main_case"]["beat"] + 1,
        "main_beat_line": beat_line(arc),
        "open_side_cases": open_side_cases(arc),
        "recent_chapters": recent,
        "cast_candidates": candidates,
    }
    return json.dumps(brief_data, ensure_ascii=False, indent=2)


# ============================================================
# 阶段 1 · 策划 prompt
# ============================================================

PLAN_PROMPT_TEMPLATE = """{register}

【策划第 {chapter} 章 / showrunner】
先别写正文，先定方案。

## 本回简报（机器生成，已按 .clinerules 第 4 节硬约束过滤）
{brief_json}

## 你的任务

按 .clinerules 第 5 节「单章节奏模板」（开篇钩子 500 → 调查推进 1500 → 侧写高光 1500 → 反转 1000 → 章末钩子 500 → 章末自查段 200）
设计本章方案，确保：
  1. **cast 名单**：从 cast_candidates 里挑 1–4 人（含本章核心涉案 ≤ 3 人规则）
  2. **POV 锁定**：全程单一聚焦角色，第三人称有限视角（.clinerules 4.1）
  3. **节拍点**：开篇冲突直接进场，3 波转折卡在 ≈22% / 47% / 68% 字数处
  4. **章末钩子**：画面钩或信息钩二选一，落物象
  5. **副线案进度**：open_side_cases 里如果有「案件零·七号仓库」「案件一·秦瑾案」等，按 CLUES_TRACKER.md 状态推进
  6. **伏笔管理**：本章若新埋伏笔，必须登记到 CLUES_TRACKER.md 第 3 节「待回收线索清单」；本章若回收伏笔，必须在第 3 节标注已回收
  7. **.clinerules 4.10 大 Boss 暗线**：本章若涉及霍爷爷，必须 100% 慈祥正派，**严禁泄露左手刻字**等专属特征

## 输出格式

只输出严格 JSON（不要 Markdown 围栏）：
```json
{{
  "title": "2-4 字标题",
  "pov": "聚焦角色名",
  "cast": ["核心角色1", "核心角色2", "..."],
  "side_case": "本章推进的副线案名（如「案件一·秦瑾案」）",
  "beat": "起/承/转/合 + 节拍描述",
  "hook_type": "画面钩/信息钩",
  "hook_object": "落物象的具体物件（如「七号仓库钥匙」「雨夜的烟蒂」）",
  "payoff": "本章爽点或痛点（30 字内）",
  "foreshadow_new": ["本章新埋的伏笔 1", "..."] 或 [],
  "foreshadow_recycle": ["本章回收的伏笔 1", "..."] 或 [],
  "rhyme_point": "本章套用的暗线母题编号（CLUES_TRACKER.md 第 5 节：1=第七个接棒链 / 2=未拨出电话 / 3=3年7年 / 4=左手刻字 / 5=问渠先生代理人 / 6=涂黑）或 null"
}}
```

## 写作铁律（.clinerules 4.1-4.13 节硬约束摘要）

- **字数**：{target_chars} 字（中位值，[1800, 2200] 区间）
- **排版**：❌ 禁止任何小标题/序号/加粗/项目符号；✅ 纯正文连续叙事
- **em dash**：每章 ≤ 5 次
- **视角**：第三人称有限，严禁上帝视角（含隐性越界）
- **8 大 AI 通病禁令**：机械衔接词只见/就在这时/不由得/不禁/似乎/仿佛/好像 / 无效副词非常/极其/格外/稍稍/默默 / 高频词眼眸/唇角/身形/骤然 / 模板化对话动作「他XX地说」/ 否定对比「没有…没有…」/ 弱转折「虽然…但是…」/ 一句一动作 / 纯台词对话
- **强迫症式精确数字禁令**：❌ 精确钟点 / 秒 / 厘米 / 步数 / 年份金额；✅ 模糊时间 + 画面感
- **术语禁令**：❌ 罪己侧写 / 签名行为 / 移情；✅ 侧写 / 侧写集 / 代理人 / 代理人网络
- **台词四件套**：语气 + 神态 + 动作 + 心理
- **主角反差**：日常漫不经心 / 侧写极度冷静
- **场景转换必须有过渡**：通过人物移动/时间流逝/环境衔接
- **章末自查段**：纯正文段落形式，无小标题，逐条对照 4.13 节
"""


def plan(chapter: int, brief_data: Optional[str] = None) -> Path:
    """生成策划 prompt 文件，返回路径。"""
    _ensure_prompts_dir()
    if brief_data is None:
        brief_data = brief(chapter)
    out = PROMPTS_DIR / f"Chapter_{chapter:02d}_plan.md"
    out.write_text(
        PLAN_PROMPT_TEMPLATE.format(
            register=REGISTER,
            chapter=chapter,
            brief_json=brief_data,
            target_chars=TARGET_CHARS,
        ),
        encoding="utf-8",
    )
    return out


# ============================================================
# 阶段 2 · 写手 prompt
# ============================================================

DRAFT_PROMPT_TEMPLATE = """{register}

【写第 {chapter} 章 / 按方案写正文】
目标 {target_chars} 字（中位值，[1800, 2200] 区间），命中 payoff，结在 hook 上。

## 策划方案

```json
{plan_json}
```

## 你的任务

按上面方案写本章正文，**严格遵守 .clinerules 第 4 节 9 大硬约束 + 第 5 节节奏模板**。

### 字数与排版（铁律）

- **目标字数**：{target_chars} 字（中位值），区间 [{min_chars}, {max_chars}]
- **❌ 禁止**：任何小标题 / 序号 / 加粗 / 项目符号 / Markdown 标记
- **✅ 结构**：「纯正文连续叙事 + 章末自查段」（章末自查段以"写完这一章，按规矩要回头自查一遍。"开头，无小标题）
- **段落**：只在场景切换时空行分隔；每两段之间最多 1 个空行；不写超长无停顿段落，也不写一句一段散文式
- **em dash `——`**：每章 ≤ 5 次（仅场景切换分隔符 / 对话引导语）

### 节奏分配（v3.1 · 适配 2000 字）

| 段落 | 字数 | 内容 |
|---|---|---|
| 开篇钩子 | 350 | 直接切入实时情节，建立悬念，**严禁**否定对比 / 弱转折句式开场 |
| 调查推进 | 600 | 多感官场景 + 轩宁蹲点 + 配角互动 |
| 侧写高光 | 500 | 5 步法推演 + 台词四件套 + 反差切换 |
| 反转 / 主线物证 | 300 | 伏笔回收或新伏笔埋下 |
| 章末钩子 | 150 | 引出下一章或长线谜团 |
| 章末自查段 | 100 | 纯正文段落，对照 4.13 节 |

### 8 大 AI 通病禁令（.clinerules 4.3 / 4.13）

- ❌ 机械衔接词：只见 / 就这时 / 片刻后 / 随即 / 于是 / 因此 / 不由得 / 不禁 / 似乎 / 仿佛 / 好像
- ❌ 无效副词：非常 / 极其 / 格外 / 稍稍 / 默默
- ❌ 高频词：眼眸 / 唇角 / 身形 / 骤然
- ❌ 模板化对话动作：「他XX地说」/「XX地看着」/「XX地走过去」
- ❌ 强迫症式精确数字：精确钟点 / 秒 / 厘米 / 步数 / 年份金额（剧情必需的 11:40 / 03:17 / VII / 七 / 17 米 等母题可保留）
- ❌ 否定对比句式：没有…没有… / 不是…而是… / 并非…而是… / 没有…只是…
- ❌ 弱转折句式：虽然…但是… / 尽管…却… / 并非…却… / 甚至…没有…
- ❌ 一句一动作、纯台词对话、括号补充说明

### 视角与人物（.clinerules 4.1 / 4.7）

- **第三人称有限视角**：全程只写 POV 角色亲眼所见 + 亲耳所闻 + 亲身感受 + 内心所思；不直接交代其他角色未被观察到的心理
- **场景转换有过渡**：通过人物移动 / 时间流逝 / 环境衔接
- **台词四件套**：每一句人物语言，必须同步写出说话人的**语气 + 面部表情 + 肢体动作 + 当下心理**
- **主角反差**：日常漫不经心 / 侧写极度冷静；切换要"无缝"
- **大 Boss 暗线**：若本章涉及霍爷爷，必须 100% 慈祥、100% 正派、100% 真诚关怀（**严禁泄露"霍渊白 = 问渠先生"或左手刻字**等专属特征）

### 章节结构模板（参考 .clinerules 第 5 节）

```markdown
# 第 {chapter} 章 《标题》

## 一

（章末自查段以"写完这一章，按规矩要回头自查一遍。"开头）
```

**注意**：「## 一」是模板占位（让 chapter_stats.ps1 能识别正文段），写正文时**标题、序号、加粗、项目符号均不可见**，仅以自然段落推进。

## 输出格式

只输出 JSON：
```json
{{
  "chapter_title": "本章标题（2-4 字）",
  "chapter_body": "完整正文（含「## 一」+ 章末自查段；不含标题行）",
  "foreshadow_new": ["本章新埋的伏笔 1", "..."] 或 [],
  "foreshadow_recycle": ["本章回收的伏笔 1", "..."] 或 [],
  "side_case_progress": "副线案状态更新（如「案件一·秦瑾案 推进至高潮」）"
}}
```
"""


def draft(chapter: int, plan_json: str) -> Path:
    """生成写手 prompt 文件。"""
    _ensure_prompts_dir()
    out = PROMPTS_DIR / f"Chapter_{chapter:02d}_draft.md"
    out.write_text(
        DRAFT_PROMPT_TEMPLATE.format(
            register=REGISTER,
            chapter=chapter,
            target_chars=TARGET_CHARS,
            min_chars=MIN_CHARS,
            max_chars=MAX_CHARS,
            plan_json=plan_json,
        ),
        encoding="utf-8",
    )
    return out


# ============================================================
# 阶段 3 · 审稿 prompt（7 维文笔 + 9 硬门 + 安全门）
# ============================================================

REVIEW_PROMPT_TEMPLATE = """{register}

【审第 {chapter} 章 / 上线门】
对照 .clinerules 第 4 节 9 大硬约束 + 第 4.13 节「章末自查段」，给出 7 维文笔分 + 9 硬门判定 + 修复方向。

## 章节内容（待审稿）

```markdown
{draft_body}
```

## 策划方案（参考目标）

```json
{plan_json}
```

## 你的任务

### 7 维文笔打分（每维 0/1/2，满分 14）

| 维 | 0 | 1 | 2 |
|---|---|---|---|
| 1 句子节奏 | 逗号碎句 / 单调 | 长短交替 | 长铺短砸、一字成句 |
| 2 用词 | 形容词糊弄 | 动词带物象 | 名词+动作写情绪 |
| 3 潜台词 | 心理直说 | 留白但硬猜 | 说 A 读到 B 不点破 |
| 4 感官 | "她很紧张" | 一个身体反应 | 锚定可触可量部位 |
| 5 对话 | 英文标签 / 看不清 | 中文标签声线分得开 | 不靠标签认得谁说 |
| 6 视角 | 视角飘 / 上帝插嘴 | 锁单一视角 | 只写视角人能感知 |
| 7 克制 | 又解释又总结 | 收得住 | 该停就停 |

**< 9 分（文笔层）或任一维 = 0 → 退回重写**，在 `修复方向` 里写明回炉点。

### 9 硬门判定（PASS / PARTIAL / FAIL）

| # | 硬门 | 来源 |
|---|---|---|
| 1 | 字数 [1800, 2200] | .clinerules 4.2（v3.1） |
| 2 | 排版（无小标题 / 序号 / 加粗）| .clinerules 4.4 |
| 3 | 8 大 AI 通病禁令 | .clinerules 4.3 / 4.13 |
| 4 | 第三人称有限视角 | .clinerules 4.1 |
| 5 | 强迫症式精确数字禁令 | .clinerules 4.5 |
| 6 | 术语禁令（不写「罪己侧写」等）| .clinerules 4.6 |
| 7 | 台词四件套 | .clinerules 4.7.2 |
| 8 | 一案一结（核心涉案 ≤ 3）| CLUES_TRACKER.md 第 4 节 |
| 9 | 大 Boss 暗线（霍爷爷 100% 慈祥）| .clinerules 4.10 |

### 安全门

- ❌ 露骨性行为
- ❌ 自我伤害细节
- ❌ 未成年角色暧昧身体描写

### 字数硬门（机器可先跑）

```bash
python engine/prose_lint.py chapters/Chapter_{chapter:02d}.md
```

## 输出格式

只输出 JSON：
```json
{{
  "scores": {{
    "句子节奏": 0-2,
    "用词": 0-2,
    "潜台词": 0-2,
    "感官": 0-2,
    "对话": 0-2,
    "视角": 0-2,
    "克制": 0-2
  }},
  "total": "七维总和（int）",
  "hard_gates": {{
    "字数": "PASS/PARTIAL/FAIL",
    "排版": "PASS/PARTIAL/FAIL",
    "AI通病": "PASS/PARTIAL/FAIL",
    "视角": "PASS/PARTIAL/FAIL",
    "精确数字": "PASS/PARTIAL/FAIL",
    "术语": "PASS/PARTIAL/FAIL",
    "台词四件套": "PASS/PARTIAL/FAIL",
    "一案一结": "PASS/PARTIAL/FAIL",
    "大Boss暗线": "PASS/PARTIAL/FAIL"
  }},
  "safety": {{
    "safe": "true/false",
    "reason": "如有违规说明"
  }},
  "review": "逐维引用正文短语（用「」逐字引用一条正文原句）、说明到位或差在哪",
  "fix_direction": "一条可执行的改法（具体句子/位置 + 怎么改）",
  "decision": "PASS / BACKEND（任一硬门 FAIL 或文笔 < 9 分）"
}}
```

**文笔七维地板是 9，但本项目上线档定在 12**——这是「同一支笔」的实际门槛。9–11 分能读但不够，标 BACKEND。
"""


def critique(chapter: int, draft_body: str, plan_json: str) -> Path:
    """生成审稿 prompt 文件。"""
    _ensure_prompts_dir()
    out = PROMPTS_DIR / f"Chapter_{chapter:02d}_review.md"
    out.write_text(
        REVIEW_PROMPT_TEMPLATE.format(
            register=REGISTER,
            chapter=chapter,
            draft_body=draft_body,
            plan_json=plan_json,
        ),
        encoding="utf-8",
    )
    return out


# ============================================================
# 编排：一键跑 plan → draft → critique 三个 prompt
# ============================================================

def compose(chapter: int, auto: bool = False, run_draft: bool = True) -> dict:
    """一键生成三个 prompt 文件。

    Args:
        chapter: 章节号
        auto: 是否自动调起 Cline 处理每个 prompt
              （依赖环境中有 `claude` 命令行；不在路径则跳过）
        run_draft: 是否生成 draft prompt（默认 True）

    Returns:
        {"plan": Path, "draft": Path|None}
    """
    brief_data = brief(chapter)
    plan_path = plan(chapter, brief_data)
    out = {"plan": plan_path}

    if run_draft:
        placeholder_plan = json.dumps({
            "title": "（待策划填入）",
            "pov": "（待策划填入）",
            "cast": [],
            "side_case": "",
            "beat": "",
            "hook_type": "",
            "hook_object": "",
            "payoff": "",
            "foreshadow_new": [],
            "foreshadow_recycle": [],
            "rhyme_point": None,
        }, ensure_ascii=False)
        draft_path = draft(chapter, placeholder_plan)
        out["draft"] = draft_path

    if auto:
        for label, path in out.items():
            print(f"\n=== 自动喂给 Cline: {label} ({path.name}) ===")
            ok = _run_claude(path)
            if not ok:
                print(f"⚠ {label} 自动跑失败，请手动复制粘贴到 Cline")
    return out


def _run_claude(prompt_path: Path) -> bool:
    """调起 `claude --file <prompt>` 命令；不存在则返回 False。"""
    try:
        r = subprocess.run(
            ["claude", "--file", str(prompt_path)],
            capture_output=True,
            text=True,
            timeout=420,
        )
        print(r.stdout)
        if r.returncode != 0:
            print(f"STDERR: {r.stderr[:500]}")
            return False
        return True
    except FileNotFoundError:
        print("⚠ `claude` 命令不在 PATH；跳过自动模式")
        return False
    except subprocess.TimeoutExpired:
        print(f"⚠ `claude` 处理超时（>420 秒）")
        return False


# ============================================================
# CLI 入口
# ============================================================

def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return

    cmd = args[0]
    if cmd == "brief":
        n = int(args[1])
        print(brief(n))
    elif cmd == "plan":
        n = int(args[1])
        out = plan(n)
        print(f"✓ {out}")
    elif cmd == "draft":
        n = int(args[1])
        plan_json = args[2] if len(args) >= 3 else "{}"
        out = draft(n, plan_json)
        print(f"✓ {out}")
    elif cmd == "review":
        n = int(args[1])
        cp = _chapter_path(n)
        if not cp.exists():
            print(f"[FAIL] {cp.name} not found")
            sys.exit(1)
        body = cp.read_text(encoding="utf-8")
        plan_json = args[2] if len(args) >= 3 else "{}"
        prompt_path = critique(n, body, plan_json)
        # critique() returns a prompt path; user feeds it to Claude and gets back YAML.
        print(f"[OK] review prompt at {prompt_path}")
        print("next: feed this prompt to Claude, then run:")
        print(f"  python engine/writer.py apply-review {n} < yaml_from_claude.txt")
    elif cmd == "apply-review":
        # Usage: python engine/writer.py apply-review <N> < yaml_file
        if len(args) < 3:
            print("usage: apply-review <chapter> <yaml_file> [--write-back]")
            sys.exit(2)
        n = int(args[1])
        yaml_path = Path(args[2])
        if not yaml_path.exists():
            print(f"[FAIL] {yaml_path} not found")
            sys.exit(1)
        review_yaml = yaml_path.read_text(encoding="utf-8")
        write_back = "--write-back" in args
        review_block = _write_yaml_review_block(review_yaml)
        review_path = apply_review_block(
            n,
            review_yaml,
            also_write_chapter=write_back,
        )
        print(f"[OK] review at {review_path}")
    elif cmd == "compose":
        n = int(args[1])
        auto = "--auto" in args
        run_draft = "--no-draft" not in args
        out = compose(n, auto=auto, run_draft=run_draft)
        for label, path in out.items():
            print(f"  {label}: {path}")
    else:
        print(f"unknown command: {cmd}")
        print("available: brief / plan / draft / review / apply-review / compose <chapter> [--auto]")


# ============================================================
# 自动把 review 块写回 chapter 文件（Q5）
# ============================================================

# 用 HTML 注释包裹 review 块 —— 不破坏 markdown 结构 + 不被 prose_lint 算入字数
_REVIEW_BLOCK_START = "\n<!-- review_block: do not edit by hand; managed by engine/writer.py -->\n"
_REVIEW_BLOCK_END = "\n<!-- /review_block -->\n"


def _render_review_block(review_data) -> str:
    """Format a critique() result dict into an HTML-comment review block.

    review_data is the dict returned by critique() (or _normalize_critique):
      {
        "scores": {...},            # 7-dim or 9-dim dict
        "total": int,
        "hard_gates": {...},        # dict of gate -> "PASS"/"PARTIAL"/"FAIL"
        "safety": {"safe": bool, "reason": str},
        "review_text": str,         # free-text review
      }
    """
    if not isinstance(review_data, dict):
        # String fallback: render verbatim
        return _REVIEW_BLOCK_START + str(review_data).strip() + _REVIEW_BLOCK_END

    lines = []
    if "total" in review_data:
        lines.append(f"score: {review_data['total']}")

    scores = review_data.get("scores") or {}
    if scores:
        lines.append("scores:")
        for k, v in scores.items():
            lines.append(f"  {k}: {v}")

    gates = review_data.get("hard_gates") or {}
    if gates:
        lines.append("hard_gates:")
        for k, v in gates.items():
            lines.append(f"  {k}: {v}")

    safety = review_data.get("safety") or {}
    if safety:
        safe = safety.get("safe", True)
        reason = safety.get("reason", "")
        lines.append(f"safety: {'safe' if safe else 'UNSAFE'} {reason}".rstrip())

    review_text = review_data.get("review_text") or review_data.get("review") or ""
    if review_text:
        lines.append("review: |")
        for line in str(review_text).splitlines():
            lines.append(f"  {line}")

    body = "\n".join(lines)
    return _REVIEW_BLOCK_START + body + _REVIEW_BLOCK_END


def apply_review_block(chapter: int, review_data, *,
                       results_dir: Optional[Path] = None,
                       also_write_chapter: bool = False) -> Path:
    """Persist a critique result for a chapter.

    Writes the review to two places (mirroring run_dispatch.py):
      1. ALWAYS: prompts/.results/Chapter_NN_review.md  (canonical verdict)
      2. OPTIONALLY: append to chapters/Chapter_NN.md as an HTML comment block

    Args:
        chapter: chapter number
        review_data: dict from critique() / _normalize_critique() (or a string)
        results_dir: override the results directory (defaults to ROOT/prompts/.results)
        also_write_chapter: if True, ALSO append the review to the chapter file.
                            Default False because editing chapter content during
                            review violates the "no side effects" rule from
                            .clinerules §11.4 (Claude must not silently edit chapters).
                            Use True only when the user explicitly asks.

    Returns:
        Path to the canonical review file (prompts/.results/Chapter_NN_review.md).
    """
    if results_dir is None:
        results_dir = ROOT / "prompts" / ".results"
    results_dir.mkdir(parents=True, exist_ok=True)

    block = _render_review_block(review_data)
    out_path = results_dir / f"Chapter_{chapter:02d}_review.md"
    out_path.write_text(block, encoding="utf-8")

    if also_write_chapter:
        cp = _chapter_path(chapter)
        if cp.exists():
            with cp.open("a", encoding="utf-8") as fh:
                fh.write(block)
            print(f"appended review to {cp}")
        else:
            print(f"WARN: {cp} not found; review written only to {out_path}")

    print(f"wrote review: {out_path}")
    return out_path


def _write_yaml_review_block(review_yaml: str) -> str:
    """Wrap a raw YAML review string in the HTML-comment fence.

    Used when the user pastes Claude's verbatim YAML output back via
    `python engine/writer.py review <N> --from-stdin`.
    """
    return _REVIEW_BLOCK_START + review_yaml.strip() + _REVIEW_BLOCK_END


if __name__ == "__main__":
    main()