/**
 * 前端最小冒烟：在无浏览器环境下加载 web/prompt-enhancer.js 并验证三块纯逻辑。
 *
 *   node tests/frontend/smoke.mjs                      # 只跑纯逻辑
 *   node tests/frontend/smoke.mjs --endpoint http://127.0.0.1:7317   # 追加真实接口
 *
 * 为什么不用 jsdom：组件零依赖、单文件，只需要 HTMLElement/customElements 等少量桩；
 * 用 node:vm 建沙箱更轻，也不会把测试依赖塞进交付物。
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SOURCE = path.join(HERE, "..", "..", "web", "prompt-enhancer.js");

function fakeElement() {
  const events = [];
  return {
    value: "",
    focused: false,
    disabled: false,
    classList: { add() {}, remove() {} },
    setAttribute() {},
    addEventListener() {},
    dispatchEvent(ev) { events.push({ type: ev.type, bubbles: !!ev.bubbles }); return true; },
    focus() { this.focused = true; },
    events
  };
}

function loadComponent(options) {
  const opts = options || {};
  const src = fs.readFileSync(SOURCE, "utf8");
  const noop = () => {};
  class StubHTMLElement {
    constructor() { this.attrs = {}; }
    getAttribute(name) { return Object.prototype.hasOwnProperty.call(this.attrs, name) ? this.attrs[name] : null; }
    setAttribute(name, value) { this.attrs[name] = String(value); }
    hasAttribute(name) { return Object.prototype.hasOwnProperty.call(this.attrs, name); }
    dispatchEvent() { return true; }
    attachShadow() { return { innerHTML: "", querySelector: () => fakeElement(), addEventListener: noop, querySelectorAll: () => [] }; }
  }

  const sandbox = {
    console,
    TextDecoder,
    TextEncoder,
    URL,
    AbortController,
    setTimeout,
    clearTimeout,
    performance: { now: () => 0 },
    requestAnimationFrame: (fn) => setTimeout(fn, 0),
    cancelAnimationFrame: (id) => clearTimeout(id),
    Event: class Event {
      constructor(type, opts) { this.type = type; Object.assign(this, opts || {}); }
    },
    CustomEvent: class CustomEvent {
      constructor(type, opts) { this.type = type; Object.assign(this, opts || {}); }
    },
    localStorage: { getItem: () => null, setItem: noop, removeItem: noop },
    navigator: { clipboard: { writeText: async () => {} } },
    location: { origin: "http://127.0.0.1:7317" },
    document: {
      currentScript: { src: "http://127.0.0.1:7317/prompt-enhancer.js" },
      readyState: "complete",
      addEventListener: noop,
      removeEventListener: noop,
      querySelector: () => null,
      querySelectorAll: () => [],
      createElement: () => fakeElement(),
      body: fakeElement()
    },
    customElements: { get: () => null, define: noop },
    HTMLElement: StubHTMLElement,
    // 默认禁用网络：纯逻辑用例若意外发起请求会立即暴露；--endpoint 时才接真 fetch
    fetch: opts.fetch || (() => Promise.reject(new Error("smoke 环境默认禁用网络"))),
    module: undefined,
    exports: undefined
  };
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  sandbox.self = sandbox;

  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename: "prompt-enhancer.js" });
  return sandbox.window.PromptEnhancer;
}

function endpointFromArgv() {
  const idx = process.argv.indexOf("--endpoint");
  return idx > -1 ? process.argv[idx + 1] : null;
}

const ENDPOINT = endpointFromArgv();
const PE = loadComponent(ENDPOINT ? { fetch: (input, init) => globalThis.fetch(input, init) } : {});
const I = PE._internals;

let passed = 0;
const failures = [];

async function check(name, fn) {
  try {
    await fn();
    passed += 1;
    console.log("ok   " + name);
  } catch (err) {
    failures.push(name + " :: " + (err && err.message));
    console.log("FAIL " + name + " :: " + (err && err.message));
  }
}

/* ------------------------------------------------------------ SSE 分帧 */
await check("暴露 internals 与版本号", () => {
  assert.equal(typeof I.parseFrame, "function");
  assert.equal(typeof I.drainFrames, "function");
  assert.ok(/^\d+\.\d+\.\d+$/.test(PE.version), "version 形如 1.0.0");
});

await check("parseFrame 解析 event + data", () => {
  const ev = I.parseFrame('event: chunk\ndata: {"delta":"你好"}');
  assert.equal(ev.event, "chunk");
  assert.equal(ev.data.delta, "你好");
});

await check("parseFrame 缺 data 返回 null", () => {
  assert.equal(I.parseFrame("event: stage"), null);
});

await check("parseFrame 坏 JSON 返回 null", () => {
  assert.equal(I.parseFrame("data: not-json"), null);
});

await check("parseFrame 支持多行 data 拼接", () => {
  const ev = I.parseFrame('data: {"delta":\ndata: "A"}');
  assert.equal(ev.data.delta, "A");
});

await check("drainFrames 半帧留到下一次", () => {
  const first = I.drainFrames("", 'event: chu');
  assert.equal(first.events.length, 0);
  assert.equal(first.rest, "event: chu");
  const second = I.drainFrames(first.rest, 'nk\ndata: {"delta":"A"}\n\n');
  assert.equal(second.events.length, 1);
  assert.equal(second.events[0].data.delta, "A");
  assert.equal(second.rest, "");
});

await check("drainFrames 一包里两帧 + 残帧", () => {
  const out = I.drainFrames("", 'data: {"delta":"A"}\n\ndata: {"delta":"B"}\n\ndata: {"del');
  // vm 沙箱里的数组原型与宿主不同，用字符串比较避免跨 realm 的 deepEqual 失败
  assert.equal(out.events.map((e) => e.data.delta).join("|"), "A|B");
  assert.equal(out.rest, 'data: {"del');
});

await check("drainFrames 脏帧不阻塞后续帧", () => {
  const out = I.drainFrames("", 'data: nope\n\ndata: {"delta":"B"}\n\n');
  assert.equal(out.events.map((e) => e.data.delta).join("|"), "B");
});

await check("drainFrames 逐字节喂入仍按序还原", () => {
  const sse = 'event: stage\ndata: {"stage":"analyze"}\n\n' +
    'event: chunk\ndata: {"delta":"第一段"}\n\n' +
    'event: done\ndata: {"chars":3}\n\n';
  let buffer = "";
  const events = [];
  for (const ch of sse) {                 // 最恶劣分片：1 个字符一块
    const out = I.drainFrames(buffer, ch);
    buffer = out.rest;
    events.push(...out.events);
  }
  assert.equal(buffer, "");
  assert.deepEqual(events.map((e) => e.event), ["stage", "chunk", "done"]);
  assert.equal(events[1].data.delta, "第一段");
});

/* -------------------------------------------------------- target 回填 */
await check("writeTarget 写值并派发 input/change", () => {
  const el = fakeElement();
  I.writeTarget(el, "替换后的文本");
  assert.equal(el.value, "替换后的文本");
  assert.deepEqual(el.events, [{ type: "input", bubbles: true }, { type: "change", bubbles: true }]);
  assert.equal(el.focused, true);
});

/* ------------------------------------------------ JSON 回退与错误映射 */
await check("supportsStream 识别无流响应", () => {
  assert.equal(I.supportsStream({}), false);
  assert.equal(I.supportsStream({ body: null }), false);
  assert.equal(I.supportsStream({ body: { getReader() {} } }), true);
});

await check("readJSONResponse 正常返回", async () => {
  const data = await I.readJSONResponse({
    ok: true, status: 200, json: async () => ({ ok: true, enhanced: "## 角色" })
  });
  assert.equal(data.enhanced, "## 角色");
});

await check("readJSONResponse 500 映射为错误消息", async () => {
  await assert.rejects(
    I.readJSONResponse({
      ok: false, status: 500,
      json: async () => ({ ok: false, error: { code: "ENGINE_ERROR", message: "引擎内部错误：boom" } })
    }),
    /引擎内部错误：boom/
  );
});

await check("readJSONResponse ok:false 也算失败", async () => {
  await assert.rejects(
    I.readJSONResponse({ ok: true, status: 200, json: async () => ({ ok: false, error: { message: "业务失败" } }) }),
    /业务失败/
  );
});

await check("readJSONResponse 非 JSON 退回状态码文案", async () => {
  await assert.rejects(
    I.readJSONResponse({ ok: false, status: 422, json: async () => { throw new SyntaxError("bad"); } }),
    /服务返回 422/
  );
});

/* ---------------------------------------------- plan.sections 章节导航 */
await check("sectionList 归一化 plan.sections", () => {
  const out = I.sectionList([{ key: "role", title: "角色设定" }, { key: "steps", title: "任务拆解" }]);
  assert.equal(out.map((s) => s.key + ":" + s.title).join("|"), "role:角色设定|steps:任务拆解");
});

await check("sectionList 兼容 blocks 与脏数据", () => {
  const out = I.sectionList([{ key: "role", title: "角色设定", body: "x" }, null, { title: "" }, { title: "输出契约" }]);
  assert.equal(out.length, 2);
  assert.equal(out[1].key, "输出契约", "缺 key 时用 title 兜底");
});

await check("sectionList 空输入返回空数组", () => {
  assert.equal(I.sectionList(null).length, 0);
  assert.equal(I.sectionList([]).length, 0);
});

/* -------------------------------------------------- 真实接口（可选） */
if (ENDPOINT) {
  await check("端到端 JSON 回退（真实服务）", async () => {
    const data = await PE.enhance("写个周报", { endpoint: ENDPOINT, mode: "concise" });
    assert.equal(data.ok, true);
    assert.ok(data.enhanced.includes("角色"), "增强结果应含角色段");
    assert.ok(data.score.after >= data.score.before, "增强后分数不应下降");
    assert.ok(Array.isArray(data.blocks) && data.blocks.length >= 4, "JSON 回退应带 blocks 供章节导航");
  });
}

console.log("----------------------------------------");
console.log("PASS " + passed + " | FAIL " + failures.length);
if (failures.length) {
  console.log(failures.join("\n"));
  process.exit(1);
}
