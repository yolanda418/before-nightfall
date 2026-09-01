# -*- coding: utf-8 -*-
"""Tianhei Zhiqian · Run publication gates only for changed files in a Git push.

移植自旧魂《众魂》open-souls 的 tools/validate_changed.py，已按天黑之前的项目结构改造：

    · 章节路径：chapters/Chapter_NN.md（NN 两位补零；不是 seasons/01-xianxia/chronicle/ch001-*.md）
    · 字数阈值：v3.1 [1800, 2200]（沿用 .clinerules 第 4.2 节）
    · 门禁脚本：
        - engine/prose_lint.py             （天黑之前版 · 8 大 AI 通病 + 视角 + 物象）
        - engine/safety_lint.py            （天黑之前版 · 露骨 / 自伤 / 14 岁以下暧昧）
        - tools/check_chapter_quality.ps1  （天黑之前独有 · v3.1 字数 + 8 大通病 + 安全）
        - tools/prescreen.py               （天黑之前独有 · 8 大通病预检）
    · 输出：ASCII-only，方便 CI 解析 + 避开 PowerShell 中文乱码
    · 全量开关：TIANHEI_FULL_PUSH=1 或 --full

设计原则：
    · 普通 commit → 只跑改动的章节（快门）
    · 共享门代码改动 → 自动拒绝，要求显式 --full（全量门）
    · 永远不修改 git 状态；只读

用法::

    # 1. 默认：跑 HEAD~1..HEAD 之间改动的所有 chapters/Chapter_*.md
    python tools/validate_changed.py --base HEAD~1 --head HEAD

    # 2. 显式指定路径（绕过 git diff；CI 场景常用）
    python tools/validate_changed.py --paths chapters/Chapter_05.md chapters/Chapter_06.md

    # 3. 强制全量（门规则或共享代码改动时）
    TIANHEI_FULL_PUSH=1 python tools/validate_changed.py --base origin/main --head HEAD
    python tools/validate_changed.py --full --base HEAD~1 --head HEAD

    # 4. 单文件快速验证（不查 git）
    python tools/validate_changed.py --paths chapters/Chapter_05.md

退出码：
    0 = pass
    1 = gate failure（某个章节没过门；push 应该被阻止）
    2 = shared gate code 改动（必须显式 --full）
    3 = git error（无法获取改动列表）

注：本文件**不**安装为 Git hook。
    如需接入 pre-push 工作流，请手动：
        cp tools/validate_changed.py .git/hooks/pre-push && chmod +x .git/hooks/pre-push
    或在 .git/hooks/pre-push 里调：
        python tools/validate_changed.py --base $remote_sha --head $local_sha
    本脚本默认不绑定任何 Git 事件，纯按需手动运行。
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


# Force UTF-8 stdout/stderr so subprocess Chinese error messages don't crash on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


ROOT = Path(__file__).resolve().parent.parent
CHAPTERS_DIRNAME = "chapters"
CHAPTER_PREFIX = CHAPTERS_DIRNAME + "/"

# ---- 共享门文件：改这些文件 → 必须显式 --full ----
# 改任何「判定规则」或「schema」时，跑全量而不是只看改动章节
# 这样能防止「只改了规则但没跑全量，旧章节突然过不了门」的盲区
SHARED_GATE_FILES = {
    # engine/ · 核心 lint / 安全 / schema
    "engine/prose_lint.py",
    "engine/safety_lint.py",
    "engine/soul.py",
    "engine/season.py",
    "engine/trace.py",
    # tools/ · 项目级门脚本
    "tools/check_chapter_quality.ps1",
    "tools/prescreen.py",
    "tools/chapter_stats.ps1",
    "tools/validate_changed.py",   # 自身改了也算（防 meta-edit 漏洞）
    # 顶层规范
    ".clinerules",
}

# Chapter file name pattern (used by _chapter_paths)
_CHAPTER_FILENAME_RE = re.compile(r"^Chapter_\d{2}\.md$")


def _powershell_exe() -> list[str]:
    """Return the command prefix to invoke PowerShell on this OS.

    PS 5.1 has a known bug parsing UTF-8 files without BOM. We avoid that
    pitfall by keeping PS command lines short (no embedded file content)
    and passing chapter paths via -Chapter (an integer) rather than a path.
    """
    if sys.platform.startswith("win"):
        return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass"]
    return ["pwsh", "-NoProfile"]


def _run(command: list[str]) -> int:
    """Run a command in the project root. Print it for traceability. Return exit code.

    Echo uses ASCII-safe rendering so console encoding can't break the trace.
    The actual subprocess still receives the original (possibly non-ASCII) args.

    Sets PYTHONIOENCODING=utf-8 on subprocess Python invocations and forces
    PowerShell to use UTF-8 output. This avoids the GBK codec crash on
    downstream scripts that print CJK / box-drawing characters (e.g.
    safety_lint.py prints '✓' on success).
    """
    print("$ " + " ".join(_ascii_safe(c) for c in command), flush=True)

    # Build env: copy current env, force UTF-8 for child Python / PS
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    # For PowerShell, force OEM code page to UTF-8 (65001)
    if command and command[0].lower().endswith(("powershell.exe", "pwsh")):
        env["PS_DEFAULT_OUTPUT_ENCODING"] = "utf-8"

    completed = subprocess.run(
        command,
        cwd=str(ROOT),
        env=env,
        check=False,
    )
    return completed.returncode


def _ascii_safe(s: str) -> str:
    """Replace non-ASCII bytes in echoes so the trace stays readable everywhere."""
    return s.encode("ascii", errors="replace").decode("ascii")


# =============================================================================
# Gate runners (one per script we shell out to)
# =============================================================================

def _gate_prose_lint(chapter_abs: Path) -> int:
    """Run prose_lint.py --strict-editorial on a single chapter file.

    --strict-editorial matches the push-gate strict mode (catches self-claim
    + motif-slot loops per .clinerules 4.13).
    """
    rel = chapter_abs.relative_to(ROOT).as_posix()
    return _run([sys.executable, "engine/prose_lint.py", "--strict-editorial", rel])


def _gate_safety_lint(chapter_abs: Path) -> int:
    """Run safety_lint.py on a single chapter file."""
    rel = chapter_abs.relative_to(ROOT).as_posix()
    return _run([sys.executable, "engine/safety_lint.py", rel])


def _gate_check_quality(chapter_abs: Path) -> int:
    """Run check_chapter_quality.ps1 on a single chapter.

    We extract the chapter number from the filename and pass it via -Chapter
    so the PS1 script only scans that one chapter. Passing an integer
    (rather than a UTF-8 path) sidesteps the PS 5.1 no-BOM UTF-8 bug.
    """
    stem = chapter_abs.stem  # 'Chapter_05'
    if not stem.startswith("Chapter_"):
        print(f"WARN: cannot parse chapter number from {chapter_abs.name}; skipping PS1 gate")
        return 0
    n_str = stem[len("Chapter_"):]
    try:
        n = int(n_str)
    except ValueError:
        print(f"WARN: cannot parse chapter number from {chapter_abs.name}; skipping PS1 gate")
        return 0

    ps_cmd = _powershell_exe() + ["-File", "tools/check_chapter_quality.ps1", "-Chapter", str(n)]
    return _run(ps_cmd)


def _gate_full_audit() -> int:
    """Full audit: every chapter via each tool. Required when shared gate files change."""
    print("Full publication audit requested.")
    cmds = [
        # prose_lint on every chapter (no arg = all)
        [sys.executable, "engine/prose_lint.py", "--strict-editorial"],
        # prescreen.py on every chapter (no arg = all)
        [sys.executable, "tools/prescreen.py"],
        # check_chapter_quality.ps1 on every chapter (no arg = all)
        _powershell_exe() + ["-File", "tools/check_chapter_quality.ps1"],
    ]
    for cmd in cmds:
        if _run(cmd):
            return 1
    return 0


# =============================================================================
# Git diff helpers
# =============================================================================

def _changed_paths(base: str, head: str) -> list[str]:
    """List files changed between two git refs. Forward-slash normalized."""
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMRTUXB", base, head, "--"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode:
        print(result.stderr.strip() or "git diff failed", file=sys.stderr)
        return []
    return sorted({
        line.strip().replace("\\", "/")
        for line in result.stdout.splitlines()
        if line.strip()
    })


def _normalise_paths(paths: list[str]) -> list[str]:
    """Resolve user-supplied paths to repo-relative POSIX paths.

    Out-of-repo paths are silently dropped (they can't be gated).
    """
    output = []
    for value in paths:
        path = Path(value)
        if not path.is_absolute():
            path = ROOT / path
        try:
            relative = path.resolve().relative_to(ROOT.resolve()).as_posix()
        except ValueError:
            continue
        output.append(relative)
    return sorted(set(output))


def _chapter_paths(paths: list[str]) -> list[str]:
    """Filter repo-relative paths to actual chapter files in chapters/.

    Match: chapters/Chapter_NN.md (NN is exactly two digits).
    Don't be greedy: ignore files like chapters/INDEX.md or subfolders.
    """
    return [
        path for path in paths
        if path.startswith(CHAPTER_PREFIX)
        and _CHAPTER_FILENAME_RE.match(path[len(CHAPTER_PREFIX):])
        and Path(ROOT / path).is_file()
    ]


# =============================================================================
# Main validate entry
# =============================================================================

def validate(paths: list[str], *, force_full: bool = False) -> int:
    paths = _normalise_paths(paths)

    # ---- 1. Full audit (shared gate change or explicit --full) ----
    if force_full or os.environ.get("TIANHEI_FULL_PUSH") == "1":
        return _gate_full_audit()

    # ---- 2. Shared gate code changed → refuse, require explicit --full ----
    shared_changes = [p for p in paths if p in SHARED_GATE_FILES]
    if shared_changes:
        print(
            "Shared gate code changed; run the full audit explicitly.",
            file=sys.stderr,
        )
        for p in shared_changes:
            print(f"  - {p}", file=sys.stderr)
        print(
            "Re-run with TIANHEI_FULL_PUSH=1 or pass --full.",
            file=sys.stderr,
        )
        return 2

    # ---- 3. Chapter changes → run three gates per changed chapter ----
    chapters = _chapter_paths(paths)
    if not chapters:
        print("No chapter files changed; chapter publication gates skipped.")
        return 0

    print(f"Changed-chapter publication gate: {len(chapters)} file(s)")
    for rel in chapters:
        chapter_abs = (ROOT / rel).resolve()
        print(f"\n--- {rel} ---")

        # Order matters: hard gates (safety) first, then quantitative (prose+PS1).
        # Any failure short-circuits — downstream noise shouldn't mask an
        # upstream hard error.
        gates = [
            ("safety",   _gate_safety_lint,         chapter_abs),
            ("prose",    _gate_prose_lint,          chapter_abs),
            ("quality",  _gate_check_quality,       chapter_abs),
        ]
        for label, fn, arg in gates:
            rc = fn(arg)
            if rc != 0:
                print(f"FAIL at gate '{label}' for {rel} (rc={rc})", file=sys.stderr)
                return 1

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--base", help="Git base ref (e.g. origin/main, HEAD~1)")
    parser.add_argument("--head", default="HEAD", help="Git head ref (default: HEAD)")
    parser.add_argument(
        "--paths", nargs="*",
        help="Explicit changed paths (skip git diff; useful for CI)",
    )
    parser.add_argument(
        "--full", action="store_true",
        help="Run full audit on every chapter (overrides shared-gate detection)",
    )
    args = parser.parse_args(argv)

    if args.paths is not None:
        paths = args.paths
    elif args.base:
        paths = _changed_paths(args.base, args.head)
        if not paths and not args.full:
            print("git diff returned no paths; nothing to validate.", file=sys.stderr)
            return 3
    else:
        parser.error("provide --base/--head or --paths")
        return 2

    return validate(paths, force_full=args.full)


if __name__ == "__main__":
    raise SystemExit(main())