"""增强流水线：analyze → plan → render → score。

同一份逻辑同时服务于「一次性 JSON」与「SSE 流式」两个接口，
保证两条链路输出完全一致（流式只是把 blocks 切片推出去）。
"""

from __future__ import annotations

import time
from typing import Iterator

from .analyzer import (
    CHANNEL_WORDS, DOMAIN_KEYWORDS, DOMAIN_LABEL, INTENT_KEYWORDS, INTENT_LABEL,
    TONE_WORDS, analyze,
)
from .renderer import Profile, assemble, build_blocks
from .scorer import compare
from .templates import MODE_HINTS

MAX_CHARS = 8000
VALID_MODES = ("struct", "concise", "creative", "academic", "code", "agent")
VALID_INTENSITY = ("light", "standard", "deep")
VALID_FORMATS = ("markdown", "text")
CHUNK_SIZE = 160


class EnhanceError(Exception):
    """带错误码的业务异常，由 HTTP 层翻译为 JSON 错误响应。"""

    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def normalize(payload: dict | None, max_chars: int = MAX_CHARS) -> dict:
    """校验与归一化。`max_chars` 由调用方注入，便于服务端按启动参数调整上限。"""
    payload = payload or {}
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise EnhanceError("EMPTY_INPUT", "text 不能为空", 422)
    text = text.strip()
    if len(text) > max_chars:
        text = text[:max_chars]

    mode = str(payload.get("mode") or "struct").lower()
    if mode not in VALID_MODES:
        mode = "struct"

    intensity = str(payload.get("intensity") or "standard").lower()
    if intensity not in VALID_INTENSITY:
        intensity = "standard"

    fmt = str(payload.get("format") or "markdown").lower()
    if fmt not in VALID_FORMATS:
        fmt = "markdown"

    lang = str(payload.get("lang") or "auto").lower()
    if lang not in ("auto", "zh", "en"):
        lang = "auto"

    return {"text": text, "mode": mode, "intensity": intensity,
            "format": fmt, "lang": lang, "truncated": len(payload.get("text") or "") > max_chars}


def _run(text: str, mode: str, intensity: str, fmt: str, lang: str):
    analysis = analyze(text, lang)
    profile = Profile(mode=mode, lang=analysis.lang, intensity=intensity, fmt=fmt)
    blocks = build_blocks(analysis, profile)
    enhanced = assemble(blocks, fmt)
    return analysis, profile, blocks, enhanced


def enhance(payload: dict | None, max_chars: int = MAX_CHARS) -> dict:
    opts = normalize(payload, max_chars)
    started = time.perf_counter()
    analysis, profile, blocks, enhanced = _run(
        opts["text"], opts["mode"], opts["intensity"], opts["format"], opts["lang"])
    score = compare(opts["text"], enhanced, profile.zh)
    return {
        "original": opts["text"],
        "enhanced": enhanced,
        "analysis": analysis.as_dict(),
        "profile": {"mode": profile.mode, "intensity": profile.intensity,
                    "lang": profile.lang, "format": profile.fmt},
        "score": score,
        "blocks": blocks,
        "truncated": opts["truncated"],
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def _chunk_text(text: str, size: int = CHUNK_SIZE) -> Iterator[str]:
    """按行优先切片，尽量不把一行劈断，保证前端逐字渲染时行结构稳定。"""
    buf = ""
    for line in text.splitlines(keepends=True):
        if len(buf) + len(line) > size and buf:
            yield buf
            buf = ""
        buf += line
        while len(buf) > size * 2:
            yield buf[:size]
            buf = buf[size:]
    if buf:
        yield buf


def stream(payload: dict | None, pace: float = 0.006,
           max_chars: int = MAX_CHARS) -> Iterator[tuple[str, dict]]:
    opts = normalize(payload, max_chars)
    started = time.perf_counter()

    yield "stage", {"stage": "analyze", "progress": 10, "label": "解析意图、约束与信息缺口"}
    analysis = analyze(opts["text"], opts["lang"])
    zh = analysis.lang == "zh"
    yield "analysis", analysis.as_dict()

    mode = opts["mode"]
    yield "stage", {"stage": "plan", "progress": 32, "label": "匹配场景模板与增强模式"}
    profile = Profile(mode=mode, lang=analysis.lang, intensity=opts["intensity"],
                      fmt=opts["format"])
    blocks = build_blocks(analysis, profile)
    yield "plan", {
        "mode": mode,
        "mode_label": {"struct": "结构化", "concise": "精简", "creative": "创意",
                       "academic": "学术", "code": "代码", "agent": "智能体"}[mode],
        "intensity": profile.intensity,
        "sections": [{"key": b["key"], "title": b["title"]} for b in blocks],
        "hint": MODE_HINTS.get(mode, {}).get("zh" if zh else "en", ""),
    }

    yield "stage", {"stage": "render", "progress": 55, "label": "组装结构化提示词"}
    parts: list[str] = []
    last = len(blocks) - 1
    for index, block in enumerate(blocks):
        head = (f"## {block['title']}\n\n" if opts["format"] == "markdown"
                else f"【{block['title']}】\n")
        # 末块不再追加分隔符：保证「流式拼接」与「一次性 JSON」逐字符一致
        piece_text = head + block["body"] + ("" if index == last else "\n\n")
        for piece in _chunk_text(piece_text):
            parts.append(piece)
            yield "chunk", {"delta": piece, "section": block["key"], "index": index}
            if pace:
                time.sleep(pace)

    enhanced = "".join(parts)

    yield "stage", {"stage": "score", "progress": 92, "label": "计算前后质量评分"}
    score = compare(opts["text"], enhanced, zh)

    yield "result", {
        "original": opts["text"],
        "enhanced": enhanced,
        "analysis": analysis.as_dict(),
        "profile": {"mode": profile.mode, "intensity": profile.intensity,
                    "lang": profile.lang, "format": profile.fmt},
        "score": score,
        "truncated": opts["truncated"],
    }
    yield "done", {"elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                   "chars": len(enhanced), "sections": len(blocks)}


def _labeled(ids: list[str], table: dict[str, tuple[str, str]]) -> list[dict[str, str]]:
    """把 id 列表翻成 {id, label, label_en}；顺序沿用词典登记顺序（general 收尾）。"""
    return [{"id": key, "label": table[key][0], "label_en": table[key][1]} for key in ids]


def _tags(table: dict[str, str]) -> list[dict[str, str]]:
    """词表 → 去重标签列表。

    渠道/语气没有独立 id：标签本身就是对外值（`constraints[].value`），
    因此 id == label；多语言词条指向同一标签时只保留一条。
    """
    tags: list[dict[str, str]] = []
    seen: set[str] = set()
    for label in table.values():
        if label not in seen:
            seen.add(label)
            tags.append({"id": label, "label": label})
    return tags


META = {
    "modes": [
        {"id": "struct", "label": "结构化", "desc": "标准八段式，通用性最好"},
        {"id": "concise", "label": "精简", "desc": "只保留高信息密度部分，适合日常对话"},
        {"id": "creative", "label": "创意", "desc": "鼓励非常规表达，输出双方案对比"},
        {"id": "academic", "label": "学术", "desc": "区分事实/推断/观点，强调来源标注"},
        {"id": "code", "label": "代码", "desc": "以可运行代码为主，解释从简"},
        {"id": "agent", "label": "智能体", "desc": "角色+工具+循环+停止条件"},
    ],
    "intensities": [
        {"id": "light", "label": "轻量", "desc": "4 个章节，最快"},
        {"id": "standard", "label": "标准", "desc": "8 个章节，日常推荐"},
        {"id": "deep", "label": "深度", "desc": "9 个章节，含风险与待确认项"},
    ],
    "formats": [{"id": "markdown", "label": "Markdown"}, {"id": "text", "label": "纯文本"}],
    "limits": {"max_chars": MAX_CHARS},
    "dims": ["清晰度", "具体性", "结构性", "约束完备", "可验证性"],
    # 识别层清单：宿主可直接渲染成筛选/下拉，不必在客户端硬编码
    "intents": _labeled(list(INTENT_KEYWORDS) + ["general"], INTENT_LABEL),
    "domains": _labeled(list(DOMAIN_KEYWORDS) + ["general"], DOMAIN_LABEL),
    "channels": _tags(CHANNEL_WORDS),
    "tones": _tags(TONE_WORDS),
}
