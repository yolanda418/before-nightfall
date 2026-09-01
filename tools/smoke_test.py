# -*- coding: utf-8 -*-
"""天黑之前 · 工具链 smoke test。

逐一验证已移植的工具是否能正常 import / 运行，输出 ASCII-only 结果（避开 PowerShell 中文乱码）。
"""
import sys
import os
import traceback
from pathlib import Path

# 自动定位项目根：smoke_test.py 在 tools/ 下，根就是父目录
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT / 'engine'))

OUT_FILE = Path(r'C:\Users\ENFANT\AppData\Local\Temp\smoke_result.txt')

results = []

def test(name, fn):
    try:
        msg = fn()
        results.append((True, name, msg or ""))
    except Exception as e:
        tb = traceback.format_exc().splitlines()[-1]
        results.append((False, name, f"{type(e).__name__}: {tb}"))

# ---- 1. prose_lint ----
def t_prose_lint():
    from prose_lint import lint_file, body_of, measure, lint_text
    from pathlib import Path
    chapters = sorted(Path(os.path.join(ROOT, 'chapters')).glob('Chapter_*.md'))
    if not chapters:
        return f"NO chapters found"
    n_pass = n_err = 0
    total_chars = 0
    for p in chapters:
        errors, warns, m = lint_file(str(p))
        total_chars += m['chars']
        if errors:
            n_err += 1
        else:
            n_pass += 1
    return f"{len(chapters)} chapters, {n_pass} PASS, {n_err} ERROR, {total_chars} total chars"
test("prose_lint.py", t_prose_lint)

# ---- 2. safety_lint ----
def t_safety_lint():
    from safety_lint import check
    sample = "轩宁蹲在仓库门口。左手捏着烟蒂。霍爷爷在客厅泡茶。"
    issues = check(sample)
    return f"clean sample: {len(issues)} issues (expected 0)"
test("safety_lint.py", t_safety_lint)

# ---- 3. soul ----
def t_soul():
    from soul import load_cast, parse, validate
    cast = load_cast(os.path.join(ROOT, 'characters'))
    return f"loaded {len(cast)} characters"
test("soul.py", t_soul)

# ---- 4. season ----
def t_season():
    from season import load_arc, beat_line, load_ties
    arc = load_arc(ROOT)
    return f"main_beat={arc['main_case']['beat']+1}/{len(arc['main_case']['beats'])}, side_cases={len(arc['side_cases'])}"
test("season.py", t_season)

# ---- 5. trace ----
def t_trace():
    from trace import chapter_appearances, chapter_metrics
    from pathlib import Path
    chapters = sorted(Path(os.path.join(ROOT, 'chapters')).glob('Chapter_*.md'))
    if not chapters:
        return f"NO chapters found"
    p = chapters[0]
    apps = chapter_appearances(str(p), ['轩宁', '沈夜', '霍渊白'])
    m = chapter_metrics(str(p))
    return f"{p.name}: {m['chars']} chars, {len(apps)} cast found"
test("trace.py", t_trace)

# ---- 6. cast ----
def t_cast():
    import cast as CAST
    n = len(CAST._load_all())
    return f"loaded {n} characters via cast._load_all()"
test("cast.py", t_cast)

# ---- 7. validate ----
def t_validate():
    from validate import validate_all
    passed, failed = validate_all()
    return f"{len(passed)} passed, {len(failed)} failed"
test("validate.py", t_validate)

# ---- 8. writer (brief only, no file output) ----
def t_writer_brief():
    from writer import brief
    # 用第 14 章做测试（即使不存在也只影响最近章节列表）
    data = brief(14)
    return f"brief OK, {len(data)} chars JSON"
test("writer.py brief()", t_writer_brief)

# ---- 输出 ----
lines = []
lines.append("=" * 70)
lines.append("SMOKE TEST RESULTS")
lines.append("=" * 70)
n_ok = 0
n_fail = 0
for ok, name, msg in results:
    flag = "PASS" if ok else "FAIL"
    if ok:
        n_ok += 1
    else:
        n_fail += 1
    lines.append(f"  [{flag}] {name:30s} {msg}")
lines.append("=" * 70)
lines.append(f"TOTAL: {n_ok} pass, {n_fail} fail")

text = "\n".join(lines)
with open(OUT_FILE, "w", encoding="utf-8") as fh:
    fh.write(text)
sys.exit(0 if n_fail == 0 else 1)