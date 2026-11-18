"""图像提示词阶段 4 评测：120 条语料 + 自动断言 + 盲评包生成。

语料按「6 场景 × 4 平台 × 5 难度」程序化构造，保证每个场景、每种方言、每档难度
都有覆盖，且可重复（无随机、无网络）。自动断言直接读规范的可测项；
盲评包只生成 A/B 顺序与评分表，**不产生任何机器评分**。

用法：
    python tools/image_eval.py            # 自动断言报告
    python tools/image_eval.py --json     # 结构化结果
    python tools/image_eval.py --packet blind.json   # 生成盲评包
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from engine import enhance, visual  # noqa: E402

PLATFORMS = ("generic", "mj", "flux", "sdxl")
TIERS = ("A", "B", "C", "D", "E")
TIER_LABEL = {
    "A": "直给（含产物词与动词）",
    "B": "口语（形容词 + 主体）",
    "C": "省略（只有主体与产物词）",
    "D": "长需求（多约束叠加）",
    "E": "冲突（风格互斥 + 负面口述）",
}
SCENES = {
    "MK": ("宣传图", ["夏天海边咖啡店", "秋日露营帐篷营地", "健身房开业现场"]),
    "EC": ("主图", ["不锈钢保温杯", "磨砂玻璃香水瓶", "无线蓝牙耳机"]),
    "IL": ("插画", ["屋顶看星星的猫", "森林里的小狐狸", "深夜书店的旧台灯"]),
    "AV": ("头像", ["戴耳机的年轻程序员", "扎马尾的插画师", "虚拟主播形象"]),
    "PS": ("海报", ["双十一促销主视觉", "音乐节活动", "读书日公益活动"]),
    "CD": ("概念图", ["赛博朋克雨夜街道", "深海探测器舱内", "1990 年代小城老街"]),
}
ADJ = ("高级感", "燃一点", "温柔", "清爽", "复古")
VISUAL_FILL = ("金属拉丝质感", "浅景深背景虚化", "三分法构图", "体积光与雾气", "青橙色调")
SPOKEN = ("高级感", "燃", "治愈", "压迫感")
CONFLICT = ("赛博朋克风格，又要有水墨的留白", "极简构图，但画面要满版铺满", "硬光直打，同时保持柔光")

# 正文长度预算（不含平台参数与负面行）：多元素 180–260，单主体/背景 150–220
BODY_BUDGET = {"MK": (180, 260), "IL": (180, 260), "CD": (180, 260),
               "EC": (150, 220), "AV": (150, 220), "PS": (150, 220)}


def build_corpus() -> list[dict]:
    """6 场景 × 4 平台 × 5 难度 = 120 条，索引确定性生成。"""
    cases = []
    for scene, (noun, subjects) in SCENES.items():
        for platform in PLATFORMS:
            for tier in TIERS:
                subject = subjects[(TIERS.index(tier) + PLATFORMS.index(platform)) % len(subjects)]
                text = _phrase(tier, subject, noun, scene, TIERS.index(tier) + PLATFORMS.index(platform))
                cases.append({"id": f"{scene}-{platform}-{tier}", "scene": scene,
                              "platform": platform, "tier": tier, "text": text})
    return cases


def _phrase(tier: str, subject: str, noun: str, scene: str, idx: int) -> str:
    adj = ADJ[idx % len(ADJ)]
    fill = VISUAL_FILL[idx % len(VISUAL_FILL)]
    fill2 = VISUAL_FILL[(idx + 2) % len(VISUAL_FILL)]
    spoken = SPOKEN[idx % len(SPOKEN)]
    conflict = CONFLICT[idx % len(CONFLICT)]
    if tier == "A":
        return f"帮我做一张{subject}的{noun}"
    if tier == "B":
        return f"想要那种{adj}的{noun}，主体是{subject}"
    if tier == "C":
        return f"{subject}{noun}"
    if tier == "D":
        return (f"做一张{noun}，画面是{subject}，{fill}，{fill2}，"
                f"留出文案区，整体要{spoken}")
    return f"做一张{noun}，{subject}，{conflict}，但不要出现文字和水印"


SHELL_WORDS = ("帮我", "请帮我", "做一张", "来一张", "出一张", "生成一张", "绘制")


def redundancy(segments: dict, n: int = 4) -> dict:
    """客观冗余检测：跨段重复、壳词残留、长片段回声。

    盲评把「无冗余」打到 3.57，但主观分说不清冗余在哪；这里用可复现的规则定位：
    - dup_pieces：整块片段（按「，」切）同时出现在两个段里 → 硬失败；
    - shell：输出里还留着「帮我/做一张」这类壳词 → 硬失败；
    - echoes：≥n 字的长子串跨段复现（如 lighting 与 texture 都说「过渡自然」）→
      只报告不判失败，属可接受的轻微呼应，留给人眼判断。
    negative 段不参与：负面词按规范本就该成串出现，重复是设计而非冗余。
    """
    body = {key: value for key, value in segments.items() if key != "negative" and value}
    pieces: list[tuple[str, str]] = []
    for key, value in body.items():
        for part in value.split("，"):
            part = part.strip()
            if part:
                pieces.append((key, part))

    dup_pieces: list[dict] = []
    seen: dict[str, str] = {}
    for key, part in pieces:
        if part in seen and seen[part] != key:
            dup_pieces.append({"text": part, "first": seen[part], "again": key})
        seen.setdefault(part, key)

    echoes: list[dict] = []
    for run in _repeated_runs("，".join(body.values()), n):
        holders = [key for key, value in body.items() if run in value]
        if len(holders) >= 2:
            echoes.append({"text": run, "segs": holders})

    shell: list[dict] = []
    for key, value in body.items():
        for word in sorted(SHELL_WORDS, key=len, reverse=True):
            if word in value and not any(word in hit["word"] for hit in shell if hit["seg"] == key):
                shell.append({"word": word, "seg": key})

    return {"dup_pieces": dup_pieces, "echoes": echoes, "shell": shell,
            "redundant": bool(dup_pieces or shell)}


def _repeated_runs(text: str, n: int = 4) -> list[str]:
    """取最长的重复子串（≥n 字），并把滑动窗口叠出的短片段并入同一条。

    直接统计 n-gram 会把一处重复记成 2–3 条（「，边缘干」+「边缘干净」），
    按最长匹配向后扩展再合并，才能一眼看清到底重复了哪个短语。
    """
    runs: list[str] = []
    i = 0
    while i <= len(text) - n:
        end = i + n
        while end < len(text) and text.find(text[i:end + 1], i + 1) != -1:
            end += 1
        run = text[i:end]
        if len(run) > n or text.find(run, i + 1) != -1:
            if not any(run in seen or seen in run for seen in runs):
                runs.append(run)
            i = end
        else:
            i += 1
    return runs


def semantic_text(segments: dict) -> str:
    """8 段语义全文（含负面），与平台无关——长度预算按这个口径量。

    直接量 `enhanced` 会把 `--ar/--v/--no` 和 `negative:` 这类平台开销算进去，
    同一句话在 MJ 与通用方言下会得出不同的长度结论。
    """
    body = "，".join(v for key, v in segments.items() if key != "negative")
    return f"{body}；避免 {segments.get('negative', '')}"


def check(case: dict) -> dict:
    """单条断言：返回 failures 列表，空表示通过。"""
    failures: list[str] = []
    result = enhance({"text": case["text"], "platform": case["platform"]})
    image = result["analysis"].get("image")
    if image is None:
        return {"id": case["id"], "failures": ["未判为图像意图"]}

    segs = image["segments"]
    for key in ("subject", "setting", "composition", "lighting", "style", "technical", "negative"):
        if not segs.get(key):
            failures.append(f"S 段缺失：{key}")
    for word in visual.BASE_NEGATIVE:
        if word not in segs["negative"]:
            failures.append(f"负面缺失：{word}")

    body = semantic_text(segs)
    low, high = BODY_BUDGET[case["scene"]]
    if not low <= len(body) <= high:
        failures.append(f"正文长度越界：{len(body)} 不在 {low}–{high}")

    red = redundancy(segs)
    for dup in red["dup_pieces"]:
        failures.append(f"跨段重复：「{dup['text']}」同时出现在 {dup['first']} 与 {dup['again']}")
    for hit in red["shell"]:
        failures.append(f"壳词残留：{hit['word']}（{hit['seg']}）")

    enhanced = result["enhanced"]
    if case["platform"] == "generic" and "；避免 " not in enhanced:
        failures.append("通用方言缺少「；避免」负面尾")
    if case["platform"] == "mj" and " --v 6 --style raw --no " not in enhanced:
        failures.append("MJ 方言参数不完整")
    if case["platform"] == "flux" and "; avoid " not in enhanced:
        failures.append("Flux 方言缺少 ; avoid")
    if case["platform"] == "sdxl" and "\n\nnegative: " not in enhanced:
        failures.append("SDXL 缺少独立 negative 行")
    if image["ratio"] not in visual.RATIOS:
        failures.append(f"比例非法：{image['ratio']}")
    if "## " in enhanced or "## 角色" in enhanced:
        failures.append("污染：混入指令式小标题")
    if not result.get("negative"):
        failures.append("缺少 negative 字段")

    return {"id": case["id"], "failures": failures, "length": len(body),
            "scene": image["scene"], "ratio": image["ratio"],
            "dup": len(red["dup_pieces"]), "shell": len(red["shell"]),
            "echoes": len(red["echoes"])}


def run(verbose: bool = False) -> dict:
    cases = build_corpus()
    results = [check(case) for case in cases]
    failed = [r for r in results if r["failures"]]
    by = {}
    for case, res in zip(cases, results):
        for key in ("scene", "platform", "tier"):
            bucket = by.setdefault(f"{key}:{case[key]}", {"pass": 0, "total": 0})
            bucket["total"] += 1
            bucket["pass"] += 0 if res["failures"] else 1
    if verbose:
        for res in failed:
            print(f"  [FAIL] {res['id']}: {res['failures']}")
    lengths = [r.get("length", 0) for r in results if "length" in r]
    echo_counts = [r.get("echoes", 0) for r in results if "echoes" in r]
    return {
        "cases": len(cases),
        "passed": len(cases) - len(failed),
        "failed": len(failed),
        "pass_rate": round((len(cases) - len(failed)) / len(cases), 3),
        "by_bucket": by,
        "length_min": min(lengths) if lengths else 0,
        "length_max": max(lengths) if lengths else 0,
        "redundancy": {
            "dup_cases": sum(1 for r in results if r.get("dup")),
            "shell_cases": sum(1 for r in results if r.get("shell")),
            "echo_cases": sum(1 for r in results if r.get("echoes")),
            "echo_max": max(echo_counts) if echo_counts else 0,
        },
        "failures": failed,
    }


def make_packet(seed: int = 20261116) -> dict:
    """盲评包：每条给 A/B 两份（系统输出 vs 原话），顺序按种子确定，分数留空。"""
    cases = build_corpus()
    packet = {"seed": seed, "dims": ["主体准确", "结构完整", "术语可执行", "平台合规", "无冗余"],
              "scale": "1–5 分，3 分为可用门槛", "items": []}
    for index, case in enumerate(cases):
        result = enhance({"text": case["text"], "platform": case["platform"]})
        system_text = result["enhanced"]
        baseline = case["text"]  # 基线：直接把这句原话粘进绘图框
        swap = (index + seed) % 2 == 0
        item = {"id": case["id"], "scene": case["scene"],
                "platform": case["platform"], "tier": case["tier"],
                "A": system_text if swap else baseline,
                "B": baseline if swap else system_text,
                "source": {"A": "system" if swap else "raw", "B": "raw" if swap else "system"},
                "scores": {"A": {}, "B": {}},
                "preference": None}
        packet["items"].append(item)
    return packet


def build_packet(path: Path, seed: int = 20261116) -> dict:
    packet = make_packet(seed)
    path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
    return packet


def format_report(r: dict) -> str:
    lines = ["## 自动断言（120 条语料）",
             f"- 通过 {r['passed']}/{r['cases']}（{r['pass_rate']:.0%}）",
             f"- 正文长度 {r['length_min']}–{r['length_max']} 字", ""]
    red = r.get("redundancy") or {}
    if red:
        lines += [f"- 冗余：跨段重复 {red['dup_cases']} 条｜壳词残留 {red['shell_cases']} 条"
                  f"｜长片段回声 {red['echo_cases']} 条（软信号，不判失败）", ""]
    for key in sorted(r["by_bucket"]):
        bucket = r["by_bucket"][key]
        lines.append(f"- {key}: {bucket['pass']}/{bucket['total']}")
    if r["failures"]:
        lines.append("")
        lines.append("## 失败明细")
        for fail in r["failures"]:
            lines.append(f"- {fail['id']}: {'；'.join(fail['failures'])}")
    return "\n".join(lines)


ANCHORS = [
    ("MK-01 · 4 分样板", "海边露天咖啡店，木质桌椅与遮阳伞，午后沙滩与浅蓝海面，右侧留出文案区，"
                        "三分法构图，平视中景，黄金时刻暖阳与柔和侧逆光，生活方式商业摄影，"
                        "原木与亚麻材质，玻璃杯水珠细节，16:9 横版，高分辨率，细节清晰；"
                        "避免低质量、模糊、文字水印、logo、比例畸变、杂乱背景、主体裁切",
     "八段齐全、留白明确，没有废话；扣分点在「生活方式商业摄影」略虚。"),
    ("EC-02 · 3 分样板", "一副白色无线耳机与充电盒，悬浮在半空，浅灰渐变背景，中心构图，平视近景，"
                        "冷调柔光加轻微投影，极简科技产品摄影，哑光塑料与金属触点，细腻磨砂纹理，"
                        "1:1 方形，高分辨率，干净背景；避免低质量、模糊、文字、水印、logo、杂乱背景、比例畸变",
     "维度够用但不惊艳，中规中矩——可用门槛的样子。"),
    ("CD-07 · 5 分样板", "1990 年代中国小城老街的夏日傍晚，一位刚下班的年轻人骑自行车穿过街道，"
                        "两侧低矮店铺与梧桐树，远处工厂烟囱，斜阳形成长影，三分法构图，平视远景，"
                        "暖色黄昏侧逆光，复古纪实电影感，褪色胶片色彩与墙面斑驳，保留清晰细节，"
                        "21:9 宽幅，高分辨率；避免低质量、模糊、文字、水印、logo、比例畸变、现代建筑、过曝、风格混杂",
     "长需求被压成场景 + 人物 + 光线 + 年代质感；用「保留清晰细节」抵消「老照片发糊」。"),
]

HTML_TEMPLATE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>图像提示词盲评</title>
<style>
:root{--bg:#0f1115;--card:#171a21;--line:#2a2f3a;--text:#e6e8ee;--dim:#9aa3b2;
--accent:#5eead4;--accent2:#818cf8;--warn:#fbbf24;--ok:#34d399}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
header{position:sticky;top:0;z-index:9;background:rgba(15,17,21,.94);
backdrop-filter:blur(8px);border-bottom:1px solid var(--line);padding:14px 22px}
h1{font-size:16px;margin:0 0 8px;font-weight:600;letter-spacing:.3px}
h1 span{color:var(--dim);font-weight:400;font-size:12px;margin-left:8px}
.bar{height:4px;background:var(--line);border-radius:2px;overflow:hidden}
.bar>i{display:block;height:100%;width:0;background:linear-gradient(90deg,var(--accent),var(--accent2));
transition:width .2s}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:10px}
button{background:#20242e;color:var(--text);border:1px solid var(--line);border-radius:8px;
padding:6px 12px;font-size:13px;cursor:pointer;transition:.15s}
button:hover{border-color:var(--accent);color:var(--accent)}
button.primary{background:var(--accent);color:#06231f;border-color:var(--accent);font-weight:600}
.meta{color:var(--dim);font-size:12px}
main{max-width:1180px;margin:0 auto;padding:18px 22px 80px}
details.anchor{max-width:1180px;margin:16px auto 0;padding:0 22px}
details.anchor summary{cursor:pointer;color:var(--accent);font-size:13px}
.anchor-body{display:grid;gap:10px;margin-top:10px}
.anchor-item{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--accent2);
border-radius:8px;padding:10px 14px;font-size:12.5px;color:var(--dim)}
.anchor-item b{color:var(--text);display:block;margin-bottom:4px;font-size:13px}
.anchor-item code{color:#cbd5e1;font-size:12px;line-height:1.7}
.case{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px 20px}
.case-head{display:flex;gap:8px;align-items:center;margin-bottom:14px;flex-wrap:wrap}
.chip{font-size:11.5px;padding:2px 9px;border-radius:999px;border:1px solid var(--line);color:var(--dim)}
.chip.p{color:var(--accent);border-color:#2b6f66}
.chip.t{color:var(--warn);border-color:#6b5620}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:820px){.grid{grid-template-columns:1fr}}
.pane{border:1px solid var(--line);border-radius:12px;padding:14px;background:#12151c}
.pane h3{margin:0 0 10px;font-size:13px;color:var(--dim);font-weight:600;letter-spacing:.5px}
.text{background:#0c0e13;border:1px solid var(--line);border-radius:8px;padding:12px;
font-size:13px;line-height:1.9;color:#d7dce6;white-space:pre-wrap;word-break:break-word;min-height:96px}
.dims{margin-top:12px;display:grid;gap:6px}
.dim{display:flex;align-items:center;justify-content:space-between;gap:8px}
.dim span{font-size:12.5px;color:var(--dim)}
.sc{display:flex;gap:4px}
.sc button{width:30px;height:28px;padding:0;font-size:12px;border-radius:6px}
.sc button.on{background:var(--accent);color:#06231f;border-color:var(--accent);font-weight:700}
.pref{margin-top:16px;display:flex;gap:8px;align-items:center;flex-wrap:wrap;
border-top:1px dashed var(--line);padding-top:14px}
.pref b{font-size:13px;font-weight:600}
.pref button.on{background:var(--accent2);color:#0b0f2a;border-color:var(--accent2);font-weight:700}
textarea{width:100%;margin-top:10px;background:#0c0e13;border:1px solid var(--line);
border-radius:8px;color:var(--text);padding:8px 10px;font:13px/1.6 inherit;resize:vertical;min-height:38px}
.hint{color:var(--dim);font-size:12px;margin-top:8px}
.done-flag{color:var(--ok);font-size:12px}
</style></head><body>
<header>
  <h1>图像提示词盲评 <span>5 维 × 1–5 分 · 3 分为可用门槛 · 选中即自动保存</span></h1>
  <div class="bar"><i id="bar"></i></div>
  <div class="row">
    <span class="meta">进度 <b id="done">0</b>/<b id="total">0</b></span>
    <span class="meta" id="live"></span>
    <span style="flex:1"></span>
    <button id="prev">← 上一条</button>
    <button id="next">下一条 →</button>
    <button id="jump">跳到未评</button>
    <button id="export" class="primary">导出评分 JSON</button>
    <label><button id="importBtn">导入续评</button>
      <input type="file" id="import" accept="application/json" hidden></label>
    <button id="reset">清空</button>
  </div>
</header>
<details class="anchor"><summary>评分锚点：先看这 3 条再开始（避免各组标准差过大）</summary>
  <div class="anchor-body" id="anchors"></div>
</details>
<main><section class="case" id="case"></section></main>
<script>
const DATA = __PACKET__;
const ANCHORS = __ANCHORS__;
const KEY = 'image-blind-' + DATA.seed;
let state = {};
try { state = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { state = {}; }
let idx = 0;

document.getElementById('anchors').innerHTML = ANCHORS.map(a =>
  `<div class="anchor-item"><b>${a[0]}</b><code>${a[1]}</code><div style="margin-top:6px">${a[2]}</div></div>`
).join('');
document.getElementById('total').textContent = DATA.items.length;

function blank() { const o = {}; DATA.dims.forEach(d => o[d] = 0); return o; }
function get(id) {
  if (!state[id]) state[id] = { A: blank(), B: blank(), preference: '', note: '' };
  return state[id];
}
function save() { localStorage.setItem(KEY, JSON.stringify(state)); }

function isDone(item) {
  const s = get(item.id);
  return DATA.dims.every(d => s.A[d] && s.B[d]) && !!s.preference;
}

function scoreButtons(side, dim, current) {
  let html = '<div class="sc">';
  for (let n = 1; n <= 5; n++) {
    html += `<button class="${current === n ? 'on' : ''}" data-side="${side}" data-dim="${dim}" data-v="${n}">${n}</button>`;
  }
  return html + '</div>';
}

function render() {
  const item = DATA.items[idx];
  const s = get(item.id);
  const dims = DATA.dims.map(d =>
    `<div class="dim"><span>${d}</span>${scoreButtons('A', d, s.A[d])}</div>`).join('');
  const dimsB = DATA.dims.map(d =>
    `<div class="dim"><span>${d}</span>${scoreButtons('B', d, s.B[d])}</div>`).join('');
  const pref = ['A', 'B', 'tie'].map(p => {
    const label = p === 'tie' ? '相当' : (p + ' 更好');
    return `<button class="${s.preference === p ? 'on' : ''}" data-pref="${p}">${label}</button>`;
  }).join('');
  document.getElementById('case').innerHTML = `
    <div class="case-head">
      <span class="chip">#${idx + 1} / ${DATA.items.length}</span>
      <span class="chip p">${item.platform}</span>
      <span class="chip t">难度 ${item.tier}</span>
      <span class="chip">${item.id}</span>
      ${isDone(item) ? '<span class="done-flag">已评</span>' : ''}
    </div>
    <div class="grid">
      <div class="pane"><h3>A</h3><div class="text">${item.A}</div><div class="dims">${dims}</div></div>
      <div class="pane"><h3>B</h3><div class="text">${item.B}</div><div class="dims">${dimsB}</div></div>
    </div>
    <div class="pref"><b>整体偏好</b>${pref}
      <span class="hint">判断依据：拿到这句提示词，你会不会直接拿去出图。</span></div>
    <textarea id="note" placeholder="备注（可空）：哪一段让它更好或更差">${s.note || ''}</textarea>`;
  document.getElementById('case').querySelectorAll('.sc button').forEach(b => {
    b.onclick = () => {
      get(item.id)[b.dataset.side][b.dataset.dim] = Number(b.dataset.v);
      save(); render();
    };
  });
  document.getElementById('case').querySelectorAll('[data-pref]').forEach(b => {
    b.onclick = () => { get(item.id).preference = b.dataset.pref; save(); render(); };
  });
  document.getElementById('note').oninput = (e) => { get(item.id).note = e.target.value; save(); };
  updateStats();
}

function updateStats() {
  const done = DATA.items.filter(isDone).length;
  document.getElementById('done').textContent = done;
  document.getElementById('bar').style.width = (done / DATA.items.length * 100) + '%';
  const side = (name) => {
    const vals = [];
    DATA.items.forEach(item => {
      const s = get(item.id);
      DATA.dims.forEach(d => { if (s[name][d]) vals.push(s[name][d]); });
    });
    return vals.length ? (vals.reduce((a, b) => a + b, 0) / vals.length) : 0;
  };
  const a = side('A'), b = side('B');
  document.getElementById('live').textContent = done
    ? `A 均分 ${a.toFixed(2)} · B 均分 ${b.toFixed(2)}` : '尚未评分';
}

document.getElementById('prev').onclick = () => { idx = (idx - 1 + DATA.items.length) % DATA.items.length; render(); };
document.getElementById('next').onclick = () => { idx = (idx + 1) % DATA.items.length; render(); };
document.getElementById('jump').onclick = () => {
  const found = DATA.items.findIndex(i => !isDone(i));
  if (found >= 0) { idx = found; render(); } else { alert('全部评完了，记得导出 JSON'); }
};
document.getElementById('reset').onclick = () => {
  if (confirm('清空本机全部评分？此操作不可撤销。')) { state = {}; save(); render(); }
};
document.getElementById('export').onclick = () => {
  const payload = { seed: DATA.seed, dims: DATA.dims,
    reviewer: prompt('留个名字或代号（可空）') || '',
    finished: new Date().toISOString(),
    items: DATA.items.map(item => {
      const s = get(item.id);
      return { id: item.id, platform: item.platform, tier: item.tier,
               A: item.A, B: item.B, scores: { A: s.A, B: s.B },
               preference: s.preference, note: s.note || '', source: item.source };
    }) };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'blind-scores.json';
  a.click(); URL.revokeObjectURL(a.href);
};
document.getElementById('importBtn').onclick = () => document.getElementById('import').click();
document.getElementById('import').onchange = (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    try {
      const data = JSON.parse(reader.result);
      data.items.forEach(it => {
        const scores = it.scores || { A: it.A, B: it.B };
        state[it.id] = { A: scores.A, B: scores.B, preference: it.preference, note: it.note };
      });
      save(); render(); alert('已导入 ' + data.items.length + ' 条');
    } catch (err) { alert('导入失败：' + err.message); }
  };
  reader.readAsText(file);
};
document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'TEXTAREA') return;
  if (e.key === 'ArrowLeft') document.getElementById('prev').click();
  if (e.key === 'ArrowRight') document.getElementById('next').click();
});
render();
</script></body></html>
"""


def pick_subset(items: list[dict], size: int) -> list[dict]:
    """分层抽样：先铺满「场景 × 难度」网格，平台按序轮流覆盖。

    120 条全评对单人是重负；30 条（6 场景 × 5 难度，平台轮转）能保住结构覆盖，
    把工作量降到四分之一，代价是每个「场景×平台」格子只有 1 条样本。
    """
    if size >= len(items):
        return list(items)
    scenes = sorted({item["scene"] for item in items})
    tiers = sorted({item["tier"] for item in items})
    platforms = sorted({item["platform"] for item in items})
    picked: list[dict] = []
    for si, scene in enumerate(scenes):
        for ti, tier in enumerate(tiers):
            platform = platforms[(si + ti) % len(platforms)]
            match = [i for i in items
                     if i["scene"] == scene and i["tier"] == tier and i["platform"] == platform]
            if match:
                picked.append(match[0])
            if len(picked) >= size:
                return picked
    return picked


def build_html(path: Path, limit: int | None = None, ids: set[str] | None = None) -> Path:
    """生成自包含的盲评页面：数据内联，无网络依赖，评分存在 localStorage。"""
    packet = make_packet()
    if ids:
        packet["items"] = [item for item in packet["items"] if item["id"] in ids]
        packet["subset"] = len(packet["items"])
    elif limit:
        packet["items"] = pick_subset(packet["items"], limit)
        packet["subset"] = limit
    for item in packet["items"]:
        item.pop("scores", None)   # 页面自己维护评分状态
    html = (HTML_TEMPLATE
            .replace("__PACKET__", json.dumps(packet, ensure_ascii=False))
            .replace("__ANCHORS__", json.dumps(ANCHORS, ensure_ascii=False)))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path


def aggregate_scores(path: Path) -> str:
    """把回收的评分 JSON 折算成报告表格：系统组 vs 原话组，按 source 认边。

    只统计真正打过分（任一分值非 0）的条目；样本不足或零方差时明确告警，
    避免拿 10 条数据冒充 120 条的验收结论。
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    dims = data["dims"]
    buckets = {"system": {d: [] for d in dims}, "raw": {d: [] for d in dims}}
    pref = {"system": 0, "raw": 0, "tie": 0}
    scored: list[dict] = []

    for item in data["items"]:
        scores = item.get("scores") or {}
        sides = {side: (scores.get(side) or {}) for side in ("A", "B")}
        if not any(any(v for v in sides[side].values()) for side in sides):
            continue                      # 未评分条目直接跳过
        scored.append(item)
        for side in ("A", "B"):
            kind = (item.get("source") or {}).get(side, "raw")
            for dim in dims:
                value = sides[side].get(dim)
                if isinstance(value, (int, float)) and value:
                    buckets[kind][dim].append(value)
        choice = item.get("preference") or "tie"
        if choice in ("A", "B"):
            pref[(item.get("source") or {}).get(choice, "raw")] += 1
        else:
            pref["tie"] += 1

    def mean(values):
        return sum(values) / len(values) if values else 0.0

    def std(values):
        if len(values) < 2:
            return 0.0
        m = mean(values)
        return (sum((v - m) ** 2 for v in values) / len(values)) ** 0.5

    lines = ["| 维度 | 系统均分 | 原话均分 | 差值 | 系统组标准差 |",
             "| --- | --- | --- | --- | --- |"]
    for dim in dims:
        sys_vals, raw_vals = buckets["system"][dim], buckets["raw"][dim]
        lines.append(f"| {dim} | {mean(sys_vals):.2f} | {mean(raw_vals):.2f} | "
                     f"{mean(sys_vals) - mean(raw_vals):+.2f} | {std(sys_vals):.2f} |")

    n = len(scored)
    total = sum(pref.values()) or 1
    system_all = [v for d in dims for v in buckets["system"][d]]
    overall = mean(system_all)
    scenes = sorted({(item.get("id") or "")[:2] for item in scored})
    platforms = sorted({item.get("platform") for item in scored if item.get("platform")})
    tiers = sorted({item.get("tier") for item in scored if item.get("tier")})

    lines += ["",
              f"- 有效样本：{n} 条（语料共 {len(data['items'])} 条）",
              f"- 覆盖：场景 {'/'.join(scenes) or '—'}｜平台 {'/'.join(platforms) or '—'}"
              f"｜难度 {''.join(tiers) or '—'}",
              f"- 系统组五维总均分：**{overall:.2f}**（门槛 3.5）",
              f"- 偏好率：系统 {pref['system'] / total:.0%}｜原话 {pref['raw'] / total:.0%}｜"
              f"相当 {pref['tie'] / total:.0%}（门槛：系统 ≥80%）"]

    warnings = []
    if n < 30:
        warnings.append(f"样本仅 {n} 条（<30），置信度不足，**不能作为验收判定**")
    if std(system_all) == 0 and system_all:
        warnings.append(f"系统组零方差（全部 {system_all[0]} 分）——存在天花板效应，"
                        "建议复评时强制拉开分档或改用 3 档量表")
    if len(scenes) < 6:
        warnings.append(f"仅覆盖 {len(scenes)}/6 个场景，场景结论不可外推")
    if warnings:
        lines += ["", "**告警**"] + [f"- {w}" for w in warnings]
    return "\n".join(lines)


def main() -> int:
    # Windows 控制台默认 GBK，报告里的「」与中文标点在重定向时会直接抛 UnicodeEncodeError
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass
    if "--html" in sys.argv:
        target = Path(sys.argv[sys.argv.index("--html") + 1])
        limit = None
        if "--limit" in sys.argv:
            limit = int(sys.argv[sys.argv.index("--limit") + 1])
        ids = None
        if "--ids" in sys.argv:
            ids = {i.strip() for i in sys.argv[sys.argv.index("--ids") + 1].split(",") if i.strip()}
        build_html(target, limit, ids)
        scale = f"（指定 {len(ids)} 条）" if ids else (f"（分层子集 {limit} 条）" if limit else "（全量）")
        print(f"盲评页面已生成：{target}{scale}")
        return 0
    if "--score" in sys.argv:
        print(aggregate_scores(Path(sys.argv[sys.argv.index("--score") + 1])))
        return 0
    if "--packet" in sys.argv:
        target = Path(sys.argv[sys.argv.index("--packet") + 1])
        build_packet(target)
        print(f"盲评包已生成：{target}")
        return 0
    result = run(verbose=True)
    print(json.dumps(result, ensure_ascii=False, indent=2) if "--json" in sys.argv
          else format_report(result))
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
