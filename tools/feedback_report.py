"""反馈看板：聚合本地反馈日志，算复制率 / 好评率 / 失败样本，并支持一键导出。

用法：
    python tools/feedback_report.py                       # 控制台看板
    python tools/feedback_report.py --json                # 机器可读
    python tools/feedback_report.py --export failures.md  # 导出失败样本（含归因候选）

日志格式：服务端 `/v1/feedback` 追加的 JSONL，每行一条，字段见 `http_layer._handle_feedback`。
口径（与计划 §5.3 对齐）：
    复制率 = copy 次数 / enhance 次数        —— 分母是「出了结果」，不是「打开了页面」
    重试率 = retry 次数 / enhance 次数
    好评率 = 有用票 /（有用票 + 没用票）      —— 只统计明确表态的，不把「没投」算成差评
    归因完成率 = 已人工标注的失败样本 / 失败样本总数

失败样本 = 「没用」票 + 「重试」请求。前者是显式否定，后者是行为上的不满意，
两者都不去重（同一需求反复重试本身就是信号）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

DEFAULT_LOG = ROOT / "logs" / "feedback.log"
ATTRIBUTIONS = ("词表缺失", "结构缺失", "平台语法", "安全问题")   # 与计划 §3 阶段 5 同名
MIN_SAMPLE = 50          # 计划 §5.3：好评率样本 ≥50 才作结论


def read_log(path: Path) -> list[dict]:
    """读 JSONL；滚动备份 `.log.1` 也读进来，但早于主文件的记录排在前面。"""
    records: list[dict] = []
    for candidate in (path.with_suffix(".log.1"), path):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue                       # 半行（进程被杀）直接跳过，不中断聚合
            if isinstance(item, dict) and item.get("kind"):
                records.append(item)
    return records


def fingerprint(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:12]


def candidate_attribution(text: str, platform: str | None) -> str:
    """归因候选：用引擎离线复跑该条输入，把失败归到四类之一（只作候选，需人工确认）。"""
    try:
        from engine import enhance
        from engine.pipeline import EnhanceError
    except Exception:                      # noqa: BLE001  引擎不可用时不做猜测
        return ""
    try:
        analysis = enhance({"text": text, "platform": platform or "generic"})["analysis"]
    except EnhanceError as error:
        return "安全问题" if getattr(error, "code", "") == "SAFETY_BLOCKED" else ""
    except Exception:                      # noqa: BLE001
        return ""
    if analysis.get("intent") != "image":
        return "结构缺失"                   # 该进图像链路却没进
    image = analysis.get("image") or {}
    if image.get("warnings"):
        return "平台语法"
    if not (image.get("picks") or {}).get("style"):
        return "词表缺失"                   # 图像链路成立，但风格槽位没东西可填
    return "结构缺失"


def load_attributions(path: Path | None) -> dict[str, str]:
    """人工归因台账：{指纹: 类别}。文件不存在时返回空表（完成率即为 0）。"""
    if not path or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(key): str(value) for key, value in (data or {}).items()} if isinstance(data, dict) else {}


def run(path: Path | None = None, attribution_file: Path | None = None) -> dict:
    records = read_log(Path(path or DEFAULT_LOG))
    kinds = Counter(record.get("kind") for record in records)
    enhances = kinds.get("enhance", 0)
    copies, retries = kinds.get("copy", 0), kinds.get("retry", 0)
    votes = [record for record in records if record.get("kind") == "vote"]
    up = sum(1 for vote in votes if vote.get("useful") is True)
    down = sum(1 for vote in votes if vote.get("useful") is False)

    rated = load_attributions(attribution_file) if attribution_file else {}
    failures = []
    for record in records:
        if record.get("kind") not in ("vote", "retry"):
            continue
        if record.get("kind") == "vote" and record.get("useful") is not False:
            continue
        text = record.get("text") or ""
        key = fingerprint(text)
        failures.append({
            "ts": record.get("ts"), "key": key, "reason": "没用票" if record.get("kind") == "vote" else "重试",
            "intent": record.get("intent"), "platform": record.get("platform"),
            "text": text, "attribution": rated.get(key, ""),
            "candidate": candidate_attribution(text, record.get("platform")) if text else "",
        })
    attributed = sum(1 for item in failures if item["attribution"])

    return {
        "log": str(path or DEFAULT_LOG),
        "events": len(records),
        "enhances": enhances,
        "copy_rate": round(copies / enhances, 3) if enhances else 0.0,
        "retry_rate": round(retries / enhances, 3) if enhances else 0.0,
        "votes": {"up": up, "down": down,
                  "positive_rate": round(up / (up + down), 3) if up + down else 0.0,
                  "sample_ok": up + down >= MIN_SAMPLE},
        "failures": failures,
        # 0/0 不写 100%：没有失败样本时「归因完成率」无定义，记为 None 由渲染层显示「—」
        "attribution": {"attributed": attributed, "total": len(failures),
                        "rate": round(attributed / len(failures), 3) if failures else None},
        "kinds": dict(kinds),
    }


def format_report(r: dict) -> str:
    votes = r["votes"]
    rated = votes["up"] + votes["down"]
    if not votes["sample_ok"]:
        verdict = f"样本不足（{rated}/{MIN_SAMPLE}）"
    elif votes["positive_rate"] >= 0.7:
        verdict = "通过"
    else:
        verdict = "未达标"
    attr = r["attribution"]
    rate_text = "—（暂无样本）" if attr["rate"] is None else f"{attr['rate']:.0%}"
    lines = [
        "## 反馈看板",
        f"- 事件 {r['events']} 条（{r['kinds']}）",
        f"- 复制率 {r['copy_rate']:.0%}（{r['enhances']} 次出结果）｜门槛 ≥60%："
        f"{'通过' if r['copy_rate'] >= 0.6 else '未达标'}",
        f"- 重试率 {r['retry_rate']:.0%}",
        f"- 好评率 {votes['positive_rate']:.0%}（{votes['up']} 有用 / {votes['down']} 没用）"
        f"｜门槛 ≥70% 且样本 ≥{MIN_SAMPLE}：{verdict}",
        f"- 失败样本 {attr['total']} 条｜归因完成率 {rate_text}"
        f"（{attr['attributed']}/{attr['total']}）",
    ]
    if not votes["sample_ok"]:
        lines.append(f"  · 好评样本仅 {rated} 条，未达 {MIN_SAMPLE} 条，好评分只作趋势参考")
    return "\n".join(lines)


def export_failures(r: dict, path: Path) -> None:
    """一键导出失败样本：给人读的 markdown，归因留空待填。"""
    rate = r["attribution"]["rate"]
    rate_text = "—" if rate is None else f"{rate:.0%}"
    lines = ["# 失败样本池", "",
             f"来源 `{r['log']}`｜共 {len(r['failures'])} 条｜归因完成率 {rate_text}", "",
             "> 归因四分类：词表缺失 / 结构缺失 / 平台语法 / 安全问题。"
             "确认后写入 `docs/image-prompt/feedback/attribution.json`（键=指纹），看板会自动统计完成率。",
             ""]
    for item in r["failures"]:
        lines += [f"## {item['ts']} · {item['reason']} · {item['key']}", "",
                  f"- 意图：{item['intent'] or '未知'}｜平台：{item['platform'] or 'generic'}",
                  f"- 归因：{item['attribution'] or '（待填）'}｜候选：{item['candidate'] or '（无）'}",
                  "", "```text", item["text"], "```", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass
    parser = argparse.ArgumentParser(description="反馈看板与失败样本导出")
    parser.add_argument("--log", default=str(DEFAULT_LOG), help="反馈日志路径（JSONL）")
    parser.add_argument("--attribution-file", default=str(ROOT / "docs" / "image-prompt"
                                                          / "feedback" / "attribution.json"),
                        help="人工归因台账（JSON）")
    parser.add_argument("--export", metavar="PATH", help="把失败样本导出为 markdown")
    parser.add_argument("--json", action="store_true", help="输出机器可读结果")
    args = parser.parse_args()

    result = run(Path(args.log), Path(args.attribution_file))
    if args.export:
        export_failures(result, Path(args.export))
        print(f"已导出 {len(result['failures'])} 条失败样本到 {args.export}")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif not args.export:
        print(format_report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
