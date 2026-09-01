# -*- coding: utf-8 -*-
"""天黑之前 · 角色缺席扫描。

移植自旧魂 tools/cast_absence_scan.py（针对众魂 frontmatter 设计），已按天黑之前
的需求改造：
  * 天黑之前章节无 frontmatter，改为调用 trace.chapter_appearances 扫正文登场角色
  * 三档阈值：
      - 核心班底：连续缺席 > 3 章 WARN
      - 大 Boss  ：连续缺席 > 10 章 WARN
      - 动态角色：连续缺席 > 8 章 WARN（一次性 / 阶段性配角天然会消失，阈值更宽）
  * 输出 ASCII 表格（grep / CI 友好）

用法：
    python tools/cast_absence_scan.py                       # 全量扫描
    python tools/cast_absence_scan.py --chapters 1 5 10     # 指定章节范围
    python tools/cast_absence_scan.py --json               # JSON 输出
"""
import os
import sys
import json
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))

from trace import load_cast_names, chapter_appearances

CHAPTERS_DIR = ROOT / "chapters"

# 缺席阈值（按 status 分档）
GAP_LIMITS = {
    "核心班底": 3,
    "大 Boss": 10,
    "动态角色": 8,
    "未分类": 5,
}


def _scan_chapters():
    """返回 [(chapter_num, path)] 列表，按章节号排序。"""
    out = []
    for p in sorted(CHAPTERS_DIR.glob("Chapter_*.md")):
        try:
            n = int(p.stem.split("_")[1])
        except (IndexError, ValueError):
            continue
        out.append((n, p))
    return out


def _load_cast_with_status():
    """从 CAST.md / characters/ 加载 {name: status}。"""
    import soul as SOUL
    CAST_FILE = ROOT / "CAST.md"
    CHARACTERS_DIR = ROOT / "characters"

    if CHARACTERS_DIR.exists() and any(CHARACTERS_DIR.glob("*.md")):
        result = {}
        for p in CHARACTERS_DIR.glob("*.md"):
            if p.name.startswith("_"):
                continue
            try:
                meta = SOUL.parse(str(p))
                if meta.get("name"):
                    result[meta["name"]] = meta.get("status", "未分类")
            except SOUL.SoulError:
                continue
        return result

    if not CAST_FILE.exists():
        return {}
    cast = SOUL.load_cast_from_md(str(CAST_FILE))
    return {n: m.get("status", "未分类") for n, m in cast.items()}


def _alias_to_main():
    """返回 {alias: main_name} 映射。"""
    import soul as SOUL
    CAST_FILE = ROOT / "CAST.md"
    if not CAST_FILE.exists():
        return {}
    cast = SOUL.load_cast_from_md(str(CAST_FILE))
    return {m["alias"]: n for n, m in cast.items() if m.get("alias")}


def scan(chapter_range=None):
    """主扫描逻辑。返回 list[dict]."""
    chapters = _scan_chapters()
    if chapter_range:
        chapters = [(n, p) for n, p in chapters if n in chapter_range]
    if not chapters:
        return []

    names = load_cast_names()
    cast_status = _load_cast_with_status()
    alias_to_main = _alias_to_main()

    # 把 alias 合并到主名（去重独立 alias 行）
    effective_names = [n for n in names if n not in alias_to_main]
    char_chapters = {n: set() for n in effective_names}
    char_last = {}
    for n, path in chapters:
        apps = chapter_appearances(str(path), names)
        for name, _count in apps:
            # alias → 主名
            main_name = alias_to_main.get(name, name)
            if main_name in char_chapters:
                char_chapters[main_name].add(n)
                char_last[main_name] = n

    results = []
    for name in effective_names:
        appeared = sorted(char_chapters[name])
        if not appeared:
            results.append({
                "name": name,
                "status": cast_status.get(name, "未分类"),
                "last_chapter": None,
                "longest_gap": 0,
                "total_appearances": 0,
                "warn": "从未登场",
            })
            continue

        latest = max(chapters, key=lambda x: x[0])[0]
        earliest = appeared[0]
        all_chs = set(n for n, _ in chapters if n >= earliest)
        gaps = []
        prev = None
        for ch in sorted(all_chs):
            if ch not in char_chapters[name]:
                if prev is None:
                    prev = ch
            else:
                if prev is not None:
                    gaps.append((prev, ch - 1))
                    prev = None
        if prev is not None:
            gaps.append((prev, latest))

        longest_gap = 0
        if gaps:
            longest_gap = max(end - start + 1 for start, end in gaps)

        limit = GAP_LIMITS.get(cast_status.get(name, "未分类"), 5)
        warn_msg = ""
        if longest_gap > limit:
            warn_msg = f"WARN-OVER-{limit}: gap={longest_gap}"

        results.append({
            "name": name,
            "status": cast_status.get(name, "未分类"),
            "last_chapter": char_last.get(name),
            "longest_gap": longest_gap,
            "total_appearances": len(appeared),
            "warn": warn_msg,
        })

    status_priority = {"核心班底": 0, "大 Boss": 1, "动态角色": 2, "未分类": 3}
    results.sort(key=lambda r: (status_priority.get(r["status"], 99), -(r["last_chapter"] or 0)))
    return results


def _print_table(results):
    print(f"{'NAME':<10} {'STATUS':<10} {'LAST':<6} {'GAP':<4} {'APPS':<5} WARN")
    print("-" * 60)
    for r in results:
        last = r["last_chapter"] if r["last_chapter"] is not None else "-"
        print(f"{r['name']:<10} {r['status']:<10} ch{last:<4} {r['longest_gap']:<4} {r['total_appearances']:<5} {r['warn']}")


def main():
    parser = argparse.ArgumentParser(
        prog="cast_absence_scan.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--chapters", type=int, nargs="*")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    chapter_range = set(args.chapters) if args.chapters else None
    results = scan(chapter_range)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        scope = f"chapters {sorted(chapter_range)}" if chapter_range else f"all {len(_scan_chapters())} chapters"
        print(f"=== Cast absence scan ({scope}) ===")
        _print_table(results)

        warns = [r for r in results if r["warn"]]
        if warns:
            print(f"\n[FAIL] {len(warns)} role(s) exceed absence threshold")
            for w in warns:
                print(f"  - {w['name']} ({w['status']}): {w['warn']}")
            return 1
        print("\n[OK] all roles within absence threshold")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())