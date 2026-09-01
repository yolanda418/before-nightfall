# -*- coding: utf-8 -*-
"""Tianhei Zhiqian · Bounded Claude Code dispatcher for chapter rewrites.

移植自旧魂《众魂》open-souls 的 engine/run_dispatch.py，已按天黑之前的需求改造：

    · 章节路径：chapters/Chapter_NN.md（NN 两位补零；不是 seasons/01-xianxia/chronicle/chNNN-*.md）
    · 提示文件：prompts/dispatch/Chapter_NN.txt（不是 chNNN.txt）
    · 结果文件：prompts/.results/Chapter_NN.md（不是 chNNN.md）
    · 路径解析：自带 _parse_chapter_spec / _target_for_prompt，不依赖 batch_rewrite
    · 公式扫描：复用 engine/prose_lint.py 的 8 大 AI 通病 metrics（不需要旧魂的方向回环）
    · 输出：ASCII-only，便于 CI 解析

设计原则：
    · 外层廉价（只调 Claude + 跑门），内核在 Claude 里（写正文）
    · 单章预算 / 超时强制（任何越界都 taskkill 进程树，不留孤儿）
    · Claude 只被允许改目标章节（chapters/Chapter_NN.md），其他任何文件改动都 BLOCKED
    · SHA256 快照：跑完 Claude 后，验证只有目标文件被改
    · Claude 自报 PASS 不具备放行权；只有本地门禁全部 PASS 才算 PASS

为什么需要这个：
    `engine/writer.py --auto` 是简易版（只 `claude --file`），没有 budget/timeout/进程清理。
    本脚本是「全自动续写」的派发器；用它替代 --auto，才能让 Cline 在
    受限范围内续写 + 不会跑死 / 不会越权改文档。

用法::

    # 1. Dry run：只列出候选章节
    python engine/run_dispatch.py --dry-run

    # 2. 派发 prompts/dispatch/Chapter_14.txt 给 Claude（420 秒超时）
    python engine/run_dispatch.py --chapters 14

    # 3. 派发多个章节（workers=2 并行）
    python engine/run_dispatch.py --chapters 14-16 --workers 2

    # 4. 自定义 budget / model / timeout
    python engine/run_dispatch.py --chapters 14 \
        --max-budget-usd 8.0 \
        --model claude-sonnet-4-6 \
        --timeout-sec 300 \
        --effort high

退出码：
    0 = 所有派发章节本地门禁全 PASS
    1 = 至少一个章节被 BLOCKED
    2 = 参数错误 / 配置缺失
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path


# Force UTF-8 stdout/stderr (matches validate_changed.py convention)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import prose_lint as PL  # noqa: E402


# ---- 路径常量 ----
DISPATCH_DIR = ROOT / "prompts" / "dispatch"
RESULTS_DIR = ROOT / "prompts" / ".results"
CHAPTERS_DIR = ROOT / "chapters"

# ---- 默认参数 ----
DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_BUDGET = 12.0        # 单章最大 USD
DEFAULT_WORKERS = 2
# 7 分钟超时：超过这个时间通常意味着 Claude 在循环读 context / 反复重开目标文件
DEFAULT_TIMEOUT = 420

# Chapter file 命名模式（两位补零，匹配 engine/prose_lint.py.chapter_number）
_CHAPTER_NUM_RE = re.compile(r"Chapter_(\d+)")
_DISPATCH_FILE_RE = re.compile(r"Chapter_(\d+)\.txt$", re.IGNORECASE)


# =============================================================================
# SHA256 snapshot helpers
# =============================================================================

def _sha256(path: Path) -> str:
    """Return hex SHA256 of a file, or empty string if missing."""
    if not path.exists() or not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _protected_paths(target: Path, prompt_path: Path, chapter: int):
    """List every file Claude is NOT allowed to mutate.

    The target is intentionally included so the caller can exempt it from the
    side-effect check. We also watch:
      · The job's prompt file
      · The job's result file (in prompts/.results/)
      · Root-level project files (.clinerules, CAST.md, ...)
      · engine/ tools/ tests/ trees (Claude should never edit these)
      · The chapter directory (to catch newly created sibling files like
        Chapter_14-new.md or Chapter_14-alt.md)
    """
    paths = {target.resolve(), prompt_path.resolve()}
    paths.add((RESULTS_DIR / f"Chapter_{chapter:02d}.md").resolve())

    if target.parent.exists():
        paths.update(p.resolve() for p in target.parent.iterdir() if p.is_file())
    if CHAPTERS_DIR.exists():
        paths.update(p.resolve() for p in CHAPTERS_DIR.rglob("*") if p.is_file())

    for path in ROOT.iterdir():
        if path.is_file():
            paths.add(path.resolve())

    for dirname in ("engine", "tools", "tests"):
        directory = ROOT / dirname
        if directory.exists():
            paths.update(p.resolve() for p in directory.rglob("*") if p.is_file())

    return paths


def _snapshot_protected(target: Path, prompt_path: Path, chapter: int):
    """Return dict {path_str: sha256_hex_or_empty} for every protected file."""
    snapshot = {}
    for path in _protected_paths(target, prompt_path, chapter):
        snapshot[str(path)] = _sha256(path)
    return snapshot


def _side_effects(before, target: Path, prompt_path: Path, allowed_paths):
    """Return list of files changed outside the allowed set.

    Re-snapshots protected paths AFTER Claude ran and diffs against `before`.
    Anything not in `allowed_paths` that changed is a side effect (= BLOCKED).

    IMPORTANT: `prompt_path` must be the SAME path that was passed to
    _snapshot_protected to build `before`. Otherwise the before/after key
    sets differ and false-positive side effects are reported.
    """
    chapter = _chapter_from_path(target)
    after = _snapshot_protected(target, prompt_path, chapter)
    allowed = {str(target.resolve())}
    for path in allowed_paths or ():
        allowed.add(str(Path(path).resolve()))

    changed = []
    for path in sorted(set(before) | set(after)):
        if path in allowed:
            continue
        if before.get(path) != after.get(path):
            changed.append(path)
    return changed


# =============================================================================
# Path resolution helpers (NOT dependent on batch_rewrite)
# =============================================================================

def _chapter_from_path(path: Path) -> int | None:
    """Extract chapter number from any path that contains Chapter_NN."""
    m = _CHAPTER_NUM_RE.search(path.name)
    return int(m.group(1)) if m else None


def _chapter_from_prompt(path: Path) -> int | None:
    """Extract chapter number from a dispatch prompt file name."""
    m = _DISPATCH_FILE_RE.search(path.name)
    return int(m.group(1)) if m else None


def _target_for_chapter(chapter: int) -> Path:
    """Return the canonical chapter file path for a given chapter number."""
    return CHAPTERS_DIR / f"Chapter_{chapter:02d}.md"


def _target_from_prompt(path: Path) -> Path | None:
    """Read a `TARGET_FILE:` marker from the prompt if present."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    match = re.search(r"^TARGET_FILE:\s*(.+?)\s*$", text, re.M)
    if not match:
        return None
    candidate = Path(match.group(1).strip().strip("`"))
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    try:
        candidate = candidate.resolve()
        candidate.relative_to(CHAPTERS_DIR.resolve())
    except (OSError, ValueError):
        return None
    return candidate if candidate.is_file() else None


def _target_for_prompt(path: Path, chapter: int | None = None) -> Path | None:
    """Resolve a dispatch prompt to its target file."""
    explicit = _target_from_prompt(path)
    if explicit is not None:
        return explicit
    if chapter is not None:
        return _target_for_chapter(chapter)
    return None


def _parse_chapter_spec(spec: str) -> list[int]:
    """Parse '14' or '14-16' or '14,15-17' into a list of chapter numbers."""
    nums: list[int] = []
    for part in spec.split(","):
        s = part.strip()
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", s)
        if not m:
            raise ValueError(f"invalid chapter spec: {part!r}")
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) else a
        nums.extend(range(a, b + 1))
    return sorted(set(nums))


def _prompt_paths(chapters: list[int] | None = None) -> list[Path]:
    """List dispatch prompts, optionally filtered to a chapter set."""
    if not DISPATCH_DIR.exists():
        return []
    paths = sorted(DISPATCH_DIR.glob("Chapter_*.txt"))
    if chapters is None:
        return paths
    wanted = set(chapters)
    return [p for p in paths if _chapter_from_prompt(p) in wanted]


# =============================================================================
# Process / subprocess primitives (Windows-safe)
# =============================================================================

def _terminate_process_tree(process: subprocess.Popen):
    """Kill process + any wrapper it spawned (e.g. claude.cmd -> node).

    On Windows, invoking `claude.cmd` creates a command-wrapper process and
    the actual Claude/Node child can survive Popen.kill(). That was the
    source of orphan Claude jobs after a timeout. `taskkill /T /F` is scoped
    to this Popen PID, so it cannot touch unrelated long-running sessions.
    """
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                check=False,
            )
            return
        except (OSError, subprocess.TimeoutExpired):
            pass
    try:
        process.kill()
    except OSError:
        pass


def _run_process(command, *, input_text=None, timeout=DEFAULT_TIMEOUT):
    """Run a subprocess with timeout + Windows-safe cleanup."""
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

    try:
        process = subprocess.Popen(
            command,
            cwd=str(ROOT),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
        )
    except OSError as exc:
        return {"returncode": 127, "stdout": "", "stderr": str(exc), "timed_out": False}

    try:
        stdout, stderr = process.communicate(input=input_text, timeout=timeout)
        return {
            "returncode": process.returncode,
            "stdout": stdout or "",
            "stderr": stderr or "",
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        _terminate_process_tree(process)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except OSError:
                pass
            stdout, stderr = process.communicate()

        def _text(value):
            if isinstance(value, bytes):
                return value.decode("utf-8", errors="replace")
            return value or ""

        return {
            "returncode": 124,
            "stdout": _text(stdout) or _text(exc.stdout),
            "stderr": "timeout; process tree terminated\n" + _text(stderr),
            "timed_out": True,
        }


# =============================================================================
# Claude CLI wrapper
# =============================================================================

def _claude(prompt, *, budget, model, effort, timeout, claude_cmd):
    """Invoke Claude Code CLI in bounded mode.

    Flags:
      -p                       non-interactive mode (read prompt from stdin)
      --bare                   no splash / no spinner
      --no-session-persistence don't write to session store
      --model                  target model
      --max-budget-usd         hard USD cap for this invocation
      --effort                 reasoning effort (low/medium/high/xhigh/max)
      --allowed-tools          only Read + Edit (no Bash / no Write)
      --permission-mode        acceptEdits (auto-accept file edits)
      --output-format          json (structured response, easier to parse)
    """
    command = [
        claude_cmd,
        "-p",
        "--bare",
        "--no-session-persistence",
        "--model", model,
        "--max-budget-usd", str(budget),
        "--effort", effort,
        "--allowed-tools", "Read,Edit",
        "--permission-mode", "acceptEdits",
        "--output-format", "json",
    ]
    raw = _run_process(command, input_text=prompt, timeout=timeout)
    payload = None
    try:
        payload = json.loads(raw["stdout"].strip())
    except (TypeError, json.JSONDecodeError):
        pass

    success = (
        raw["returncode"] == 0
        and isinstance(payload, dict)
        and payload.get("is_error") is not True
        and payload.get("subtype") not in {"error_max_budget_usd", "error"}
    )
    return {
        "ok": success,
        "returncode": raw["returncode"],
        "payload": payload,
        "stdout_tail": raw["stdout"][-2000:],
        "stderr_tail": raw["stderr"][-1000:],
        "timed_out": raw["timed_out"],
    }


def _gate(command, *, timeout):
    """Run a local gate (prose_lint / safety_lint) and capture pass/fail."""
    result = _run_process(command, timeout=timeout)
    return {
        "ok": result["returncode"] == 0 and not result["timed_out"],
        "returncode": result["returncode"],
        "output": (result["stdout"] + result["stderr"])[-2500:],
        "timed_out": result["timed_out"],
    }


# =============================================================================
# Local formula / AI-bans scan (replaces 旧魂's direction_formula)
# =============================================================================

# 8 AI-bans + 4.13 ultimate bans from .clinerules section 4.
# A chapter fails the formula gate if any metric exceeds its threshold.
_FORMULA_METRIC_THRESHOLDS = {
    "ai_connector": 3,
    "ai_filler_adv": 3,
    "ai_highfreq": 3,
    "template_verb": 2,
    "unreasonable_num": 1,
    "god_view": 1,
    "inner_leak": 1,
    "negative_contrast": 1,
    "weak_transition": 1,
    "one_action": 3,
    "direction_formula": 3,
}


def _formula_hits(target: Path) -> dict:
    """Return dict of {metric: count} for any metric exceeding threshold.

    Empty dict means no formula hits; chapter is clean on this dimension.
    """
    if not target.exists():
        return {"missing_target": 1}
    body = PL.body_of(target.read_text(encoding="utf-8"))
    metrics = PL.measure(body)
    return {k: v for k, v in metrics.items() if _FORMULA_METRIC_THRESHOLDS.get(k, 99) <= v}


# =============================================================================
# Result file writer
# =============================================================================

def _write_result(chapter: int, target: Path, result: dict):
    """Write the dispatch verdict to prompts/.results/Chapter_NN.md."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = result["claude"].get("payload") or {}
    claude_note = payload.get("result") if isinstance(payload, dict) else ""
    if not isinstance(claude_note, str):
        claude_note = json.dumps(claude_note, ensure_ascii=False)

    lines = [
        f"status: {'PASS' if result['pass'] else 'BLOCKED'}",
        f"chapter: {chapter}",
        f"target: {target}",
        f"claude: {'ok' if result['claude']['ok'] else 'fail'}",
        f"changed: {'yes' if result['changed'] else 'no'}",
        f"lint: {'ok' if result['lint']['ok'] else 'fail'}",
        f"strict: {'ok' if result['strict']['ok'] else 'fail'}",
        f"formula_scan: {'ok' if not result['formula_hits'] else 'fail'}",
        f"side_effects: {'clean' if not result.get('side_effects') else 'FAIL'}",
        f"elapsed_seconds: {result['elapsed_seconds']:.1f}",
        "claude_subtype: " + str(payload.get("subtype", "")),
        "claude_stop_reason: " + str(payload.get("stop_reason", "")),
        "claude_cost_usd: " + str(payload.get("total_cost_usd", "")),
        "claude_errors: " + json.dumps(payload.get("errors", []), ensure_ascii=False),
        "formula_hits: " + (json.dumps(result["formula_hits"], ensure_ascii=False) if result["formula_hits"] else "{}"),
        "side_effects_list: " + (json.dumps(result.get("side_effects", []), ensure_ascii=False) if result.get("side_effects") else "[]"),
        "note: " + " ".join(claude_note.strip().split())[:1200],
    ]
    (RESULTS_DIR / f"Chapter_{chapter:02d}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# =============================================================================
# Single chapter job
# =============================================================================

def run_one(prompt_path: Path, *, budget=DEFAULT_BUDGET, model=DEFAULT_MODEL,
            effort="medium", timeout=DEFAULT_TIMEOUT, claude_cmd="claude.cmd",
            allowed_targets=None):
    """Run a single chapter dispatch.

    Lifecycle:
      1. Resolve target chapter file from prompt (or fall back to canonical).
      2. Snapshot SHA256 of every protected file.
      3. Invoke Claude with the prompt (bounded budget + timeout).
      4. Run local gates: prose_lint, prose_lint --strict, safety_lint.
      5. Compute side-effects (any protected file changed outside allowed set).
      6. PASS only if: claude.ok AND file changed AND lint/strict/safety ok
                       AND formula clean AND no side effects.
      7. Write verdict to prompts/.results/Chapter_NN.md.
    """
    chapter = _chapter_from_prompt(prompt_path)
    if chapter is None:
        raise ValueError(f"invalid dispatch prompt name: {prompt_path.name}")

    target = _target_for_prompt(prompt_path, chapter)
    if target is None:
        raise FileNotFoundError(f"no target for {prompt_path}")

    started = time.monotonic()

    # 1. Snapshot
    before_snapshot = _snapshot_protected(target, prompt_path, chapter)

    # 2. Read prompt
    prompt_text = prompt_path.read_text(encoding="utf-8")

    # 3. Run Claude (bounded)
    claude_result = _claude(
        prompt_text,
        budget=budget,
        model=model,
        effort=effort,
        timeout=timeout,
        claude_cmd=claude_cmd,
    )

    # 4. Side effects
    side_effects = _side_effects(before_snapshot, target, prompt_path, allowed_targets)

    # 5. Local gates
    target_rel = str(target.relative_to(ROOT))
    lint = _gate([sys.executable, "engine/prose_lint.py", target_rel], timeout=60)
    strict = _gate(
        [sys.executable, "engine/prose_lint.py", "--strict-editorial", target_rel],
        timeout=60,
    )
    safety = _gate([sys.executable, "engine/safety_lint.py", target_rel], timeout=30)

    # 6. Formula / AI-bans
    formula_hits = _formula_hits(target) if target.exists() else {"missing_target": 1}

    # 7. Did Claude change the file?
    after_sha = _sha256(target)
    before_sha = before_snapshot.get(str(target.resolve()), "")
    changed = bool(after_sha) and bool(before_sha) and after_sha != before_sha

    # 8. PASS verdict
    passed = bool(
        claude_result["ok"]
        and changed
        and lint["ok"]
        and strict["ok"]
        and safety["ok"]
        and not formula_hits
        and not side_effects
    )

    result = {
        "pass": passed,
        "chapter": chapter,
        "target": str(target),
        "changed": changed,
        "claude": claude_result,
        "lint": lint,
        "strict": strict,
        "safety": safety,
        "formula_hits": formula_hits,
        "side_effects": side_effects,
        "elapsed_seconds": time.monotonic() - started,
    }
    _write_result(chapter, target, result)
    return result


# =============================================================================
# Main entry
# =============================================================================

def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--chapters",
        help="Chapter numbers to dispatch, e.g. 14 or 14-16 or 14,16-18",
    )
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--max-budget-usd", type=float, default=DEFAULT_BUDGET)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--effort",
        choices=("low", "medium", "high", "xhigh", "max"),
        default="medium",
    )
    parser.add_argument("--timeout-sec", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument(
        "--claude-cmd",
        default=os.environ.get("CLAUDE_CMD", "claude.cmd"),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Dispatch even if target chapter already passes local gates",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List candidates only; do not invoke Claude",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)

    # 1. Resolve prompts
    try:
        chapters = _parse_chapter_spec(args.chapters) if args.chapters else None
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    paths = _prompt_paths(chapters)
    if not paths:
        if chapters:
            print(
                f"no dispatch prompts matching --chapters={args.chapters} "
                f"(looked in {DISPATCH_DIR})",
                file=sys.stderr,
            )
        else:
            print(f"no dispatch prompts in {DISPATCH_DIR}", file=sys.stderr)
        return 2

    # 2. Filter by --force / pre-check
    selected = []
    skipped = []  # list of (chapter: int, reason: str)
    for path in paths:
        chapter = _chapter_from_prompt(path)
        if chapter is None:
            continue
        target = _target_for_prompt(path, chapter)
        if target is None or not target.exists():
            skipped.append((chapter, "target missing"))
            continue
        if not args.force:
            # Quick pre-check: if already PASS, skip
            try:
                body = target.read_text(encoding="utf-8")
                errors, _, _ = PL.lint_text(body, strict=True)
                if not errors:
                    skipped.append((chapter, "already passes strict"))
                    continue
            except (OSError, UnicodeError):
                pass
        selected.append(path)

    # 3. Print plan
    print(
        f"dispatch_targets={len(selected)} skipped={len(skipped)} "
        f"workers={max(1, args.workers)} budget_usd={args.max_budget_usd} "
        f"timeout_sec={args.timeout_sec} model={args.model}"
    )
    for path in selected:
        ch = _chapter_from_prompt(path)
        print(f"  ch{ch:02d} <- {path}")
    for ch, reason in skipped:
        print(f"  [skip] ch{ch:02d}: {reason}")

    if args.dry_run or not selected:
        return 0

    # 4. allowed_targets across batch
    allowed_targets: set[str] = set()
    for path in selected:
        ch = _chapter_from_prompt(path)
        target = _target_for_prompt(path, ch)
        if target is not None:
            allowed_targets.add(str(target.resolve()))

    # 5. Parallel run
    outcomes = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {
            pool.submit(
                run_one,
                path,
                budget=args.max_budget_usd,
                model=args.model,
                effort=args.effort,
                timeout=args.timeout_sec,
                claude_cmd=args.claude_cmd,
                allowed_targets=allowed_targets,
            ): path
            for path in selected
        }
        for future in concurrent.futures.as_completed(futures):
            path = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                ch = _chapter_from_prompt(path)
                target = _target_for_prompt(path, ch) or _target_for_chapter(ch or 0)
                result = {
                    "pass": False,
                    "chapter": ch,
                    "target": str(target),
                    "changed": False,
                    "claude": {"ok": False, "payload": None, "stderr_tail": str(exc)},
                    "lint": {"ok": False},
                    "strict": {"ok": False},
                    "safety": {"ok": False},
                    "formula_hits": {},
                    "side_effects": [],
                    "elapsed_seconds": 0.0,
                }
                if ch is not None:
                    _write_result(ch, target, result)
            outcomes.append(result)
            state = "PASS" if result["pass"] else "BLOCKED"
            print(f"ch{result['chapter']:02d}: {state}")

    return 0 if all(item["pass"] for item in outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(main())