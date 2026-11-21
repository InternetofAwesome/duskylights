// Dusky Lights panel: curve graph, settings, lights and demo controls.
// Plain web component, no build step. It reads and writes the integration's own
// entities through Home Assistant's `hass` object; it keeps no state of its own.

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

// ---- curve maths (kept in step with curve.py; tests compare the two) --------
export function shape(x, a = 0, b = 0) {
  a = clamp(a, 0, 3);
  b = clamp(b, 0, 3);
  x = clamp(x, 0, 1);
  const h00 = 2 * x ** 3 - 3 * x ** 2 + 1;
  const h10 = x ** 3 - 2 * x ** 2 + x;
  const h11 = x ** 3 - x ** 2;
  return clamp(h00 - a * h10 - b * h11, 0, 1);
}

export function progress(elevation, start, end) {
  if (start <= end) return 0;
  return clamp((start - elevation) / (start - end), 0, 1);
}

export function targetPct(elevation, p) {
  const low = Math.min(p.low, p.high);
  return low + (p.high - low) * shape(progress(elevation, p.start, p.end), p.sharpStart, p.sharpEnd);
}

// ---- helpers -----------------------------------------------------------------
const esc = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const fmt = (v, d = 1) => (Number.isFinite(v) ? (Math.round(v * 10 ** d) / 10 ** d).toString() : "-");
const SERIES = ["#2f80ed", "#27ae60", "#9b51e0", "#e0568a", "#16a2a2", "#c8791c"];
const AMBER = "#f2a33a";

const SETTINGS = [
  ["start_elevation", "Start elevation", "Sun elevation where dimming begins"],
  ["end_elevation", "End elevation", "Sun elevation where the low level is reached"],
  ["normal_pct", "High", "Brightness during the day"],
  ["floor_pct", "Low", "Brightness at night"],
  ["sharp_start", "Start sharpness", "0 = soft, 1 = straight, 3 = abrupt at the start"],
  ["sharp_end", "End sharpness", "0 = soft, 1 = straight, 3 = abrupt at the end"],
];

const STYLE = `
:host { display:block; background:var(--primary-background-color,#fafafa); color:var(--primary-text-color,#212121);
  min-height:100%; font-family:var(--paper-font-body1_-_font-family, Roboto, sans-serif); }
* { box-sizing:border-box; }
header { display:flex; align-items:center; gap:12px; height:56px; padding:0 16px;
  background:var(--app-header-background-color,var(--primary-color,#03a9f4)); color:var(--app-header-text-color,#fff); }
header h1 { font-size:20px; font-weight:400; margin:0; flex:1; }
main { max-width:1100px; margin:0 auto; padding:16px; display:grid; gap:16px; }
.card { background:var(--ha-card-background,var(--card-background-color,#fff)); border-radius:var(--ha-card-border-radius,12px);
  box-shadow:var(--ha-card-box-shadow,0 1px 3px rgba(0,0,0,.2)); padding:16px; min-width:0; }
.card h2 { font-size:16px; font-weight:500; margin:0 0 12px; }
.sub { color:var(--secondary-text-color,#727272); font-size:13px; }
.two { display:grid; grid-template-columns:minmax(0,3fr) minmax(0,2fr); gap:16px; }
@media (max-width: 860px) { .two { grid-template-columns:minmax(0,1fr); } }
svg { width:100%; height:auto; display:block; }
.axis { fill:var(--secondary-text-color,#727272); font-size:12px; }
.grid { stroke:var(--divider-color,#e0e0e0); stroke-width:1; }
.row { display:grid; grid-template-columns:minmax(90px,1fr) minmax(0,2fr) 76px; gap:10px; align-items:center; padding:6px 0; }
.row label { font-size:14px; }
.row .sub { grid-column:1 / -1; margin-top:-4px; }
input[type=range] { width:100%; accent-color:var(--primary-color,#03a9f4); }
input[type=number], select { width:100%; padding:6px 8px; font:inherit; color:inherit; background:transparent;
  border:1px solid var(--divider-color,#ccc); border-radius:6px; }
button { font:inherit; cursor:pointer; padding:7px 14px; border-radius:8px; border:1px solid var(--primary-color,#03a9f4);
  background:transparent; color:var(--primary-color,#03a9f4); }
button.fill { background:var(--primary-color,#03a9f4); color:var(--text-primary-color,#fff); }
button:disabled { opacity:.5; cursor:default; }
table { width:100%; border-collapse:collapse; }
th, td { text-align:left; padding:8px 6px; border-bottom:1px solid var(--divider-color,#e0e0e0); font-size:14px; vertical-align:middle; }
th { font-weight:500; color:var(--secondary-text-color,#727272); font-size:12px; }
td input[type=number] { width:104px; }
.dot { display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:6px; }
.badge { font-size:12px; padding:2px 8px; border-radius:10px; background:var(--divider-color,#e0e0e0); }
.badge.hold { background:var(--warning-color,#ffa600); color:#000; }
.badge.demo { background:var(--primary-color,#03a9f4); color:var(--text-primary-color,#fff); }
.demo-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; align-items:end; }
.demo-grid label { display:block; font-size:12px; color:var(--secondary-text-color,#727272); margin-bottom:4px; }
.legend { display:flex; flex-wrap:wrap; gap:14px; margin-top:8px; font-size:13px; }
.err { color:var(--error-color,#db4437); padding:16px; }
@media (max-width: 640px) {
  table, tbody, tr, td { display:block; }
  thead { display:none; }
  tr { padding:8px 0; border-bottom:1px solid var(--divider-color,#e0e0e0); display:grid; grid-template-columns:1fr 1fr; gap:6px 12px; }
  td { border:none; padding:2px 0; display:flex; justify-content:space-between; align-items:center; gap:8px; }
  td:first-child { grid-column:1 / -1; font-weight:500; }
  td[data-l]::before { content:attr(data-l); color:var(--secondary-text-color,#727272); font-size:12px; }
  td input[type=number] { width:100px; }
}
`;

class DuskyPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._info = null;
    this._loading = false;
    this._error = null;
    this._draft = {}; // entity_id -> value being dragged
    this._narrow = false;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._info && !this._loading) this._load();
    if (this._info) this._update();
  }
  set narrow(v) {
    this._narrow = v;
    if (this._menu) this._menu.narrow = v;
  }
  set panel(_p) {}
  set route(_r) {}

  async _load() {
    this._loading = true;
    try {
      this._info = await this._hass.callWS({ type: "duskylights/info" });
      this._error = null;
      this._build();
      this._update();
    } catch (e) {
      this._error = e && e.message ? e.message : String(e);
      this.shadowRoot.innerHTML = `<style>${STYLE}</style><div class="err">Could not load Dusky Lights: ${esc(this._error)}</div>`;
    } finally {
      this._loading = false;
    }
  }

  // ---- state access ---------------------------------------------------------
  _state(id) {
    return id && this._hass ? this._hass.states[id] : undefined;
  }
  _num(id, fallback = NaN) {
    if (id in this._draft) return this._draft[id];
    const s = this._state(id);
    const v = s ? parseFloat(s.state) : NaN;
    return Number.isFinite(v) ? v : fallback;
  }
  _params() {
    const s = this._info.settings;
    return {
      start: this._num(s.start_elevation, 10),
      end: this._num(s.end_elevation, -6),
      high: this._num(s.normal_pct, 50),
      low: this._num(s.floor_pct, 10),
      sharpStart: this._num(s.sharp_start, 0),
      sharpEnd: this._num(s.sharp_end, 0),
    };
  }
  _lightParams(light, g) {
    const hi = this._num(light.high, 0);
    const lo = this._num(light.low, 0);
    return { ...g, high: hi || g.high, low: lo || g.low };
  }
  _call(domain, service, data) {
    return this._hass.callService(domain, service, data);
  }
  _setNumber(id, value) {
    this._draft[id] = value;
    const done = () => setTimeout(() => delete this._draft[id], 1500);
    this._call("number", "set_value", { entity_id: id, value }).then(done, done);
  }

  // ---- build (once) -----------------------------------------------------------
  _build() {
    const info = this._info;
    const root = this.shadowRoot;
    root.innerHTML = `<style>${STYLE}</style>
      <header><span id="menu"></span><h1>Dusky Lights</h1></header>
      <main>
        <div class="two">
          <section class="card"><h2>Brightness follows the sun</h2><div id="graph"></div><div class="legend" id="legend"></div></section>
          <section class="card"><h2>Settings</h2><div id="settings"></div></section>
        </div>
        <section class="card"><h2>Lights</h2><div style="overflow-x:auto"><table id="lights"></table></div>
          <p style="margin:12px 0 0"><button id="releaseAll">Release all to the curve</button></p></section>
        <section class="card"><h2>Demo</h2><div class="demo-grid" id="demo"></div><p class="sub" id="demoNote"></p></section>
      </main>`;

    // sidebar menu button on narrow screens (element is provided by Home Assistant)
    if (customElements.get("ha-menu-button")) {
      const m = document.createElement("ha-menu-button");
      m.hass = this._hass;
      m.narrow = this._narrow;
      root.getElementById("menu").appendChild(m);
      this._menu = m;
    }

    // settings rows
    this._rows = {};
    const box = root.getElementById("settings");
    for (const [key, label, hint] of SETTINGS) {
      const id = info.settings[key];
      const st = this._state(id);
      const a = (st && st.attributes) || {};
      const row = document.createElement("div");
      row.className = "row";
      row.innerHTML = `<label>${esc(label)}</label>
        <input type="range" min="${a.min ?? 0}" max="${a.max ?? 100}" step="${a.step ?? 1}">
        <input type="number" min="${a.min ?? 0}" max="${a.max ?? 100}" step="${a.step ?? 1}">
        <span class="sub">${esc(hint)}${a.unit_of_measurement ? " (" + esc(a.unit_of_measurement) + ")" : ""}</span>`;
      const [range, num] = row.querySelectorAll("input");
      range.addEventListener("input", () => {
        this._draft[id] = parseFloat(range.value);
        num.value = range.value;
        this._drawGraph();
      });
      range.addEventListener("change", () => this._setNumber(id, parseFloat(range.value)));
      num.addEventListener("change", () => {
        const v = clamp(parseFloat(num.value), parseFloat(num.min), parseFloat(num.max));
        if (Number.isFinite(v)) this._setNumber(id, v);
      });
      box.appendChild(row);
      this._rows[key] = { id, range, num };
    }

    // lights table
    const table = root.getElementById("lights");
    table.innerHTML = `<thead><tr><th>Light</th><th>Now</th><th>Target</th>
      <th>High</th><th>Low</th><th>State</th><th></th></tr></thead><tbody></tbody>`;
    this._lightRows = info.lights.map((l, i) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td><span class="dot" style="background:${SERIES[i % SERIES.length]}"></span><span class="name"></span></td>
        <td data-l="Now" class="now"></td><td data-l="Target" class="target"></td>
        <td data-l="High"><input type="number" class="hi" min="0" max="100" step="1"></td>
        <td data-l="Low"><input type="number" class="lo" min="0" max="100" step="1"></td>
        <td data-l="State" class="state"></td><td><button class="rel">Release</button></td>`;
      tr.querySelector(".name").textContent = l.name;
      const wire = (cls, id) => {
        const inp = tr.querySelector(cls);
        inp.addEventListener("change", () => {
          const v = inp.value === "" ? 0 : clamp(parseFloat(inp.value), 0, 100);
          this._setNumber(id, Number.isFinite(v) ? v : 0);
        });
        return inp;
      };
      const hi = wire(".hi", l.high);
      const lo = wire(".lo", l.low);
      tr.querySelector(".rel").addEventListener("click", () => this._call("button", "press", { entity_id: l.release }));
      table.querySelector("tbody").appendChild(tr);
      return { l, tr, hi, lo };
    });
    this._lastW = 0;
    new ResizeObserver(() => {
      const w = root.getElementById("graph").clientWidth;
      if (w && w !== this._lastW) {
        this._lastW = w;
        this._drawGraph();
      }
    }).observe(root.getElementById("graph"));
    root.getElementById("releaseAll").addEventListener("click", () => this._call("button", "press", { entity_id: info.release_all }));

    // demo controls
    const d = info.demo;
    const demo = root.getElementById("demo");
    demo.innerHTML = `<div><label>Light</label><select id="dLight"></select></div>
      <div><label>Repeat</label><select id="dRepeat"></select></div>
      <div><label>Length (s, 0 = automatic)</label><input id="dLen" type="number" min="0" max="600" step="1"></div>
      <div><button id="dGo" class="fill"></button></div>`;
    this._demo = {
      light: demo.querySelector("#dLight"),
      repeat: demo.querySelector("#dRepeat"),
      len: demo.querySelector("#dLen"),
      go: demo.querySelector("#dGo"),
    };
    this._demo.light.addEventListener("change", () => this._call("select", "select_option", { entity_id: d.light, option: this._demo.light.value }));
    this._demo.repeat.addEventListener("change", () => this._call("select", "select_option", { entity_id: d.repeat, option: this._demo.repeat.value }));
    this._demo.len.addEventListener("change", () => this._setNumber(d.length, clamp(parseFloat(this._demo.len.value) || 0, 0, 600)));
    this._demo.go.addEventListener("click", () => {
      const on = (this._state(d.switch) || {}).state === "on";
      this._call("switch", on ? "turn_off" : "turn_on", { entity_id: d.switch });
    });
  }

  // ---- update (every hass change) ---------------------------------------------
  _update() {
    if (!this._info || !this._rows) return;
    if (this._menu) this._menu.hass = this._hass;
    const active = this.shadowRoot.activeElement;

    for (const key in this._rows) {
      const { id, range, num } = this._rows[key];
      const v = this._num(id);
      if (!Number.isFinite(v)) continue;
      if (active !== range) range.value = v;
      if (active !== num) num.value = v;
    }

    const g = this._params();
    for (const r of this._lightRows) {
      const { l, hi, lo } = r;
      const t = this._state(l.target);
      const ls = this._state(l.light);
      const bri = ls && ls.attributes ? ls.attributes.brightness : null;
      r.tr.querySelector(".now").textContent = ls && ls.state === "on" && bri != null ? fmt((bri * 100) / 255, 0) + "%" : ls ? ls.state : "-";
      r.tr.querySelector(".target").textContent = t ? fmt(parseFloat(t.state), 0) + "%" : "-";
      const holding = t && t.attributes && t.attributes.holding;
      const demo = t && t.attributes && t.attributes.demo;
      r.tr.querySelector(".state").innerHTML = demo
        ? '<span class="badge demo">demo</span>'
        : holding
          ? `<span class="badge hold">holding ${fmt(((t.attributes.hold_brightness || 0) * 100) / 255, 0)}%</span>`
          : '<span class="badge">on curve</span>';
      const set = (inp, id, glob) => {
        if (this.shadowRoot.activeElement === inp) return;
        const v = this._num(id, 0);
        inp.value = v ? v : "";
        inp.placeholder = "global " + fmt(glob, 0);
      };
      set(hi, l.high, g.high);
      set(lo, l.low, g.low);
      r.tr.querySelector(".rel").disabled = !holding;
    }

    // demo controls
    const d = this._info.demo;
    const sw = this._state(d.switch);
    const running = sw && sw.state === "on";
    const fill = (sel, st, fallback) => {
      const opts = (st && st.attributes && st.attributes.options) || [];
      if (sel.dataset.opts !== opts.join("|")) {
        sel.innerHTML = opts.map((o) => `<option>${esc(o)}</option>`).join("");
        sel.dataset.opts = opts.join("|");
      }
      if (this.shadowRoot.activeElement !== sel && st) sel.value = st.state;
    };
    fill(this._demo.light, this._state(d.light));
    fill(this._demo.repeat, this._state(d.repeat));
    if (this.shadowRoot.activeElement !== this._demo.len) this._demo.len.value = this._num(d.length, 0);
    this._demo.go.textContent = running ? "Stop demo" : "Start demo";
    this._demo.go.disabled = !sw || sw.state === "unavailable";
    this.shadowRoot.getElementById("demoNote").textContent =
      "Plays a compressed dusk and dawn on one light, starting from where it is now, then puts it back as it was.";

    this._drawGraph();
  }

  // ---- graph -----------------------------------------------------------------
  _drawGraph() {
    const info = this._info;
    const g = this._params();
    const box = this.shadowRoot.getElementById("graph");
    const W = clamp(Math.round(box.clientWidth || 720), 300, 900);
    const H = Math.round(clamp(W * 0.58, 250, 460));
    const L = 44, R = 14, T = 18, B = 42;
    const xMax = Math.max(g.start + 14, 25);
    const xMin = Math.min(g.end - 8, -14);
    let yMax = Math.max(g.high, ...info.lights.map((l) => this._lightParams(l, g).high), 20);
    yMax = Math.min(100, Math.ceil((yMax + 8) / 10) * 10);
    const X = (e) => L + ((xMax - e) / (xMax - xMin)) * (W - L - R);
    const Y = (p) => T + (1 - p / yMax) * (H - T - B);
    const path = (params) => {
      const pts = [];
      for (let i = 0; i <= 160; i++) {
        const e = xMax - ((xMax - xMin) * i) / 160;
        pts.push(`${i ? "L" : "M"}${X(e).toFixed(1)},${Y(targetPct(e, params)).toFixed(1)}`);
      }
      return pts.join("");
    };

    const o = [];
    // ramp window shading
    o.push(`<rect x="${X(g.start).toFixed(1)}" y="${T}" width="${Math.max(0, X(g.end) - X(g.start)).toFixed(1)}" height="${H - T - B}" fill="${AMBER}" opacity=".12"/>`);
    for (let p = 0; p <= yMax; p += yMax > 60 ? 20 : 10) {
      o.push(`<line class="grid" x1="${L}" x2="${W - R}" y1="${Y(p)}" y2="${Y(p)}"/><text class="axis" x="${L - 8}" y="${Y(p) + 4}" text-anchor="end">${p}%</text>`);
    }
    const ticks = new Set([Math.round(xMax / 10) * 10, 10, 0, -6, -12, Math.round(g.start), Math.round(g.end)].filter((e) => e <= xMax && e >= xMin));
    for (const e of ticks) {
      o.push(`<line class="grid" x1="${X(e)}" x2="${X(e)}" y1="${T}" y2="${H - B}" stroke-dasharray="2 4"/><text class="axis" x="${X(e)}" y="${H - B + 20}" text-anchor="middle">${e}°</text>`);
    }
    o.push(`<text class="axis" x="${(L + W - R) / 2}" y="${H - 8}" text-anchor="middle">sun elevation (sinking toward dusk)</text>`);

    // per-light curves where they differ from the global one
    info.lights.forEach((l, i) => {
      const lp = this._lightParams(l, g);
      if (lp.high !== g.high || lp.low !== g.low) {
        o.push(`<path d="${path(lp)}" fill="none" stroke="${SERIES[i % SERIES.length]}" stroke-width="2" stroke-dasharray="6 4" opacity=".9"/>`);
      }
    });
    o.push(`<path d="${path(g)}" fill="none" stroke="${AMBER}" stroke-width="4" stroke-linecap="round"/>`);
    o.push(`<circle cx="${X(g.start)}" cy="${Y(g.high)}" r="5" fill="${AMBER}"/><circle cx="${X(g.end)}" cy="${Y(Math.min(g.low, g.high))}" r="5" fill="#d9567a"/>`);

    // live sun and each light's target
    const elev = this._num(info.elevation);
    if (Number.isFinite(elev)) {
      const ex = X(clamp(elev, xMin, xMax));
      o.push(`<line x1="${ex}" x2="${ex}" y1="${T}" y2="${H - B}" stroke="var(--primary-text-color,#333)" stroke-width="1" stroke-dasharray="4 3" opacity=".7"/>`);
      o.push(`<text class="axis" x="${ex}" y="${T + 12}" text-anchor="${ex > W - 90 ? "end" : "start"}" dx="${ex > W - 90 ? -4 : 4}">sun ${fmt(elev, 1)}°</text>`);
      info.lights.forEach((l, i) => {
        const t = this._state(l.target);
        const v = t ? parseFloat(t.state) : NaN;
        if (Number.isFinite(v)) {
          o.push(`<circle cx="${ex}" cy="${Y(v)}" r="6" fill="${SERIES[i % SERIES.length]}" stroke="var(--card-background-color,#fff)" stroke-width="2"><title>${esc(l.name)}: target ${fmt(v, 0)}%</title></circle>`);
        }
      });
    }
    box.innerHTML =
      `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Brightness against sun elevation">${o.join("")}</svg>`;

    this.shadowRoot.getElementById("legend").innerHTML =
      `<span><span class="dot" style="background:${AMBER}"></span>global curve</span>` +
      info.lights
        .map((l, i) => `<span><span class="dot" style="background:${SERIES[i % SERIES.length]}"></span>${esc(l.name)}</span>`)
        .join("");
  }
}

if (!customElements.get("dusky-panel")) customElements.define("dusky-panel", DuskyPanel);
