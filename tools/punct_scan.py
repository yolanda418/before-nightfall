# -*- coding: utf-8 -*-
"""天黑之前 · 中文标点规范化扫描器（只检测不修改）。

移植自旧魂 engine/punct_normalize.py 的核心检测逻辑，已按天黑之前的需求改造：
  * 不直接修改章节正文（§11.4 硬约束：Cline 不许未经明确指令修改 chapter 文件）
  * 只扫描 + 报告 + 给出修复建议
  * 区分"应当全角"的标点 vs"剧情必需的半角"（如章节号、英文名、数字 + 单位）
  * 输出 ASCII 表格（grep / CI 友好）

用法：
    python tools/punct_scan.py                          # 全部章节
    python tools/punct_scan.py --chapters 1 5 10        # 指定章节
    python tools/punct_scan.py --json                  # JSON 输出
    python tools/punct_scan.py --write                 # 写到 prompts/punct_scan.md
"""
import os
import sys
import json
import argparse
import re
from pathlib import Path
from collections import Counter as Cnt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))

from prose_lint import body_of

CHAPTERS_DIR = ROOT / "chapters"
PROMPTS_DIR = ROOT / "prompts"

# JJWXC 标准：中文正文里所有标点都应是全角
SIMPLE_MAP = [
    ("...", "……"),
    (",", "，"),
    (";", "；"),
    (":", "："),
    ("!", "！"),
    ("?", "？"),
    ("(", "（"),
    (")", "）"),
]


def _is_safe_to_fix(src, ctx_before, ctx_after):
    if "Chapter_" in ctx_before[-20:] or "Chapter_" in ctx_after[:20]:
        return False
    if ctx_before and ctx_before[-1].isascii() and ctx_before[-1].isalnum():
        if ctx_after and ctx_after[0].isascii() and ctx_after[0].isalnum():
            return False
    return True

def scan_chapter(n):
    p = CHAPTERS_DIR / f"Chapter_{n:02d}.md"
    if not p.exists():
        return {"error": f"Chapter_{n:02d}.md not found"}
    body = body_of(p.read_text(encoding="utf-8"))
    lines = body.splitlines()
    violations = []

    for line_no, line in enumerate(lines, start=1):
        if line.lstrip().startswith(">") or "ASCII" in line:
            continue
        if line.strip() == "---":
            continue
        for src, dst in SIMPLE_MAP:
            idx = 0
            while True:
                idx = line.find(src, idx)
                if idx == -1:
                    break
                ctx_before = line[max(0, idx - 30):idx]
                ctx_after = line[idx + len(src):idx + len(src) + 30]
                safe = _is_safe_to_fix(src, ctx_before, ctx_after)
                violations.append({
                    "src": src, "dst": dst, "line_no": line_no,
                    "context_before": ctx_before[-15:] if len(ctx_before) > 15 else ctx_before,
                    "context_after": ctx_after[:15] if len(ctx_after) > 15 else ctx_after,
                    "safe_to_fix": safe,
                })
                idx += len(src)

    LINE_BREAK = re.compile(r"^[ \t]*---[ \t]*$")
    INLINE_DOUBLE_DASH = re.compile(r"(?<![—])(--)(?![—])")
    for line_no, line in enumerate(lines, start=1):
        if LINE_BREAK.match(line):
            continue
        for m in INLINE_DOUBLE_DASH.finditer(line):
            i = m.start()
            prev = line[i - 1] if i > 0 else ""
            nxt = line[i + 2] if i + 2 < len(line) else ""
            if prev.isascii() and prev.isalpha() and nxt.isascii() and nxt.isalpha():
                continue
            violations.append({
                "src": "--", "dst": "——", "line_no": line_no,
                "context_before": line[max(0, i - 15):i],
                "context_after": line[i + 2:i + 17],
                "safe_to_fix": True,
            })

    return {
        "chapter": n, "file": p.name, "body_chars": len(body),
        "violations": violations, "violation_count": len(violations),
    }

def _print_table(results):
    print(f"{'CHAPTER':<10} {'BODY':<6} {'VIOLATIONS':<12}")
    print("-" * 40)
    for r in results:
        if "error" in r:
            print(f"ch{r['chapter']:<8} ERROR: {r['error']}")
            continue
        print(f"ch{r['chapter']:<8} {r['body_chars']:<6} {r['violation_count']:<12}")


def main():
    parser = argparse.ArgumentParser(prog="punct_scan.py", description=__doc__)
    parser.add_argument("--chapters", type=int, nargs="*")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    if args.chapters:
        chapters = args.chapters
    else:
        chapters = sorted([
            int(p.stem.split("_")[1])
            for p in CHAPTERS_DIR.glob("Chapter_*.md")
            if p.stem.split("_")[1].isdigit()
        ])

    results = [scan_chapter(n) for n in chapters]

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    print(f"=== Punctuation scan ({len(chapters)} chapters) ===")
    _print_table(results)

    total = sum(r.get("violation_count", 0) for r in results if "error" not in r)
    safe = sum(
        1 for r in results if "error" not in r
        for v in r["violations"] if v["safe_to_fix"]
    )
    unsafe = total - safe

    print(f"\n  total={total}  safe_to_fix={safe}  unsafe={unsafe}")

    if total > 0:
        print("\n=== Violation sources (top) ===")
        src_counts = Cnt(
            v["src"] for r in results if "error" not in r
            for v in r["violations"]
        )
        for src, count in src_counts.most_common():
            print(f"  {src!r:<5} x {count}")

    if args.write:
        PROMPTS_DIR.mkdir(exist_ok=True)
        out = PROMPTS_DIR / "punct_scan.md"
        lines = ["# Punctuation scan report\n"]
        lines.append(f"> auto-generated: tools/punct_scan.py --write")
        lines.append(f"> scanned: {len(chapters)} chapters\n")
        lines.append("\n## per chapter\n")
        lines.append("| ch | body chars | violations |\n|---|---:|---:|")
        for r in results:
            if "error" in r:
                lines.append(f"| ch{r['chapter']} | - | ERROR |")
            else:
                lines.append(f"| ch{r['chapter']} | {r['body_chars']} | {r['violation_count']} |")

        lines.append("\n## detail\n")
        for r in results:
            if "error" in r or r["violations"] == []:
                continue
            lines.append(f"\n### Chapter_{r['chapter']:02d} ({r['violation_count']} violations)\n")
            for v in r["violations"][:50]:
                safe_mark = "OK" if v["safe_to_fix"] else "X"
                lines.append(f"- L{v['line_no']:>3} {v['src']!r} -> {v['dst']!r} [{safe_mark}]")

        lines.append("\n## fix guide\n")
        lines.append("- [OK] safe to auto-fix when editing chapter manually")
        lines.append("- [X] may be English name / unit / file reference, keep half-width")
        out.write_text("\n".join(lines), encoding="utf-8")
        print(f"\n[OK] {out}")


if __name__ == "__main__":
    main()