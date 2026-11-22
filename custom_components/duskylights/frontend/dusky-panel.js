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
.build { color:var(--secondary-text-color,#727272); font-size:11px; opacity:.7; text-align:center; margin:4px 0 0; user-select:text; }
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
[hidden] { display:none !important; }
.sethead { display:flex; justify-content:space-between; align-items:center; gap:8px; }
.sethead h2 { margin:0; }
.lnk { background:none; border:0; padding:0; margin-left:8px; color:var(--primary-color,#03a9f4); font-size:13px; cursor:pointer; }
.row.locked { opacity:.5; }
.row.locked input { cursor:not-allowed; }
.row.inh input[type=number] { color:var(--secondary-text-color,#888); font-style:italic; }
.warn { display:flex; gap:10px; align-items:center; justify-content:space-between; margin:6px 0; padding:8px 12px; border-radius:8px; font-size:13px;
  background:color-mix(in srgb, var(--warning-color,#ffa600) 20%, transparent); }
.warn .lnk { white-space:nowrap; flex:none; margin:0; }
.addrow { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-top:12px; }
.addrow { align-items:flex-end; }
.combo { position:relative; flex:1 1 260px; min-width:220px; }
.combo label { display:block; font-size:12px; color:var(--secondary-text-color,#666); margin:0 0 2px 12px; }
.combo input { width:100%; box-sizing:border-box; height:48px; padding:0 12px; font:inherit; color:var(--primary-text-color,#333);
  background:var(--input-fill-color, color-mix(in srgb, var(--primary-text-color,#333) 6%, transparent));
  border:0; border-bottom:1px solid var(--input-idle-line-color, var(--secondary-text-color,#888)); border-radius:4px 4px 0 0; outline:none; }
.combo input:hover { background:color-mix(in srgb, var(--primary-text-color,#333) 9%, transparent); }
.combo input:focus { border-bottom:2px solid var(--primary-color,#03a9f4); padding-bottom:1px; }
.combo input:disabled { opacity:.5; }
.combo ul { position:absolute; left:0; right:0; top:100%; z-index:6; margin:2px 0 0; padding:8px 0; list-style:none; max-height:264px; overflow:auto;
  background:var(--card-background-color,#fff); border-radius:4px; box-shadow:0 5px 16px rgba(0,0,0,.25); }
.combo li { padding:8px 16px; cursor:pointer; display:flex; flex-direction:column; min-height:36px; justify-content:center; }
.combo li small { color:var(--secondary-text-color,#666); font-size:12px; }
.combo li.act, .combo li:hover { background:color-mix(in srgb, var(--primary-text-color,#333) 8%, transparent); }
.combo li.none { color:var(--secondary-text-color,#666); cursor:default; }
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
tr.sel td:first-child { font-weight:600; }
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
    // High and Low are the only per-light settings; 0 means "use the shared value"
    const hi = this._num(light.high, 0);
    const lo = this._num(light.low, 0);
    return { ...g, high: hi || g.high, low: lo || g.low };
  }
  _rowId(key) {
    const sel = this._info.lights.find((l) => l.light === this._sel);
    const own = sel && { normal_pct: sel.high, floor_pct: sel.low }[key];
    return own || this._info.settings[key];
  }
  _call(domain, service, data) {
    return this._hass.callService(domain, service, data);
  }
  _edit(id, value) {
    Object.assign(this._draft, this._constrain(id, value));
    this._update();
  }
  // Saved values that break the same rules (set outside the panel, or before the rules existed).
  // They are reported with a one-click fix that stages the change; nothing is saved until Save.
  _problems() {
    const S = this._info.settings, g = this._params(), out = [];
    if (g.start <= g.end) {
      out.push({
        text: `Dimmest at (${fmt(g.end, 1)}\u00b0) is not below Dim starts at (${fmt(g.start, 1)}\u00b0), so the lights will never dim.`,
        fix: () => this._constrain(S.start_elevation, g.start),
      });
    }
    if (g.low > g.high) {
      out.push({
        text: `Night brightness (${fmt(g.low, 0)}%) is above Day brightness (${fmt(g.high, 0)}%), so the lights will not dim.`,
        fix: () => this._constrain(S.normal_pct, g.high),
      });
    }
    for (const l of this._info.lights) {
      const p = this._lightParams(l, g);
      const ownLow = this._num(l.low, 0) > 0, ownHigh = this._num(l.high, 0) > 0;
      if (p.low > p.high && (ownLow || ownHigh)) { // a light that only inherits is covered by the shared warning
        out.push({
          text: `${l.name}: night brightness (${fmt(p.low, 0)}%) is above its day brightness (${fmt(p.high, 0)}%), so it will not dim.`,
          fix: () => (ownLow ? { [l.low]: p.high } : { [l.high]: p.low }),
        });
      }
    }
    return out;
  }
  // Keep pairs in a sensible order: dimming must end below where it starts, and Night cannot be
  // brighter than Day. The value being dragged pushes the other one along (like a two-handled range
  // slider); if the other is already at its limit, the dragged one stops instead.
  _constrain(id, v) {
    const S = this._info.settings, out = { [id]: v };
    const limit = (eid, key) => ((this._state(eid) || {}).attributes || {})[key];
    const label = (key) => (SETTINGS.find((r) => r[0] === key) || [])[1] || key;
    const GAP = 1; // degrees of sun height between start and end
    const say = (text) => {
      this._pushNote = text;
      clearTimeout(this._pushTimer);
      this._pushTimer = setTimeout(() => { this._pushNote = null; this._update(); }, 4000);
    };
    if (id === S.start_elevation || id === S.end_elevation) {
      const isStart = id === S.start_elevation;
      const other = isStart ? S.end_elevation : S.start_elevation;
      const o = this._num(other);
      if (Number.isFinite(o) && (isStart ? v < o + GAP : v > o - GAP)) {
        const lim = limit(other, isStart ? "min" : "max");
        const no = isStart ? Math.max(lim ?? -Infinity, v - GAP) : Math.min(lim ?? Infinity, v + GAP);
        out[other] = no;
        out[id] = isStart ? Math.max(v, no + GAP) : Math.min(v, no - GAP);
        say(`${label(isStart ? "end_elevation" : "start_elevation")} moved to ${fmt(no, 1)}\u00b0 so dimming still ends below where it starts.`);
      }
    } else if (id === S.normal_pct || id === S.floor_pct) {
      const isHigh = id === S.normal_pct;
      const other = isHigh ? S.floor_pct : S.normal_pct;
      const o = this._num(other);
      if (Number.isFinite(o) && (isHigh ? v < o : v > o)) {
        out[other] = v;
        say(`${label(isHigh ? "floor_pct" : "normal_pct")} moved to ${fmt(v, 0)}% so Night is never brighter than Day.`);
      }
    } else {
      const l = this._info.lights.find((x) => x.high === id || x.low === id);
      if (l && v > 0) {
        const eff = this._lightParams(l, this._params());
        if (id === l.high && v < eff.low) {
          out[l.low] = v;
          say(`${l.name}'s night brightness moved to ${fmt(v, 0)}% so it is never brighter than its day brightness.`);
        } else if (id === l.low && v > eff.high) {
          out[l.high] = v;
          say(`${l.name}'s day brightness moved to ${fmt(v, 0)}% so it is never dimmer than its night brightness.`);
        }
      }
    }
    return out;
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
          <section class="card"><h2>Brightness follows the sun</h2><div id="graph"></div><p class="sub" id="times"></p></section>
          <section class="card"><div class="sethead"><h2 id="setTitle">Settings</h2><button id="setAll" hidden data-tip="Go back to editing the settings every light shares">All lights</button></div><p class="sub" id="setNote"></p><div id="problems"></div><div id="settings"></div></section>
        </div>
        <section class="card"><h2>Lights</h2><div style="overflow-x:auto"><table id="lights"></table></div>
          <p style="margin:12px 0 0"><button id="releaseAll" data-tip="Cancel every manual dim so all lights follow the sun again">Resume all</button></p>
          <div class="addrow"><div class="combo"><label for="addIn">Add a light</label><input id="addIn" type="text" autocomplete="off" role="combobox" aria-expanded="false" aria-controls="addList" placeholder="Search by name or entity id"><ul id="addList" role="listbox"></ul></div><button id="addBtn" data-tip="Have Dusky manage the selected light">Add light</button>
            <span class="sub" id="addNote"></span></div></section>
        <section class="card"><h2>Demo</h2><div class="demo-grid" id="demo"></div><p class="sub" id="demoNote"></p></section>
        <p class="build" id="build"></p>
      </main><div id="tip" role="tooltip"></div>`;

    root.getElementById("build").textContent = info.build ? `build ${info.build}` : "";
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
      const gid = info.settings[key];
      const st = this._state(gid);
      const a = (st && st.attributes) || {};
      const row = document.createElement("div");
      row.className = "row";
      row.innerHTML = `<label>${esc(label)}</label>
        <input type="range" min="${a.min ?? 0}" max="${a.max ?? 100}" step="${a.step ?? 1}">
        <input type="number" min="${a.min ?? 0}" max="${a.max ?? 100}" step="${a.step ?? 1}">
        <span class="sub">${esc(hint)}${a.unit_of_measurement ? " (" + esc(a.unit_of_measurement) + ")" : ""}<button class="lnk" hidden>Use default</button></span>`;
      const [range, num] = row.querySelectorAll("input");
      const lnk = row.querySelector(".lnk");
      range.addEventListener("input", () => {
        num.value = range.value;
        this._edit(this._rowId(key), parseFloat(range.value));
      });
      num.addEventListener("change", () => {
        const v = clamp(parseFloat(num.value), parseFloat(num.min), parseFloat(num.max));
        if (Number.isFinite(v)) this._edit(this._rowId(key), v);
        else this._update();
      });
      lnk.addEventListener("click", () => this._edit(this._rowId(key), 0)); // 0 = use the shared value
      box.appendChild(row);
      this._rows[key] = { gid, range, num, row, lnk, tip, zero: key === "normal_pct" || key === "floor_pct" };
    }
    this._zeroIds = new Set(info.lights.flatMap((l) => [l.high, l.low]));
    root.getElementById("setAll").addEventListener("click", () => {
      this._sel = null;
      this._markSel();
      this._update();
    });

    // lights table
    const table = root.getElementById("lights");
    table.innerHTML = `<thead><tr><th>Light</th><th data-tip="What the light is at right now">Now</th>
      <th data-tip="What Dusky wants it to be right now, following the sun">Should be</th>
      <th data-tip="Day brightness for this light. Empty uses the global setting.">Day</th>
      <th data-tip="Night brightness for this light. Empty uses the global setting.">Night</th>
      <th data-tip="Auto follows the sun. Manual means you dimmed it by hand.">Mode</th><th></th></tr></thead><tbody></tbody>`;
    this._lightRows = info.lights.map((l, i) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td><span class="name"></span></td>
        <td data-l="Now" class="now"></td><td data-l="Should be" class="target"></td>
        <td data-l="Day"><input type="number" class="hi" min="0" max="100" step="1"></td>
        <td data-l="Night"><input type="number" class="lo" min="0" max="100" step="1"></td>
        <td data-l="Mode" class="state"></td><td><button class="rel" data-tip="You dimmed this light by hand. Click to let it follow the sun again.">Resume auto</button> <button class="rm" data-tip="Stop Dusky managing this light. The light itself is not changed.">Remove</button></td>`;
      tr.querySelector(".name").textContent = l.name;
      tr.querySelector("td").style.cursor = "pointer";
      tr.querySelector("td").setAttribute("data-tip", "Click to see this light's own curve on the graph.");
      tr.querySelector("td").addEventListener("click", () => {
        this._pickLight(l.light);
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
    // type-to-filter light picker (substring of the name or entity id)
    this._addPick = null;
    const inp = root.getElementById("addIn"), list = root.getElementById("addList");
    const cands = info.candidates || [];
    let shown = [], active = 0;
    const render = () => {
      const q = inp.value.trim().toLowerCase();
      shown = this._addPick ? cands : cands.filter((c) => !q || c.name.toLowerCase().includes(q) || c.light.toLowerCase().includes(q));
      list.innerHTML = shown.length
        ? shown.map((c, n) => `<li role="option" data-i="${n}" class="${n === active ? "act" : ""}"><span>${esc(c.name)}</span><small>${esc(c.light)}</small></li>`).join("")
        : '<li class="none">No matching lights</li>';
      const a = list.querySelector(".act");
      if (a) a.scrollIntoView({ block: "nearest" });
    };
    const open = () => {
      if (inp.disabled) return;
      render();
      list.style.display = "block";
      inp.setAttribute("aria-expanded", "true");
    };
    const close = () => {
      list.style.display = "none";
      inp.setAttribute("aria-expanded", "false");
    };
    const pick = (c) => {
      this._addPick = c.light;
      inp.value = c.name;
      close();
      this._update();
    };
    inp.addEventListener("focus", () => { inp.select(); open(); });
    inp.addEventListener("input", () => {
      this._addPick = null; // typing again means the earlier pick no longer counts
      active = 0;
      open();
      this._update();
    });
    inp.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        if (list.style.display !== "block") open();
        active = shown.length ? (active + (e.key === "ArrowDown" ? 1 : -1) + shown.length) % shown.length : 0;
        render();
      } else if (e.key === "Enter") {
        if (list.style.display === "block" && shown[active]) { e.preventDefault(); pick(shown[active]); }
      } else if (e.key === "Escape") close();
    });
    inp.addEventListener("blur", close);
    list.addEventListener("mousedown", (e) => {
      e.preventDefault(); // keep focus in the box so blur does not close the list first
      const li = e.target.closest("li[data-i]");
      if (li) pick(shown[+li.dataset.i]);
    });
    close();
    root.getElementById("addBtn").addEventListener("click", () => {
      if (this._addPick) this._setLights([...info.lights.map((x) => x.light), this._addPick]);
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
    const overrides = { normal: this._num(lt.high, 0), floor: this._num(lt.low, 0) };
    return { settings, overrides };
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
      const same = Number.isFinite(v) && Math.abs(v - this._draft[id]) < 1e-9;
      if (same) delete this._draft[id];
    }
    const dirty = this._dirtyIds().length;
    {
      const root = this.shadowRoot, many = this._info.lights.length > 1;
      const inp = root.getElementById("addIn"), btn = root.getElementById("addBtn");
      const none = !(this._info.candidates || []).length;
      inp.disabled = dirty > 0 || none;
      btn.disabled = inp.disabled || !this._addPick;
      this._txt(root.getElementById("addNote"), dirty > 0 ? "Save or discard your changes first." : none ? "No other lights to add." : "");
      for (const r of this._lightRows) r.tr.querySelector(".rm").disabled = dirty > 0 || !many;
    }
    const root = this.shadowRoot;
    this._txt(root.getElementById("dirty"), this._saveError
      ? "Save failed: " + this._saveError
      : dirty
        ? `${dirty} unsaved change${dirty > 1 ? "s" : ""}`
        : "");
    root.getElementById("save").disabled = !dirty || this._saving;
    root.getElementById("discard").disabled = !dirty || this._saving;

    const sel = this._info.lights.find((l) => l.light === this._sel);
    for (const key in this._rows) {
      const r = this._rows[key];
      const locked = !!sel && !r.zero; // only High and Low can differ per light
      let v = this._num(this._rowId(key));
      let inherited = false;
      if (sel && r.zero && (!Number.isFinite(v) || v === 0)) {
        v = this._num(r.gid); // this light has no value of its own: show the shared one
        inherited = true;
      }
      r.row.classList.toggle("inh", inherited);
      r.row.classList.toggle("locked", locked);
      r.range.disabled = r.num.disabled = locked;
      r.lnk.hidden = !sel || !r.zero || inherited;
      r.row.setAttribute("data-tip", locked
        ? `${r.tip} This one is shared by every light. Only day and night brightness can be set for a single room.`
        : sel
          ? `${r.tip} Applies only to ${sel.name}. "Use default" goes back to the shared value.`
          : `${r.tip} This is the default for every light. To set it for just one, click that light's name below.`);
      if (!Number.isFinite(v)) continue;
      if (active !== r.range) r.range.value = v;
      if (active !== r.num) r.num.value = v;
    }
    const problems = this._problems();
    const key = problems.map((p) => p.text).join("|");
    if (key !== this._problemKey) {
      this._problemKey = key;
      const box = root.getElementById("problems");
      box.innerHTML = "";
      for (const pr of problems) {
        const d = document.createElement("div");
        d.className = "warn";
        d.innerHTML = `<span>${esc(pr.text)}</span><button class="lnk" data-tip="Stage a correction. Nothing changes until you press Save.">Fix it</button>`;
        d.querySelector("button").addEventListener("click", () => {
          Object.assign(this._draft, pr.fix());
          this._update();
        });
        box.appendChild(d);
      }
    }
    this._txt(root.getElementById("setTitle"), sel ? `Settings: ${sel.name}` : "Settings");
    root.getElementById("setAll").hidden = !sel;
    this._txt(root.getElementById("setNote"), this._pushNote ? this._pushNote : sel
      ? `Only day and night brightness can differ per light. Greyed-out settings are shared by every light.`
      : "These apply to every light unless it has its own. Click a light's name below to set just that one.");

    const g = this._params();
    for (const r of this._lightRows) {
      const { l, hi, lo } = r;
      const t = this._state(l.target);
      const ls = this._state(l.light);
      const bri = ls && ls.attributes ? ls.attributes.brightness : null;
      this._txt(r.tr.querySelector(".now"), ls && ls.state === "on" && bri != null ? fmt((bri * 100) / 255, 0) + "%" : ls ? ls.state : "-");
      this._txt(r.tr.querySelector(".target"), t ? fmt(parseFloat(t.state), 0) + "%" : "-");
      const holding = t && t.attributes && t.attributes.holding;
      const demo = t && t.attributes && t.attributes.demo;
      this._html(r.tr.querySelector(".state"), demo
        ? '<span class="badge demo">demo</span>'
        : holding
          ? `<span class="badge hold" data-tip="You dimmed it by hand. It stays there until the sun's curve catches down to it.">manual ${fmt(((t.attributes.hold_brightness || 0) * 100) / 255, 0)}%</span>`
          : '<span class="badge" data-tip="Following the sun">auto</span>');
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
    this._txt(this._demo.go, running ? "Stop demo" : dirty ? "Try changes" : "Start demo");
    const sw = this._state(this._info.demo.switch);
    this._demo.go.disabled = !this._info.lights.length || !sw || sw.state === "unavailable";
    this._txt(root.getElementById("demoNote"), !this._info.lights.length
      ? "Add a light above to run a demo."
      : this._demoError
      ? "Could not start: " + this._demoError
      : dirty
        ? `Runs ${lname} with the unsaved values shown here. Nothing is saved until you press Save.`
        : `Plays a compressed dusk and dawn on ${lname}, starting from where it is now, then puts it back as it was.`);

    this._drawGraph();
  }

  // ---- graph -----------------------------------------------------------------
  _pickLight(id) {
    this._sel = this._sel === id ? null : id;
    if (this._sel) this._d.light = id; // the demo now tries changes on the light you are looking at
    this._markSel();
    this._update();
  }

  _markSel() {
    for (const r of this._lightRows || []) r.tr.classList.toggle("sel", r.l.light === this._sel);
  }

  // The graph does not jump when a setting changes: every number it draws with (curve shape, axis
  // ranges, per-light levels) chases its target like a critically damped spring (what a well-tuned
  // PID loop settles to): quick, no overshoot, about a quarter of a second.
  _drawGraph() {
    if (!this._info) return;
    const info = this._info, g = this._params();
    const lights = info.lights.map((l) => this._lightParams(l, g));
    const yMax = Math.max(g.high, ...lights.map((p) => p.high), 20);
    const tgt = {
      ...g,
      xMax: Math.max(g.start + 14, 25),
      xMin: Math.min(g.end - 8, -19),
      yMax: Math.min(100, Math.ceil((yMax + 8) / 10) * 10),
    };
    lights.forEach((p, i) => { tgt["h" + i] = p.high; tgt["l" + i] = p.low; });
    this._tgt = tgt;
    const same = this._cur && Object.keys(tgt).length === Object.keys(this._cur).length && Object.keys(tgt).every((k) => k in this._cur);
    const calm = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!same || calm) {
      this._cur = { ...tgt };
      this._vel = {};
    } else if (Object.keys(tgt).some((k) => Math.abs(tgt[k] - this._cur[k]) > 1e-6)) {
      this._animate();
    }
    this._paint();
  }

  _animate() {
    if (this._raf) return;
    let last = null;
    const W = 22; // rad/s; critically damped, settles in about 0.26 s
    const step = (now) => {
      const dt = last == null ? 1 / 60 : Math.min(0.033, (now - last) / 1000);
      last = now;
      let moving = false;
      for (const k of Object.keys(this._tgt)) {
        const x = this._cur[k], v = this._vel[k] || 0, t = this._tgt[k];
        const nv = v + (W * W * (t - x) - 2 * W * v) * dt;
        let nx = x + nv * dt;
        if (Math.abs(t - nx) < 1e-3 * Math.max(1, Math.abs(t)) && Math.abs(nv) < 1e-2) {
          this._cur[k] = t;
          this._vel[k] = 0;
        } else {
          this._cur[k] = nx;
          this._vel[k] = nv;
          moving = true;
        }
      }
      this._paint();
      this._raf = moving && this.isConnected ? requestAnimationFrame(step) : 0;
    };
    this._raf = requestAnimationFrame(step);
  }

  _lp(light, m = this._cur) {
    const i = this._info.lights.indexOf(light);
    return { ...m, high: m["h" + i], low: m["l" + i] };
  }

  _paint() {
    const info = this._info;
    if (this._sel && !info.lights.some((l) => l.light === this._sel)) this._sel = null;
    const sel = info.lights.find((l) => l.light === this._sel);
    const G = this._tgt, g = this._cur; // G: where it is heading (for labels); g: what is on screen
    const box = this.shadowRoot.getElementById("graph");
    const W = clamp(Math.round(box.clientWidth || 720), 300, 900);
    const H = Math.round(clamp(W * 0.58, 250, 460));
    const L = 44, R = 14, T = 18, B = 74;
    const { xMax, xMin, yMax } = g;
    const ep = sel ? this._lp(sel) : g; // the curve being looked at
    const Gs = sel ? this._lp(sel, G) : G;
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
    // how dark the sky is: day, three twilights, night (standard definitions by sun height)
    for (const [top, bottom, short, name, shade, blurb] of [
      [Infinity, 0, "day", "Day", 0, "The sun is above the horizon."],
      [0, -6, "civil", "Civil twilight", 0.06, "Still bright enough to see outdoors without lights."],
      [-6, -12, "nautical", "Nautical twilight", 0.12, "The horizon fades; most people want lights on."],
      [-12, -18, "astro", "Astronomical twilight", 0.18, "Nearly dark; only faint sky glow remains."],
      [-18, -Infinity, "night", "Night", 0.24, "Fully dark."],
    ]) {
      const hi = Math.min(top, xMax), lo = Math.max(bottom, xMin);
      if (hi <= lo) continue;
      const t0 = this._crossing(top === Infinity ? 0 : top, top === Infinity ? false : true);
      const t1 = this._crossing(bottom === -Infinity ? -18 : bottom, true);
      const when = top === Infinity
        ? (t0 != null && t1 != null ? ` Today: ${this._clock(t0)} to ${this._clock(this._crossing(0, true))}.` : "")
        : bottom === -Infinity
          ? (t1 != null ? ` Today from about ${this._clock(t1)}.` : "")
          : (this._crossing(top, true) != null && t1 != null ? ` Today: ${this._clock(this._crossing(top, true))} to ${this._clock(t1)}.` : "");
      const range = top === Infinity ? "" : bottom === -Infinity ? " (sun more than 18\u00b0 below the horizon)" : ` (sun ${Math.abs(top)}\u00b0 to ${Math.abs(bottom)}\u00b0 below the horizon)`;
      const x1 = X(hi), x2 = X(lo);
      o.push(`<g class="band" data-tip="${esc(name + range + ". " + blurb + when)}"><rect x="${x1.toFixed(1)}" y="${T}" width="${(x2 - x1).toFixed(1)}" height="${H - B - T}" fill="var(--primary-text-color,#333)" fill-opacity="${shade}"/>` +
        (x2 - x1 >= 40 ? `<text class="axis band-label" x="${((x1 + x2) / 2).toFixed(1)}" y="${((T + H - B) / 2 + 4).toFixed(1)}" text-anchor="middle">${short}</text>` : "") + "</g>");
    }
    // ramp window shading
    o.push(`<rect x="${X(ep.start).toFixed(1)}" y="${T}" width="${Math.max(0, X(ep.end) - X(ep.start)).toFixed(1)}" height="${H - T - B}" fill="${AMBER}" opacity=".12"/>`);
    for (let p = 0; p <= G.yMax; p += G.yMax > 60 ? 20 : 10) {
      if (Y(p) < T - 1) continue;
      o.push(`<line class="grid" x1="${L}" x2="${W - R}" y1="${Y(p)}" y2="${Y(p)}"/><text class="axis" x="${L - 8}" y="${Y(p) + 4}" text-anchor="end">${p}%</text>`);
    }
    const ticks = new Set([Math.round(G.xMax / 10) * 10, 10, 0, -6, -12, -18, Math.round(Gs.start), Math.round(Gs.end)].filter((e) => e <= xMax && e >= xMin));
    for (const e of ticks) {
      o.push(`<line class="grid" x1="${X(e)}" x2="${X(e)}" y1="${T}" y2="${H - B}" stroke-dasharray="2 4"/><text class="axis" x="${X(e)}" y="${H - B + 33}" text-anchor="middle">${e}°</text>`);
    }
    // this evening's clock time for each elevation (skipped where labels would touch)
    let lastX = -1e9;
    for (const e of [...ticks].sort((p, q) => q - p)) {
      const t = this._crossing(e, true);
      if (t != null && Math.abs(X(e) - lastX) >= 46) {
        o.push(`<text class="axis" x="${X(e)}" y="${H - B + 48}" text-anchor="middle">${esc(this._clock(t))}</text>`);
        lastX = X(e);
      }
    }
    o.push(`<text class="axis" x="${(L + W - R) / 2}" y="${H - 6}" text-anchor="middle">sun height above the horizon, with this evening\u2019s clock times</text>`);

    // the picked light is the bold line with the shared default dotted behind it; with none picked,
    // the default is the bold line
    if (sel) {
      o.push(`<path d="${path(g)}" fill="none" stroke="${AMBER}" stroke-width="2.5" stroke-linecap="round" stroke-dasharray="1 6" opacity=".85"/>`);
      o.push(`<path d="${path(ep)}" fill="none" stroke="${AMBER}" stroke-width="4" stroke-linecap="round"/>`);
    } else {
      o.push(`<path d="${path(g)}" fill="none" stroke="${AMBER}" stroke-width="4" stroke-linecap="round"/>`);
    }
    o.push(`<circle cx="${X(ep.start)}" cy="${Y(ep.high)}" r="5" fill="${AMBER}"/><circle cx="${X(ep.end)}" cy="${Y(Math.min(ep.low, ep.high))}" r="5" fill="#d9567a"/>`);

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
      const shown = demoLight || sel; // the light being looked at, else the default curve
      const t = shown ? this._state(shown.target) : null;
      const v = shown ? (t ? parseFloat(t.state) : NaN) : targetPct(elev, g);
      if (Number.isFinite(v)) {
        o.push(`<circle cx="${ex}" cy="${Y(v)}" r="6" fill="${AMBER}" stroke="var(--card-background-color,#fff)" stroke-width="2"><title>${esc(shown ? shown.name : "Default")}: target ${fmt(v, 0)}%</title></circle>`);
      }
    }
    const d0 = this._crossing(Gs.start, true), d1 = this._crossing(Gs.end, true);
    const r0 = this._crossing(Gs.end, false), r1 = this._crossing(Gs.start, false);
    const span = (a, b) => (a != null && b != null ? `${this._clock(a)} to ${this._clock(b)}` : null);
    const dusk = span(d0, d1), dawn = span(r0, r1);
    this._txt(this.shadowRoot.getElementById("times"), !this._sun
      ? ""
      : dusk && dawn
        ? `Today's sun: dimming runs ${dusk}; brightening runs ${dawn}.`
        : "Today's sun doesn't pass through both of these elevations at your location, so the ramp doesn't complete today.");
    this._html(box, `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Brightness against sun elevation">${o.join("")}</svg>`);
  }

  // The panel refreshes on every Home Assistant state change. Rewriting a node with identical content
  // still replaces it, which drops text selections and hover targets (and so hides tooltips), so only
  // touch the DOM when something actually changed.
  _html(el, html) {
    if (el._h !== html) { el._h = html; el.innerHTML = html; }
  }
  _txt(el, text) {
    if (el.textContent !== text) el.textContent = text;
  }
}

if (!customElements.get("dusky-panel")) customElements.define("dusky-panel", DuskyPanel);
