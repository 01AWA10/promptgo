# image_* 元数据清单与体积预算 v0.1

> 阶段 3 交付物 · 2026-11-16 · 关联：[`VISUAL-TERMS-v1.0.md`](VISUAL-TERMS-v1.0.md)、[`IMAGE-PROMPT-SPEC-v1.0.md`](IMAGE-PROMPT-SPEC-v1.0.md) §9.3
> 约束来源：计划 §1.4 —— `/v1/meta` 整体 ≤12 KB、图像相关字段 ≤5 KB；组件 ≤44 KB。

## 1. 核心决策：全量词表不进 `/v1/meta`

324 条词条若整体下发，仅「中文 + 英文」两列就约 8.7 KB，直接击穿 5 KB 预算。因此：

| 数据 | 去向 | 理由 |
| --- | --- | --- |
| 全量 324 词条（含别名、场景、权重） | **只留服务端** `TERMS` 常量 | 别名用于召回，前端不需要；也避免体积进组件 |
| 分组展示清单（约 70 条精选） | `/v1/meta` 的 `image_*` | chips 只展示高频项，够用即可 |
| 比例 / 平台 / 场景枚举 | `/v1/meta` 的 `image_imageratios` 等 | 枚举小，直接给 |

原则沿用现有工程纪律：**词表放服务端，前端只加展示**。

## 2. 字段清单

### 2.1 六个字段

| 字段 | 类型 | 条数 | 内容 | 实测 |
| --- | --- | --- | --- | --- |
| `image_styles` | `object[]`，`{id,label}` | 17 | 高频主风格（取自词典 28 条；v1.3 起加 `概念设定`，上限 16 → 17 以免挤掉 `黏土动画`） | — |
| `image_lighting` | 同上 | 12 | 光线（取自词典 24 条） | — |
| `image_compositions` | 同上 | 12 | 构图（取自词典 24 条） | — |
| `image_materials` | 同上 | 8 | 材质（取自词典 20 条） | — |
| `image_negatives` | 同上 | 4 | 通用必备负面 4 项 | — |
| `image_ratios` | 同上 | 8 | 1:1 / 4:5 / 3:4 / 16:9 / 9:16 / 2:3 / 21:9 | — |
| `image_platforms` | 同上 | 5 | generic / mj / sdxl / flux / dalle3 | — |
| `image_scenes` | 同上 | 6 | MK / EC / IL / AV / PS / CD | — |

**实测 3,383 B（8 个字段）**，占 5 KB 字段预算的 66%；`/v1/meta` 合计 10,154 B，占 12 KB 预算的 83%。
比原计划的 6 字段多出 `image_materials` 与 `image_negatives`——它们直接来自词典，不额外维护。

### 2.2 响应示例

```json
{
  "version": "1.2.0",
  "meta": {
    "image_styles": ["photorealistic|写实摄影", "cinematic|电影感", "flat-illustration|扁平插画"],
    "image_lighting": ["natural-light|自然光", "golden-hour|黄金时刻"],
    "image_compositions": ["rule-of-thirds|三分法", "centered|中心构图"],
    "image_ratios": {"1:1": "主图/头像", "16:9": "横版"},
    "image_platforms": {"generic": "通用", "mj": "Midjourney v6"},
    "image_scenes": {"MK": "营销配图", "EC": "电商主图"}
  }
}
```

## 3. 加载与体积控制

1. **默认内联（实现修订）**：v1 实测 `image_*` 仅 3,383 B、`/v1/meta` 合计 10,154 B，两者都在预算内，因此不做 `?image=1` 门控——少一个参数、少一条分支。门控留待字段继续膨胀到接近 5 KB 时再上。
2. **单组懒加载**：`?image=styles` 只返回该组，前端 chips 按 Tab 切换时再取。
3. **id 化**：元素统一 `"id|中文"` 单字符串，省掉对象键名（对象形如 `{"id":…,"zh":…}` 每条多 12–16 B）。
4. **别名不上线**：`aliases`、`scenes`、`weight` 仅服务端使用；前端不做匹配，只做展示与回传。
5. **体积守护**：`tests/test_meta.py` 增断言——`image_*` 序列化后 ≤5 KB、整体 ≤12 KB、字段数 = 6；超限即失败。
6. **版本化**：`image_*` 随 `engine.__version__` 走，词表改动须同步 `meta` 快照，避免前端 chips 与后端词典不一致。

## 4. 与现有 meta 的关系

| 项 | 现状 | 变更 |
| --- | --- | --- |
| 现有分组 | 12 意图 / 22 领域 / 55 渠道 / 63 语气 | 不动，字段顺序不变 |
| 新增分组 | — | 6 个 `image_*`，追加在末尾 |
| 总负载 | 6.7 KB | 6.7 + 2.55 ≈ 9.3 KB（≤12 KB ✓） |
| 老客户端 | 忽略新字段 | 无影响（`?image=1` 才出现，默认零增量） |

## 5. 验收对照

| 验收项 | 要求 | 本文件情况 |
| --- | --- | --- |
| 图像字段 ≤5 KB | 是 | 2.55 KB（32%） |
| 总负载 ≤12 KB | 是 | 约 9.3 KB |
| 懒加载 | 按分组 | `?image=1` / `?image=styles` |
| 可断言 | 有测试点 | 第 3 节第 5 条 |
| 与词表一致 | id 一一对应 | 24/16/16 均取自 44/40/40 条的子集 |
