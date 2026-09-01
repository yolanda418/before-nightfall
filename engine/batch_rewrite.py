# -*- coding: utf-8 -*-
"""Tianhei Zhiqian batch rewrite engine (picker + dispatch).

Migrated from open-souls engine/batch_rewrite.py, adapted to v3.1 rules:
  * Path: Chapter_NN.md (not chNNN-title.md)
  * Word count: v3.1 [1800, 2200]
  * Detection: 8 AI bans + 4.13 ultimate bans + 4.5 numbers + 4.6 terms
  * ASCII-only output for grep/CI
  * No Anthropic API (Tianhei Zhiqian uses Cline, semi-automatic mode)

Usage:
    python engine/batch_rewrite.py status                       # show status
    python engine/batch_rewrite.py pick --pick 5               # pick 5 chapters
    python engine/batch_rewrite.py pick --pick 5 --stubs-only  # only stubs
    python engine/batch_rewrite.py pick --pick 5 --disease-only # only disease
    python engine/batch_rewrite.py pick --chapters 3 7 12      # specific
    python engine/batch_rewrite.py pick --dry-run --pick 3      # dry run
    python engine/batch_rewrite.py clear-cache                 # clear cache
"""
import os
import sys
import json
import hashlib
import argparse
import glob
import re
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))

from prose_lint import lint_file, body_of, measure

CHAPTERS_DIR = ROOT / "chapters"
AUDIT_TMP_DIR = ROOT / ".audit_tmp"
LINT_CACHE_NAME = "batch_lint_cache.json"

MIN_CHAPTER_CHARS = 1800
TARGET_CHAPTER_CHARS = 2200


def _lint_cache_path():
    AUDIT_TMP_DIR.mkdir(exist_ok=True)
    return AUDIT_TMP_DIR / LINT_CACHE_NAME


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _lint_cache_version():
    digest = hashlib.sha256()
    pl_path = Path(__file__).resolve().parent / "prose_lint.py"
    if pl_path.exists():
        digest.update(pl_path.read_bytes())
    return digest.hexdigest()[:16]


def _load_cache():
    p = _lint_cache_path()
    if not p.exists():
        return {"version": _lint_cache_version(), "files": {}}
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"version": _lint_cache_version(), "files": {}}
    if payload.get("version") != _lint_cache_version():
        return {"version": _lint_cache_version(), "files": {}}
    return payload


def _save_cache(cache):
    p = _lint_cache_path()
    cache["version"] = _lint_cache_version()
    p.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _scan_chapters():
    files = sorted(CHAPTERS_DIR.glob("Chapter_*.md"))
    out = []
    for p in files:
        m = re.match(r"Chapter_(\d+)", p.name)
        if m:
            out.append((int(m.group(1)), p, _sha256_file(p)))
    return out


def _lint_chapter(path):
    errors, warns, m = lint_file(str(path), strict=False)
    n_err = len(errors)
    n_warn = len(warns)
    chars = m["chars"]
    is_stub = chars < 1000
    is_disease = n_err > 0
    return n_err, n_warn, chars, is_stub, is_disease


# =============================================================================
# Status reporting
# =============================================================================

def _status_line(n_err, n_warn, chars, is_stub, is_disease):
    """One ASCII row for the status table."""
    flags = []
    if is_stub:
        flags.append("STUB")
    if is_disease:
        flags.append("DISEASE")
    if chars < MIN_CHAPTER_CHARS:
        flags.append("UNDER")
    elif chars > TARGET_CHAPTER_CHARS:
        flags.append("OVER")
    return f"err={n_err} warn={n_warn} chars={chars} flags={'+'.join(flags) or 'ok'}"


def cmd_status(args):
    """List every chapter with its lint state."""
    rows = []
    for chapter, path, sha in _scan_chapters():
        n_err, n_warn, chars, is_stub, is_disease = _lint_chapter(path)
        rows.append((chapter, _status_line(n_err, n_warn, chars, is_stub, is_disease), path.name))
    rows.sort()
    print(f"status: {len(rows)} chapters")
    for ch, status, name in rows:
        print(f"  ch{ch:02d}  {status}  {name}")
    print()
    disease_count = sum(1 for _, s, _ in rows if "DISEASE" in s)
    stub_count = sum(1 for _, s, _ in rows if "STUB" in s)
    under_count = sum(1 for _, s, _ in rows if "UNDER" in s)
    over_count = sum(1 for _, s, _ in rows if "OVER" in s)
    print(f"summary: disease={disease_count} stub={stub_count} under={under_count} over={over_count}")


# =============================================================================
# Picker
# =============================================================================

def _parse_pick_args(chapters, pick):
    """Resolve which chapter numbers to operate on.

    Priority: --chapters > --pick N (auto-pick N needing work).
    """
    if chapters:
        return list(chapters)
    if pick and pick > 0:
        # Auto-pick chapters that need work
        candidates = []
        for chapter, path, sha in _scan_chapters():
            n_err, n_warn, chars, is_stub, is_disease = _lint_chapter(path)
            if is_disease or is_stub:
                candidates.append((chapter, path, n_err, is_stub, is_disease))
        # Sort: disease (err count desc) > stub
        candidates.sort(key=lambda x: (-x[2], x[3], x[0]))
        return [c[0] for c in candidates[:pick]]
    return []


def cmd_pick(args):
    """Select chapters needing rewrite.

    Filters:
      --stubs-only    only chapters with chars < 1000
      --disease-only  only chapters with n_err > 0
      --dry-run       don't cache the pick
    """
    chapter_nums = _parse_pick_args(args.chapters, args.pick)
    if not chapter_nums:
        print("no chapters selected (pass --pick N or --chapters N [N ...])")
        return 0

    selected = []
    for chapter, path, sha in _scan_chapters():
        if chapter not in chapter_nums:
            continue
        n_err, n_warn, chars, is_stub, is_disease = _lint_chapter(path)
        if args.stubs_only and not is_stub:
            continue
        if args.disease_only and not is_disease:
            continue
        selected.append((chapter, path, n_err, n_warn, chars))

    selected.sort(key=lambda x: x[0])
    if args.dry_run:
        print(f"dry-run: would pick {len(selected)} chapters")
    else:
        print(f"picked: {len(selected)} chapters")
    for chapter, path, n_err, n_warn, chars in selected:
        print(f"  ch{chapter:02d}  err={n_err} warn={n_warn} chars={chars}  {path.name}")
    return 0


def cmd_clear_cache(args):
    """Remove the lint cache to force a re-scan."""
    p = _lint_cache_path()
    if p.exists():
        p.unlink()
        print(f"cleared: {p}")
    else:
        print("no cache to clear")
    return 0


# =============================================================================
# CLI dispatch
# =============================================================================

def _build_arg_parser():
    parser = argparse.ArgumentParser(
        prog="batch_rewrite.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # status
    p_status = sub.add_parser("status", help="Show lint state for every chapter")

    # pick
    p_pick = sub.add_parser("pick", help="Pick chapters needing rewrite")
    p_pick.add_argument("--pick", type=int, default=0, help="Auto-pick N chapters")
    p_pick.add_argument("--chapters", type=int, nargs="*", help="Specific chapter numbers")
    p_pick.add_argument("--stubs-only", action="store_true", help="Only chapters with chars < 1000")
    p_pick.add_argument("--disease-only", action="store_true", help="Only chapters with n_err > 0")
    p_pick.add_argument("--dry-run", action="store_true", help="Don't cache the pick")

    # clear-cache
    sub.add_parser("clear-cache", help="Remove the lint cache to force a re-scan")

    return parser


def main(argv=None):
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    if args.cmd == "status":
        return cmd_status(args)
    if args.cmd == "pick":
        return cmd_pick(args)
    if args.cmd == "clear-cache":
        return cmd_clear_cache(args)

    parser.error(f"unknown command: {args.cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())