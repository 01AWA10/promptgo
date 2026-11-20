"""领域 × 风格合理性抽样校验（阶段 3 验收项：100 条，合理率 ≥85%）。

用法：
    py tools/style_matrix_check.py          # 人读报告（未达 85% 时退出码 1）
    py tools/style_matrix_check.py --json   # 结构化结果

为什么这样抽样（对齐 `DOMAIN-STYLE-MAP-v0.1.md` §4）：
    1. 样本直接从文档表格解析，不另抄一份——改表即改样本，避免两侧漂移；
    2. 每领域取「推荐 ×2、中性 ×1、灰区 ×1、禁配 ×1」，22 领域合计 110 条，按等级轮转取前 100；
    3. 判定看**输出**而不是看表：用户点名的风格词是否被正确承接（推荐/中性）、
       是否补了限定词并留痕（灰区）、是否被替换并解释了原因（禁配）。

判定规则（可复现，不依赖主观打分）：
    推荐/中性  词出现在正文任一位置 → 合理；词根本不在 325 词表里 → 记「词表外」不计入分母
    灰区      保留 + 限定词在同一段 + `warnings` 有 `style_gray` → 合理
    禁配      不在正文 + `warnings` 有 `style_conflict` → 合理
    命中安全红线被拦（如医疗的「血腥」）→ 记「合理（拦截优先于替换）」

为什么要单列「词表外」：文档表的四列混装了光线/构图/材质/背景词（「影棚柔光」「白底无缝背景」
「建筑外观」），它们不属于风格维度，引擎的风格槽位接不住。这类样本算作**文档-词表漂移**，
在报告里单列，不混进合理率，否则等于用文档自身的分类错误给引擎扣分。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from engine import enhance, visual  # noqa: E402
from engine.analyzer import DOMAIN_KEYWORDS  # noqa: E402
from engine.pipeline import EnhanceError  # noqa: E402

MAP_PATH = ROOT / "docs" / "image-prompt" / "DOMAIN-STYLE-MAP-v0.1.md"
ROW_RE = re.compile(
    r"^\|\s*([a-z]+)\s+([^|]+?)\s*\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|\s*$", re.M)
GRAY_RE = re.compile(r"^(.+?)（需(?:限定)?「(.+?)」）$")
TIERS = ("推荐", "中性", "灰区", "禁配")
PROBE = "做一张{kw}的宣传图，风格要{term}"


def load_rows(path: Path | None = None) -> list[dict]:
    """解析文档第 2 节的 22 行映射表。"""
    text = Path(path or MAP_PATH).read_text(encoding="utf-8")
    rows = []
    for match in ROW_RE.finditer(text):
        code, label, rec, neutral, gray, ban = [part.strip() for part in match.groups()]
        rows.append({"domain": code, "label": label,
                     "推荐": _terms(rec), "中性": _terms(neutral),
                     "灰区": _terms(gray), "禁配": _terms(ban)})
    return rows


def _split_terms(cell: str) -> list[str]:
    """按「、」切词，但不切括号/引号内部——「（需限定「企业级、非废土」）」里的顿号不是分隔符。"""
    pieces, buf, depth = [], "", 0
    for char in cell:
        if char in "（「":
            depth += 1
        elif char in "）」":
            depth = max(0, depth - 1)
        if char == "、" and depth == 0:
            pieces.append(buf)
            buf = ""
        else:
            buf += char
    pieces.append(buf)
    return [piece.strip() for piece in pieces if piece.strip()]


def _terms(cell: str) -> list[tuple[str, str, str]]:
    """拆成 [(词, 需补齐的限定词, 适用条件)]。

    `（需「X」）` / `（需限定「X」）` → 限定词必须补进正文，否则组合自相矛盾；
    其它括号（`（仅年轻向活动）`）→ 只是适用条件，写成提示即可，
    把它塞进正文会得到「像素艺术，仅年轻向活动」这种怪句子。
    """
    out = []
    for piece in _split_terms(cell):
        gray = GRAY_RE.match(piece)
        if gray:
            out.append((gray.group(1).strip(), gray.group(2).strip(), ""))
            continue
        paren = re.search(r"（([^）]*)）$", piece)
        if paren:
            out.append((piece[:paren.start()].strip(), "", paren.group(1).strip()))
        else:
            out.append((piece, "", ""))
    return out


def build_samples(rows: list[dict], size: int = 100) -> list[dict]:
    """每领域取推荐 ×2、中性 ×1、灰区 ×1、禁配 ×1，按等级轮转取到 size 条。"""
    buckets: dict[str, list[dict]] = {tier: [] for tier in TIERS}
    for row in rows:
        picks = {"推荐": row["推荐"][:2], "中性": row["中性"][:1],
                 "灰区": row["灰区"][:1], "禁配": row["禁配"][:1]}
        for tier, items in picks.items():
            for term, qualifier, condition in items:
                buckets[tier].append({"domain": row["domain"], "domain_label": row["label"],
                                      "tier": tier, "term": term, "qualifier": qualifier,
                                      "condition": condition})
    samples: list[dict] = []
    while len(samples) < min(size, sum(len(v) for v in buckets.values())):
        for tier in TIERS:                  # 轮转四档，避免某一档独占 100 条
            for item in buckets[tier]:
                if item not in samples:
                    samples.append(item)
                    break
    return samples[:size]


def vocab_words() -> set[str]:
    """325 词表里所有可比对的形式（主词 + 别名 + 英文），全部小写。"""
    return set(vocab_map())


def vocab_map() -> dict[str, str]:
    """所有写法 → 词表主词。文档写「低调光」、引擎输出「低调」时按等价处理。"""
    mapping: dict[str, str] = {}
    for rows in visual.TERMS.values():
        for zh, en, aliases, _scenes in rows:
            mapping.setdefault(zh.lower(), zh)
            mapping.setdefault(en.lower(), zh)
            for alias in aliases:
                mapping.setdefault(alias.lower(), zh)
    return mapping


def testable(sample: dict, vocab: set[str]) -> bool:
    """推荐/中性的词必须先在词表里，才谈得上「有没有承接」。"""
    if sample["tier"] == "禁配":
        return True                      # 禁配不要求词表命中，但必须给替换提示
    return sample["term"].lower() in vocab


def judge(sample: dict, analysis: dict, canon: dict[str, str] | None = None) -> dict:
    """按文档 §4 的判定标准核对单条输出。"""
    image = analysis.get("image") or {}
    segs = image.get("segments") or {}
    body = "，".join(v for k, v in segs.items() if k != "negative")
    warnings = image.get("warnings") or []
    kinds = {w.get("type") for w in warnings}
    term, tier = sample["term"], sample["tier"]
    # 文档术语可能是词表别名（「低调光」），引擎按主词（「低调」）输出即算承接
    canonical = (canon or {}).get(term.lower(), term)
    present = term in body or canonical in body

    if tier in ("推荐", "中性"):
        ok = present
        reason = "" if ok else "点名风格未进入正文"
    elif tier == "灰区":
        kept = present
        # 「需限定」类必须把限定词写进正文；「适用条件」类只需留痕（塞进正文会成怪句）
        qualified = (not sample["qualifier"]) or sample["qualifier"] in body
        flagged = "style_gray" in kinds
        ok = kept and qualified and flagged
        reason = "；".join(name for name, hit in (("未保留", not kept),
                                                 ("限定词未补齐", not qualified),
                                                 ("未留痕 style_gray", not flagged)) if hit)
    else:                                # 禁配
        removed = not present
        flagged = "style_conflict" in kinds
        ok = removed and flagged
        reason = "；".join(name for name, hit in (("禁配词仍在正文", not removed),
                                                 ("未给出替换提示", not flagged)) if hit)
    return {"id": f"{sample['domain']}-{tier}-{term}", **sample, "ok": ok, "reason": reason,
            "style": segs.get("style", ""), "warnings": [w.get("text", "") for w in warnings]}


def attribute(result: dict) -> str:
    """把不合理项归到四类根因，便于直接排期。"""
    if result["tier"] == "灰区":
        return "灰区归属维度错配"      # 梯队已实现；剩下的都是词表维度放错（如 quality 不渲染）
    if result["tier"] == "禁配":
        return "禁用表未覆盖该词"
    return "命中缺失或槽位被覆盖"


def run(rows: list[dict] | None = None, size: int = 100) -> dict:
    rows = rows if rows is not None else load_rows()
    canon = vocab_map()
    vocab = set(canon)
    samples = build_samples(rows, size)
    results: list[dict] = []
    for sample in samples:
        kw = DOMAIN_KEYWORDS.get(sample["domain"], (sample["domain_label"],))[0]
        text = PROBE.format(kw=kw, term=sample["term"])
        item = {**sample, "text": text}
        if not testable(sample, vocab):
            results.append({"id": f"{sample['domain']}-{sample['tier']}-{sample['term']}", **item,
                            "ok": False, "measured": False, "reason": "词表外（文档术语不在 325 词表）",
                            "style": "", "warnings": []})
            continue
        try:
            analysis = enhance({"text": text})["analysis"]
        except EnhanceError as error:
            # 禁配里混着红线词（如医疗的「血腥」）：拦截比替换更强，按「合理」记
            blocked = getattr(error, "code", "") == "SAFETY_BLOCKED"
            results.append({"id": f"{sample['domain']}-{sample['tier']}-{sample['term']}", **item,
                            "ok": blocked, "measured": True,
                            "reason": "" if blocked else "调用失败",
                            "style": "", "warnings": [getattr(error, "message", "")]})
            continue
        results.append({**judge(item, analysis, canon), "measured": True})

    measured = [r for r in results if r["measured"]]
    passed = [r for r in measured if r["ok"]]
    failures = [r for r in measured if not r["ok"]]
    by_tier: dict[str, dict] = {}
    for tier in TIERS:
        group = [r for r in measured if r["tier"] == tier]
        by_tier[tier] = {"pass": sum(1 for r in group if r["ok"]), "total": len(group)}
    buckets: dict[str, int] = {}
    for fail in failures:
        buckets[attribute(fail)] = buckets.get(attribute(fail), 0) + 1
    return {
        "domains": len(rows),
        "samples": len(results),
        "measured": len(measured),
        "untestable": [r for r in results if not r["measured"]],
        "passed": len(passed),
        "rate": round(len(passed) / len(measured), 3) if measured else 0.0,
        "by_tier": by_tier,
        "buckets": buckets,
        "failures": failures,
    }


def format_report(r: dict) -> str:
    gate = "通过" if r["rate"] >= 0.85 else "未通过"
    lines = ["## 领域 × 风格合理性抽样",
             f"- 抽样 {r['samples']} 条（{r['domains']} 领域）｜可测 {r['measured']} 条"
             f"（词表外 {len(r['untestable'])} 条）",
             f"- 合理 {r['passed']}/{r['measured']}（{r['rate']:.0%}）｜门槛 ≥85%：{gate}"]
    for tier, data in r["by_tier"].items():
        lines.append(f"- {tier}：{data['pass']}/{data['total']}")
    if r["buckets"]:
        lines.append("- 不合理归因：" + "｜".join(f"{k} {v} 条" for k, v in r["buckets"].items()))
    if r["failures"]:
        lines += ["", "## 不合理明细"]
        for fail in r["failures"]:
            lines.append(f"- {fail['id']}［{attribute(fail)}］：{fail['reason']}"
                         f"｜style={fail['style'] or '（空）'}"
                         f"｜warnings={fail['warnings'] or '（无）'}")
    if r["untestable"]:
        lines += ["", f"## 词表外术语（{len(r['untestable'])} 条，不计入合理率）",
                  "- " + "、".join(sorted({r_['term'] for r_ in r["untestable"]}))]
    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2) if "--json" in sys.argv
          else format_report(result))
    return 0 if result["rate"] >= 0.85 else 1


if __name__ == "__main__":
    raise SystemExit(main())
