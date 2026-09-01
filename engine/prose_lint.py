# -*- coding: utf-8 -*-
"""天黑之前 · 文笔自动审计（prose quality gate）。

移植自旧魂《众魂》open-souls 的 engine/prose_lint.py，已按天黑之前的需求重写：

  · 路径：Chapter_NN.md（两位补零，从 01 开始；不是 ch001-标题.md）
  · 字数：v3.1 = 纯字 [1800, 2200]，中位 2000（用户 2026/8/31 决策；
          降字以保证 Cline 输出质量；不是旧魂的 1500，也不是 v3 的 2500-3000）
  · 章节结构：从「## 二」标题行到下一个「---」分隔符（沿用 chapter_stats.ps1）
  · 8 大硬禁令：替换旧魂的「方向/朝/那一X」病句为天黑之前的禁词
  · 视角规则：第三人称有限（杜绝上帝视角）
  · 一案一结：单章核心涉案人物 ≤ 3（核心硬门）
  · 4.13 节终极禁令：否定对比 / 弱转折 / 一句一动作 / 纯台词对话

两档：
  ERROR  ——退回。卡的是已经垮掉的机械腔或硬门违反。
  WARN   ——提个醒。卡的是离"好文笔"还有距离、但还没垮的章节。

用法：
    python engine/prose_lint.py                          # 扫全部
    python engine/prose_lint.py chapters/Chapter_05.md   # 只扫指定文件
    python engine/prose_lint.py --warn-as-error          # WARN 也当失败（更严）
    python engine/prose_lint.py --strict-editorial       # 严格 editorial（额外卡回声）
"""
import os
import re
import sys
import glob
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHAPTERS_DIR = ROOT / "chapters"

# ---- 阈值 ----
# v3.1（2026/8/31 用户最新决策）：[1800, 2200] 中位 2000，保证 Cline 输出质量
MIN_CHAPTER_CHARS = 1800        # 纯字下限
TARGET_CHAPTER_CHARS = 2200     # 纯字上限
WIDEN_LOW = 1600                # 容忍下沿
WIDEN_HIGH = 2400               # 容忍上沿

# 微碎片率与段长（沿用旧魂值，对网文节奏也适用）
MICRO_ERROR = 0.42
MICRO_WARN = 0.30
AVGSEG_ERROR = 3.5
AVGSEG_WARN = 4.5
DASH_PARAGRAPH_ERROR = 5        # 单段破折号上限

# 8 大硬禁令相关阈值
AI_TONE_ERROR = 3               # AI 机械衔接词 / 高频词超此数即 ERROR
TEMPLATE_VERB_ERROR = 2         # "他XX地说/XX地看着"模板动作
UNREASONABLE_NUMBER_ERROR = 2   # 强迫症式精确数字（精确到分秒的描写）

# ---- 字符类正则 ----
SEG_SPLIT = re.compile(r"[，。！？、：；\n]")
HAN = re.compile(r"[一-鿿]")

# ============================================================
# 1. 8 大硬禁令禁词（移植自 .clinerules 第 4.3 节）
# ============================================================

# 机械衔接词（绝对禁词）
AI_CONNECTOR_WORDS = [
    "只见", "只见他", "就在这时", "片刻后", "随即", "于是", "因此",
    "不由得", "不禁", "似乎", "仿佛", "好像", "似乎是", "仿佛是",
]
AI_CONNECTOR_RE = re.compile("|".join(re.escape(w) for w in AI_CONNECTOR_WORDS))

# 无效副词（绝对禁词）
AI_FILLER_ADVS = ["非常", "极其", "格外", "稍稍", "默默"]
AI_FILLER_ADV_RE = re.compile("|".join(re.escape(w) for w in AI_FILLER_ADVS))

# 高频 AI 词
AI_HIGHFREQ_WORDS = ["眼眸", "唇角", "身形", "骤然"]
AI_HIGHFREQ_RE = re.compile("|".join(re.escape(w) for w in AI_HIGHFREQ_WORDS))

# 模板化对话动作："他XX地说" / "XX地看着" / "XX地走过去"
TEMPLATE_VERB_RE = re.compile(
    r"[一-鿿]{1,4}"                       # 主语（他/她/轩宁/沈夜...）
    r"(?:[一-鿿]{0,2})?"                  # 可选修饰
    r"(?:地说|说着|看向|看着|望着|走过去|走开|问道|问)"
)

# 强迫症式精确数字（"距离他七点三十二分......"）
UNREASONABLE_NUMBER_RE = re.compile(
    r"(?:零点[零一二三四五六七八九]+分?|"
    r"[一二三四五六七八九十百]+点[零一二三四五六七八九]+分|"
    r"精确到[零一二三四五六七八九]+位|"
    r"分秒不差)"
)

# ============================================================
# 1b. 4.13 节终极禁令：否定对比 / 弱转折 / 一句一动作
# ============================================================

# 否定对比句式（"没有…没有…" / "不是…而是…" / "并非…而是…" / "没有…只是…" / "没有…也没有…"）
NEGATIVE_CONTRAST_RE = re.compile(
    r"(?:没有[^。！？\n]{0,15}没有|"
    r"不是[^。！？\n]{0,15}而是|"
    r"并非[^。！？\n]{0,15}而是|"
    r"没有[^。！？\n]{0,15}只是|"
    r"没有[^。！？\n]{0,15}也没有|"
    r"不是[^。！？\n]{0,15}就是)"
)

# 弱转折句式（"虽然…但是…" / "尽管…却…" / "并非…却…" / "甚至…没有…"）
WEAK_TRANSITION_RE = re.compile(
    r"(?:虽然[^。！？\n]{0,15}但是|"
    r"尽管[^。！？\n]{0,15}却|"
    r"并非[^。！？\n]{0,15}却|"
    r"甚至[^。！？\n]{0,15}没有|"
    r"就算[^。！？\n]{0,15}也|"
    r"即使[^。！？\n]{0,15}也)"
)

# 一句一动作（连续多个 "她/他 + 短动作 + 。" 句式）
ONE_SENTENCE_ONE_ACTION_RE = re.compile(
    r"(?:[她他][^。！？\n]{0,6}[了着过][^。！？\n]{0,6}[。！？])"
    r"(?:[她他][^。！？\n]{0,6}[了着过][^。！？\n]{0,6}[。！？])"
    r"(?:[她他][^。！？\n]{0,6}[了着过][^。！？\n]{0,6}[。！？])"
)

# 纯台词对话（连续 3+ 句纯台词，无配套描写）
# 简化检测：一行内只有引号内容
DIALOGUE_ONLY_LINE_RE = re.compile(
    r"^[「『\"][^」』\"]{1,50}[」』\"][。]?$",
    re.M,
)

# ============================================================
# 2. 视角与叙事硬门（移植自 .clinerules 第 4.1 节）
# ============================================================

# 上帝视角泄漏
GOD_VIEW_RE = re.compile(
    r"(?:读者们都知道|所有人都知道|事实上|其实[一-鿿]{0,8}并不知道|"
    r"原来[一-鿿]{0,8}(?:一直|早就|从来))"
)

# 内心独白泄漏（聚焦角色不该感知到的他人心理）
INNER_LEAK_RE = re.compile(
    r"[一-鿿]{1,4}(?:心里|心中|暗想|暗自)想[：:]?"
    r"(?=[一-鿿]{0,30}(?:她|他)(?:其实|根本|一直))"
)

# ============================================================
# 3. 旧魂移植的文笔维度正则
# ============================================================

# 填充描写
FILLER = [
    re.compile(r"(?:屋里|院中|院子里|院里|屋内|屋子里|厅里|廊下|廊里|门外|"
               r"四周|周遭|巷子里|空气里?|气氛中|夜|风)"
               r"[^一-鿿]{0,3}"
               r"(?:很\s*|十分\s*|格外\s*|异常\s*|死一般\s*)?"
               r"(?:安静|寂静|静悄悄|静得|悄|凝重|沉静)"),
    re.compile(r"(?:周围|四周)\s*(?:很\s*|一片\s*)?(?:安静|寂静|静悄悄)"),
]
FILLER_HEART = re.compile(r"心里\s*(?:咚|扑通|咯噔)(?:\s*(?:一?[下了]?[一下跳])?)?")

# 旧魂的「方向/朝」病句（保留为 WARN）
DIRECTION_FORMULA = re.compile(
    r"(?:[一-鿿]{1,8}的?)?方向(?:朝(?:向|着)|落在|落下|不必替|是)"
)

# ============================================================
# 4. 章节结构解析（沿用 chapter_stats.ps1 的 Extract-Body 逻辑）
# ============================================================

def body_of(text):
    """从 Chapter_NN.md 提取正文段。

    兼容 v3.1 新结构（2026/8/31 三次修订后）：纯正文 + 章末散文式自查段，无小标题。

    提取规则（按优先级）：
      1. 老结构兼容：找「## 二」标题行之后、下一个「---」分隔符之前的段落
      2. 新结构：找「本章自查」之前的全文（章末散文式自查段从该关键字起算）
      3. 兜底：返回全文
    """
    if text.startswith("\ufeff"):
        text = text[1:]
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 规则 1：老结构（## 二 ... ---）
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
    if start >= 0 and end > start:
        return "\n".join(lines[start:end])

    # 规则 2：新结构（散文式自查段以"本章自查"开头）—— 切掉自查段
    self_check_markers = ["本章自查", "本章自检", "本章自校"]
    for marker in self_check_markers:
        idx = text.find(marker)
        if idx > 0:
            return text[:idx].rstrip()

    # 规则 3：兜底
    return text


def chapter_number(path):
    """Chapter_NN.md -> N (int)"""
    m = re.search(r"Chapter_(\d+)", os.path.basename(str(path)))
    return int(m.group(1)) if m else None


def measure(body):
    """返回所有度量值。"""
    han = HAN.findall(body)
    chars = len(han)
    segs = [s for s in SEG_SPLIT.split(body) if HAN.search(s)]
    seglens = [len(HAN.findall(s)) for s in segs]
    micro = (sum(1 for L in seglens if 1 <= L <= 3) / len(seglens)) if seglens else 0.0
    avg = (sum(seglens) / len(seglens)) if seglens else 99.0
    filler = sum(len(p.findall(body)) for p in FILLER) + len(FILLER_HEART.findall(body))
    paragraphs = [p for p in body.split("\n\n") if p.strip()]
    dash_max = max((p.count("——") for p in paragraphs), default=0)

    ai_connector_hits = AI_CONNECTOR_RE.findall(body)
    ai_filler_adv_hits = AI_FILLER_ADV_RE.findall(body)
    ai_highfreq_hits = AI_HIGHFREQ_RE.findall(body)
    template_verb_hits = TEMPLATE_VERB_RE.findall(body)
    unreasonable_num_hits = UNREASONABLE_NUMBER_RE.findall(body)

    god_view_hits = GOD_VIEW_RE.findall(body)
    inner_leak_hits = INNER_LEAK_RE.findall(body)

    direction_formula = DIRECTION_FORMULA.findall(body)

    # 4.13 节终极禁令
    negative_contrast_hits = NEGATIVE_CONTRAST_RE.findall(body)
    weak_transition_hits = WEAK_TRANSITION_RE.findall(body)
    one_action_hits = ONE_SENTENCE_ONE_ACTION_RE.findall(body)
    dialogue_only_hits = DIALOGUE_ONLY_LINE_RE.findall(body)

    return {
        "chars": chars,
        "micro": micro,
        "avg": avg,
        "filler": filler,
        "dash_max": dash_max,
        "ai_connector": len(ai_connector_hits),
        "ai_filler_adv": len(ai_filler_adv_hits),
        "ai_highfreq": len(ai_highfreq_hits),
        "template_verb": len(template_verb_hits),
        "unreasonable_num": len(unreasonable_num_hits),
        "god_view": len(god_view_hits),
        "inner_leak": len(inner_leak_hits),
        "direction_formula": len(direction_formula),
        "negative_contrast": len(negative_contrast_hits),
        "weak_transition": len(weak_transition_hits),
        "one_action": len(one_action_hits),
        "dialogue_only_lines": len(dialogue_only_hits),
    }


def lint_text(text, strict=False):
    """对一章正文做全维度检查，返回 (errors, warns, metrics)。"""
    body = body_of(text)
    m = measure(body)
    errors = []
    warns = []

    if m["chars"] < 50:
        return errors, warns, m

    # ---- 字数硬门（v3.1 标准：保证 Cline 输出质量）----
    if m["chars"] < MIN_CHAPTER_CHARS:
        errors.append(
            f"字数不足：{m['chars']} 字 < v3.1 下限 {MIN_CHAPTER_CHARS}。"
            f"补足场景/心理/伏笔，禁止以短章形式定稿"
        )
    elif m["chars"] > TARGET_CHAPTER_CHARS:
        errors.append(
            f"字数超标：{m['chars']} 字 > v3.1 上限 {TARGET_CHAPTER_CHARS}。"
            f"精简冗余废话（删雾/风堆砌、合并近似描写），保留钩子"
        )
    elif m["chars"] < WIDEN_LOW or m["chars"] > WIDEN_HIGH:
        warns.append(
            f"字数偏离 v3.1 区间 [{MIN_CHAPTER_CHARS}, {TARGET_CHAPTER_CHARS}]"
            f"→ 容忍区间 [{WIDEN_LOW}, {WIDEN_HIGH}]，自查是否需要调整"
        )

    # ---- 节奏硬门 ----
    if m["micro"] > MICRO_ERROR:
        errors.append(
            f"逗号碎句：微碎片率 {m['micro']*100:.0f}% > {MICRO_ERROR*100:.0f}%，"
            f"把一两字一顿的碎句合成通顺短句"
        )
    if m["avg"] < AVGSEG_ERROR:
        errors.append(
            f"逗号碎句：平均段长 {m['avg']:.1f} < {AVGSEG_ERROR}，句子被剁太碎"
        )
    if m["filler"] > 0:
        errors.append(
            f"填充描写：{m['filler']} 处「屋里安静/夜很静/心里咚」——"
            f"删了，或换成具体写景写人"
        )
    if m["dash_max"] >= DASH_PARAGRAPH_ERROR:
        errors.append(
            f"破折号过载：单段最多 {m['dash_max']} 个「——」>={DASH_PARAGRAPH_ERROR}，"
            f"节奏被拖成散文诗，分段或换叙述"
        )

    # ---- 8 大硬禁令 ----
    if m["ai_connector"] >= AI_TONE_ERROR:
        errors.append(
            f"机械衔接词：{m['ai_connector']} 处 AI 禁词"
            f"（只见/就在这时/片刻后/随即/于是/因此/不由得/不禁/似乎/仿佛/好像）。"
            f"删掉或换成具体动作"
        )
    elif m["ai_connector"] > 0:
        warns.append(f"机械衔接词 {m['ai_connector']} 处（临界），自查是否开始染病")

    if m["ai_filler_adv"] >= AI_TONE_ERROR:
        errors.append(
            f"无效副词：{m['ai_filler_adv']} 处（非常/极其/格外/稍稍/默默）"
            f"——用具体动作/细节替代"
        )

    if m["ai_highfreq"] >= AI_TONE_ERROR:
        errors.append(
            f"高频词：{m['ai_highfreq']} 处「眼眸/唇角/身形/骤然」——"
            f"替换为差异化精准词汇"
        )

    if m["template_verb"] >= TEMPLATE_VERB_ERROR:
        errors.append(
            f"模板化对话动作：{m['template_verb']} 处「他XX地说/XX地看着」"
            f"——千人一面的对话动作模板一律禁用"
        )

    if m["unreasonable_num"] >= UNREASONABLE_NUMBER_ERROR:
        errors.append(
            f"强迫症式精确数字：{m['unreasonable_num']} 处——"
            f"刑侦可写精确，但要服务剧情，不为精确而精确"
        )

    # ---- 视角硬门 ----
    if m["god_view"] > 0:
        errors.append(
            f"上帝视角泄漏：{m['god_view']} 处（读者们都知道/事实上/原来......）。"
            f"严格第三人称有限视角，不直接交代未感知信息"
        )

    if m["inner_leak"] > 0:
        errors.append(
            f"内心独白泄漏：{m['inner_leak']} 处。"
            f"严禁泄露聚焦角色听不到/看不到的他人心理"
        )

    # ---- 4.13 节终极禁令 ----
    if m["negative_contrast"] > 0:
        errors.append(
            f"否定对比句式：{m['negative_contrast']} 处（没有…没有…/不是…而是…/并非…而是…/没有…只是…）。"
            f"改用正向陈述或具体动作"
        )

    if m["weak_transition"] > 0:
        errors.append(
            f"弱转折句式：{m['weak_transition']} 处（虽然…但是…/尽管…却…/甚至…没有…）。"
            f"删掉转折连词或用具体动作过渡"
        )

    if m["one_action"] > 0:
        errors.append(
            f"一句一动作：{m['one_action']} 处连续「她/他+短动作+。」句式。"
            f"把多个短动作合并为连贯动作链，或穿插感官/心理"
        )

    if m["dialogue_only_lines"] >= 5:
        warns.append(
            f"纯台词行：{m['dialogue_only_lines']} 行只有引号内容。"
            f"台词需配套「语气+神态+动作+心理」四件套（.clinerules 4.7.2）"
        )

    # ---- 旧魂移植（保留为 WARN）----
    if m["direction_formula"] >= 3:
        warns.append(
            f"句式回环：{m['direction_formula']} 处「X 的方向朝着/落在」"
            f"同构句式，疑似生成循环"
        )

    # ---- Strict Editorial 模式 ----
    if strict:
        self_claim = len(re.findall(r"(?:我|他|她)自己", body))
        if self_claim >= 18:
            errors.append(
                f"自我承担回环：{self_claim} 处「我/他/她自己」后置解释"
            )
        motif_slot = len(re.findall(r"那一(?:寸|截|道|笔|层|行|刻|处|回|端|角|点)", body))
        if motif_slot >= 30:
            errors.append(f"物象位置回环：{motif_slot} 处「那一X」位置短语")

    # ---- WARN 级微调 ----
    if not errors:
        if m["micro"] > MICRO_WARN:
            warns.append(f"微碎片率 {m['micro']*100:.0f}% 偏高(>{MICRO_WARN*100:.0f}%)，可再揉顺")
        if m["avg"] < AVGSEG_WARN:
            warns.append(f"平均段长 {m['avg']:.1f} 偏短(<{AVGSEG_WARN})")

    return errors, warns, m


def lint_file(path, strict=False):
    text = open(path, encoding="utf-8").read()
    return lint_text(text, strict=strict)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    flags = {a for a in sys.argv[1:] if a.startswith("-")}
    warn_as_error = "--warn-as-error" in flags
    strict = "--strict-editorial" in flags

    if args:
        targets = args
    else:
        targets = sorted(glob.glob(str(CHAPTERS_DIR / "Chapter_*.md")))

    bad = False
    n_err = 0
    n_warn = 0
    for p in targets:
        if not os.path.isfile(p):
            print(f"✗ {p}: 文件不存在")
            n_err += 1
            bad = True
            continue
        errors, warns, m = lint_file(p, strict=strict)
        rel = os.path.relpath(p, ROOT)
        if errors:
            bad = True
            n_err += 1
            print(f"[X] {rel}  (pure_chars={m['chars']}, range [{MIN_CHAPTER_CHARS}, {TARGET_CHAPTER_CHARS}])")
            for e in errors:
                print(f"   ERROR  {e}")
            for w in warns:
                print(f"   warn   {w}")
        elif warns:
            n_warn += 1
            print(f"[!] {rel}  (pure_chars={m['chars']}, range [{MIN_CHAPTER_CHARS}, {TARGET_CHAPTER_CHARS}])")
            for w in warns:
                print(f"   warn   {w}")
            if warn_as_error:
                bad = True
        else:
            print(f"[OK] {rel}  (pure_chars={m['chars']}, range [{MIN_CHAPTER_CHARS}, {TARGET_CHAPTER_CHARS}])")

    total = len(targets)
    print(f"\nScanned {total} chapters: {n_err} ERROR, {n_warn} WARN.")
    if bad:
        print("FAIL: fix ERROR first, then WARN.")
        sys.exit(1)
    print("PASS.")


if __name__ == "__main__":
    main()