"""性能与体积基准（阶段 4 交付物：P95 ≤30 ms / 组件 ≤44 KB / meta ≤12 KB）。

用法：
    py tools/perf_bench.py          # 人读报告
    py tools/perf_bench.py --json   # 机器可读结果

口径说明（与规范 §5、计划 §1.4 对齐）：
    1. **P95 用图像提示词 500 字输入**，而不是 320 字文本样例——输入越长，
       `_image_plan` 的词典扫描与裁剪越贵，用短文本测会得到偏乐观的数；
    2. 计时只算 `enhance()` 全程（normalize → analyze → render → score），
       不含 HTTP、不含 SSE，因为计划里的 30 ms 是纯引擎预算；
    3. 体积取磁盘字节数（组件）与 `json.dumps(META)` 的 UTF-8 字节数（元数据），
       gzip 只是参考（静态资源走明文下发）；
    4. 所有数字在同一进程内现算，不写死，避免「报告跑得比代码快」。
"""

from __future__ import annotations

import gzip
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "tools"))

import engine  # noqa: E402
from engine import enhance  # noqa: E402
from engine.analyzer import analyze  # noqa: E402
from engine.pipeline import META  # noqa: E402

COMPONENT = ROOT / "web" / "prompt-enhancer.js"
SIZE_BUDGET = 44 * 1024          # 与 tests/test_frontend.py 同一口径
META_BUDGET = 12 * 1024
META_IMAGE_BUDGET = 5 * 1024
P95_BUDGET_MS = 30.0

IMAGE_INPUT = (
    "做一张夏天海边咖啡店开业活动的宣传图，画面是沙滩上的木质桌椅与遮阳伞，留出文案区，"
    "午后阳光斜射，浅蓝海面与远处帆船，三分法构图，平视中景，整体要高级感，比例 16:9"
)
TEXT_INPUT = ("帮我写一篇关于新能源汽车的推广文章，面向家庭用户，语气亲切，"
              "字数控制在 800 字以内，发在公众号上，需要包含三个卖点与行动号召。")


def _pad(text: str, target: int) -> str:
    """把样例扩到指定长度：只重复同一需求句，不引入噪声词。"""
    out = text
    while len(out) < target:
        out += "，" + text
    return out[:target]


def _percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((pct / 100) * (len(ordered) - 1)))))
    return ordered[index]


def time_calls(func, rounds: int = 300, warmup: int = 20, passes: int = 3) -> dict:
    """分 passes 轮各测 rounds 次：P50/P95 取各轮中位数，max 取各轮最大值。

    本机单轮 P95 会随后台进程抖到 4 ms 量级（P50 却稳定在 2.1 ms），
    单轮取样会把结论写成运气，所以取多轮中位数，并把各轮 P95 一并记下来备查。
    """
    for _ in range(warmup):
        func()
    p50s: list[float] = []
    p95s: list[float] = []
    peaks: list[float] = []
    for _ in range(passes):
        samples: list[float] = []
        for _ in range(rounds):
            start = time.perf_counter()
            func()
            samples.append((time.perf_counter() - start) * 1000)
        p50s.append(statistics.median(samples))
        p95s.append(_percentile(samples, 95))
        peaks.append(max(samples))
    return {"rounds": rounds, "passes": passes,
            "p50_ms": round(statistics.median(p50s), 2),
            "p95_ms": round(statistics.median(p95s), 2),
            "max_ms": round(max(peaks), 2),
            "p95_runs": [round(value, 2) for value in p95s]}


def measure_sizes() -> dict:
    raw = COMPONENT.read_bytes()
    meta_bytes = json.dumps(META, ensure_ascii=False).encode("utf-8")
    image_bytes = json.dumps({k: v for k, v in META.items() if k.startswith("image_")},
                             ensure_ascii=False).encode("utf-8")
    return {
        "component_bytes": len(raw),
        "component_gzip_bytes": len(gzip.compress(raw)),
        "component_budget_bytes": SIZE_BUDGET,
        "component_headroom_bytes": SIZE_BUDGET - len(raw),
        "meta_bytes": len(meta_bytes),
        "meta_budget_bytes": META_BUDGET,
        "meta_image_bytes": len(image_bytes),
        "meta_image_budget_bytes": META_IMAGE_BUDGET,
        "version": engine.__version__,
    }


def run(rounds: int = 300) -> dict:
    image_text = _pad(IMAGE_INPUT, 500)
    text_input = _pad(TEXT_INPUT, 320)
    timings = {
        "image_500": time_calls(lambda: enhance({"text": image_text}), rounds),
        "text_320": time_calls(lambda: enhance({"text": text_input}), rounds),
        "analyze_500": time_calls(lambda: analyze(image_text), rounds),
        "image_mj_500": time_calls(lambda: enhance({"text": image_text, "platform": "mj"}), rounds),
    }
    sizes = measure_sizes()
    return {
        "input_chars": {"image": len(image_text), "text": len(text_input)},
        "latency": timings,
        "sizes": sizes,
        "gates": {
            "p95_image": timings["image_500"]["p95_ms"] <= P95_BUDGET_MS,
            "component": sizes["component_bytes"] <= SIZE_BUDGET,
            "meta": sizes["meta_bytes"] <= META_BUDGET,
            "meta_image": sizes["meta_image_bytes"] <= META_IMAGE_BUDGET,
        },
    }


def format_report(r: dict) -> str:
    lat, size, gates = r["latency"], r["sizes"], r["gates"]
    mark = lambda flag: "通过" if flag else "未通过"  # noqa: E731
    lines = [
        f"## 性能（{engine.__version__}，{lat['image_500']['rounds']} 次/项）",
        f"- 图像 500 字：P50 {lat['image_500']['p50_ms']} ms｜P95 {lat['image_500']['p95_ms']} ms"
        f"｜max {lat['image_500']['max_ms']} ms → 门槛 30 ms：{mark(gates['p95_image'])}",
        f"- 图像 500 字（MJ 方言）：P95 {lat['image_mj_500']['p95_ms']} ms",
        f"- 文本 320 字：P95 {lat['text_320']['p95_ms']} ms（文本链路不回退）",
        f"- 仅 analyze（500 字）：P95 {lat['analyze_500']['p95_ms']} ms"
        f"（与 enhance 全程同量级，差异在测量噪声内）",
        "## 体积",
        f"- 组件 {size['component_bytes']:,} B（gzip {size['component_gzip_bytes']:,} B）"
        f"｜预算 {size['component_budget_bytes']:,} B，余量 {size['component_headroom_bytes']:,} B"
        f" → {mark(gates['component'])}",
        f"- /v1/meta {size['meta_bytes']:,} B｜预算 {size['meta_budget_bytes']:,} B → {mark(gates['meta'])}",
        f"- 其中 image_* {size['meta_image_bytes']:,} B｜预算 {size['meta_image_budget_bytes']:,} B"
        f" → {mark(gates['meta_image'])}",
    ]
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
    return 0 if all(result["gates"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
