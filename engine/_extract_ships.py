# -*- coding: utf-8 -*-
"""天黑之前 · 羁绊线抽取器（辅助 CLUES.md / CAST.md 更新）。

移植自旧魂 engine/_extract_ships.py（针对众魂 YAML frontmatter 设计），
已按天黑之前的需求改造：
  * 天黑之前章节无 frontmatter，改为扫正文提取羁绊线
  * 母题关键词驱动（心结 / 茶香 / 三年 / 代理人 / VII / 雨夜 / 问渠 / 老陈 等）
  * 输出 prompts/extract_ships_Chapter_NN.md 报告
  * ASCII 表格（grep / CI 友好）

用法：
    python engine/_extract_ships.py 14                    # 抽第 14 章（stdout）
    python engine/_extract_ships.py 14 --write            # 落盘到 prompts/
"""
import os
import sys
import json
import argparse
import re
from pathlib import Path
from collections import Counter, defaultdict

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))

from trace import load_cast_names, chapter_appearances
from prose_lint import body_of

CHAPTERS_DIR = ROOT / "chapters"
PROMPTS_DIR = ROOT / "prompts"
CAST_FILE = ROOT / "CAST.md"
CLUES_FILE = ROOT / "CLUES.md"

SHIP_KEYWORDS = [
    ("三年",     "心结 / 时间锚"),
    ("心结",     "角色未说出口的痛点"),
    ("茶香",     "顾星阑雨夜母题"),
    ("雨夜",     "三年前关键事件"),
    ("代理人",   "问渠先生网络特征"),
    ("VII",      "问渠先生签名符号"),
    ("问渠",     "大 Boss 暗线"),
    ("老陈",     "陈砚青 / 已灭口"),
    ("圆圈",     "另一套代理人网络"),
    ("旧石灰",   "周秉文遗留"),
    ("霍爷爷",   "霍渊白 / 大 Boss 明面"),
    ("监听器",   "鹰眼监听器"),
    ("代币",     "1987 港城公交代币"),
    ("签字",     "三年前除名签字"),
    ("涂黑",     "涂黑母题"),
    ("空白点",   "未出现 = 线索"),
    ("问渠先生", "大 Boss 代号"),
    ("上一级",   "林岳洲背后"),
    ("阁楼",     "轩宁侧写集场所"),
    ("刚好",     "顾星阑书店母题"),
    ("咖啡",     "轩宁日常伪装"),
    ("便利店",   "轩宁日常伪装场所"),
    ("大衣",     "轩宁标志性"),
    ("侧写集",   "轩宁标志性"),
    ("钢笔",     "轩宁标志性"),
    ("收音机",   "沈夜标志性"),
    ("对讲机",   "沈夜联络工具"),
    ("圆框眼镜", "顾星阑标志性"),
    ("橡木门",   "刚好书店门"),
    ("茶垢",     "顾星阑茶具"),
]


def _scan_chapter(n: int):
    p = CHAPTERS_DIR / f"Chapter_{n:02d}.md"
    if not p.exists():
        return None
    text = p.read_text(encoding="utf-8")
    return p, body_of(text), text


def _count_keyword_hits(body: str):
    """统计所有母题关键词在正文里的命中次数。"""
    hits = Counter()
    for kw, _desc in SHIP_KEYWORDS:
        c = body.count(kw)
        if c > 0:
            hits[kw] = c
    return hits

def _co_occurrence(names, body):
    co = defaultdict(int)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            positions_a = [m.start() for m in re.finditer(re.escape(a), body)]
            positions_b = [m.start() for m in re.finditer(re.escape(b), body)]
            for pa in positions_a:
                for pb in positions_b:
                    if abs(pa - pb) <= 500:
                        co[(a, b)] += 1
                        break
    return co


def _find_clue_alignment(body):
    alignments = []
    if "霍爷爷" in body or "霍渊白" in body:
        alignments.append("霍渊白登场：本章必须 100% 慈祥正派")
    if "三年前" in body:
        alignments.append("三年前时间锚出现：可能回收 M-1 / M-6 心结")
    if "代理人" in body:
        alignments.append("问渠先生代理人网络提及")
    if "VII" in body or "问渠先生" in body or "问渠" in body:
        alignments.append("问渠先生暗线符号出现（M-2 / M-8）")
    if "圆圈" in body:
        alignments.append("另一套代理人网络符号出现（M-5）")
    if "涂黑" in body:
        alignments.append("涂黑母题出现（M-4 长线钩子）")
    if "茶香" in body:
        alignments.append("茶香母题 = 顾星阑 / 三年前雨夜（M-3 长线）")
    return alignments


def extract(n):
    scan = _scan_chapter(n)
    if scan is None:
        return {"error": f"Chapter_{n:02d}.md not found"}
    path, body, _raw = scan
    names = load_cast_names()
    import soul as SOUL
    alias_to_main = {}
    if CAST_FILE.exists():
        cast = SOUL.load_cast_from_md(str(CAST_FILE))
        alias_to_main = {m["alias"]: n for n, m in cast.items() if m.get("alias")}
    apps = chapter_appearances(str(path), names)
    effective_apps = []
    for name, count in apps:
        main = alias_to_main.get(name, name)
        if main not in [a[0] for a in effective_apps]:
            effective_apps.append((main, count))
    kw_hits = _count_keyword_hits(body)
    co = _co_occurrence([a[0] for a in effective_apps], body)
    alignments = _find_clue_alignment(body)
    return {
        "chapter": n,
        "file": path.name,
        "appeared_cast": effective_apps,
        "keyword_hits": dict(kw_hits),
        "co_occurrence": {f"{a}+{b}": c for (a, b), c in co.items()},
        "clue_alignments": alignments,
        "body_chars": len(body),
    }

def _format_markdown(report):
    if "error" in report:
        return f"# 抽取失败\n\n{report['error']}\n"
    n = report["chapter"]
    lines = [
        f"# 第 {n} 章 · 羁绊线抽取报告",
        "",
        f"> **自动生成**：`engine/_extract_ships.py {n}`",
        f"> **源文件**：`{report['file']}`",
        f"> **正文字数**：{report['body_chars']} 字（按 prose_lint.body_of 口径）",
        "",
        "## 一、登场角色",
        "",
        "| 角色 | 出现次数 |",
        "|---|---:|",
    ]
    for name, count in report["appeared_cast"]:
        lines.append(f"| {name} | {count} |")
    lines += [
        "",
        "## 二、母题关键词命中",
        "",
        "| 关键词 | 含义 | 命中次数 |",
        "|---|---|---:|",
    ]
    desc_map = dict(SHIP_KEYWORDS)
    for kw, count in sorted(report["keyword_hits"].items(), key=lambda x: -x[1]):
        lines.append(f"| {kw} | {desc_map.get(kw, '-')} | {count} |")
    lines += [
        "",
        "## 三、角色共现（500 字窗口内同时出现）",
        "",
        "| 角色对 | 共现次数 |",
        "|---|---:|",
    ]
    co = report["co_occurrence"]
    if co:
        for pair, count in sorted(co.items(), key=lambda x: -x[1]):
            lines.append(f"| {pair} | {count} |")
    else:
        lines.append("| - | 0 |")
    lines += [
        "",
        "## 四、CLUES.md 对齐",
        "",
    ]
    for a in report["clue_alignments"]:
        lines.append(f"- {a}")
    lines += [
        "",
        "---",
        "",
        "> 本报告供 Cline 续写 / 人审时参考。",
        "> 1. 判断本章是否回收了已浮出的旧线索（CLUES_TRACKER.md 第 3 节）",
        "> 2. 判断本章是否引入新钩子（CLUES.md 需登记）",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(prog="_extract_ships.py", description=__doc__)
    parser.add_argument("chapter", type=int, help="章节号")
    parser.add_argument("--write", action="store_true", help="落盘到 prompts/")
    args = parser.parse_args()
    report = extract(args.chapter)
    md = _format_markdown(report)
    if args.write:
        PROMPTS_DIR.mkdir(exist_ok=True)
        out = PROMPTS_DIR / f"extract_ships_Chapter_{args.chapter:02d}.md"
        out.write_text(md, encoding="utf-8")
        print(f"[OK] {out}")
    else:
        print(md)


if __name__ == "__main__":
    main()
