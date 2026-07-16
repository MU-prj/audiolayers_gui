/* audiolayers gui — stato controlli -> API -> wav */
"use strict";

/* Le definizioni dei parametri NON vivono qui: arrivano dal motore
   via /api/params (fonte unica: bounds, default, enum, env, info).
   `boot()` le carica e poi disegna la GUI. */
let GLOBAL_DEFS = [], LAYER_DEFS = [], PROVISION_DEFS = [];
let ALL_LAYER_DEFS = [];
let DEF_BY_PATH = {};

function defFromCatalog(entry) {
  const d = {
    path: entry.path, label: entry.label, def: entry.default,
    env: !!entry.env, info: entry.info,
    hardMin: entry.min, hardMax: entry.max,
    min: entry.ui?.min ?? entry.min, max: entry.ui?.max ?? entry.max,
    step: entry.step,
  };
  if (entry.mode) d.mode = entry.mode;
  if (entry.options) d.options = entry.options;
  if (entry.kind !== "float") d.kind = entry.kind;
  return d;
}

async function loadParamDefs() {
  const cat = await (await fetch("/api/params")).json();
  GLOBAL_DEFS = cat.global.map(defFromCatalog);
  LAYER_DEFS = cat.layer.map(defFromCatalog);
  PROVISION_DEFS = cat.provision.map(defFromCatalog);
  ALL_LAYER_DEFS = [...LAYER_DEFS, ...PROVISION_DEFS];
  DEF_BY_PATH = Object.fromEntries(
    [...GLOBAL_DEFS, ...ALL_LAYER_DEFS].map(d => [d.path, d]));
}

const state = { global: {}, layers: [] };
let layerCounter = 0;

function newControl(def, enabled = false) {
  return { enabled, value: def.def };
}

function newLayer() {
  layerCounter += 1;
  const params = {};
  for (const def of ALL_LAYER_DEFS) params[def.path] = newControl(def, def.path === "duration");
  // pool vuoto = derivato: la chiave non entra nello YAML e il motore
  // risolve da provision.pool globale o audio/pool/<layer_id> (issue #3).
  return { layer_id: `layer${String(layerCounter).padStart(2, "0")}`,
           pool: "", params };
}

/* Pool a 3 stati (issue #3): "" derivato | "auto" | path esplicito. */
function poolModeOf(pool) {
  return pool === "" ? "default" : pool === "auto" ? "auto" : "custom";
}

/* La cartella EFFETTIVA del layer: stessa logica del resolver del
   motore (audiolayers.audio.pool.resolve_pool), per la preview. */
function resolvedPoolOf(layer) {
  const g = state.global["provision.pool"];
  const base = (g?.enabled && g.value)
    ? String(g.value).replace(/\/+$/, "") : "";
  if (layer.pool === "auto") return `${base || "audio/pool"}/${layer.layer_id}`;
  if (layer.pool) return layer.pool;
  return base || `audio/pool/${layer.layer_id}`;
}

/* ---------- envelope editor ---------- */
function drawEnvelope(canvas, def, control, layerDur) {
  const ctx = canvas.getContext("2d");
  const W = canvas.width = canvas.clientWidth * 2;
  const H = canvas.height = 112;
  ctx.clearRect(0, 0, W, H);
  ctx.strokeStyle = "#eee";
  for (let i = 1; i < 4; i++) {
    ctx.beginPath(); ctx.moveTo(0, H * i / 4); ctx.lineTo(W, H * i / 4); ctx.stroke();
  }
  const pts = control.value;
  ctx.strokeStyle = "#111"; ctx.fillStyle = "#111"; ctx.lineWidth = 2;
  ctx.beginPath();
  pts.forEach(([t, v], i) => {
    const x = (t / layerDur) * W;
    const y = H - ((v - def.min) / (def.max - def.min)) * H;
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.stroke();
  pts.forEach(([t, v]) => {
    const x = (t / layerDur) * W;
    const y = H - ((v - def.min) / (def.max - def.min)) * H;
    ctx.beginPath(); ctx.arc(x, y, 5, 0, 7); ctx.fill();
  });
}

function attachEnvelopeEditor(canvas, def, control, getDur, onchange) {
  const toPoint = (ev) => {
    const r = canvas.getBoundingClientRect();
    const t = Math.max(0, Math.min(1, (ev.clientX - r.left) / r.width)) * getDur();
    const v = def.min + Math.max(0, Math.min(1, 1 - (ev.clientY - r.top) / r.height)) * (def.max - def.min);
    return [Number(t.toFixed(3)), Number(v.toFixed(4))];
  };
  const nearest = (ev) => {
    const r = canvas.getBoundingClientRect();
    let best = -1, bestD = 14;
    control.value.forEach(([t, v], i) => {
      const x = (t / getDur()) * r.width;
      const y = r.height - ((v - def.min) / (def.max - def.min)) * r.height;
      const d = Math.hypot(x - (ev.clientX - r.left), y - (ev.clientY - r.top));
      if (d < bestD) { bestD = d; best = i; }
    });
    return best;
  };
  let dragging = -1;
  let moved = false;
  let wasExisting = false;
  const redraw = () => drawEnvelope(canvas, def, control, getDur());
  canvas.addEventListener("pointerdown", (ev) => {
    const hit = nearest(ev);
    if (ev.button === 2) {                 // destro: edita ascissa/ordinata
      if (hit >= 0) openPointEditor(ev, def, control, hit, getDur(),
                                    () => { redraw(); if (onchange) onchange(); });
      return;
    }
    moved = false;
    wasExisting = hit >= 0;
    if (hit >= 0) { dragging = hit; }
    else {
      const p = toPoint(ev);
      control.value.push(p);
      control.value.sort((a, b) => a[0] - b[0]);
      dragging = control.value.indexOf(p);
    }
    canvas.setPointerCapture(ev.pointerId);
    redraw();
  });
  canvas.addEventListener("pointermove", (ev) => {
    if (dragging < 0) return;
    const p = toPoint(ev);
    moved = true;
    control.value[dragging] = p;
    control.value.sort((a, b) => a[0] - b[0]);
    dragging = control.value.indexOf(p);   // il punto puo' aver scavalcato
    redraw();
  });
  canvas.addEventListener("pointerup", () => {
    if (dragging < 0) return;
    // Click secco su un punto esistente = rimozione (minimo 2 punti).
    if (!moved && wasExisting && control.value.length > 2)
      control.value.splice(dragging, 1);
    dragging = -1;
    redraw();
    if (onchange) onchange();
  });
  canvas.addEventListener("contextmenu", (ev) => ev.preventDefault());
  redraw();
}

/* Popup per editare a mano ascissa (tempo) e ordinata (valore) di un
   punto: tasto destro sul pallino. */
function openPointEditor(ev, def, control, index, dur, apply) {
  document.getElementById("ptedit")?.remove();
  const [t0, v0] = control.value[index];
  const box = document.createElement("div");
  box.id = "ptedit";
  box.style.left = Math.min(ev.clientX, window.innerWidth - 190) + "px";
  box.style.top = (ev.clientY + 8) + "px";
  const mk = (label, val) => {
    const l = document.createElement("label");
    l.textContent = label;
    const i = document.createElement("input");
    i.type = "number"; i.value = val; i.step = "any";
    l.append(i);
    box.append(l);
    return i;
  };
  const it = mk("t (s)", t0);
  const iv = mk("valore", v0);
  const ok = document.createElement("button");
  ok.textContent = "ok";
  const close = () => box.remove();
  const commit = () => {
    const t = Math.max(0, Math.min(dur, parseFloat(it.value)));
    const v = parseFloat(iv.value);
    if (!isNaN(t) && !isNaN(v)) {
      control.value[index] = [Number(t.toFixed(3)), Number(v.toFixed(4))];
      control.value.sort((a, b) => a[0] - b[0]);
      apply();
    }
    close();
  };
  ok.onclick = commit;
  box.addEventListener("keydown", e => {
    if (e.key === "Enter") commit();
    if (e.key === "Escape") close();
  });
  box.append(ok);
  document.body.append(box);
  it.focus(); it.select();
}

/* ---------- pattern ritmico: sintassi compatta (issue #10) ----------
   Una voce può ripetersi un numero casuale di volte (seedato nel
   motore): "0.125x3" fisso, "0.125x2-4" range, "0.125x[2,7]" scelte.
   In YAML diventa {value, repeat}; gli scalari restano numeri puri. */
function voiceToText(v) {
  if (typeof v !== "object" || v === null) return String(v);
  const rep = Array.isArray(v.repeat) ? `[${v.repeat.join(",")}]` : v.repeat;
  return `${v.value}x${rep}`;
}

function splitVoices(text) {
  // split sulle virgole fuori dalle parentesi: "0.5x[2,7]" è UNA voce
  const out = []; let depth = 0, cur = "";
  for (const ch of text) {
    if (ch === "[") depth++;
    else if (ch === "]") depth = Math.max(0, depth - 1);
    if (ch === "," && depth === 0) { out.push(cur); cur = ""; }
    else cur += ch;
  }
  out.push(cur);
  return out.map(s => s.trim()).filter(Boolean);
}

function parseVoice(token) {
  const m = token.match(/^([0-9.]+)\s*x\s*(.+)$/i);
  if (!m) {
    const n = parseFloat(token);
    return !isNaN(n) && n > 0 ? n : null;
  }
  const value = parseFloat(m[1]);
  if (isNaN(value) || value <= 0) return null;
  const spec = m[2].trim();
  if (/^\[[^\]]*\]$/.test(spec)) {          // lista di scelte [2,7]
    const choices = spec.slice(1, -1).split(",")
      .map(s => parseInt(s.trim(), 10)).filter(n => !isNaN(n) && n >= 1);
    return choices.length ? { value, repeat: choices } : null;
  }
  if (/^\d+\s*-\s*\d+$/.test(spec)) {        // range "2-4" (stringa YAML)
    const [lo, hi] = spec.split("-").map(s => parseInt(s, 10));
    return lo >= 1 && lo <= hi
      ? { value, repeat: spec.replace(/\s+/g, "") } : null;
  }
  const n = parseInt(spec, 10);              // intero fisso
  return !isNaN(n) && n >= 1 && /^\d+$/.test(spec) ? { value, repeat: n } : null;
}

/* ---------- righe parametro ---------- */
function paramRow(def, control, getDur) {
  const row = document.createElement("div");
  row.className = "param" + (control.enabled ? "" : " off");

  const chk = document.createElement("input");
  chk.type = "checkbox"; chk.checked = control.enabled;
  chk.onchange = () => { control.enabled = chk.checked; rerender(); };

  const name = document.createElement("span");
  name.className = "name"; name.textContent = def.label;
  name.title = "clicca per la spiegazione";
  name.onclick = () => showInfo(def);

  const slot = document.createElement("span");
  slot.className = "ctl";
  const val = document.createElement("span"); val.className = "value";

  // Spento: solo checkbox + nome, niente controlli che ingombrano.
  if (!control.enabled) {
    row.append(chk, name);
    row.classList.add("bare");
    return row;
  }

  const showScalar = () => {
    slot.innerHTML = ""; val.textContent = "";
    if (def.kind === "select") {
      const sel = document.createElement("select");
      for (const o of def.options) {
        const opt = document.createElement("option");
        opt.value = o; opt.textContent = o;
        if (String(o) === String(control.value)) opt.selected = true;
        sel.append(opt);
      }
      sel.onchange = () => { control.value = def.options[sel.selectedIndex]; };
      slot.append(sel);
    } else if (def.kind === "int") {
      const num = document.createElement("input");
      num.type = "number"; num.value = control.value;
      num.onchange = () => { control.value = parseInt(num.value, 10) || 0; };
      slot.append(num);
    } else if (def.kind === "numlist") {
      const txt = document.createElement("input");
      txt.type = "text";
      txt.value = (control.value || []).map(voiceToText).join(", ");
      txt.placeholder = "es. 0.25, 0.125x2-4, 0.5x[2,7]";
      txt.onchange = () => {
        control.value = splitVoices(txt.value).map(parseVoice)
                                              .filter(v => v !== null);
      };
      slot.append(txt);
    } else if (def.kind === "text" || def.kind === "list" || def.kind === "listlist") {
      const txt = document.createElement("input");
      txt.type = "text";
      txt.value = def.kind === "text" ? (control.value || "")
                : def.kind === "list" ? (control.value || []).join(", ")
                : (control.value?.[0] || []).join(", ");
      txt.placeholder = def.kind === "text" ? "" : "voci separate da virgola";
      txt.onchange = () => {
        const items = txt.value.split(",").map(s => s.trim()).filter(Boolean);
        control.value = def.kind === "text" ? txt.value.trim()
                      : def.kind === "list" ? items : [items];
      };
      slot.append(txt);
    } else {
      // Slider + campo numerico: stesso valore, scrivibile a mano.
      const rng = document.createElement("input");
      rng.type = "range"; rng.min = def.min; rng.max = def.max; rng.step = def.step;
      rng.value = Array.isArray(control.value) ? def.def : control.value;
      const num = document.createElement("input");
      num.type = "number"; num.step = def.step; num.value = rng.value;
      rng.oninput = () => { control.value = parseFloat(rng.value); num.value = rng.value; };
      num.onchange = () => {
        const v = parseFloat(num.value);
        if (isNaN(v)) { num.value = rng.value; return; }
        control.value = v; rng.value = v;   // il campo può anche sforare lo slider
      };
      slot.append(rng);
      val.append(num);
    }
  };

  if (["text", "list", "listlist", "numlist"].includes(def.kind))
    row.classList.add("wide");   // il box di testo prende tutta la riga
  row.append(chk, name, slot, val);

  // La curva si edita nel pannello inviluppi a sinistra: qui solo il
  // bottone env (presente SOLO dove il motore supporta le curve) e un
  // rimando quando la curva è attiva.
  if (def.env) {
    const envBtn = document.createElement("button");
    envBtn.className = "envbtn"; envBtn.textContent = "env";
    envBtn.title = "curva nel tempo (si edita nel pannello inviluppi)";
    const isCurve = Array.isArray(control.value);
    envBtn.classList.toggle("on", isCurve);
    envBtn.onclick = () => {
      if (Array.isArray(control.value)) {
        control.value = control.value[0][1];   // torna fisso
      } else {
        control.value = [[0, control.value], [getDur(), control.value]];
        control.enabled = true;
      }
      rerender();
    };
    name.append(" ", envBtn);
    if (isCurve) val.textContent = "curva";   // si edita nel pannello inviluppi
    else showScalar();
  } else showScalar();

  return row;
}



function setColumnFlow(grid) {
  const n = grid.children.length;
  grid.style.gridTemplateRows = `repeat(${Math.max(1, Math.ceil(n / 3))}, auto)`;
}

/* ---------- pannelli ---------- */
function renderGlobals() {
  const box = document.getElementById("global-params");
  box.innerHTML = "";
  for (const def of GLOBAL_DEFS) {
    if (!state.global[def.path]) state.global[def.path] = newControl(def);
    box.append(paramRow(def, state.global[def.path], () => 60));
  }
  const globalDig = document.getElementById("global-dig");
  globalDig.innerHTML = "";
  if (document.getElementById("chk-digall").checked) {
    const tit = document.createElement("h2");
    tit.textContent = "digger globale";
    tit.style.margin = "8px 0 4px";
    const grid = document.createElement("div");
    grid.className = "params";
    for (const def of PROVISION_DEFS) {
      if (!state.global[def.path]) state.global[def.path] = newControl(def);
      grid.append(paramRow(def, state.global[def.path], () => 60));
    }
    // provision.pool cambia le preview dei pool derivati nei layer.
    grid.addEventListener("change", () => renderLayers());
    globalDig.append(tit, grid);
  }
  setColumnFlow(box);
}

function renderLayers() {
  const main = document.getElementById("layers");
  main.innerHTML = "";
  state.layers.forEach((layer, idx) => {
    const panel = document.createElement("section");
    panel.className = "panel";
    const head = document.createElement("div");
    head.className = "layer-head";
    const id = document.createElement("input");
    id.type = "text"; id.value = layer.layer_id;
    id.onchange = () => { layer.layer_id = id.value; };
    const poolMode = document.createElement("select");
    poolMode.title = "pool: derivato (default), sottocartella auto, o path a mano";
    for (const [v, l] of [["default", "pool: derivato"], ["auto", "pool: auto"],
                          ["custom", "pool: personalizzato"]]) {
      const o = document.createElement("option");
      o.value = v; o.textContent = l;
      if (v === poolModeOf(layer.pool)) o.selected = true;
      poolMode.append(o);
    }
    const poolPath = document.createElement("input");
    poolPath.type = "text"; poolPath.placeholder = "cartella pool";
    poolPath.hidden = poolModeOf(layer.pool) !== "custom";
    poolPath.value = poolPath.hidden ? "" : layer.pool;
    const poolPreview = document.createElement("span");
    poolPreview.className = "pool-preview";
    poolPreview.title = "cartella effettiva dei file sorgente";
    const refreshPoolPreview = () => {
      poolPreview.textContent = `→ ${resolvedPoolOf(layer)}`;
    };
    poolMode.onchange = () => {
      layer.pool = poolMode.value === "default" ? ""
                 : poolMode.value === "auto" ? "auto"
                 : (poolPath.value.trim() || "audio/pool/");
      renderLayers();
    };
    poolPath.onchange = () => {
      layer.pool = poolPath.value.trim();
      refreshPoolPreview();
    };
    refreshPoolPreview();
    // Modalità grano: continua (tendency) o ritmica (bpm+pattern),
    // mutuamente esclusive nel motore.
    const isRhythm = () => layer.params["fragment.rhythm.pattern"]?.enabled
                        || layer.params["fragment.rhythm.bpm"]?.enabled;
    const mode = document.createElement("select");
    for (const [v, l] of [["tendency", "grano continuo"], ["rhythm", "modalità ritmica"]]) {
      const o = document.createElement("option");
      o.value = v; o.textContent = l;
      if ((v === "rhythm") === !!isRhythm()) o.selected = true;
      mode.append(o);
    }
    mode.onchange = () => {
      const rhythm = mode.value === "rhythm";
      // Il grano (duration/range) resta disponibile in ENTRAMBE le
      // modalità: il ritmo decide quando, il grano quanto dura.
      for (const p of ["fragment.rhythm.bpm", "fragment.rhythm.pattern"])
        layer.params[p].enabled = rhythm;
      if (!rhythm && !layer.params["fragment.duration"].enabled
          && Array.isArray(layer.params["fragment.duration"].value) === false)
        layer.params["fragment.duration"].enabled = true;
      renderLayers();
    };
    const flags = document.createElement("span");
    flags.className = "flags";
    for (const flag of ["solo", "mute"]) {
      if (!layer.params[flag]) layer.params[flag] = { enabled: false, value: true };
      const lab = document.createElement("label");
      lab.className = "toggle";
      const chk = document.createElement("input");
      chk.type = "checkbox"; chk.checked = layer.params[flag].enabled;
      chk.onchange = () => { layer.params[flag] = { enabled: chk.checked, value: true }; };
      lab.append(chk, ` ${flag}`);
      flags.append(lab);
    }
    const del = document.createElement("button");
    del.className = "danger"; del.textContent = "×";
    del.onclick = () => { state.layers.splice(idx, 1); renderLayers(); };
    head.append(id, poolMode, poolPath, poolPreview, mode, flags, del);
    panel.append(head);
    const grid = document.createElement("div");
    grid.className = "params";
    const getDur = () => {
      const d = layer.params["duration"];
      return (d.enabled && !Array.isArray(d.value)) ? d.value : 20;
    };
    const grainMode = isRhythm() ? "rhythm" : "tendency";
    for (const def of LAYER_DEFS) {
      if (!layer.params[def.path]) layer.params[def.path] = newControl(def);
      if (def.mode && def.mode !== grainMode) continue;
      grid.append(paramRow(def, layer.params[def.path], getDur));
    }
    panel.append(grid);
    // Sezione digger per-layer: solo con "download (dig)" attivo e
    // digger globale spento (il globale la sostituisce).
    if (document.getElementById("chk-dig").checked && !document.getElementById("chk-digall").checked) {
      const digTitle = document.createElement("h2");
      digTitle.textContent = "digger";
      digTitle.style.margin = "1rem 0 .6rem";
      const digGrid = document.createElement("div");
      digGrid.className = "params";
      for (const def of PROVISION_DEFS) {
        // La base dei pool ha senso solo nel blocco globale: sul layer
        // la cartella si sceglie col controllo pool in testata.
        if (def.path === "provision.pool") continue;
        if (!layer.params[def.path]) layer.params[def.path] = newControl(def);
        digGrid.append(paramRow(def, layer.params[def.path], getDur));
      }
      panel.append(digTitle, digGrid);
    }
    main.append(panel);
  });
}

function rerender() { renderGlobals(); renderLayers(); renderEnvPanel(); }

/* ---------- pannello inviluppi (sinistra) ----------
   Ogni curva attiva è una corsia col suo nome sopra: si edita qui,
   il pannello principale resta pulito. */
const envPanel = { open: false };

function envPanelWidth() { return parseInt(localStorage.getItem("envW") || 380, 10); }

function envPanelOpen() {
  envPanel.open = true;
  applyPanelsLayout();
  renderEnvPanel();
}

function renderEnvPanel() {
  if (!envPanel.open) return;
  const box = document.getElementById("env-scroll");
  box.innerHTML = "";
  const lanes = [];
  for (const def of GLOBAL_DEFS) {
    const c = state.global[def.path];
    if (def.env && c?.enabled && Array.isArray(c.value))
      lanes.push({ name: `globale — ${def.label}`, def, control: c, getDur: () => 60 });
  }
  for (const layer of state.layers) {
    const du = layer.params["duration"];
    const dur = du?.enabled && !Array.isArray(du.value) ? du.value : 20;
    for (const def of LAYER_DEFS) {
      const c = layer.params[def.path];
      if (def.env && c?.enabled && Array.isArray(c.value))
        lanes.push({ name: `${layer.layer_id} — ${def.label}`,
                     def, control: c, getDur: () => dur });
    }
  }
  for (const lane of lanes) {
    const head = document.createElement("div");
    head.className = "lane-head";
    const title = document.createElement("span");
    title.className = "lane-name";
    title.textContent = lane.name;
    title.onclick = () => showInfo(lane.def);

    // Range di lavoro dell'asse Y, scelto dall'utente (default: bounds
    // del parametro). Vive sul controllo, così sopravvive ai re-render.
    const c = lane.control;
    if (c.viewMin === undefined) c.viewMin = lane.def.min;
    if (c.viewMax === undefined) c.viewMax = lane.def.max;
    const viewDef = { ...lane.def, min: c.viewMin, max: c.viewMax };

    const range = document.createElement("span");
    range.className = "lane-range";
    const mkBound = (key, title_) => {
      const inp = document.createElement("input");
      inp.type = "number"; inp.value = c[key]; inp.title = title_;
      inp.step = lane.def.step ?? 1;
      inp.onchange = () => {
        const v = parseFloat(inp.value);
        if (isNaN(v)) { inp.value = c[key]; return; }
        // Non solo scala visiva: i punti della curva vengono RIMAPPATI
        // nel nuovo intervallo (stesse posizioni, nuovi valori reali).
        const oldMin = c.viewMin, oldMax = c.viewMax;
        c[key] = v;
        if (c.viewMin >= c.viewMax) c.viewMax = c.viewMin + (lane.def.step ?? 1);
        const span = oldMax - oldMin || 1;
        c.value = c.value.map(([t, val]) => {
          const frac = (val - oldMin) / span;
          const nuovo = c.viewMin + frac * (c.viewMax - c.viewMin);
          return [t, Number(nuovo.toFixed(4))];
        });
        rerender();
      };
      return inp;
    };
    const lo = mkBound("viewMin", "minimo dell'asse");
    const hi = mkBound("viewMax", "massimo dell'asse");
    const sep = document.createElement("span");
    sep.textContent = "…";
    range.append(lo, sep, hi);

    const reset = document.createElement("button");
    reset.className = "envbtn"; reset.textContent = "reset";
    reset.title = "curva piatta al default, asse ai bounds del parametro";
    reset.onclick = () => {
      c.viewMin = lane.def.min; c.viewMax = lane.def.max;
      c.value = [[0, lane.def.def], [lane.getDur(), lane.def.def]];
      rerender();
    };
    const fisso = document.createElement("button");
    fisso.className = "envbtn"; fisso.textContent = "×";
    fisso.title = "chiudi la curva: torna a valore fisso (primo punto)";
    fisso.onclick = () => { lane.control.value = lane.control.value[0][1]; rerender(); };
    head.append(title, range, reset, fisso);
    const cv = document.createElement("canvas");
    cv.className = "envelope";
    box.append(head, cv);
    attachEnvelopeEditor(cv, viewDef, lane.control, lane.getDur,
                         () => { renderGlobals(); renderLayers(); });
  }
  if (!lanes.length) {
    const hint = document.createElement("p");
    hint.className = "muted-hint";
    hint.textContent = "nessuna curva: premi «env» su un parametro e apparirà qui.";
    box.append(hint);
  }
}

document.getElementById("env-close").onclick = () => {
  envPanel.open = false; applyPanelsLayout();
};
document.getElementById("btn-env").onclick = () => {
  envPanel.open ? (envPanel.open = false, applyPanelsLayout()) : envPanelOpen();
};
document.getElementById("env-divider").addEventListener("pointerdown", ev => {
  ev.preventDefault();
  const move = e => {
    localStorage.setItem("envW", Math.round(e.clientX));
    applyPanelsLayout(); renderEnvPanel();
  };
  const up = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
});

/* ---------- pannello info ---------- */
function showInfo(def) {
  const box = document.getElementById("infobox");
  box.querySelector(".chiudi").onclick = () => { box.hidden = true; };
  box.querySelector("h3").textContent = def.label;
  box.querySelector("p").textContent = def.info || "nessuna descrizione";
  box.hidden = false;
}

/* ---------- azioni ---------- */
const status = () => {};   // niente scritte in basso: parla il terminale

async function doRender() {
  status("render in corso…");
  document.getElementById("player").hidden = true;
  document.getElementById("btn-download").hidden = true;
  const dig = document.getElementById("chk-dig").checked;
  const res = await fetch("/api/render", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ state, dig }),
  });
  const { job_id } = await res.json();
  const poll = setInterval(async () => {
    const s = await (await fetch(`/api/jobs/${job_id}`)).json();
    if (s.state === "running") { status(dig ? "download + render…" : "render…"); return; }
    clearInterval(poll);
    if (s.state === "error") { status(`errore: ${s.detail}`, true); return; }
    status("fatto");
    const url = `/api/jobs/${job_id}/audio`;
    const player = document.getElementById("player");
    player.src = url; player.hidden = false; player.play().catch(() => {});
    const dl = document.getElementById("btn-download");
    dl.href = url; dl.hidden = false;
    dawNotify(url);
  }, 500);
}

async function doExport() {
  const res = await fetch("/api/yaml", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ state }),
  });
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = "score.yaml"; a.click();
}

async function doImport(file) {
  const text = await file.text();
  const res = await fetch("/api/import", {
    method: "POST", headers: { "Content-Type": "text/yaml" }, body: text,
  });
  const imported = await res.json();
  state.global = {};
  for (const def of GLOBAL_DEFS)
    state.global[def.path] = imported.global[def.path] ?? newControl(def);
  state.layers = imported.layers.map((l) => {
    const layer = newLayer();
    // pool assente/vuoto resta derivato: nessun default fisso (issue #3).
    layer.layer_id = l.layer_id; layer.pool = l.pool ?? "";
    for (const def of ALL_LAYER_DEFS)
      layer.params[def.path] = l.params[def.path] ?? newControl(def);
    for (const [path, ctl] of Object.entries(l.params))
      if (!layer.params[path]) layer.params[path] = ctl;  // solo, mute, extra
    return layer;
  });
  renderGlobals(); renderLayers();
  status("yaml importato");
}

document.getElementById("btn-add-layer").onclick = () => {
  state.layers.push(newLayer()); renderLayers();
};
document.getElementById("chk-dig").onchange = renderLayers;
document.getElementById("chk-digall").onchange = () => {
  // Globale attivo: spegne i blocchi provision dei layer nello stato
  // (il motore comunque li ignora quando c'e' il blocco top-level).
  rerender();
};

/* ---------- tema chiaro/scuro ---------- */
const themeBtn = document.getElementById("btn-theme");
function setTheme(dark) {
  document.body.classList.toggle("dark", dark);
  themeBtn.textContent = dark ? "☾" : "☀";
  localStorage.setItem("theme", dark ? "dark" : "light");
}
themeBtn.onclick = () => setTheme(!document.body.classList.contains("dark"));
setTheme(localStorage.getItem("theme") === "dark");

/* ---------- terminale a tendina ---------- */
const termBody = document.getElementById("term-body");
let termNext = 0;
document.getElementById("term-head").onclick = () => {
  const open = termBody.hidden;
  termBody.hidden = !open;
  document.getElementById("term-arrow").textContent = open ? "▾" : "▸";
  if (open) termBody.scrollTop = termBody.scrollHeight;
};
setInterval(async () => {
  try {
    const data = await (await fetch(`/api/log?since=${termNext}`)).json();
    if (!data.lines.length) return;
    termNext = data.next;
    const atBottom = termBody.scrollHeight - termBody.scrollTop
                     - termBody.clientHeight < 30;
    for (const [ts, line] of data.lines)
      termBody.textContent += `[${ts}] ${line}\n`;
    if (atBottom || termBody.hidden) termBody.scrollTop = termBody.scrollHeight;
  } catch { /* server assente: riprova al giro dopo */ }
}, 1000);
document.getElementById("btn-render").onclick = doRender;
document.getElementById("btn-export").onclick = doExport;
document.getElementById("file-import").onchange = (ev) => {
  if (ev.target.files[0]) doImport(ev.target.files[0]);
};

/* ==================== pannello DAW (v2) ====================
   Finestra a destra, ridimensionabile: forma d'onda o spettrogramma
   del render, timeline con playhead, e le curve envelope come corsie
   di automazione (nome sopra, editing senza sporcare il pannello). */
const daw = {
  el: document.getElementById("daw"),
  open: false, view: "wave", url: null, buffer: null, spec: null,
};
const player = document.getElementById("player");

function dawWidth() { return parseInt(localStorage.getItem("dawW") || 460, 10); }

/* Layout a tre finestre: inviluppi | principale | daw. */
function applyPanelsLayout() {
  const root = document.documentElement.style;
  const dawW = daw.open ? Math.min(Math.max(dawWidth(), 280), window.innerWidth - 380) : 0;
  const envW = envPanel.open
    ? Math.min(Math.max(envPanelWidth(), 240), window.innerWidth - dawW - 380) : 0;
  daw.el.hidden = !daw.open;
  daw.el.style.width = dawW + "px";
  root.setProperty("--daw-w", dawW + "px");
  const ep = document.getElementById("envpanel");
  ep.hidden = !envPanel.open;
  ep.style.width = envW + "px";
  root.setProperty("--env-w", envW + "px");
}

function dawTotal() {
  if (daw.buffer) return daw.buffer.duration;
  let t = 20;
  for (const l of state.layers) {
    const on = l.params["onset"], du = l.params["duration"];
    const onset = on?.enabled && !Array.isArray(on.value) ? on.value : 0;
    const dur = du?.enabled && !Array.isArray(du.value) ? du.value : 20;
    t = Math.max(t, onset + dur);
  }
  return t;
}

async function dawLoad(url) {
  daw.url = url; daw.spec = null;
  const ctx = new (window.AudioContext || window.webkitAudioContext)();
  try {
    const data = await (await fetch(url)).arrayBuffer();
    daw.buffer = await ctx.decodeAudioData(data);
  } finally { ctx.close(); }
  dawDraw();
}

function dawNotify(url) {
  if (daw.open) dawLoad(url);
  else daw.url = url;   // caricato alla prossima apertura
}

/* --- disegno --- */
function themeInk() {
  const dark = document.body.classList.contains("dark");
  return { ink: dark ? "#f2f2f2" : "#000", paper: dark ? "#111" : "#fff",
           dim: dark ? "#555" : "#bbb", dark };
}

function dawDraw() {
  document.getElementById("daw-empty").hidden = !!daw.buffer;
  drawRuler(); drawWaveOrSpec();
}

function drawRuler() {
  const cv = document.getElementById("daw-ruler");
  const { ink } = themeInk();
  const W = cv.width = cv.clientWidth * 2, H = cv.height = 36;
  const g = cv.getContext("2d");
  g.clearRect(0, 0, W, H);
  const total = dawTotal();
  const step = total > 150 ? 30 : total > 60 ? 10 : total > 20 ? 5 : 1;
  g.strokeStyle = ink; g.fillStyle = ink; g.font = "16px Courier New";
  for (let t = 0; t <= total; t += step) {
    const x = (t / total) * W;
    g.beginPath(); g.moveTo(x, H); g.lineTo(x, H - 12); g.stroke();
    g.fillText(`${t}s`, x + 4, H - 16);
  }
}

function drawWaveOrSpec() {
  const cv = document.getElementById("daw-wave");
  const { ink, paper, dim } = themeInk();
  const W = cv.width = cv.clientWidth * 2, H = cv.height = 280;
  const g = cv.getContext("2d");
  g.fillStyle = paper; g.fillRect(0, 0, W, H);
  if (!daw.buffer) { return; }
  const ch = daw.buffer.getChannelData(0);
  if (daw.view === "wave") {
    g.strokeStyle = dim;
    g.beginPath(); g.moveTo(0, H / 2); g.lineTo(W, H / 2); g.stroke();
    g.fillStyle = ink;
    const hop = Math.max(1, Math.floor(ch.length / W));
    for (let x = 0; x < W; x++) {
      let lo = 1, hi = -1;
      const base = x * hop, end = Math.min(base + hop, ch.length);
      for (let i = base; i < end; i++) {
        const v = ch[i];
        if (v < lo) lo = v;
        if (v > hi) hi = v;
      }
      const y1 = (1 - hi) * H / 2, y2 = (1 - lo) * H / 2;
      g.fillRect(x, y1, 1, Math.max(1, y2 - y1));
    }
  } else {
    if (!daw.spec || daw.spec.width !== W) daw.spec = computeSpec(ch, W, H);
    g.putImageData(daw.spec, 0, 0);
  }
}

/* Spettrogramma: FFT radix-2 (512), finestra di Hann, scala dB in
   grigio — bianco e nero come tutto il resto. */
function computeSpec(samples, W, H) {
  const N = 512, half = N / 2;
  const hann = new Float32Array(N);
  for (let i = 0; i < N; i++) hann[i] = 0.5 * (1 - Math.cos(2 * Math.PI * i / N));
  const re = new Float32Array(N), im = new Float32Array(N);
  const img = new ImageData(W, H);
  const { dark } = themeInk();
  const hop = Math.max(1, Math.floor((samples.length - N) / W));
  for (let x = 0; x < W; x++) {
    const base = x * hop;
    for (let i = 0; i < N; i++) {
      re[i] = (samples[base + i] || 0) * hann[i]; im[i] = 0;
    }
    fft(re, im);
    for (let y = 0; y < H; y++) {
      // asse log: le basse frequenze respirano come in una DAW
      const frac = 1 - y / H;
      const bin = Math.min(half - 1, Math.floor(Math.pow(half, frac)));
      const mag = Math.hypot(re[bin], im[bin]);
      const db = 20 * Math.log10(mag + 1e-9);
      let v = Math.max(0, Math.min(1, (db + 90) / 90));
      if (!dark) v = 1 - v;               // chiaro: energia = scuro
      const p = (y * W + x) * 4, c = Math.round(v * 255);
      img.data[p] = img.data[p + 1] = img.data[p + 2] = c;
      img.data[p + 3] = 255;
    }
  }
  return img;
}

function fft(re, im) {
  const n = re.length;
  for (let i = 1, j = 0; i < n; i++) {          // bit reversal
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) { [re[i], re[j]] = [re[j], re[i]]; [im[i], im[j]] = [im[j], im[i]]; }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const ang = -2 * Math.PI / len;
    const wr = Math.cos(ang), wi = Math.sin(ang);
    for (let i = 0; i < n; i += len) {
      let cr = 1, ci = 0;
      for (let k = 0; k < len / 2; k++) {
        const ur = re[i + k], ui = im[i + k];
        const vr = re[i + k + len / 2] * cr - im[i + k + len / 2] * ci;
        const vi = re[i + k + len / 2] * ci + im[i + k + len / 2] * cr;
        re[i + k] = ur + vr; im[i + k] = ui + vi;
        re[i + k + len / 2] = ur - vr; im[i + k + len / 2] = ui - vi;
        const nr = cr * wr - ci * wi; ci = cr * wi + ci * wr; cr = nr;
      }
    }
  }
}

/* --- trasporto e playhead --- */
function fmtTime(s) {
  return `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, "0")}`;
}
setInterval(() => {
  if (!daw.open || !daw.buffer) return;
  const frac = player.duration ? player.currentTime / player.duration : 0;
  const track = document.getElementById("daw-track");
  document.getElementById("daw-playhead").style.left =
    (frac * track.clientWidth) + "px";
  document.getElementById("daw-time").textContent = fmtTime(player.currentTime || 0);
  document.getElementById("daw-play").textContent = player.paused ? "▶" : "❚❚";
}, 100);

document.getElementById("daw-play").onclick = () =>
  player.paused ? player.play() : player.pause();
document.getElementById("daw-wave").addEventListener("click", ev => {
  if (!daw.buffer || !player.duration) return;
  const r = ev.currentTarget.getBoundingClientRect();
  player.currentTime = ((ev.clientX - r.left) / r.width) * player.duration;
});
document.getElementById("daw-view").onclick = () => {
  daw.view = daw.view === "wave" ? "spec" : "wave";
  document.getElementById("daw-view").textContent =
    daw.view === "wave" ? "onda" : "spettro";
  drawWaveOrSpec();
};

/* --- apertura, chiusura, resize --- */
document.getElementById("btn-daw").onclick = () => {
  daw.open = true; applyPanelsLayout();
  if (daw.url && !daw.buffer) dawLoad(daw.url); else dawDraw();
};
document.getElementById("daw-close").onclick = () => {
  daw.open = false; applyPanelsLayout();
};
document.getElementById("daw-divider").addEventListener("pointerdown", ev => {
  ev.preventDefault();
  const move = e => {
    localStorage.setItem("dawW", Math.round(window.innerWidth - e.clientX));
    applyPanelsLayout(); dawDraw();
  };
  const up = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
});
window.addEventListener("resize", () => { if (daw.open) { applyPanelsLayout(); dawDraw(); } });
themeBtn.addEventListener("click", () => { if (daw.open) { daw.spec = null; dawDraw(); } });

async function boot() {
  await loadParamDefs();
  state.layers.push(newLayer());
  renderGlobals();
  renderLayers();
  applyPanelsLayout();
}
boot();
