/*!
 * PromptGo · 可嵌入的离线提示词增强组件
 * 单文件、零依赖、Shadow DOM 隔离。ES2020+。
 * 用法：
 *   <script src="http://127.0.0.1:7317/prompt-enhancer.js" defer></script>
 *   <prompt-enhancer target="#my-input" mode="struct" layout="bubble"></prompt-enhancer>
 */
(function () {
  "use strict";

  if (window.customElements && window.customElements.get("prompt-enhancer")) return;

  var VERSION = "1.0.0";
  var DEFAULT_PORT = 7317;
  var SELF_SCRIPT = document.currentScript;

  /* ------------------------------------------------------------------ 工具 */
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function inlineMd(s) {
    return s
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`]+)`/g, "<code>$1</code>");
  }

  /* 极简 Markdown 渲染：只支持本工具会产出的语法，避免引入第三方解析器 */
  function renderMd(src) {
    var lines = esc(src).split("\n");
    var html = "";
    var list = null;
    var inFence = false;
    var fenceBuf = [];

    function closeList() {
      if (list) { html += "</" + list + ">"; list = null; }
    }

    for (var i = 0; i < lines.length; i++) {
      var line = lines[i].replace(/\s+$/, "");
      var m;

      if (/^```/.test(line.trim())) {
        if (inFence) {
          html += '<pre class="pg-pre">' + fenceBuf.join("\n") + "</pre>";
          fenceBuf = [];
          inFence = false;
        } else {
          closeList();
          inFence = true;
        }
        continue;
      }
      if (inFence) { fenceBuf.push(lines[i]); continue; }

      if (!line.trim()) { closeList(); continue; }

      if ((m = line.match(/^###\s+(.*)$/))) { closeList(); html += "<h5>" + inlineMd(m[1]) + "</h5>"; continue; }
      if ((m = line.match(/^##\s+(.*)$/))) { closeList(); html += "<h4>" + inlineMd(m[1]) + "</h4>"; continue; }
      if ((m = line.match(/^#\s+(.*)$/))) { closeList(); html += "<h3>" + inlineMd(m[1]) + "</h3>"; continue; }

      if ((m = line.match(/^[-*]\s+\[\s?\]\s*(.*)$/))) {
        if (list !== "ul") { closeList(); html += "<ul>"; list = "ul"; }
        html += '<li class="pg-check"><i></i><span>' + inlineMd(m[1]) + "</span></li>";
        continue;
      }
      if ((m = line.match(/^[-*]\s+(.*)$/))) {
        if (list !== "ul") { closeList(); html += "<ul>"; list = "ul"; }
        html += "<li>" + inlineMd(m[1]) + "</li>";
        continue;
      }
      if ((m = line.match(/^\d+[.)]\s+(.*)$/))) {
        if (list !== "ol") { closeList(); html += "<ol>"; list = "ol"; }
        html += "<li>" + inlineMd(m[1]) + "</li>";
        continue;
      }
      closeList();
      html += "<p>" + inlineMd(line) + "</p>";
    }
    closeList();
    if (inFence && fenceBuf.length) html += '<pre class="pg-pre">' + fenceBuf.join("\n") + "</pre>";
    return html;
  }

  function parseFrame(frame) {
    var event = "message";
    var data = [];
    frame.split("\n").forEach(function (line) {
      if (line.indexOf("event:") === 0) event = line.slice(6).trim();
      else if (line.indexOf("data:") === 0) data.push(line.slice(5).trim());
    });
    if (!data.length) return null;
    try { return { event: event, data: JSON.parse(data.join("\n")) }; }
    catch (e) { return null; }
  }

  /* SSE 分帧：把新到的文本并入缓冲，切出所有完整帧（以 \n\n 结尾）。
     返回 events（已解析）与 rest（半帧残留），纯函数，便于单测。 */
  function drainFrames(buffer, chunk) {
    var text = buffer + (chunk || "");
    var events = [];
    var idx;
    while ((idx = text.indexOf("\n\n")) >= 0) {
      var ev = parseFrame(text.slice(0, idx));
      text = text.slice(idx + 2);
      if (ev) events.push(ev);
    }
    return { events: events, rest: text };
  }

  /* 回填目标输入框：写值 + 派发 input/change，保证 React/Vue 受控组件能感知 */
  function writeTarget(el, text) {
    el.value = text;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    if (el.focus) el.focus();
    return true;
  }

  /* 流式响应体是否可用：不可用时回退到一次性 JSON 接口 */
  function supportsStream(res) {
    return !!(res && res.body && res.body.getReader);
  }

  /* 统一 JSON 响应处理：非 2xx、非 JSON、或 ok:false 都转成可读错误 */
  async function readJSONResponse(res) {
    var data = null;
    try { data = await res.json(); } catch (e) { data = null; }
    if (!res.ok || !data || data.ok === false) {
      throw new Error((data && data.error && data.error.message) || ("服务返回 " + res.status));
    }
    return data;
  }

  /* plan.sections 与 JSON 的 blocks 字段形状不同，统一成 {key,title} 供导航渲染 */
  function sectionList(src) {
    return (src || []).filter(function (s) { return s && s.title; })
      .map(function (s) { return { key: String(s.key || s.title), title: String(s.title) }; });
  }

  function detectEndpoint(el) {
    var explicit = el.getAttribute("endpoint");
    if (explicit) return explicit.replace(/\/$/, "");
    try {
      var stored = localStorage.getItem("pg:endpoint");
      if (stored) return stored.replace(/\/$/, "");
    } catch (e) { /* 隐私模式 */ }
    if (SELF_SCRIPT && SELF_SCRIPT.src) {
      try { return new URL(SELF_SCRIPT.src).origin; } catch (e) { /* noop */ }
    }
    return "http://127.0.0.1:" + DEFAULT_PORT;
  }

  /* ------------------------------------------------------------------ 样式 */
  var CSS = `
  :host{all:initial;--pg-accent:#4f46e5;--pg-accent-2:#7c3aed;--pg-bg:#fff;--pg-bg-2:#f7f8fc;--pg-fg:#14161f;--pg-fg-2:#5b6178;--pg-line:#e6e8f0;--pg-ok:#059669;--pg-warn:#d97706;--pg-bad:#dc2626;--pg-radius:16px;--pg-bd:1px solid var(--pg-line);--pg-shadow:0 18px 48px #14161f2e,0 2px 8px #14161f14;font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;color:var(--pg-fg);display:block;contain:layout style}
  @media (prefers-color-scheme:dark){:host{--pg-bg:#171a24;--pg-bg-2:#1e2230;--pg-fg:#eef0f7;--pg-fg-2:#9aa2ba;--pg-line:#2b3040;--pg-shadow:0 18px 48px #00000080,0 2px 8px #0000004d}}
  :host([theme="dark"]){--pg-bg:#171a24;--pg-bg-2:#1e2230;--pg-fg:#eef0f7;--pg-fg-2:#9aa2ba;--pg-line:#2b3040;--pg-shadow:0 18px 48px #00000080}
  *{box-sizing:border-box}
  button,select,textarea{font:inherit;color:inherit}
  button{cursor:pointer;border:0;background:none}
  .pg-bubble{position:fixed;right:24px;bottom:24px;z-index:var(--pg-z,2147483000);display:flex;align-items:center;gap:8px;padding:12px 18px;border-radius:999px;color:#fff;font-weight:600;letter-spacing:.2px;background:linear-gradient(135deg,var(--pg-accent),var(--pg-accent-2));box-shadow:0 10px 26px #4f46e561;transition:transform .18s,box-shadow .18s}
  .pg-bubble:hover{transform:translateY(-2px);box-shadow:0 14px 32px #4f46e575}
  .pg-bubble:active{transform:scale(.98)}
  .pg-bubble svg{width:17px;height:17px}
  :host([position="left"]) .pg-bubble{right:auto;left:24px}
  .pg-bubble[hidden]{display:none}
  .pg-panel{position:fixed;right:24px;bottom:88px;z-index:var(--pg-z,2147483000);width:min(392px,calc(100vw - 32px));max-height:min(688px,calc(100vh - 120px));display:flex;flex-direction:column;background:var(--pg-bg);border:var(--pg-bd);border-radius:var(--pg-radius);box-shadow:var(--pg-shadow);overflow:hidden;opacity:0;transform:translateY(12px) scale(.98);pointer-events:none;transition:opacity .2s,transform .2s}
  :host([open]) .pg-panel{opacity:1;transform:none;pointer-events:auto}
  :host([position="left"]) .pg-panel{right:auto;left:24px}
  :host([layout="inline"]) .pg-panel{position:static;opacity:1;transform:none;pointer-events:auto;width:100%;max-height:none;box-shadow:none}
  :host([layout="inline"]) .pg-bubble{display:none}
  .pg-head{display:flex;align-items:center;gap:8px;padding:12px 14px;border-bottom:var(--pg-bd);background:var(--pg-bg-2)}
  .pg-title{font-weight:600;font-size:13.5px;display:flex;align-items:center;gap:7px}
  .pg-dot{width:7px;height:7px;border-radius:50%;background:var(--pg-fg-2);flex:none}
  .pg-dot.ok{background:var(--pg-ok);box-shadow:0 0 0 3px #05966929}
  .pg-dot.bad{background:var(--pg-bad);box-shadow:0 0 0 3px #dc262629}
  .pg-dot.busy{background:var(--pg-accent);animation:pg-pulse 1s infinite}
  @keyframes pg-pulse{0%,100%{opacity:1}50%{opacity:.35}}
  .pg-spacer{flex:1}
  .pg-ver{font-size:11px;color:var(--pg-fg-2)}
  .pg-icon-btn{width:26px;height:26px;border-radius:8px;display:grid;place-items:center;color:var(--pg-fg-2)}
  .pg-icon-btn:hover{background:var(--pg-line);color:var(--pg-fg)}
  .pg-icon-btn svg{width:14px;height:14px}

  .pg-body{padding:12px 14px;overflow-y:auto;overscroll-behavior:contain;flex:1;min-height:0}
  .pg-label{font-size:11.5px;font-weight:600;letter-spacing:.4px;text-transform:uppercase;color:var(--pg-fg-2);margin:2px 0 6px}
  .pg-input{width:100%;min-height:84px;max-height:180px;resize:vertical;padding:10px 12px;border:var(--pg-bd);border-radius:10px;background:var(--pg-bg);font-size:13.5px;line-height:1.6;outline:none}
  .pg-input:focus{border-color:var(--pg-accent);box-shadow:0 0 0 3px #4f46e51f}
  .pg-input::placeholder{color:var(--pg-fg-2);opacity:.75}
  .pg-row{display:flex;gap:8px;margin-top:10px;align-items:center}
  .pg-row-mt{margin-top:12px}
  .pg-select{flex:1;min-width:0;padding:7px 9px;border:var(--pg-bd);border-radius:9px;background:var(--pg-bg);font-size:12.5px;outline:none}
  .pg-select:focus{border-color:var(--pg-accent)}
  .pg-btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:8px 14px;border-radius:9px;font-size:13px;font-weight:600;background:var(--pg-bg-2);color:var(--pg-fg);border:var(--pg-bd);white-space:nowrap}
  .pg-btn:hover{filter:brightness(.97)}
  .pg-btn:active{transform:scale(.985)}
  .pg-btn.primary{background:linear-gradient(135deg,var(--pg-accent),var(--pg-accent-2));color:#fff;border-color:transparent;box-shadow:0 4px 14px #4f46e54d;flex:1}
  .pg-btn.primary[disabled]{opacity:.6;cursor:not-allowed;box-shadow:none}
  .pg-btn svg{width:14px;height:14px}
  .pg-btn[disabled]{opacity:.45;cursor:not-allowed}
  .pg-btn.ghost{border-color:transparent;background:transparent;color:var(--pg-fg-2)}
  .pg-btn.ghost:hover{background:var(--pg-bg-2);color:var(--pg-fg)}

  .pg-chips{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0 2px}
  .pg-chip{font-size:11.5px;padding:3px 9px;border-radius:999px;background:var(--pg-bg-2);border:var(--pg-bd);color:var(--pg-fg-2)}
  .pg-chip b{color:var(--pg-fg);font-weight:600}
  .pg-chip.warn{color:var(--pg-warn);border-color:#d977064d;background:#d9770614}
  .pg-result{margin-top:12px;border:var(--pg-bd);border-radius:12px;background:var(--pg-bg-2);overflow:hidden;display:none}
  .pg-result.show{display:block}
  .pg-result-head{display:flex;align-items:center;gap:6px;padding:7px 10px;border-bottom:var(--pg-bd);font-size:11.5px;font-weight:600;letter-spacing:.4px;text-transform:uppercase;color:var(--pg-fg-2)}
  .pg-nav{display:flex;flex-wrap:wrap;gap:4px;padding:7px 10px;border-bottom:var(--pg-bd);background:var(--pg-bg)}
  .pg-nav[hidden]{display:none}
  .pg-nav button{padding:2px 8px;font-size:11px}
  .pg-nav button:hover{border-color:var(--pg-accent);color:var(--pg-accent)}
  .pg-md{padding:10px 12px;max-height:260px;overflow-y:auto;font-size:13px;line-height:1.68}
  :host([layout="inline"]) .pg-md{max-height:none}
  .pg-md h3,.pg-md h4,.pg-md h5{margin:10px 0 4px;font-size:13px;font-weight:700}
  .pg-md h3{font-size:14px}
  .pg-md h4{color:var(--pg-accent)}
  .pg-md h4:first-child,.pg-md h3:first-child{margin-top:0}
  .pg-md p{margin:0 0 6px}
  .pg-md ul,.pg-md ol{margin:0 0 8px;padding-left:18px}
  .pg-md li{margin:2px 0}
  .pg-md li.pg-check{list-style:none;display:flex;gap:7px;align-items:flex-start;margin-left:-14px}
  .pg-md li.pg-check i{width:12px;height:12px;margin-top:4px;border:1.5px solid var(--pg-line);border-radius:3px;flex:none}
  .pg-md code{background:#4f46e51a;color:var(--pg-accent);padding:1px 4px;border-radius:4px;font-size:12px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
  .pg-md .pg-pre{background:var(--pg-bg);border:var(--pg-bd);border-radius:8px;padding:8px 10px;overflow-x:auto;font-size:12px;margin:0 0 8px}
  .pg-md strong{font-weight:600}
  .pg-caret{display:inline-block;width:2px;height:13px;background:var(--pg-accent);vertical-align:-2px;animation:pg-blink .9s steps(2) infinite}
  @keyframes pg-blink{0%,100%{opacity:1}50%{opacity:0}}

  .pg-score{padding:9px 12px 11px;border-top:1px solid var(--pg-line);display:none}
  .pg-score.show{display:block}
  .pg-score-top{display:flex;align-items:baseline;gap:8px;margin-bottom:8px}
  .pg-score-num{font-size:20px;font-weight:700;letter-spacing:-.4px}
  .pg-score-num small{font-size:11.5px;font-weight:500;color:var(--pg-fg-2)}
  .pg-delta{font-size:12px;font-weight:700;color:var(--pg-ok)}
  .pg-dim{display:grid;grid-template-columns:64px 1fr 34px;align-items:center;gap:8px;font-size:11.5px;color:var(--pg-fg-2);margin:3px 0}
  .pg-bar{position:relative;height:5px;border-radius:3px;background:var(--pg-line);overflow:hidden}
  .pg-bar span{position:absolute;inset:0 auto 0 0;border-radius:3px;background:linear-gradient(90deg,var(--pg-accent),var(--pg-accent-2));transition:width .5s cubic-bezier(.22,1,.36,1)}
  .pg-dim em{font-style:normal;text-align:right;color:var(--pg-fg);font-weight:600}
  .pg-grade{margin-top:7px;font-size:11.5px;color:var(--pg-fg-2)}
  .pg-foot{display:flex;gap:8px;padding:10px 14px;border-top:1px solid var(--pg-line);background:var(--pg-bg-2)}
  .pg-note{font-size:11.5px;color:var(--pg-fg-2);padding:8px 10px;border-radius:9px;background:var(--pg-bg-2);border:1px dashed var(--pg-line);display:none;margin-top:10px}
  .pg-note.show{display:block}
  .pg-note code{background:#4f46e51a;padding:1px 5px;border-radius:4px;font-family:ui-monospace,monospace;font-size:11.5px}
  .pg-note.err{border-style:solid;border-color:#dc262659;color:var(--pg-bad);background:#dc26260f}
  .pg-toast{position:absolute;left:50%;bottom:14px;transform:translate(-50%,8px);background:var(--pg-fg);color:var(--pg-bg);font-size:12px;padding:6px 12px;border-radius:999px;opacity:0;pointer-events:none;transition:all .22s;z-index:5}
  .pg-toast.show{opacity:1;transform:translate(-50%,0)}
  .pg-loading{display:flex;align-items:center;gap:8px;font-size:12.5px;color:var(--pg-fg-2)}
  .pg-loading i{width:13px;height:13px;border:2px solid var(--pg-line);border-top-color:var(--pg-accent);border-radius:50%;animation:pg-spin .7s linear infinite}
  @keyframes pg-spin{to{transform:rotate(360deg)}}
  @media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
  `;

  /* ------------------------------------------------------------------ 组件 */
  class PromptEnhancer extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._state = { status: "idle", result: null, analysis: null, score: null, text: "" };
      this._health = null;
      this._abort = null;
      this._toastTimer = null;
    }

    /* -------------------------------------------------- 生命周期 */
    connectedCallback() {
      if (this._built) return;
      this._built = true;
      this.endpoint = detectEndpoint(this);
      this._build();
      this._bind();
      this._restoreDraft();
      if (this.hasAttribute("open")) this.open();
      this._checkHealth();
    }

    disconnectedCallback() {
      if (this._abort) this._abort.abort();
      if (this._docKey) document.removeEventListener("keydown", this._docKey);
    }

    static get observedAttributes() { return ["open", "mode", "theme"]; }

    attributeChangedCallback(name, oldV, newV) {
      if (!this._built) return;
      if (name === "open" && this.shadowRoot) {
        var panel = this.shadowRoot.querySelector(".pg-panel");
        if (panel) panel.setAttribute("aria-hidden", newV === null ? "true" : "false");
      }
      if (name === "mode" && this.shadowRoot) {
        var sel = this.shadowRoot.querySelector(".pg-mode");
        if (sel && newV) sel.value = newV;
      }
    }

    /* -------------------------------------------------- 构建 DOM */
    _build() {
      var root = this.shadowRoot;
      var style = document.createElement("style");
      style.textContent = CSS;
      root.appendChild(style);

      var wrap = document.createElement("div");
      wrap.className = "pg-root";
      wrap.innerHTML = [
        '<button class="pg-bubble" type="button" title="提示词增强">',
        '  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v3M12 18v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M3 12h3M18 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/><circle cx="12" cy="12" r="3.2"/></svg>',
        "  <span>" + esc(this.getAttribute("label") || "提示词增强") + "</span>",
        "</button>",
        '<section class="pg-panel" role="dialog" aria-label="提示词增强" aria-hidden="true">',
        '  <header class="pg-head">',
        '    <span class="pg-title"><span class="pg-dot"></span>PromptGo</span>',
        '    <span class="pg-spacer"></span>',
        '    <span class="pg-ver">v' + VERSION + "</span>",
        '    <button class="pg-icon-btn pg-clear" type="button" title="清空">',
        '      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14"/></svg>',
        "    </button>",
        '    <button class="pg-icon-btn pg-close" type="button" title="收起 (Esc)">',
        '      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>',
        "    </button>",
        "  </header>",
        '  <div class="pg-body">',
        '    <div class="pg-label">原始需求</div>',
        '    <textarea class="pg-input" placeholder="用一句话描述你要做什么，越具体越好…&#10;例如：给新能源车企写一条小红书文案，突出充电 5 分钟续航 300 公里"></textarea>',
        '    <div class="pg-note pg-health"></div>',
        '    <div class="pg-row">',
        '      <select class="pg-select pg-mode" title="增强模式">',
        '        <option value="struct">结构化</option><option value="concise">精简</option>',
        '        <option value="creative">创意</option><option value="academic">学术</option>',
        '        <option value="code">代码</option><option value="agent">智能体</option>',
        "      </select>",
        '      <select class="pg-select pg-intensity" title="增强深度">',
        '        <option value="light">轻量</option><option value="standard" selected>标准</option>',
        '        <option value="deep">深度</option>',
        "      </select>",
        "    </div>",
        '    <div class="pg-chips"></div>',
        '    <div class="pg-row pg-row-mt">',
        '      <button class="pg-btn primary pg-run" type="button">',
        '        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>',
        "        <span>增强 (Ctrl+Enter)</span>",
        "      </button>",
        "    </div>",
        '    <div class="pg-result">',
        '      <div class="pg-result-head"><span class="pg-result-title">增强结果</span><span class="pg-spacer"></span><span class="pg-len"></span></div>',
        '      <div class="pg-nav" hidden></div>',
        '      <div class="pg-md"></div>',
        '      <div class="pg-score"></div>',
        "    </div>",
        "  </div>",
        '  <footer class="pg-foot">',
        '    <button class="pg-btn pg-copy" type="button" disabled>复制</button>',
        '    <button class="pg-btn pg-replace" type="button" disabled>替换原文</button>',
        '    <span class="pg-spacer"></span>',
        '    <button class="pg-btn ghost pg-retry" type="button" title="重新生成">重试</button>',
        "  </footer>",
        '  <div class="pg-toast"></div>',
        "</section>"
      ].join("");
      root.appendChild(wrap);

      var q = root.querySelector.bind(root);
      this._els = {
        bubble: q(".pg-bubble"),
        panel: q(".pg-panel"),
        body: q(".pg-body"),
        input: q(".pg-input"),
        mode: q(".pg-mode"),
        intensity: q(".pg-intensity"),
        run: q(".pg-run"),
        chips: q(".pg-chips"),
        result: q(".pg-result"),
        resultTitle: q(".pg-result-title"),
        len: q(".pg-len"),
        nav: q(".pg-nav"),
        md: q(".pg-md"),
        score: q(".pg-score"),
        copy: q(".pg-copy"),
        replace: q(".pg-replace"),
        retry: q(".pg-retry"),
        close: q(".pg-close"),
        clear: q(".pg-clear"),
        dot: q(".pg-dot"),
        toast: q(".pg-toast"),
        health: q(".pg-health")
      };

      if (this.getAttribute("mode")) this._els.mode.value = this.getAttribute("mode");
      if (this.getAttribute("intensity")) this._els.intensity.value = this.getAttribute("intensity");
      if (this.getAttribute("z")) this.style.setProperty("--pg-z", this.getAttribute("z"));
      if (this.hasAttribute("layout") === false) this.setAttribute("layout", "bubble");

      var ph = this.getAttribute("placeholder");
      if (ph) this._els.input.placeholder = ph;
    }

    /* -------------------------------------------------- 事件 */
    _bind() {
      var self = this;
      var e = this._els;

      e.bubble.addEventListener("click", function () { self.open(); });
      e.close.addEventListener("click", function () { self.close(); });
      e.clear.addEventListener("click", function () { self._reset(); });

      e.run.addEventListener("click", function () { self.enhance(); });
      e.retry.addEventListener("click", function () { self.enhance(); });
      e.copy.addEventListener("click", function () { self._copy(); });
      e.replace.addEventListener("click", function () { self._replace(); });

      e.input.addEventListener("keydown", function (ev) {
        if ((ev.ctrlKey || ev.metaKey) && ev.key === "Enter") { ev.preventDefault(); self.enhance(); }
      });

      this.shadowRoot.addEventListener("keydown", function (ev) {
        if (ev.key === "Escape") { self.close(); }
      });

      this._els.input.addEventListener("input", function () {
        clearTimeout(self._draftTimer);
        self._draftTimer = setTimeout(function () { self._persistDraft(); }, 400);
      });

      document.addEventListener("keydown", this._docKey = function (ev) {
        if (ev.key === "Escape" && self.hasAttribute("open")) self.close();
      });
    }

    /* -------------------------------------------------- 公开 API */
    open() {
      if (this.getAttribute("layout") === "inline") return;
      this.setAttribute("open", "");
      this._els.panel.setAttribute("aria-hidden", "false");
      this._pullFromTarget();
      this._checkHealth();
      this._emit("pe:open", {});
      var self = this;
      requestAnimationFrame(function () { self._els.input.focus(); });
    }

    close() {
      this.removeAttribute("open");
      this._els.panel.setAttribute("aria-hidden", "true");
      this._emit("pe:close", {});
    }

    toggle() { this.hasAttribute("open") ? this.close() : this.open(); }

    get value() { return this._els ? this._els.input.value : ""; }

    set value(v) { if (this._els) this._els.input.value = v; }

    /* -------------------------------------------------- 采集 */
    _targetEl() {
      var sel = this.getAttribute("target");
      if (!sel) return null;
      try { return document.querySelector(sel); } catch (err) { return null; }
    }

    _pullFromTarget() {
      var t = this._targetEl();
      if (t && typeof t.value === "string" && t.value.trim() && !this._els.input.value.trim()) {
        this._els.input.value = t.value;
      }
    }

    _persistDraft() {
      try { localStorage.setItem("pg:draft", this._els.input.value); } catch (e) { /* noop */ }
    }

    _restoreDraft() {
      try {
        var d = localStorage.getItem("pg:draft");
        if (d && !this._els.input.value) this._els.input.value = d;
      } catch (e) { /* noop */ }
    }

    /* -------------------------------------------------- 健康检查 */
    _checkHealth() {
      var self = this;
      var headers = {};
      var token = this.getAttribute("token");
      if (token) headers["X-PE-Token"] = token;
      fetch(this.endpoint + "/v1/health", { headers: headers })
        .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status)); })
        .then(function (data) {
          self._health = data;
          self._setDot("ok");
          self._els.health.classList.remove("show", "err");
        })
        .catch(function () {
          self._health = null;
          self._setDot("bad");
          self._els.health.classList.add("show", "err");
          self._els.health.innerHTML =
            "未连接到本地服务 <code>" + esc(self.endpoint) + "</code>。<br>请先启动：<code>python server/app.py --port 7317</code>";
        });
    }

    _setDot(kind) {
      this._els.dot.className = "pg-dot" + (kind ? " " + kind : "");
    }

    /* -------------------------------------------------- 核心流程 */
    async _requestJSON(payload, headers) {
      var res = await fetch(this.endpoint + "/v1/enhance", {
        method: "POST",
        headers: headers,
        body: JSON.stringify(payload),
        signal: this._abort.signal
      });
      return readJSONResponse(res);
    }

    async enhance() {
      var self = this;
      var text = this._els.input.value.trim() || (this._targetEl() || {}).value || "";
      text = (text || "").trim();

      if (!text) { this._toast("请先输入需求"); this._els.input.focus(); return; }
      var truncated = text.length > 8000;
      if (truncated) { text = text.slice(0, 8000); }

      this._state.status = "loading";
      this._setDot("busy");
      this._els.run.disabled = true;
      this._els.run.querySelector("span").textContent = "增强中…";
      this._els.chips.innerHTML = "";
      this._renderNav(null);
      this._els.result.classList.add("show");
      this._els.score.classList.remove("show");
      this._els.resultTitle.textContent = "增强中";
      this._els.len.textContent = "";
      this._els.md.innerHTML = '<div class="pg-loading"><i></i><span>解析意图与约束…</span></div>';
      this._els.copy.disabled = true;
      this._els.replace.disabled = true;

      var payload = {
        text: text,
        mode: this._els.mode.value,
        intensity: this._els.intensity.value,
        lang: this.getAttribute("lang") || "auto",
        format: "markdown"
      };

      var headers = { "Content-Type": "application/json" };
      var token = this.getAttribute("token");
      if (token) headers["X-PE-Token"] = token;

      var started = performance.now();
      var acc = "";
      if (truncated) this._toast("输入超过 8000 字，已截断");

      if (this._abort) this._abort.abort();
      this._abort = new AbortController();

      try {
        var res = await fetch(this.endpoint + "/v1/enhance/stream", {
          method: "POST",
          headers: headers,
          body: JSON.stringify(payload),
          signal: this._abort.signal
        });
        if (!res.ok) {
          var detail = "";
          try { var err = await res.json(); detail = err.error ? err.error.message : ""; } catch (e2) { /* noop */ }
          throw new Error(detail || ("服务返回 " + res.status));
        }
        if (!supportsStream(res)) {
          // 不支持流式响应体的浏览器：回退到一次性 JSON 接口
          // （不能对 SSE 响应调用 res.json()，那会直接抛出解析错误）
          var full = await this._requestJSON(payload, headers);
          this._applyResult(full, performance.now() - started);
          return;
        }

        var reader = res.body.getReader();
        var decoder = new TextDecoder("utf-8");
        var buffer = "";
        this._paint = null;
        var flush = function () {
          if (self._paint) return;
          self._paint = requestAnimationFrame(function () {
            self._paint = null;
            if (self._state.status !== "loading") return;
            self._els.md.innerHTML = renderMd(acc) + '<span class="pg-caret"></span>';
            self._els.md.scrollTop = self._els.md.scrollHeight;
          });
        };

        while (true) {
          var step = await reader.read();
          if (step.done) break;
          var drained = drainFrames(buffer, decoder.decode(step.value, { stream: true }));
          buffer = drained.rest;
          for (var f = 0; f < drained.events.length; f++) {
            var ev = drained.events[f];
            if (ev.event === "chunk") {
              acc += ev.data.delta || "";
              flush();
            } else if (ev.event === "analysis") {
              this._renderChips(ev.data);
            } else if (ev.event === "plan") {
              this._els.resultTitle.textContent = "增强结果 · " + (ev.data.mode_label || "");
              this._renderNav(ev.data.sections);
            } else if (ev.event === "result") {
              this._applyResult({ ok: true, enhanced: ev.data.enhanced, score: ev.data.score,
                analysis: ev.data.analysis }, performance.now() - started);
            } else if (ev.event === "error") {
              throw new Error(ev.data.message || ev.data.code || "增强失败");
            }
          }
        }
      } catch (err) {
        if (err && err.name === "AbortError") return;
        this._setDot("bad");
        this._els.result.classList.remove("show");
        this._els.health.classList.add("show", "err");
        this._els.health.innerHTML = "调用失败：" + esc(err.message || String(err)) +
          "<br>请确认本地服务已启动 <code>" + esc(this.endpoint) + "</code>";
        this._emit("pe:error", { message: err.message });
      } finally {
        this._state.status = "idle";
        this._els.run.disabled = false;
        this._els.run.querySelector("span").textContent = "增强 (Ctrl+Enter)";
      }
    }

    _applyResult(payload, elapsed) {
      var enhanced = payload.enhanced || "";
      if (this._paint) {               // 取消尚未执行的增量绘制，避免覆盖最终结果
        cancelAnimationFrame(this._paint);
        this._paint = null;
      }
      this._state.result = enhanced;
      if (payload.blocks) this._renderNav(payload.blocks);   // JSON 回退路径没有 plan 事件
      this._els.md.innerHTML = renderMd(enhanced);
      this._els.md.scrollTop = 0;
      this._els.resultTitle.textContent = "增强结果";
      this._els.len.textContent = enhanced.length + " 字";
      this._els.copy.disabled = false;
      this._els.replace.disabled = !this._targetEl();
      this._setDot("ok");

      if (payload.analysis) this._renderChips(payload.analysis);
      if (payload.score) this._renderScore(payload.score);
      if (this._health) {
        this._els.health.classList.remove("show", "err");
      }

      this._emit("pe:result", {
        original: this._els.input.value,
        enhanced: enhanced,
        analysis: payload.analysis || null,
        score: payload.score || null,
        sections: this._sections || [],
        elapsed_ms: elapsed ? Math.round(elapsed) : null
      });
    }

    /* -------------------------------------------------- 章节导航 */
    /* 章节顺序与正文标题顺序一致（正文只由 sections 拼成），故按下标定位 */
    _renderNav(src) {
      var list = sectionList(src);
      var nav = this._els.nav;
      var self = this;
      this._sections = list;
      nav.innerHTML = "";
      nav.hidden = !list.length;
      list.forEach(function (s, i) {
        var b = document.createElement("button");
        b.className = "pg-chip";
        b.textContent = s.title;
        b.onclick = function () {
          var h = self._els.md.querySelectorAll("h3,h4,h5")[i];
          if (h) self._els.md.scrollTop += h.getBoundingClientRect().top
            - self._els.md.getBoundingClientRect().top - 6;
        };
        nav.appendChild(b);
      });
    }

    _renderChips(a) {
      if (!a) return;
      var chips = [];
      var chip = '<span class="pg-chip">';
      if (a.intent_label) chips.push(chip + "意图 <b>" + esc(a.intent_label) + "</b></span>");
      if (a.domain_label) chips.push(chip + "领域 <b>" + esc(a.domain_label) + "</b></span>");
      (a.constraints || []).forEach(function (c) {
        chips.push(chip + esc(c.label) + " <b>" + esc(c.value) + "</b></span>");
      });
      var riskCount = (a.risks || []).length;
      if (riskCount) chips.push('<span class="pg-chip warn">风险 ' + riskCount + "</span>");
      var missCount = (a.missing || []).length;
      if (missCount) chips.push('<span class="pg-chip warn">待确认 ' + missCount + "</span>");
      this._els.chips.innerHTML = chips.join("");
    }

    _renderScore(score) {
      var dims = score.dims || [];
      var clamp = function (v) {
        var n = Math.round(Number(v));
        return isNaN(n) ? 0 : Math.max(0, Math.min(100, n));
      };
      var after = clamp(score.after);
      var before = clamp(score.before);
      var delta = Math.max(0, after - before);

      var rows = dims.map(function (d) {
        var val = clamp(d.after);
        return '<div class="pg-dim"><span>' + esc(d.label) + "</span>" +
          '<span class="pg-bar"><span data-w="' + val + '"></span></span>' +
          "<em>" + val + "</em></div>";
      }).join("");

      var grade = score.grade_after
        ? '<div class="pg-grade">评估：' + esc(score.grade_after) + "</div>" : "";

      this._els.score.innerHTML =
        '<div class="pg-score-top"><span class="pg-score-num">' + after +
        ' <small>/100</small></span><span class="pg-delta">+' + delta +
        '</span><span class="pg-spacer"></span>' +
        (score.skeleton ? '<span class="pg-chip">含骨架</span>' : "") +
        '<span class="pg-chip">原 ' + before + "</span></div>" + rows + grade;

      // 通过 CSSOM 设置宽度，避免行内 style 属性（严格 CSP 下会被拦截）
      this._els.score.querySelectorAll(".pg-bar > span").forEach(function (bar) {
        bar.style.width = (bar.getAttribute("data-w") || 0) + "%";
      });
      this._els.score.classList.add("show");
    }

    /* -------------------------------------------------- 复制 / 回填 */
    async _copy() {
      var text = this._state.result || "";
      if (!text) return;
      var ok = false;
      try {
        await navigator.clipboard.writeText(text);
        ok = true;
      } catch (e) {
        // 回退方案必须挂在 document.body：Shadow DOM 内的选区在部分浏览器
        // 无法被 execCommand("copy") 读取
        var ta = document.createElement("textarea");
        ta.value = text;
        ta.setAttribute("readonly", "");
        ta.style.cssText = "position:fixed;top:0;left:0;width:1px;height:1px;opacity:0;font-size:12px";
        document.body.appendChild(ta);
        ta.select();
        ta.setSelectionRange(0, text.length);
        try { ok = document.execCommand("copy"); } catch (e2) { ok = false; }
        ta.remove();
      }
      this._toast(ok ? "已复制到剪贴板" : "复制失败，请手动选择");
      this._emit("pe:copy", { text: text });
    }

    _replace() {
      var target = this._targetEl();
      if (!target) { this._toast("未绑定目标输入框"); return; }
      var text = this._state.result || "";
      if (!text) return;
      writeTarget(target, text);
      this._toast("已替换原文");
    }

    /* -------------------------------------------------- 辅助 */
    _reset() {
      this._els.input.value = "";
      this._els.chips.innerHTML = "";
      this._renderNav(null);
      this._els.result.classList.remove("show");
      this._els.score.classList.remove("show");
      this._els.copy.disabled = true;
      this._els.replace.disabled = true;
      this._state.result = null;
      this._persistDraft();
      this._els.input.focus();
    }

    _toast(msg) {
      var el = this._els.toast;
      el.textContent = msg;
      el.classList.add("show");
      clearTimeout(this._toastTimer);
      this._toastTimer = setTimeout(function () { el.classList.remove("show"); }, 1600);
    }

    _emit(name, detail) {
      this.dispatchEvent(new CustomEvent(name, { detail: detail, bubbles: true, composed: true }));
    }
  }

  /* ------------------------------------------------------ 程序化 API */
  function programmaticEnhance(text, options) {
    var opts = options || {};
    var endpoint = (opts.endpoint || "http://127.0.0.1:" + DEFAULT_PORT).replace(/\/$/, "");
    var headers = { "Content-Type": "application/json" };
    if (opts.token) headers["X-PE-Token"] = opts.token;
    return fetch(endpoint + "/v1/enhance", {
      method: "POST",
      headers: headers,
      body: JSON.stringify({
        text: text, mode: opts.mode || "struct", lang: opts.lang || "auto",
        intensity: opts.intensity || "standard", format: opts.format || "markdown"
      })
    }).then(function (r) {
      if (!r.ok) return r.json().then(function (e) { throw new Error((e.error || {}).message || "请求失败"); });
      return r.json();
    });
  }

  customElements.define("prompt-enhancer", PromptEnhancer);

  window.PromptEnhancer = {
    version: VERSION,
    enhance: programmaticEnhance,
    create: function (attrs) {
      var el = document.createElement("prompt-enhancer");
      Object.keys(attrs || {}).forEach(function (k) { el.setAttribute(k, attrs[k]); });
      document.body.appendChild(el);
      return el;
    },
    render: renderMd,
    // 纯函数出口：供 tests/frontend/smoke.mjs 在无浏览器环境下冒烟
    _internals: {
      parseFrame: parseFrame,
      drainFrames: drainFrames,
      writeTarget: writeTarget,
      supportsStream: supportsStream,
      readJSONResponse: readJSONResponse,
      sectionList: sectionList
    }
  };
})();
