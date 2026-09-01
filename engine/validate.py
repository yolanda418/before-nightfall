# -*- coding: utf-8 -*-
"""天黑之前 · 角色档案验证（高层 API）。

CLI 入口：扫 characters/ 下所有角色档案，校验 schema + 防注入 + 长度上限。
复用 engine/soul.py 的 parse() + validate()。
"""
import os
import sys
import glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))

import soul as SOUL


def validate_all():
    """验证 characters/ 下所有角色档案。返回 (passed, failed) 文件名列表。"""
    passed, failed = [], []
    for p in sorted(glob.glob(os.path.join(ROOT, "characters", "*.md"))):
        base = os.path.basename(p)
        if base.startswith("_"):
            continue
        try:
            meta = SOUL.parse(p)
            errs = SOUL.validate(meta)
            if errs:
                failed.append((base, errs))
            else:
                passed.append(base)
        except SOUL.SoulError as e:
            failed.append((base, [str(e)]))
    return passed, failed


def main():
    passed, failed = validate_all()
    print(f"角色档案验证：{len(passed)} 通过, {len(failed)} 失败\n")
    for base in passed:
        print(f"  ✓ {base}")
    for base, errs in failed:
        print(f"  ✗ {base}")
        for e in errs:
            print(f"      - {e}")
    if failed:
        sys.exit(1)
    print("\n所有角色档案通过验证。")


if __name__ == "__main__":
    main()