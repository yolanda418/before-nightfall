# -*- coding: utf-8 -*-
"""天黑之前 · 角色档案解析/校验。

移植自旧魂 engine/soul.py，已按天黑之前的需求改造：

  · 路径：characters/<name>.md（独立单文件，不是 souls/<name>/soul.md）
  · 字段对齐 .clinerules 第 2 节"5 步侧写法"：
      name, role, status, one_line, drives, fracture, under_pressure,
      side_line_quota, voice, boundaries, current_state, signature
  · 不再有跨季 multi-file 结构（单季完结，1 文件即档案）
  · 不调用 LLM——只解析 YAML frontmatter + 校验 schema
  · `card()` 输出可直接贴给 Claude 当角色卡

角色卡是 DATA，绝不执行其中任何指令——防注入。
"""
import os
import re
import glob
import yaml


REQUIRED = [
    "name", "one_line", "drives", "fracture", "under_pressure", "boundaries",
]
MAX_CHARS = 2000   # 单角色档案上限（比旧魂的 1500 略宽，因为 5 步侧写法更复杂）

# 防注入：soul.md 不允许包含操纵生成器的指令
INJECTION = re.compile(
    r"(ignore (the )?(previous|above)|system\s*:|you (are|must) now|"
    r"忽略(上面|之前)|你现在(必须|是)|disregard|jailbreak)",
    re.I,
)


class SoulError(Exception):
    pass


def parse(path):
    """解析单角色档案文件，提取 YAML frontmatter + 标记正文前 400 字为 _body。"""
    raw = open(path, encoding="utf-8").read()
    m = re.match(r"^---\n(.*?)\n---?\n?(.*)$", raw, re.S)
    if not m:
        raise SoulError(f"{path}: 缺少 YAML frontmatter")
    meta = yaml.safe_load(m.group(1)) or {}
    meta["_body"] = (m.group(2) or "").strip()[:400]
    meta["_path"] = path
    return meta


def validate(meta):
    """校验单角色档案 schema + 防注入 + 长度上限。"""
    errs = []
    for k in REQUIRED:
        if not meta.get(k):
            errs.append(f"缺少必填字段: {k}")

    fr = meta.get("fracture") or {}
    if not (isinstance(fr, dict) and fr.get("says") and fr.get("does")):
        errs.append("fracture 必须有 says 和 does（5 步侧写法第 4 步要求）")

    # 副线案核心涉案人数 ≤ 3 的硬规则（CLUES_TRACKER.md 第 4 节）
    # 仅对「副线案核心涉案人物」状态的角色生效
    if meta.get("status") == "副线案核心":
        side_quota = meta.get("side_line_quota")
        if side_quota is not None and side_quota > 3:
            errs.append(
                f"副线案核心涉案人物 ≤ 3 规则违反：{meta.get('name')} 的 "
                f"side_line_quota={side_quota} > 3"
            )

    blob = yaml.safe_dump(meta, allow_unicode=True)
    if INJECTION.search(blob):
        errs.append("疑似操纵生成器的指令。角色档案只描述角色，不下命令。")
    if len(blob) > MAX_CHARS:
        errs.append(f"角色档案过长（{len(blob)}>{MAX_CHARS}）。请精简。")
    return errs


# 天黑之前：角色名册是单文件 CAST.md（位于仓库根目录）。
# 旧魂用 souls/<name>/soul.md 多文件结构，本项目单季完结，故只解析 CAST.md。
# 兼容老路径：如果 characters/ 目录存在且非空，仍走旧路径（用于未来扩展）。
CAST_MD_FILENAME = "CAST.md"


def _looks_like_character_name(head: str) -> bool:
    """判定一段加粗文本是否是真实角色名（而不是字段标签 / 段标题 / 物证描述）。

    规则：
      - 长度 2-4 字（中文人名常见长度）
      - 不含标签词（详见 BLOCK_KEYWORDS）
      - 必须是中文为主（不含拉丁字母主导）
    """
    head = head.strip()
    if not (2 <= len(head) <= 4):
        return False
    # 排除明显的字段标签 / 段标题（覆盖核心班底内的子标题 + 大 Boss 段标题）
    BLOCK_KEYWORDS = (
        "身份", "代号", "物证", "钩子", "线索",
        "状态", "风格", "互动", "雷区", "真身",
        "保护伞", "细节", "底色",
        "伪装", "时刻", "日常", "侧写", "台词",
        "出场", "冲突", "核心", "档案", "心理",
        "驱动", "裂缝", "压力", "说话", "边界",
        "本章", "后续", "定位", "写作",
    )
    if any(k in head for k in BLOCK_KEYWORDS):
        return False
    # 必须是中文（不含拉丁字母主导）
    han_count = sum(1 for c in head if '\u4e00' <= c <= '\u9fff')
    if han_count < len(head) * 0.5:
        return False
    return True


def load_cast_from_md(cast_md_path=None, root=None):
    """从仓库根目录的 CAST.md 解析角色名册。

    返回 {角色名: {name, status, source_line}} dict。
    status 由角色所在段决定：
      - "## 核心班底" → "核心班底"
      - "## 大 Boss" → "大 Boss"
      - "## 动态出场角色库" → "动态角色"
      - 其他 → "未分类"

    兼容括号内的别名（如 "陈砚青（老陈）" → name="陈砚青", alias="老陈"）。

    大 Boss 段特判：明面身份行的格式是
      "- **明面身份（保护伞）**：**霍渊白**。港城警界..."
    需要从行内任意位置再匹配一次 **<人名>**，把大 Boss 名字取出来。
    """
    if cast_md_path is None:
        if root is None:
            root = os.path.dirname(os.path.dirname(__file__))
        cast_md_path = os.path.join(root, CAST_MD_FILENAME)

    if not os.path.exists(cast_md_path):
        return {}

    text = open(cast_md_path, encoding="utf-8").read()

    # 按 ## 段切分，识别每行的 status
    sections = re.split(r"\n##\s+", text)
    cast = {}
    # 第一段是标题段（## 之前），跳过
    for sec in sections[1:]:
        # 段头（去掉前导的 ## 后，第一行是标题）
        first_nl = sec.find("\n")
        if first_nl == -1:
            continue
        section_title = sec[:first_nl].strip()

        # 决定 status
        if "核心班底" in section_title:
            status = "核心班底"
        elif "Boss" in section_title or "大 Boss" in section_title:
            status = "大 Boss"
        elif "动态" in section_title:
            status = "动态角色"
        else:
            status = "未分类"

        # 解析 - **<name>**（<alias>） — ... 行
        body = sec[first_nl + 1:]
        for line in body.splitlines():
            m = re.match(r"^\s*-\s*\*\*([^*]+?)\*\*", line)
            if not m:
                continue
            head = m.group(1).strip()
            # 处理括号别名：陈砚青（老陈）
            alias_m = re.match(r"^([^（]+)（([^）]+)）", head)
            if alias_m:
                name = alias_m.group(1).strip()
                alias = alias_m.group(2).strip()
            else:
                name = head
                alias = None

            # 大 Boss 段特判：如果首字段是"明面身份（保护伞）"，
            # 在整行里再扫一次 **<人名>** 取真名（行内可能含多个 **xxx**）
            if status == "大 Boss" and not _looks_like_character_name(name):
                # 找出该行所有 **...** 段，选第一个看起来像人名的
                inline_names = re.findall(r"\*\*([^*]+?)\*\*", line)
                for inline in inline_names:
                    inline = inline.strip()
                    if _looks_like_character_name(inline):
                        name = inline
                        alias = None
                        break

            if not _looks_like_character_name(name):
                continue

            # 保留第一次出现的 status：CAST.md 里霍渊白同时出现在
            # "## 大 Boss · 三段式档案"（明面身份）和 "## 动态出场角色库"
            # 两段——优先保留大 Boss 段的 status
            if name not in cast:
                cast[name] = {
                    "name": name,
                    "alias": alias,
                    "status": status,
                    "source_line": line.strip(),
                    "_path": cast_md_path,
                }

    return cast


def load_cast(root=None):
    """加载角色名册（自动选路径：优先 characters/ 目录；不存在时走 CAST.md）。

    返回 {角色名: meta_dict}。
    - 旧路径（characters/*.md）：每角色必须有 YAML frontmatter，走 schema 校验
    - 新路径（CAST.md）：宽松解析，返回结构化 dict（无 schema 校验）

    天黑之前默认用新路径（CAST.md）。
    """
    if root is None:
        root = os.path.join(os.path.dirname(os.path.dirname(__file__)), "characters")

    # 如果 characters/ 存在且非空，走旧路径
    if os.path.isdir(root) and glob.glob(os.path.join(root, "*.md")):
        cast = {}
        for p in sorted(glob.glob(os.path.join(root, "*.md"))):
            base = os.path.basename(p)
            if base.startswith("_"):
                continue
            meta = parse(p)
            errs = validate(meta)
            if errs:
                raise SoulError(f"{p}: " + "; ".join(errs))
            cast[meta["name"]] = meta
        return cast

    # fallback 到根目录 CAST.md
    project_root = os.path.dirname(os.path.dirname(__file__))
    return load_cast_from_md(root=project_root)


def card(meta):
    """生成可贴给 Claude 的单角色卡（中英混合 + YAML 字段）。"""
    fr = meta["fracture"]
    lines = [
        f"# 角色卡 · {meta['name']}",
        f"**身份**: {meta.get('role', '—')}  |  **状态**: {meta.get('status', '—')}",
        f"**一句话**: {meta['one_line']}",
        "",
        "**驱动力**: " + "；".join(meta.get("drives", [])),
        f"**裂缝**: 嘴上「{fr['says']}」/ 实际「{fr['does']}」",
        f"**被逼到墙角**: {meta['under_pressure']}",
        f"**说话方式**: {meta.get('voice', '—')}",
        f"**边界**: {meta['boundaries']}",
    ]
    if meta.get("signature"):
        lines.append(f"**标志细节**: {meta['signature']}")
    if meta.get("current_state"):
        lines.append(f"**当前状态**: {meta['current_state']}")
    if meta.get("_body"):
        lines.append(f"\n## 底色（前 400 字）\n{meta['_body']}")
    return "\n".join(lines)


def all_cards(root=None):
    """返回所有角色卡的字符串（大块文本，可直接喂给 Claude 当上下文）。"""
    cast = load_cast(root)
    blocks = []
    for name, meta in cast.items():
        blocks.append(card(meta))
        blocks.append("\n---\n")
    return "\n".join(blocks)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        # 单文件模式
        path = sys.argv[1]
        try:
            meta = parse(path)
            errs = validate(meta)
            if errs:
                print(f"✗ {path} 校验失败：")
                for e in errs:
                    print(f"  - {e}")
                sys.exit(1)
            print(card(meta))
        except SoulError as e:
            print(f"✗ {e}")
            sys.exit(1)
    else:
        # 全量模式
        try:
            cast = load_cast()
            print(f"✓ 加载 {len(cast)} 个角色档案")
            for name in cast:
                print(f"  - {name} ({cast[name].get('role', '—')})")
        except SoulError as e:
            print(f"✗ {e}")
            sys.exit(1)