# -*- coding: utf-8 -*-
"""天黑之前 · 每章定稿后自动追踪器。

移植自旧魂 engine/trace.py 的核心思路（"有迹可循"），已按天黑之前的需求简化：

  · 不依赖章节 frontmatter（旧魂用 chronicle.json 喂 trace.py；天黑之前章节结构简单）
  · 不写 characters/<name>/dossier.md（天黑之前是单文件角色卡，状态写在 current_state 段）
  · 三个核心子任务：
      1. 统计每章出场角色频次（基于 CAST.md 名册扫正文）
      2. 校验"副线案核心涉案人物 ≤ 3"硬规则
      3. 把章节字数 / 状态写到 _chapter_status.csv（可被 _chapter_stats.ps1 替代或并存）

用法：
    python engine/trace.py                    # 全量追踪
    python engine/trace.py --chapter Chapter_05.md   # 只追一章
"""
import os
import sys
import re
import csv
import glob
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))

import soul as SOUL
from prose_lint import body_of, measure


CHAPTERS_DIR = ROOT / "chapters"
CHARACTERS_DIR = ROOT / "characters"
CAST_FILE = ROOT / "CAST.md"


def load_cast_names():
    """加载角色名清单。

    路径选择（与 soul.load_cast 保持一致）：
      - 若 characters/ 目录存在且非空，走旧 frontmatter 路径
      - 否则走 CAST.md 新路径

    返回 list[str]（角色名）+ 别名（陈砚青 / 老陈 双名都返回，扫正文更稳）
    """
    # 旧路径：characters/*.md
    if CHARACTERS_DIR.exists() and any(CHARACTERS_DIR.glob("*.md")):
        names = []
        for p in sorted(CHARACTERS_DIR.glob("*.md")):
            if p.name.startswith("_"):
                continue
            try:
                meta = SOUL.parse(str(p))
                if meta.get("name"):
                    names.append(meta["name"])
            except SOUL.SoulError:
                continue
        return names

    # 新路径：CAST.md
    if not CAST_FILE.exists():
        return []
    cast = SOUL.load_cast_from_md(str(CAST_FILE))
    names = []
    for name, meta in cast.items():
        names.append(name)
        if meta.get("alias"):
            names.append(meta["alias"])
    return names


def chapter_appearances(chapter_path, cast_names):
    """扫一章正文，统计每个角色是否出现（基于姓名全名匹配）。

    返回 list[(name, count)]，按出现次数降序。
    """
    text = open(chapter_path, encoding="utf-8").read()
    body = body_of(text)
    appearances = []
    for name in cast_names:
        if len(name) < 2:    # 跳过单字（避免误判）
            continue
        count = body.count(name)
        if count > 0:
            appearances.append((name, count))
    return sorted(appearances, key=lambda x: -x[1])


def chapter_metrics(chapter_path):
    """返回单章的所有度量值（复用 prose_lint.measure）。"""
    text = open(chapter_path, encoding="utf-8").read()
    body = body_of(text)
    return measure(body)


def check_side_case_quota(chapter_path, cast_meta):
    """校验"副线案核心涉案人物 ≤ 3"硬规则。

    逻辑：扫章节正文里出现的所有角色，若其中标 status="副线案核心" 的角色
    数量 > 3，报警（CLUES_TRACKER.md 第 4 节硬规则）。
    """
    apps = chapter_appearances(chapter_path, list(cast_meta.keys()))
    side_core_present = [n for n, _ in apps if cast_meta.get(n, {}).get("status") == "副线案核心"]
    return side_core_present, len(side_core_present) > 3


def update_cast_appearances():
    """扫所有章节，统计每个角色的总出场次数，写入 CAST.md 顶部的统计段。

    CAST.md 现有结构是手工维护的；本函数追加/刷新一个
    `<!-- trace:auto -->` 注释块，便于人肉复核，不破坏手写内容。
    """
    if not CAST_FILE.exists():
        return False
    names = load_cast_names()
    counts = {n: 0 for n in names}

    for ch in sorted(CHAPTERS_DIR.glob("Chapter_*.md")):
        apps = chapter_appearances(str(ch), names)
        for n, c in apps:
            counts[n] = counts.get(n, 0) + c

    # 渲染新统计块
    sorted_counts = sorted(counts.items(), key=lambda x: -x[1])
    lines = ["<!-- trace:auto -->", "## 自动追踪 · 角色出场统计", ""]
    lines.append("| 角色 | 出场次数 |")
    lines.append("|---|---:|")
    for n, c in sorted_counts:
        if c > 0:
            lines.append(f"| {n} | {c} |")
    lines.append("")
    lines.append("<!-- /trace:auto -->")

    new_block = "\n".join(lines)

    # 替换旧块（如果存在）或追加
    text = CAST_FILE.read_text(encoding="utf-8")
    if "<!-- trace:auto -->" in text:
        text = re.sub(
            r"<!-- trace:auto -->.*?<!-- /trace:auto -->\n*",
            new_block + "\n\n",
            text,
            flags=re.S,
        )
    else:
        # 追加到末尾
        text = text.rstrip() + "\n\n" + new_block + "\n"

    CAST_FILE.write_text(text, encoding="utf-8")
    return True


def write_chapter_status_csv():
    """把每章的字数 / 视角 / 出场角色写到 _chapter_status.csv。"""
    csv_path = CHAPTERS_DIR / "_chapter_status.csv"
    cast_names = load_cast_names()

    rows = []
    rows.append(["chapter", "pure_chars", "micro", "avg", "dash_max", "n_cast"])
    for ch in sorted(CHAPTERS_DIR.glob("Chapter_*.md")):
        m = chapter_metrics(str(ch))
        apps = chapter_appearances(str(ch), cast_names)
        rows.append([
            ch.name,
            m["chars"],
            f"{m['micro']:.3f}",
            f"{m['avg']:.2f}",
            m["dash_max"],
            len(apps),
        ])

    with open(csv_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerows(rows)
    return csv_path


def main():
    args = sys.argv[1:]
    if "--chapter" in args:
        idx = args.index("--chapter")
        target = args[idx + 1]
        ch_path = CHAPTERS_DIR / target
        if not ch_path.exists():
            print(f"✗ {target} 不存在")
            sys.exit(1)
        names = load_cast_names()
        apps = chapter_appearances(str(ch_path), names)
        m = chapter_metrics(str(ch_path))
        print(f"📖 {target}")
        print(f"  纯字: {m['chars']}, 微碎片率: {m['micro']:.2%}, 平均段长: {m['avg']:.2f}")
        print(f"  出场角色 ({len(apps)}):")
        for n, c in apps:
            print(f"    - {n} × {c}")

        # 副线案 3 人规则
        # 路径选择：若 characters/ 存在，按 frontmatter 加载；否则从 CAST.md 取
        cast_meta = {}
        if CHARACTERS_DIR.exists() and any(CHARACTERS_DIR.glob("*.md")):
            for n in names:
                for p in CHARACTERS_DIR.glob("*.md"):
                    if p.name.startswith("_"):
                        continue
                    try:
                        meta = SOUL.parse(str(p))
                        if meta.get("name") == n:
                            cast_meta[n] = meta
                            break
                    except SOUL.SoulError:
                        continue
        elif CAST_FILE.exists():
            cast_meta = SOUL.load_cast_from_md(str(CAST_FILE))
        side_core, over = check_side_case_quota(str(ch_path), cast_meta)
        if over:
            print(f"  ⚠ 副线案核心涉案人物 > 3 规则违反：{side_core}")
        return

    print("📚 全量追踪 ...")
    csv_path = write_chapter_status_csv()
    print(f"  ✓ 章节状态表写入 {csv_path.name}")
    if update_cast_appearances():
        print(f"  ✓ CAST.md 出场统计刷新")
    else:
        print(f"  ⚠ CAST.md 不存在，跳过出场统计")


if __name__ == "__main__":
    main()