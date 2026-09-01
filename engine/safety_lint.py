# -*- coding: utf-8 -*-
"""天黑之前 · 安全门（确定性卡死硬线）。

移植自旧魂 engine/safety_lint.py：
  · 露骨性行为 → 永久卡死（与 rating 无关）
  · 自我伤害细节 → 永久卡死
  · 未成年角色暧昧身体描写 → 永久卡死

天黑之前的特殊点：
  · 没有「仙侠未成年」角色，但法律 / 案件题材天然有"未达刑事责任年龄"的边缘情况
  · 小说里有未成年（如校园案 / 儿童证人），规则改为：
      "出现与 14 岁以下角色（含 14 岁上下文中）相关的暧昧身体描写" → 永久卡死

用法：
    from safety_lint import check
    issues = check(chapter_body)
    if issues:
        print("硬线违规:", issues)
"""
import re

# 露骨性行为（命中即永久卡死）
EXPLICIT_PATTERNS = [
    (re.compile(r"(?:他|她)\s*插入"), "可能露骨"),
    (re.compile(r"(?:射精|阴茎|阴道|口交|自慰|做爱|性交)"), "可能露骨"),
]

# 自我伤害细节（命中即永久卡死）
SELF_HARM_PATTERNS = [
    (re.compile(r"(?:割腕|割脉|吞药|上吊|跳楼|自杀|自残)"), "可能自伤"),
]

# 全部硬线合并
HARDLINE_PATTERNS = EXPLICIT_PATTERNS + SELF_HARM_PATTERNS

# 未成年暧昧：14 岁以下角色名（关键词触发）
MINOR_INTIMACY = re.compile(
    r"(?:耳根|颈侧|指节|手腕|亲吻|吻|拥抱|抚摸|贴近|暧昧|胸部|大腿)"
)

# 默认未成年角色关键词白名单（按需扩展）
DEFAULT_MINOR_KEYWORDS = (
    "小女孩", "男孩", "女儿", "儿子", "弟弟", "妹妹", "侄子", "侄女",
    "儿童", "小孩", "少女", "少年", "初中生", "小学生", "高中生",
)


def check(text, minor_keywords=None):
    """Return hardline violations; empty means no deterministic hit.

    Args:
        text: 章节正文
        minor_keywords: 触发未成年卡门的关键词元组；None = 用 DEFAULT_MINOR_KEYWORDS
    """
    issues = []
    for pattern, description in HARDLINE_PATTERNS:
        if pattern.search(text):
            issues.append(description)

    keys = minor_keywords if minor_keywords is not None else DEFAULT_MINOR_KEYWORDS
    for name in keys or ():
        if name and re.search(
            re.escape(name) + r"[^。！？\n]{0,60}" + MINOR_INTIMACY.pattern,
            text,
        ):
            issues.append(f"未成年/边缘角色「{name}」不得出现暧昧身体描写")

    return list(dict.fromkeys(issues))


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python engine/safety_lint.py <chapter.md>")
        sys.exit(1)
    text = open(sys.argv[1], encoding="utf-8").read()
    issues = check(text)
    if issues:
        print("✗ 硬线违规：")
        for i in issues:
            print(f"  - {i}")
        sys.exit(1)
    print("✓ 安全门通过")