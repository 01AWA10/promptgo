"""质量评分器（启发式）。

说明：这是可解释的规则打分，用于「增强前 vs 增强后」的直观对比与自检提示，
不是模型困惑度或人工评分。所有分值都能追溯到具体规则，便于调参与单测。
"""

from __future__ import annotations

import re

DIM_WEIGHTS = {
    "clarity": 0.22,
    "specificity": 0.22,
    "structure": 0.18,
    "constraints": 0.20,
    "verifiability": 0.18,
}

DIM_LABELS = {
    "clarity": ("清晰度", "clarity"),
    "specificity": ("具体性", "specificity"),
    "structure": ("结构性", "structure"),
    "constraints": ("约束完备", "constraints"),
    "verifiability": ("可验证性", "verifiability"),
}

VAGUE_MARKERS = ("尽量", "大概", "差不多", "一些", "有点", "可能", "等等", "之类",
                 "比较好", "适当", "合理", "相关", "随便", "看情况",
                 "some", "maybe", "kind of", "etc", "appropriate", "reasonable")

ACTION_MARKERS = ("写", "生成", "分析", "实现", "设计", "总结", "翻译", "对比", "评估",
                  "制定", "输出", "解释", "write", "generate", "analyze", "build",
                  "design", "summarize", "translate", "compare", "evaluate", "explain")

CONSTRAINT_MARKERS = ("不超过", "以内", "必须", "禁止", "不得", "只能", "仅", "至少",
                      "字以内", "面向", "语气", "格式", "表格", "json", "markdown",
                      "must", "never", "only", "at most", "format", "tone")

VERIFY_MARKERS = ("验收", "自检", "标准", "示例", "例如", "输出格式", "字段", "检查",
                  "acceptance", "criteria", "example", "self-check", "verify", "format")

# 成品骨架是渲染器显式注入的结构化产出，必须计入评分，
# 否则「加了骨架但分数没涨」会被误读成增强无效。
SKELETON_MARKERS = ("输出骨架", "output skeleton")


def _clamp(value: float) -> int:
    return int(max(0, min(100, round(value))))


def _count(text: str, pool: tuple[str, ...]) -> int:
    lowered = text.lower()
    return sum(1 for w in pool if w in lowered)


def _has_skeleton(text: str) -> bool:
    """标记之后至少两条骨架条目才算数，避免正文里一句「输出骨架」就白拿分。"""
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if any(marker in line.lower() for marker in SKELETON_MARKERS):
            following = lines[idx + 1: idx + 13]
            return sum(1 for item in following if item.lstrip().startswith("- ")) >= 2
    return False


def score(text: str) -> dict:
    """对任意提示词文本打分，返回总分与维度明细。"""
    raw = text or ""
    lowered = raw.lower()
    length = len(raw.strip())

    vague = _count(raw, VAGUE_MARKERS)
    actions = _count(raw, ACTION_MARKERS)
    constraint_hits = _count(raw, CONSTRAINT_MARKERS)
    verify_hits = _count(raw, VERIFY_MARKERS)
    headings = len(re.findall(r"^##\s+", raw, re.M))
    bullets = len(re.findall(r"^\s*[-*]\s+", raw, re.M))
    ordered = len(re.findall(r"^\s*\d+\.\s+", raw, re.M))
    numbers = len(re.findall(r"\d+", raw))
    sentences = len(re.findall(r"[。！？.!?]", raw))

    # 清晰度：长度合理 + 有动作动词 + 少模糊词 + 有标点分句
    clarity = 34
    if 16 <= length <= 2000:
        clarity += 18
    elif length > 2000:
        clarity += 8
    clarity += min(18, actions * 9)
    clarity -= min(24, vague * 7)
    if sentences >= 2:
        clarity += 12
    elif sentences == 1 and length > 60:
        clarity -= 8
    if length < 12:
        clarity -= 18

    # 具体性：数字、实体、专有名词带来的可执行度
    specificity = 26
    specificity += min(26, numbers * 8)
    if re.search(r"[「『“\"'].{2,30}[」』”\"']", raw):
        specificity += 10
    if re.search(r"\b[A-Z][A-Za-z0-9+#.]{2,}\b", raw):
        specificity += 8
    specificity += min(16, (constraint_hits + verify_hits) * 4)
    if length > 120:
        specificity += 6
    specificity -= min(14, vague * 4)

    # 结构性：标题、列表、编号，以及成品骨架是否落地。
    # 上限刻意留在 80 附近：原公式 4 个标题即顶到 100，导致骨架与深度在分数上体现不出来。
    skeleton = _has_skeleton(raw)
    structure = 10
    structure += min(26, headings * 6)
    structure += min(18, bullets * 2)
    structure += min(10, ordered * 2)
    if "\n\n" in raw:
        structure += 4
    if skeleton:
        structure += 12

    # 约束完备
    constraints = 8
    constraints += min(48, constraint_hits * 10)
    if re.search(r"(禁止|不得|不要|do not|never)", raw, re.I):
        constraints += 6
    if re.search(r"(待确认|占位|placeholder|TBD)", raw, re.I):
        constraints += 8
    constraints += min(10, verify_hits * 3)

    # 可验证性
    verifiability = 10
    verifiability += min(34, verify_hits * 9)
    verifiability += min(20, numbers * 5)
    if re.search(r"^##\s*(输出格式|Output format)", raw, re.M):
        verifiability += 12
    if re.search(r"\[ \]", raw):
        verifiability += 10

    dims = {
        "clarity": _clamp(clarity),
        "specificity": _clamp(specificity),
        "structure": _clamp(structure),
        "constraints": _clamp(constraints),
        "verifiability": _clamp(verifiability),
    }
    total = _clamp(sum(dims[k] * w for k, w in DIM_WEIGHTS.items()))
    return {"total": total, "dims": dims, "skeleton": skeleton}


def _grade(total: int, zh: bool) -> str:
    if total >= 85:
        return "可直接执行" if zh else "ready to run"
    if total >= 70:
        return "基本可用，建议补细节" if zh else "usable, refine details"
    if total >= 50:
        return "信息不足，模型输出方差大" if zh else "under-specified, high variance"
    return "过于模糊，几乎不可执行" if zh else "too vague to execute"


def compare(before_text: str, after_text: str, zh: bool = True) -> dict:
    before = score(before_text)
    after = score(after_text)
    dims = []
    for key, weight in DIM_WEIGHTS.items():
        dims.append({
            "key": key,
            "label": DIM_LABELS[key][0 if zh else 1],
            "before": before["dims"][key],
            "after": after["dims"][key],
            "delta": after["dims"][key] - before["dims"][key],
            "weight": weight,
        })
    return {
        "before": before["total"],
        "after": after["total"],
        "delta": after["total"] - before["total"],
        "grade_before": _grade(before["total"], zh),
        "grade_after": _grade(after["total"], zh),
        "skeleton": after["skeleton"],     # 增强结果是否落了成品骨架，供前端/宿主解释分数
        "dims": dims,
    }
