"""结构化渲染器：把分析结果 + 模板 + 模式 组装为最终提示词文本。

输出是「分节 + 分块」的，便于上层按块流式推送。
纯函数：同样的输入永远得到同样的输出。
"""

from __future__ import annotations

from dataclasses import dataclass

from .analyzer import Analysis
from .templates import DOMAIN_HINTS, MODE_HINTS, OUTLINES, TEMPLATES

INTENT_VERB = {
    "coding": ("实现", "implement"),
    "marketing": ("撰写", "write"),
    "analysis": ("完成", "produce"),
    "summarize": ("提炼", "distill"),
    "translate": ("翻译", "translate"),
    "plan": ("制定", "produce"),
    "writing": ("撰写", "write"),
    "qa": ("解释", "explain"),
    "agent": ("设计", "design"),
    "review": ("审查", "review"),
    "product": ("起草", "draft"),
    "general": ("完成", "complete"),
}

INTENT_DELIVERABLE = {
    "coding": ("可直接运行的代码与验证步骤", "runnable code plus verification steps"),
    "marketing": ("可直接投放的文案与备选标题", "publish-ready copy and alternative headlines"),
    "analysis": ("带证据与假设标注的分析结论", "conclusions with explicit evidence and assumptions"),
    "summarize": ("分层要点摘要", "hierarchical summary"),
    "translate": ("保留格式的高质量译文", "high-quality translation with formatting preserved"),
    "plan": ("可执行方案（含负责人与验收标准）", "actionable plan with owners and acceptance criteria"),
    "writing": ("完整成稿", "finished draft"),
    "qa": ("由浅入深的结构化解释", "layered explanation from intuition to rigor"),
    "agent": ("可直接使用的智能体系统提示词", "ready-to-use system prompt for an agent"),
    "review": ("带优先级的问题清单与修复建议", "prioritized issue list with concrete fixes"),
    "product": ("可直接评审的需求文档", "review-ready requirement document"),
    "general": ("可直接使用的交付物", "directly usable deliverable"),
}


@dataclass
class Profile:
    mode: str = "struct"
    lang: str = "zh"
    intensity: str = "standard"
    fmt: str = "markdown"

    @property
    def zh(self) -> bool:
        return self.lang == "zh"


def _topic(analysis: Analysis) -> str:
    if analysis.topic:
        return analysis.topic
    if analysis.entities:
        return "、".join(analysis.entities[:2])
    text = analysis.text.replace("\n", " ").strip()
    return text[:24] + ("…" if len(text) > 24 else "")


def _audience(analysis: Analysis, zh: bool) -> str:
    values = analysis.constraint_values("audience")
    if values:
        return values[0]
    return "目标读者（待确认）" if zh else "target reader (to be confirmed)"


def _length(analysis: Analysis, zh: bool) -> str:
    values = analysis.constraint_values("length")
    return values[0] if values else ("未限定（建议 300–800 字）" if zh else "unspecified (300-800 words suggested)")


def _format(analysis: Analysis, profile: Profile) -> str:
    values = analysis.constraint_values("format")
    zh = profile.zh
    if values:
        return values[0]
    tpl = TEMPLATES.get(analysis.intent, TEMPLATES["general"])
    return tpl["output_zh" if zh else "output_en"]


def _quote_source(text: str, zh: bool, limit: int = 120) -> str:
    """引用原始需求时压缩空白并截断，避免长输入把目标段撑成原文副本。"""
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    return flat[:limit] + ("…" if zh else "...")


def _objective(analysis: Analysis, profile: Profile) -> str:
    zh = profile.zh
    idx = 0 if zh else 1
    verb = INTENT_VERB[analysis.intent][idx]
    deliverable = INTENT_DELIVERABLE[analysis.intent][idx]
    topic = _topic(analysis)
    audience = _audience(analysis, zh)
    source = _quote_source(analysis.text, zh)
    if zh:
        return (
            f"围绕「{topic}」，{verb}{deliverable}，供{audience}使用。\n"
            f"原始需求：{source}"
        )
    return (
        f'Around "{topic}", {verb} a {deliverable} for {audience}.\n'
        f"Original request: {source}"
    )


def _context(analysis: Analysis, profile: Profile) -> str:
    zh = profile.zh
    lines: list[str] = []
    lines.append(("任务类型：" if zh else "Task type: ") + analysis.intent_label
                 + ("｜领域：" if zh else " | domain: ") + analysis.domain_label)
    if analysis.constraints:
        pairs = [f"{c.label}={c.value}" for c in analysis.constraints]
        prefix = "已知约束：" if zh else "Known constraints: "
        lines.append(prefix + "；".join(pairs))
    if analysis.entities:
        prefix = "关键实体：" if zh else "Key entities: "
        lines.append(prefix + "、".join(analysis.entities))
    if analysis.keywords:
        prefix = "关键词：" if zh else "Keywords: "
        lines.append(prefix + "、".join(analysis.keywords[:6]))
    if not analysis.entities and not analysis.constraints and len(analysis.text) < 40:
        lines.append("（原始信息较少，以下按可执行的最保守假设推进）" if zh
                     else "(Sparse input; proceeding on the most conservative executable assumptions)")
    return "\n".join(f"- {line}" for line in lines)


def _steps(analysis: Analysis, profile: Profile) -> str:
    zh = profile.zh
    tpl = TEMPLATES.get(analysis.intent, TEMPLATES["general"])
    steps = tpl["steps_zh" if zh else "steps_en"]
    if profile.intensity == "light":
        steps = steps[:3]
    elif profile.intensity == "deep":
        extra_zh = "补充：给出 1 组反例或失败案例，说明在什么情况下该做法不成立。"
        extra_en = "Extra: include one counter-example showing when the approach fails."
        steps = list(steps) + [extra_zh if zh else extra_en]
    lines = [f"{i}. {s}" for i, s in enumerate(steps, 1)]

    # 骨架细化：步骤回答「怎么做」，骨架回答「成品长什么样」。
    # concise 模式只保留过程步骤，避免与「极致精简」的定位冲突。
    entry = OUTLINES.get(analysis.intent) or OUTLINES.get("general") or {}
    outline = entry.get("zh" if zh else "en") or []
    if outline and profile.mode != "concise":
        lines.append("")
        lines.append("输出骨架（成品按此顺序成文，不得跳节）：" if zh
                     else "Output skeleton (write in this order, skip no section):")
        lines.extend(f"- {item}" for item in outline)
    return "\n".join(lines)


def _constraints(analysis: Analysis, profile: Profile) -> str:
    zh = profile.zh
    items: list[str] = []

    for c in analysis.constraints:
        if c.kind == "length":
            items.append(f"篇幅：{c.value}" if zh else f"Length: {c.value}")
        elif c.kind == "tone":
            items.append(f"语气：{c.value}，全篇保持一致" if zh else f"Tone: {c.value}, consistent throughout")
        elif c.kind == "channel":
            items.append(f"渠道适配：{c.value}，开头需符合该渠道的阅读习惯" if zh
                         else f"Channel fit: {c.value}; hook must match that channel's habits")
        elif c.kind == "language":
            items.append(f"输出语言：{c.value}" if zh else f"Output language: {c.value}")

    domain_hint = DOMAIN_HINTS.get(analysis.domain, DOMAIN_HINTS["general"])
    if domain_hint["zh" if zh else "en"]:
        items.append(domain_hint["zh" if zh else "en"])

    mode_hint = MODE_HINTS.get(profile.mode)
    if mode_hint:
        items.append(mode_hint["zh" if zh else "en"])

    if zh:
        items.extend([
            "不得编造事实、数据、引用或链接；确需使用但无法确认时，写成【待确认：xxx】占位。",
            "不确定的地方明确说明不确定性来源，不要用模糊措辞掩盖。",
            "不输出与任务无关的寒暄、免责声明与自我评价。",
        ])
    else:
        items.extend([
            "Do not fabricate facts, figures, citations or links; use [TBD: ...] placeholders instead.",
            "State the source of any uncertainty instead of hedging.",
            "No pleasantries, disclaimers or self-evaluation unrelated to the task.",
        ])
    return "\n".join(f"- {i}" for i in items)


def _output_contract(analysis: Analysis, profile: Profile) -> str:
    zh = profile.zh
    lines = [_format(analysis, profile)]
    lines.append(("篇幅：" if zh else "Length: ") + _length(analysis, zh))
    if zh:
        lines.append("层级：最多使用两级标题；要点用有序/无序列表，不要嵌套超过两层。")
    else:
        lines.append("Hierarchy: at most two heading levels; bullets not nested deeper than two levels.")
    return "\n".join(f"- {line}" for line in lines)


def _selfcheck(analysis: Analysis, profile: Profile) -> str:
    tpl = TEMPLATES.get(analysis.intent, TEMPLATES["general"])
    zh = profile.zh
    checks = list(tpl["selfcheck_zh" if zh else "selfcheck_en"])
    checks += (["所有【待确认】项已显式列出", "结论与约束之间无冲突"] if zh
               else ["All [TBD] items are explicitly listed", "No conflict between output and constraints"])
    return "\n".join(f"- [ ] {c}" for c in checks)


def _open_questions(analysis: Analysis, profile: Profile) -> str:
    zh = profile.zh
    if not analysis.missing:
        return ("- 现有信息已足够，可直接执行；若与事实不符请指出，我将按修正后的前提重做。" if zh
                else "- Enough information to proceed. Flag any factual mismatch and I will redo it.")
    return "\n".join(f"- {m['question']}" for m in analysis.missing)


def _risks(analysis: Analysis, profile: Profile) -> str:
    zh = profile.zh
    if not analysis.risks:
        return ("- 未发现明显歧义；如结果偏离预期，请指出具体偏差处。" if zh
                else "- No obvious ambiguity detected.")
    lines = [f"- ({r['level']}) {r['text']}" for r in analysis.risks]
    return "\n".join(lines)


SECTION_TITLES = {
    "role": ("角色", "Role"),
    "objective": ("目标", "Objective"),
    "context": ("背景与已知信息", "Context"),
    "steps": ("任务拆解", "Task breakdown"),
    "constraints": ("约束条件", "Constraints"),
    "output": ("输出格式", "Output format"),
    "selfcheck": ("质量自检", "Quality self-check"),
    "questions": ("待确认信息（不足时先追问，不要臆测）", "Open questions (ask, do not assume)"),
    "risks": ("风险提示", "Risk notes"),
}

_BLOCK_TITLES_ZH = {
    "role": "角色", "objective": "目标", "context": "背景与已知信息", "steps": "任务拆解",
    "constraints": "约束条件", "output": "输出格式", "selfcheck": "质量自检",
    "questions": "待确认信息（信息不足时先追问）", "risks": "风险提示",
}
_BLOCK_TITLES_EN = {
    "role": "Role", "objective": "Objective", "context": "Context", "steps": "Task breakdown",
    "constraints": "Constraints", "output": "Output format", "selfcheck": "Quality self-check",
    "questions": "Open questions (ask before assuming)", "risks": "Risk notes",
}


def build_blocks(analysis: Analysis, profile: Profile) -> list[dict]:
    """返回分块列表：[{key, title, body}]，顺序即最终文本顺序。"""
    zh = profile.zh
    tpl = TEMPLATES.get(analysis.intent, TEMPLATES["general"])

    bodies = {
        "role": tpl["role_zh" if zh else "role_en"],
        "objective": _objective(analysis, profile),
        "context": _context(analysis, profile),
        "steps": _steps(analysis, profile),
        "constraints": _constraints(analysis, profile),
        "output": _output_contract(analysis, profile),
        "selfcheck": _selfcheck(analysis, profile),
        "questions": _open_questions(analysis, profile),
        "risks": _risks(analysis, profile),
    }

    if profile.mode == "concise":
        order = ["role", "objective", "steps", "constraints", "output"]
    elif profile.intensity == "light":
        order = ["role", "objective", "steps", "output"]
    elif profile.intensity == "deep":
        order = ["role", "objective", "context", "steps", "constraints", "output",
                 "selfcheck", "questions", "risks"]
    else:
        order = ["role", "objective", "context", "steps", "constraints", "output",
                 "selfcheck", "questions"]

    blocks = []
    for key in order:
        titles = _BLOCK_TITLES_ZH if zh else _BLOCK_TITLES_EN
        blocks.append({"key": key, "title": titles[key], "body": bodies[key]})
    return blocks


def assemble(blocks: list[dict], fmt: str = "markdown") -> str:
    if fmt == "text":
        return "\n\n".join(f"【{b['title']}】\n{b['body']}" for b in blocks)
    return "\n\n".join(f"## {b['title']}\n\n{b['body']}" for b in blocks)


def to_plain(blocks: list[dict]) -> str:
    return "\n\n".join(f"{b['title']}\n{b['body']}" for b in blocks)
