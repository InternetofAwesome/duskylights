// Dusky Lights panel: curve graph, settings, lights and demo controls.
// Plain web component, no build step. It reads and writes the integration's own
// entities through Home Assistant's `hass` object. Edits stay a local draft until
// Save is pressed; Discard drops them; the demo can run on the draft.

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

// ---- curve maths (kept in step with curve.py; tests compare the two) --------
// A jerk-limited S-curve: constant-jerk (cubic) entries into both plateaus, so the
// ramp meets each plateau with zero slope and zero acceleration. Sharpness 0 is
// the longest entry (a quarter of the ramp), 1 is no entry (a straight line).
const MAX_ENTRY = 0.25;
const entry = (sharpness) => MAX_ENTRY * (1 - clamp(sharpness, 0, 1));

export function shape(x, a = 0, b = 0) {
  if (x <= 0) return 1;
  if (x >= 1) return 0;
  const s = entry(a);
  const e = entry(b);
  const v = 1 / (1 - s - e); // slope of the middle section
  const j1 = s > 1e-12 ? v / s ** 2 : 0;
  const j2 = e > 1e-12 ? v / e ** 2 : 0;
  const xc0 = 2 * s;
  const xc1 = 1 - 2 * e;
  const base = s > 1e-12 ? j1 * s ** 3 : 0;
  let p;
  if (s > 1e-12 && x < xc0) {
    if (x <= s) {
      p = (j1 * x ** 3) / 6;
    } else {
      const t = x - s;
      p = (j1 * s ** 3) / 6 + ((j1 * s ** 2) / 2) * t + (j1 * s * t ** 2) / 2 - (j1 * t ** 3) / 6;
    }
  } else if (e > 1e-12 && x > xc1) {
    const t = x - xc1;
    const pc = v * (xc1 - 2 * s) + base;
    if (t <= e) {
      p = pc + v * t - (j2 * t ** 3) / 6;
    } else {
      const u = t - e;
      const pce = pc + v * e - (j2 * e ** 3) / 6;
      p = pce + (v / 2) * u - (j2 * e * u ** 2) / 2 + (j2 * u ** 3) / 6;
    }
  } else {
    p = base + v * (x - 2 * s);
  }
  return clamp(1 - p, 0, 1);
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
  ["start_elevation", "Dim starts at", "Sun height when dimming begins",
    "How high the sun is, in degrees above the horizon. 0\u00b0 is sunset; higher numbers start dimming earlier in the afternoon."],
  ["end_elevation", "Dimmest at", "Sun height when night level is reached",
    "Negative means the sun is below the horizon. -6\u00b0 is about when civil twilight ends."],
  ["normal_pct", "Day brightness", "How bright lights are in daytime",
    "Lights ease down from this level at dusk, and back up to it at dawn."],
  ["floor_pct", "Night brightness", "How dim lights get at night",
    "The lowest level the schedule will set. You can still dim further by hand."],
  ["sharp_start", "Start sharpness", "0 = very gentle, 1 = no easing",
    "How abruptly dimming begins. 0 eases in as slowly as possible; 1 starts at full speed."],
  ["sharp_end", "End sharpness", "0 = very gentle, 1 = no easing",
    "How abruptly dimming stops at the night level. 0 eases to a stop; 1 stops at full speed."],
];

const STYLE = `
:host { display:block; background:var(--primary-background-color,#fafafa); color:var(--primary-text-color,#212121);
  min-height:100%; font-family:var(--paper-font-body1_-_font-family, Roboto, sans-serif); }
* { box-sizing:border-box; }
header { display:flex; align-items:center; gap:12px; height:56px; padding:0 16px;
  background:var(--app-header-background-color,var(--primary-color,#03a9f4)); color:var(--app-header-text-color,#fff); }
header h1 { font-size:20px; font-weight:400; margin:0; flex:1; }
header .actions { display:flex; align-items:center; gap:8px; }
header .dirty { font-size:13px; opacity:.9; }
header button { color:inherit; border-color:currentColor; padding:5px 12px; }
header button.fill { background:#fff; color:var(--primary-color,#03a9f4); border-color:#fff; }
header button:disabled { opacity:.45; }
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
.row { display:grid; grid-template-columns:minmax(130px,1fr) minmax(0,2fr) 76px; gap:10px; align-items:center; padding:6px 0; }
.row label { font-size:14px; }
.row .sub { grid-column:1 / -1; margin-top:-4px; }
input[type=range] { width:100%; accent-color:var(--primary-color,#03a9f4); }
input[type=number], select { width:100%; padding:6px 8px; font:inherit; color:inherit; background:transparent;
  border:1px solid var(--divider-color,#ccc); border-radius:6px; }
tr.sel { background:color-mix(in srgb, var(--primary-color,#03a9f4) 12%, transparent); }
#tip { position:fixed; display:none; z-index:10; max-width:45ch; padding:8px 11px; border-radius:8px; font-size:13px; line-height:1.4; pointer-events:none;
  color:var(--primary-text-color,#333); border:1px solid var(--divider-color,#ddd);
  background:color-mix(in srgb, var(--primary-text-color,#333) 5%, var(--card-background-color,#fff)); box-shadow:0 2px 10px rgba(0,0,0,.15); }
.addrow { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-top:12px; }
.addrow select { max-width:100%; min-width:220px; flex:1 1 220px; }
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
    this._tipTimer = null;
    const hide = () => {
      clearTimeout(this._tipTimer);
      const tip = this.shadowRoot.getElementById("tip");
      if (tip) tip.style.display = "none";
    };
    const show = (el) => {
      const tip = this.shadowRoot.getElementById("tip");
      if (!tip || !el.isConnected) return;
      tip.textContent = el.getAttribute("data-tip");
      tip.style.display = "block";
      const r = el.getBoundingClientRect(), t = tip.getBoundingClientRect();
      tip.style.left = Math.max(8, Math.min(innerWidth - t.width - 8, r.left + r.width / 2 - t.width / 2)) + "px";
      tip.style.top = (r.bottom + t.height + 12 < innerHeight ? r.bottom + 8 : Math.max(8, r.top - t.height - 8)) + "px";
    };
    const find = (e) => (e.target.closest ? e.target.closest("[data-tip]") : null);
    this.shadowRoot.addEventListener("mouseover", (e) => {
      const el = find(e);
      hide();
      if (el) this._tipTimer = setTimeout(() => show(el), 600); // short delay so it never gets in the way
    });
    this.shadowRoot.addEventListener("mouseout", hide);
    this.shadowRoot.addEventListener("mousedown", hide);
    this.shadowRoot.addEventListener("focusin", (e) => { const el = find(e); if (el) show(el); });
    this.shadowRoot.addEventListener("focusout", hide);
    addEventListener("scroll", hide, true);
    this._hass = null;
    this._info = null;
    this._loading = false;
    this._error = null;
    this._draft = {}; // entity_id -> unsaved value (kept until saved or discarded)
    this._d = { light: null, repeat: "Once", len: 0 }; // demo choices (local)
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
      await this._loadSun();
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

  async _loadSun() {
    try {
      this._sun = await this._hass.callWS({ type: "duskylights/sun_path" });
    } catch (e) {
      this._sun = null; // the graph still works, just without clock times
    }
  }
  _sunEnd() {
    const s = this._sun;
    return s ? s.start + s.elevations.length * s.step_s * 1000 : Infinity;
  }
  // when today's sun crosses `elev` going down (evening) or up (morning); null if it never does
  _crossing(elev, evening) {
    const sun = this._sun;
    if (!sun || !sun.elevations.length || !Number.isFinite(elev)) return null;
    const e = sun.elevations;
    let noon = 0;
    for (let i = 1; i < e.length; i++) if (e[i] > e[noon]) noon = i;
    if (e[noon] < elev) return null; // the sun doesn't get that high today
    const at = (i, f) => sun.start + (i + f) * sun.step_s * 1000;
    if (evening) {
      for (let i = noon; i < e.length - 1; i++) if (e[i] >= elev && e[i + 1] < elev) return at(i, (e[i] - elev) / (e[i] - e[i + 1]));
    } else {
      for (let i = noon; i > 0; i--) if (e[i] >= elev && e[i - 1] < elev) return at(i - 1, (elev - e[i - 1]) / (e[i] - e[i - 1]));
    }
    return null; // the sun doesn't get that low today
  }
  _clock(ms) {
    const h = this._hass;
    const o = { hour: "numeric", minute: "2-digit" };
    if (h.config && h.config.time_zone) o.timeZone = h.config.time_zone;
    const tf = h.locale && h.locale.time_format;
    if (tf === "12") o.hour12 = true;
    else if (tf === "24") o.hour12 = false;
    try {
      return new Date(ms).toLocaleTimeString(h.locale && h.locale.language, o);
    } catch (e) {
      return new Date(ms).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
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
  _edit(id, value) {
    this._draft[id] = value;
    this._update();
  }
  _dirtyIds() {
    return Object.keys(this._draft);
  }
  async _save() {
    const ids = this._dirtyIds();
    this._saving = true;
    this._update();
    try {
      await Promise.all(ids.map((id) => this._call("number", "set_value", { entity_id: id, value: this._draft[id] })));
      this._saveError = null;
    } catch (e) {
      this._saveError = e && e.message ? e.message : String(e);
    }
    this._saving = false;
    this._update();
  }
  _discard() {
    this._draft = {};
    this._saveError = null;
    this._update();
  }

  async _setLights(lights) {
    this._draft = {};
    try {
      await this._hass.callWS({ type: "duskylights/set_lights", lights });
    } catch (e) {
      this._saveError = e && e.message ? e.message : String(e);
    }
    await this._load();
  }

  // ---- build (once) -----------------------------------------------------------
  _build() {
    const info = this._info;
    const root = this.shadowRoot;
    root.innerHTML = `<style>${STYLE}</style>
      <header><span id="menu"></span><h1>Dusky Lights</h1>
        <div class="actions"><span class="dirty" id="dirty"></span>
          <button id="discard" data-tip="Throw away unsaved changes">Discard</button><button id="save" class="fill" data-tip="Apply your changes to the lights">Save</button></div></header>
      <main>
        <div class="two">
          <section class="card"><h2>Brightness follows the sun</h2><div id="graph"></div><div class="legend" id="legend"></div><p class="sub" id="times"></p></section>
          <section class="card"><h2>Settings</h2><div id="settings"></div></section>
        </div>
        <section class="card"><h2>Lights</h2><div style="overflow-x:auto"><table id="lights"></table></div>
          <p style="margin:12px 0 0"><button id="releaseAll" data-tip="Cancel every manual dim so all lights follow the sun again">Resume all</button></p>
          <div class="addrow"><select id="addSel"></select><button id="addBtn" data-tip="Have Dusky manage the selected light">Add light</button>
            <span class="sub" id="addNote"></span></div></section>
        <section class="card"><h2>Demo</h2><div class="demo-grid" id="demo"></div><p class="sub" id="demoNote"></p></section>
      </main><div id="tip" role="tooltip"></div>`;

    root.getElementById("save").addEventListener("click", () => this._save());
    root.getElementById("discard").addEventListener("click", () => this._discard());

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
    for (const [key, label, hint, tip] of SETTINGS) {
      const id = info.settings[key];
      const st = this._state(id);
      const a = (st && st.attributes) || {};
      const row = document.createElement("div");
      row.className = "row";
      row.setAttribute("data-tip", `${tip} This is the default for every light; a light can set its own in the table below.`);
      row.innerHTML = `<label>${esc(label)}</label>
        <input type="range" min="${a.min ?? 0}" max="${a.max ?? 100}" step="${a.step ?? 1}">
        <input type="number" min="${a.min ?? 0}" max="${a.max ?? 100}" step="${a.step ?? 1}">
        <span class="sub">${esc(hint)}${a.unit_of_measurement ? " (" + esc(a.unit_of_measurement) + ")" : ""}</span>`;
      const [range, num] = row.querySelectorAll("input");
      range.addEventListener("input", () => {
        num.value = range.value;
        this._edit(id, parseFloat(range.value));
      });
      num.addEventListener("change", () => {
        const v = clamp(parseFloat(num.value), parseFloat(num.min), parseFloat(num.max));
        if (Number.isFinite(v)) this._edit(id, v);
        else num.value = this._num(id, "");
      });
      box.appendChild(row);
      this._rows[key] = { id, range, num };
    }

    // lights table
    const table = root.getElementById("lights");
    table.innerHTML = `<thead><tr><th>Light</th><th data-tip="What the light is at right now">Now</th>
      <th data-tip="What Dusky wants it to be right now, following the sun">Should be</th>
      <th data-tip="Day brightness for this light. Empty uses the global setting.">Day</th>
      <th data-tip="Night brightness for this light. Empty uses the global setting.">Night</th>
      <th data-tip="Auto follows the sun. Manual means you dimmed it by hand.">Mode</th><th></th></tr></thead><tbody></tbody>`;
    this._lightRows = info.lights.map((l, i) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td><span class="dot" style="background:${SERIES[i % SERIES.length]}"></span><span class="name"></span></td>
        <td data-l="Now" class="now"></td><td data-l="Should be" class="target"></td>
        <td data-l="Day"><input type="number" class="hi" min="0" max="100" step="1"></td>
        <td data-l="Night"><input type="number" class="lo" min="0" max="100" step="1"></td>
        <td data-l="Mode" class="state"></td><td><button class="rel" data-tip="You dimmed this light by hand. Click to let it follow the sun again.">Resume auto</button> <button class="rm" data-tip="Stop Dusky managing this light. The light itself is not changed.">Remove</button></td>`;
      tr.querySelector(".name").textContent = l.name;
      tr.querySelector("td").style.cursor = "pointer";
      tr.querySelector("td").setAttribute("data-tip", "Click to see this light's own curve on the graph.");
      tr.querySelector("td").addEventListener("click", () => {
        this._sel = this._sel === l.light ? null : l.light;
        this._drawGraph();
        this._markSel();
      });
      const wire = (cls, id) => {
        const inp = tr.querySelector(cls);
        inp.addEventListener("change", () => {
          const v = inp.value === "" ? 0 : clamp(parseFloat(inp.value), 0, 100);
          this._edit(id, Number.isFinite(v) ? v : 0);
        });
        return inp;
      };
      const hi = wire(".hi", l.high);
      const lo = wire(".lo", l.low);
      tr.querySelector(".rel").addEventListener("click", () => this._call("button", "press", { entity_id: l.release }));
      tr.querySelector(".rm").addEventListener("click", () => {
        if (info.lights.length < 2) return;
        if (confirm(`Stop managing ${l.name}? The light stays as it is; its Dusky settings are removed.`))
          this._setLights(info.lights.map((x) => x.light).filter((x) => x !== l.light));
      });
      table.querySelector("tbody").appendChild(tr);
      return { l, tr, hi, lo };
    });
    const sel = root.getElementById("addSel");
    sel.innerHTML = `<option value="">Choose a light to add…</option>` +
      (info.candidates || []).map((c) => `<option value="${esc(c.light)}">${esc(c.name)} (${esc(c.light)})</option>`).join("");
    sel.addEventListener("change", () => this._update());
    root.getElementById("addBtn").addEventListener("click", () => {
      if (sel.value) this._setLights([...info.lights.map((x) => x.light), sel.value]);
    });
    this._markSel();
    this._lastW = 0;
    if (this._ro) this._ro.disconnect();
    this._ro = new ResizeObserver(() => {
      const w = root.getElementById("graph").clientWidth;
      if (w && w !== this._lastW) {
        this._lastW = w;
        this._drawGraph();
      }
    });
    this._ro.observe(root.getElementById("graph"));
    root.getElementById("releaseAll").addEventListener("click", () => this._call("button", "press", { entity_id: info.release_all }));

    // demo controls: local choices; runs on what is on screen, saved or not
    const demo = root.getElementById("demo");
    if (!info.lights.some((l) => l.light === this._d.light)) this._d.light = info.lights[0] && info.lights[0].light;
    demo.innerHTML = `<div><label>Light</label><select id="dLight" data-tip="The light to run the demo on"></select></div>
      <div><label>Repeat</label><select id="dRepeat" data-tip="Once plays one day and night. Loop keeps going until you stop it."><option>Once</option><option>Loop</option></select></div>
      <div><label>Seconds (0 = auto)</label><input id="dLen" data-tip="How long the demo takes. 0 picks a length that looks smooth." type="number" min="0" max="600" step="1" value="0"></div>
      <div><button id="dGo" class="fill"></button></div>`;
    this._demo = {
      light: demo.querySelector("#dLight"),
      repeat: demo.querySelector("#dRepeat"),
      len: demo.querySelector("#dLen"),
      go: demo.querySelector("#dGo"),
    };
    this._demo.light.innerHTML = info.lights.map((l) => `<option value="${esc(l.light)}">${esc(l.name)}</option>`).join("");
    this._demo.light.addEventListener("change", () => {
      this._d.light = this._demo.light.value;
      this._update();
    });
    this._demo.repeat.addEventListener("change", () => (this._d.repeat = this._demo.repeat.value));
    this._demo.len.addEventListener("change", () => (this._d.len = clamp(parseFloat(this._demo.len.value) || 0, 0, 600)));
    this._demo.go.addEventListener("click", () => this._toggleDemo());
  }

  _demoRunning() {
    const sw = this._state(this._info.demo.switch);
    return !!sw && sw.state === "on";
  }
  _previewPayload(light) {
    const s = this._info.settings;
    const settings = {};
    for (const key in s) settings[key] = this._num(s[key]);
    const lt = this._info.lights.find((l) => l.light === light);
    return { settings, overrides: { normal: this._num(lt.high, 0), floor: this._num(lt.low, 0) } };
  }
  async _toggleDemo() {
    try {
      if (this._demoRunning()) {
        await this._hass.callWS({ type: "duskylights/demo_stop" });
      } else {
        await this._hass.callWS({
          type: "duskylights/demo",
          light: this._d.light,
          seconds: this._d.len,
          loop: this._d.repeat === "Loop",
          preview: this._previewPayload(this._d.light),
        });
      }
      this._demoError = null;
    } catch (e) {
      this._demoError = e && e.message ? e.message : String(e);
    }
    this._update();
  }

  // ---- update (every hass change) ---------------------------------------------
  _update() {
    if (!this._info || !this._rows) return;
    if (this._menu) this._menu.hass = this._hass;
    const active = this.shadowRoot.activeElement;

    if (Date.now() > this._sunEnd() && !this._sunBusy) {
      this._sunBusy = true;
      this._loadSun().finally(() => (this._sunBusy = false));
    }
    // a draft value that now equals the saved value is no longer a change
    for (const id of Object.keys(this._draft)) {
      const st = this._state(id);
      const v = st ? parseFloat(st.state) : NaN;
      if (Number.isFinite(v) && Math.abs(v - this._draft[id]) < 1e-9) delete this._draft[id];
    }
    const dirty = this._dirtyIds().length;
    {
      const root = this.shadowRoot, many = this._info.lights.length > 1;
      const sel = root.getElementById("addSel"), btn = root.getElementById("addBtn");
      const none = !(this._info.candidates || []).length;
      sel.disabled = dirty > 0 || none;
      btn.disabled = sel.disabled || !sel.value;
      root.getElementById("addNote").textContent = dirty > 0 ? "Save or discard your changes first." : none ? "No other lights to add." : "";
      for (const r of this._lightRows) r.tr.querySelector(".rm").disabled = dirty > 0 || !many;
    }
    const root = this.shadowRoot;
    root.getElementById("dirty").textContent = this._saveError
      ? "Save failed: " + this._saveError
      : dirty
        ? `${dirty} unsaved change${dirty > 1 ? "s" : ""}`
        : "";
    root.getElementById("save").disabled = !dirty || this._saving;
    root.getElementById("discard").disabled = !dirty || this._saving;

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
          ? `<span class="badge hold" data-tip="You dimmed it by hand. It stays there until the sun's curve catches down to it.">manual ${fmt(((t.attributes.hold_brightness || 0) * 100) / 255, 0)}%</span>`
          : '<span class="badge" data-tip="Following the sun">auto</span>';
      const set = (inp, id, glob) => {
        if (this.shadowRoot.activeElement === inp) return;
        const v = this._num(id, 0);
        inp.value = v ? v : "";
        inp.placeholder = fmt(glob, 0) + " (default)";
        inp.setAttribute("data-tip", `Leave empty to use the default (${fmt(glob, 0)}%) from Settings. Type a number to give just this light its own ${inp.classList.contains("hi") ? "day" : "night"} brightness.`);
      };
      set(hi, l.high, g.high);
      set(lo, l.low, g.low);
      r.tr.querySelector(".rel").disabled = !holding;
    }

    // demo controls
    const running = this._demoRunning();
    if (active !== this._demo.light) this._demo.light.value = this._d.light || "";
    if (active !== this._demo.repeat) this._demo.repeat.value = this._d.repeat;
    if (active !== this._demo.len) this._demo.len.value = this._d.len;
    for (const k of ["light", "repeat", "len"]) this._demo[k].disabled = running;
    const lname = ((this._info.lights.find((l) => l.light === this._d.light) || {}).name) || "the light";
    this._demo.go.setAttribute("data-tip", "Plays a quick dusk and dawn on this one light, then puts it back as it was.");
    this._demo.go.textContent = running ? "Stop demo" : dirty ? "Try changes" : "Start demo";
    const sw = this._state(this._info.demo.switch);
    this._demo.go.disabled = !this._info.lights.length || !sw || sw.state === "unavailable";
    root.getElementById("demoNote").textContent = !this._info.lights.length
      ? "Add a light above to run a demo."
      : this._demoError
      ? "Could not start: " + this._demoError
      : dirty
        ? `Runs ${lname} with the unsaved values shown here. Nothing is saved until you press Save.`
        : `Plays a compressed dusk and dawn on ${lname}, starting from where it is now, then puts it back as it was.`;

    this._drawGraph();
  }

  // ---- graph -----------------------------------------------------------------
  _markSel() {
    for (const r of this._lightRows || []) r.tr.classList.toggle("sel", r.l.light === this._sel);
  }

  _drawGraph() {
    const info = this._info;
    if (this._sel && !info.lights.some((l) => l.light === this._sel)) this._sel = null;
    const sel = info.lights.find((l) => l.light === this._sel);
    const g = this._params();
    const box = this.shadowRoot.getElementById("graph");
    const W = clamp(Math.round(box.clientWidth || 720), 300, 900);
    const H = Math.round(clamp(W * 0.58, 250, 460));
    const L = 44, R = 14, T = 18, B = 58;
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
      o.push(`<line class="grid" x1="${X(e)}" x2="${X(e)}" y1="${T}" y2="${H - B}" stroke-dasharray="2 4"/><text class="axis" x="${X(e)}" y="${H - B + 18}" text-anchor="middle">${e}°</text>`);
    }
    // this evening's clock time for each elevation (skipped where labels would touch)
    let lastX = -1e9;
    for (const e of [...ticks].sort((p, q) => q - p)) {
      const t = this._crossing(e, true);
      if (t != null && Math.abs(X(e) - lastX) >= 46) {
        o.push(`<text class="axis" x="${X(e)}" y="${H - B + 33}" text-anchor="middle">${esc(this._clock(t))}</text>`);
        lastX = X(e);
      }
    }
    o.push(`<text class="axis" x="${(L + W - R) / 2}" y="${H - 6}" text-anchor="middle">sun elevation, with this evening\u2019s clock times</text>`);

    // per-light curves: the picked light alone and bold, else every light that differs
    info.lights.forEach((l, i) => {
      const lp = this._lightParams(l, g);
      const mine = sel && l === sel;
      if (mine || (!sel && (lp.high !== g.high || lp.low !== g.low))) {
        o.push(`<path d="${path(lp)}" fill="none" stroke="${SERIES[i % SERIES.length]}" stroke-width="${mine ? 4 : 2}" ${mine ? 'stroke-linecap="round"' : 'stroke-dasharray="6 4"'} opacity=".95"/>`);
      }
    });
    o.push(`<path d="${path(g)}" fill="none" stroke="${AMBER}" stroke-width="${sel ? 2 : 4}" stroke-linecap="round" ${sel ? 'stroke-dasharray="5 4" opacity=".7"' : ""}/>`);
    const ep = sel ? this._lightParams(sel, g) : g;
    o.push(`<circle cx="${X(g.start)}" cy="${Y(ep.high)}" r="5" fill="${AMBER}"/><circle cx="${X(g.end)}" cy="${Y(Math.min(ep.low, ep.high))}" r="5" fill="#d9567a"/>`);

    // live sun and each light's target
    const demoLight = info.lights.find((l) => {
      const t = this._state(l.target);
      return t && t.attributes && t.attributes.demo && t.attributes.demo_elevation != null;
    });
    const elev = demoLight ? this._state(demoLight.target).attributes.demo_elevation : this._num(info.elevation);
    if (Number.isFinite(elev)) {
      const ex = X(clamp(elev, xMin, xMax));
      o.push(`<line x1="${ex}" x2="${ex}" y1="${T}" y2="${H - B}" stroke="var(--primary-text-color,#333)" stroke-width="1" stroke-dasharray="4 3" opacity=".7"/>`);
      o.push(`<text class="axis" x="${ex}" y="${T + 12}" text-anchor="${ex > W - 90 ? "end" : "start"}" dx="${ex > W - 90 ? -4 : 4}">${demoLight ? "demo sun" : "sun"} ${fmt(elev, 1)}°</text>`);
      info.lights.forEach((l, i) => {
        if (demoLight && l !== demoLight) return; // only the demo light is moving
        if (!demoLight && sel && l !== sel) return;
        const t = this._state(l.target);
        const v = t ? parseFloat(t.state) : NaN;
        if (Number.isFinite(v)) {
          o.push(`<circle cx="${ex}" cy="${Y(v)}" r="6" fill="${SERIES[i % SERIES.length]}" stroke="var(--card-background-color,#fff)" stroke-width="2"><title>${esc(l.name)}: target ${fmt(v, 0)}%</title></circle>`);
        }
      });
    }
    const d0 = this._crossing(g.start, true), d1 = this._crossing(g.end, true);
    const r0 = this._crossing(g.end, false), r1 = this._crossing(g.start, false);
    const span = (a, b) => (a != null && b != null ? `${this._clock(a)} to ${this._clock(b)}` : null);
    const dusk = span(d0, d1), dawn = span(r0, r1);
    this.shadowRoot.getElementById("times").textContent = !this._sun
      ? ""
      : dusk && dawn
        ? `Today's sun: dimming runs ${dusk}; brightening runs ${dawn}.`
        : "Today's sun doesn't pass through both of these elevations at your location, so the ramp doesn't complete today.";
    box.innerHTML =
      `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Brightness against sun elevation">${o.join("")}</svg>`;

    this.shadowRoot.getElementById("legend").innerHTML =
      (sel
        ? `<span><b>${esc(sel.name)}</b>: High ${fmt(this._lightParams(sel, g).high, 0)}%, Low ${fmt(this._lightParams(sel, g).low, 0)}% (dashed = global)</span>`
        : `<span class="sub">Click a light's name below to see just its curve.</span>`) +
      `<span><span class="dot" style="background:${AMBER}"></span>global curve</span>` +
      info.lights
        .map((l, i) => `<span><span class="dot" style="background:${SERIES[i % SERIES.length]}"></span>${esc(l.name)}</span>`)
        .join("");
  }
}

if (!customElements.get("dusky-panel")) customElements.define("dusky-panel", DuskyPanel);
