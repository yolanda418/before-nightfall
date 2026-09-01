# -*- coding: utf-8 -*-
"""天黑之前 · 案件管理器（单季完结版）。

旧魂的 season.py 是「赛季 = 世界」（多季投胎）。
天黑之前是单季完结，不需要投胎——把"赛季"改造为"案件管理器"：

  · 一个主线大案（贯穿全剧）
  · 多个副线小案（每 4–6 章一个，"一案一结"）

数据结构：
  world.md       ← 世界观 / 港城地理 / 关键物件（沿用现有 WORLDVIEW.md）
  ties.json      ← 角色关系网（affection / trust / tension / feeling）
  arc.json       ← 主线节拍（主案进度）+ 副线案进度

用法：
    from season import load_world, load_ties, load_arc, advance_arc, rel, apply_update
"""
import os
import json
import re
import yaml


# 案件节拍模板（沿用旧魂的"起承转合"+ 刑侦特色）
DEFAULT_ARC_BEATS = [
    "起：第七起钩子，主角登场",
    "承：副线小案 1 + 1 条主案物证浮现",
    "承：副线小案 2 + 关系网建立",
    "转：一场变故打乱所有人",
    "合：副线小案收束 + 大 Boss 暗线加强",
    "合：直面大 Boss + 主角觉醒",
]

# 单季模式：根目录没有 seasons/ 子目录——世界在根的 WORLDVIEW.md
def _world_path(root=None):
    if root is None:
        root = os.path.dirname(os.path.dirname(__file__))
    return os.path.join(root, "WORLDVIEW.md")


def _p(root, f):
    return os.path.join(root, f)


def load_world(root=None):
    """读 WORLDVIEW.md，提取 YAML frontmatter + 标记正文前 300 字为 _body。"""
    p = _world_path(root)
    if not os.path.exists(p):
        return {"_body": "", "_path": p}
    raw = open(p, encoding="utf-8").read()
    m = re.match(r"^---\n(.*?)\n---?\n?(.*)$", raw, re.S)
    meta = (yaml.safe_load(m.group(1)) if m else {}) or {}
    meta["_body"] = ((m.group(2) if m else raw) or "").strip()[:300]
    meta["_path"] = p
    return meta


def load_ties(root=None):
    """读 ties.json（角色关系网）；不存在返回 {}。"""
    if root is None:
        root = os.path.dirname(os.path.dirname(__file__))
    p = _p(root, "ties.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def save_ties(root, ties):
    """保存 ties.json。"""
    p = _p(root, "ties.json")
    json.dump(ties, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def rel(ties, a, b):
    """获取/创建角色 a 对 b 的关系条目。"""
    return ties.setdefault(a, {}).setdefault(
        b, {"affection": 0, "trust": 0, "tension": 0, "feeling": ""}
    )


def apply_update(ties, u):
    """应用一次关系变化。u = {"from": A, "to": B, "affection_delta": int, ...}"""
    r = rel(ties, u["from"], u["to"])
    for k in ("affection", "trust", "tension"):
        delta = int(u.get(k + "_delta", 0))
        r[k] = max(-10, min(10, r[k] + delta))
    if u.get("feeling"):
        r["feeling"] = u["feeling"]


def load_arc(root=None):
    """读 arc.json（主线 + 副线进度）；不存在则初始化。"""
    if root is None:
        root = os.path.dirname(os.path.dirname(__file__))
    p = _p(root, "arc.json")
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    return {
        "main_case": {"name": "第七起系列", "beats": DEFAULT_ARC_BEATS, "beat": 0, "in_beat": 0},
        "side_cases": [],   # 每条 = {"name", "ch_start", "ch_end", "status": "open"/"closed"}
    }


def save_arc(root, arc):
    p = _p(root, "arc.json")
    json.dump(arc, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def advance_arc(root, arc, per_beat=4):
    """推进主线节拍。每 per_beat 章推进一节。

    与旧魂的区别：副线案不在此函数处理，由 side_cases 列表手动管理
    （对应 CLUES_TRACKER.md 第 4 节"一案一结"框架）。
    """
    arc["main_case"]["in_beat"] += 1
    main = arc["main_case"]
    if main["in_beat"] >= per_beat and main["beat"] < len(main["beats"]) - 1:
        main["beat"] += 1
        main["in_beat"] = 0
    save_arc(root, arc)
    return arc


def beat_line(arc):
    return arc["main_case"]["beats"][arc["main_case"]["beat"]]


def open_side_case(root, arc, name, ch_start):
    """开一个副线案。"""
    arc["side_cases"].append({
        "name": name, "ch_start": ch_start, "ch_end": None, "status": "open",
    })
    save_arc(root, arc)
    return arc


def close_side_case(root, arc, name, ch_end):
    """结一个副线案（"一案一结"硬规则）。"""
    for sc in arc["side_cases"]:
        if sc["name"] == name and sc["status"] == "open":
            sc["ch_end"] = ch_end
            sc["status"] = "closed"
            break
    save_arc(root, arc)
    return arc


def open_side_cases(arc):
    """返回所有未结的副线案列表（用于 lint 检查"未结副线案数 ≤ 1"）。"""
    return [sc for sc in arc["side_cases"] if sc["status"] == "open"]


if __name__ == "__main__":
    import sys
    root = os.path.dirname(os.path.dirname(__file__))
    world = load_world(root)
    ties = load_ties(root)
    arc = load_arc(root)
    open_side_n = len(open_side_cases(arc))
    print(f"世界观: {world.get('name', '—')} ({world.get('_path', '—')})")
    print(f"关系网: {len(ties)} 个角色")
    print(f"主线进度: beat {arc['main_case']['beat']+1}/{len(arc['main_case']['beats'])} ({beat_line(arc)})")
    print(f"副线案: {len(arc['side_cases'])} 个，{open_side_n} 个未结")