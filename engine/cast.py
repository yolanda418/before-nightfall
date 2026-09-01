# -*- coding: utf-8 -*-
"""天黑之前 · 角色名册辅助函数。

旧魂的 cast.py 管理 state.json（每季投胎身份）+ memory.md（跨季记忆）。
天黑之前是单季完结，这些信息直接写在 characters/<name>.md 的
`current_state` 字段——本文件只提供查询函数。
"""
import os
import sys
import re
import glob
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# 天黑之前：角色名册是仓库根目录的 CAST.md（单文件），不是 characters/ 目录。
# 保留 CHARACTERS_DIR 变量名以便向后兼容（若日后建立 characters/ 目录，可平滑切换）。
CHARACTERS_DIR = ROOT / "characters"
CAST_MD = ROOT / "CAST.md"


def _load_all():
    sys.path.insert(0, str(ROOT / "engine"))
    import soul as SOUL
    # 优先走 characters/ 旧路径（如果目录存在）；fallback 到 CAST.md
    return SOUL.load_cast(str(CHARACTERS_DIR) if CHARACTERS_DIR.exists() else str(ROOT))


def state(name):
    """获取角色的当前状态（current_state 字段原文）。"""
    cast = _load_all()
    return cast.get(name, {}).get("current_state", "—")


def update_state(name, new_state):
    """更新角色的 current_state 字段。

    注意：直接改源文件——小心使用，建议在 Cline 监督下执行。
    """
    p = CHARACTERS_DIR / f"{name}.md"
    if not p.exists():
        raise FileNotFoundError(p)
    text = p.read_text(encoding="utf-8")
    new_text = re.sub(
        r"(^current_state:\s*).*$",
        r"\g<1>" + new_state.replace("\n", " ").strip(),
        text,
        count=1,
        flags=re.M,
    )
    p.write_text(new_text, encoding="utf-8")


def recall(name, k=5):
    """获取角色底色前 k 字（粗略的"记得的事"）。"""
    cast = _load_all()
    body = cast.get(name, {}).get("_body", "")
    if not body:
        return []
    chunks = [c.strip() for c in body.split("\n") if c.strip()]
    return chunks[:k]


def incarnated(name):
    """单季模式下所有角色都视为"已登场"。"""
    return True


def list_by_status(status):
    """按 status 字段筛选角色（如 '核心班底' / '副线案核心' / '一次性工具人'）。"""
    cast = _load_all()
    return {n: m for n, m in cast.items() if m.get("status") == status}


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2:
        cmd = sys.argv[1]
        if cmd == "list":
            cast = _load_all()
            print(f"总角色数: {len(cast)}")
            for n, m in cast.items():
                print(f"  - {n} | {m.get('role', '—')} | {m.get('status', '—')}")
        elif cmd == "state" and len(sys.argv) >= 3:
            print(state(sys.argv[2]))
        elif cmd == "by-status" and len(sys.argv) >= 3:
            results = list_by_status(sys.argv[2])
            print(f"status={sys.argv[2]}: {len(results)} 人")
            for n in results:
                print(f"  - {n}")
        else:
            print("用法：python engine/cast.py list|state <name>|by-status <status>")
    else:
        print("用法：python engine/cast.py list|state <name>|by-status <status>")