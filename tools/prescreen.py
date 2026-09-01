# -*- coding: utf-8 -*-
"""天黑之前 · 全章 AI 通病预检 (Python 版).

移植自旧魂《众魂》open-souls 的 tools/prescreen.sh，已按天黑之前的需求改造：
  · 路径：Chapter_NN.md（不是 ch001-标题.md）
  · 字数：v3.1 [1800, 2200]
  · 检测 8 大 AI 通病 + 4.13 节终极禁令 + 4.5 节精确数字 + 4.6 节术语禁令
  · 输出 ASCII-only，方便 grep / CI 解析

用法：
    python tools/prescreen.py              # 扫全部
    python tools/prescreen.py 5 7 12       # 只扫指定章
    python tools/prescreen.py --json       # 输出 JSON
"""
import sys
import os
import re
import json
import glob
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHAPTERS_DIR = ROOT / "chapters"

# ---- v3.1 阈值 ----
MIN_CHARS = 1800
TARGET_CHARS = 2200

# ---- 正则（AI 通病 / 4.13 终极禁令 / 4.5 精确数字 / 4.6 术语） ----
AI_CONNECTOR = r"只见|只见他|就在这时|片刻后|随即|于是|因此|不由得|不禁|似乎|仿佛|好像|似乎是|仿佛是"
AI_FILLER_ADV = r"非常|极其|格外|稍稍|默默"
AI_HIGHFREQ = r"眼眸|唇角|身形|骤然"
NEG_CONTRAST = r"没有[^。！？\n]{0,15}没有|不是[^。！？\n]{0,15}而是|并非[^。！？\n]{0,15}而是|没有[^。！？\n]{0,15}只是"
WEAK_TRANS = r"虽然[^。！？\n]{0,15}但是|尽管[^。！？\n]{0,15}却|甚至[^。！？\n]{0,15}没有"
ONE_ACTION = r"[她他][^。！？\n]{0,6}[了着过][^。！？\n]{0,6}[。！？]"
GOD_VIEW = r"读者们都知道|所有人都知道|事实上|原来[一-鿿]{0,8}(?:一直|早就|从来)"
BANNED_TERMS = r"罪己侧写|签名行为|场依存性|防御性创伤|移情|Overkill"
TEMPLATE_VERB = r"[一-鿿]{1,4}(?:[一-鿿]{0,2})?(?:地说|说着|看向|看着|望着|走过去|走开|问道|问)"
UNREASONABLE_NUM = r"(?:零点[零一二三四五六七八九]+分?|[一二三四五六七八九十百]+点[零一二三四五六七八九]+分|精确到[零一二三四五六七八九]+位|分秒不差)"


def body_of(text: str) -> str:
    """Extract chapter body (from "## 二" line to next "---" separator)."""
    if text.startswith("\ufeff"):
        text = text[1:]
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    prefix = "## " + chr(0x4E8C)
    start = -1
    end = len(lines)
    for i, line in enumerate(lines):
        t = line.strip()
        if start < 0 and t.startswith(prefix):
            start = i + 1
            continue
        if start >= 0 and t == "---":
            end = i
            break
    if start < 0:
        return text
    if end <= start:
        return ""
    return "\n".join(lines[start:end])


def count_pure(text: str) -> int:
    """Count CJK ideographs + ASCII letters/digits (the 'pure' chars)."""
    return sum(1 for c in text if re.match(r"[\u4e00-\u9fff\u3400-\u4dbfA-Za-z0-9]", c))


def measure(body: str) -> dict:
    """Return all hit counts for one chapter body."""
    return {
        "ai_connector": len(re.findall(AI_CONNECTOR, body)),
        "ai_filler_adv": len(re.findall(AI_FILLER_ADV, body)),
        "ai_highfreq": len(re.findall(AI_HIGHFREQ, body)),
        "neg_contrast": len(re.findall(NEG_CONTRAST, body)),
        "weak_trans": len(re.findall(WEAK_TRANS, body)),
        "god_view": len(re.findall(GOD_VIEW, body)),
        "banned_terms": len(re.findall(BANNED_TERMS, body)),
        "template_verb": len(re.findall(TEMPLATE_VERB, body)),
        "unreasonable_num": len(re.findall(UNREASONABLE_NUM, body)),
    }


def main():
    args = sys.argv[1:]
    json_out = "--json" in args
    chapters = [a for a in args if not a.startswith("-")]

    if chapters:
        files = []
        for c in chapters:
            n = int(c)
            p = CHAPTERS_DIR / f"Chapter_{n:02d}.md"
            if p.exists():
                files.append(p)
            else:
                print(f"WARN: {p.name} not found")
    else:
        files = sorted(CHAPTERS_DIR.glob("Chapter_*.md"))

    if not files:
        print("ERROR: no chapters found")
        sys.exit(1)

    results = []
    for f in files:
        text = f.read_text(encoding="utf-8")
        body = body_of(text)
        pure = count_pure(body)
        m = measure(body)

        char_status = "OK"
        if pure < MIN_CHARS:
            char_status = "UNDER"
        elif pure > TARGET_CHARS:
            char_status = "OVER"

        verdict = "OK "
        if char_status != "OK":
            verdict = "OUT"
        if m["god_view"] > 0 or m["neg_contrast"] > 0:
            verdict = "FAIL"

        r = {
            "file": f.name,
            "pure_chars": pure,
            "char_status": char_status,
            "verdict": verdict,
            **m,
        }
        results.append(r)

        if not json_out:
            print(f"[{verdict}] {f.name}  pure={pure} ({char_status})")
            hits = []
            for k, v in m.items():
                if v > 0:
                    hits.append(f"{k}={v}")
            if char_status != "OK":
                hits.insert(0, f"target [{MIN_CHARS}, {TARGET_CHARS}]")
            if hits:
                print(f"    {', '.join(hits)}")
            print()

    if json_out:
        print(json.dumps(results, ensure_ascii=False, indent=2))

    print(f"Total: {len(results)} chapters scanned")


if __name__ == "__main__":
    main()