const $ = (id) => document.getElementById(id);
let current = null, data = {}, clean = "{}", currentTab = "requirements", running = false;

// Shape of requirements.yaml: a string is a field kind, [x] is a list of x, {...} is a group of fields.
const TYPES = ["Class", "ObjectProperty", "DatatypeProperty", "NamedIndividual"];
const SCHEMA = {
  metadata: { id: "text", status: "text" },
  scenario: { title: "text", description: "long", examples: ["long"] },
  glossary: [{ term: "text", type: "owltype", definition: "long", align_to: "text", rules: { domain: "text", range: "text", subclass_of: "text", subproperty_of: "text", member_of: "text" } }],
  abox: [{ individual: "text", type: "text", properties: [{ property: "text", value: "text" }] }],
  competency_questions: [{ id: "text", question: "long", expected_result: "rows", query: "code", refactored_query: "code" }],
};

// Steps of each phase. `writes` uses {it} for the iteration name; `tab` steps only point to another tab.
const TABS = ["requirements", "first", "refactoring", "merge"];
const STATUSES = ["draft", "tested", "aligned", "merged"];
const DONE = { first: "tested", refactoring: "aligned", merge: "merged" };  // status reached when the phase passes
const STEPS = {
  first: [
    { id: "tbox", cmd: "tbox", title: "Generate TBox", does: "Builds the OWL TBox from the glossary.", writes: "iterations/{it}/tbox.ttl" },
    { id: "draft-abox", cmd: "draft-abox", title: "Draft ABox (optional, LLM)",
      does: "Drafts example individuals from the scenario and replaces the ABox section of the requirements. Check them under Requirements before the next step.",
      writes: "iterations/{it}/requirements.yaml" },
    { id: "abox", cmd: "abox", title: "Generate ABox", does: "Builds the RDF ABox from the ABox section of the requirements.", writes: "iterations/{it}/abox.ttl" },
    { id: "diagram", cmd: "diagram", title: "Draw diagrams", does: "Draws the TBox and, once it exists, the ABox, in Graffoo. Run it again after changing either.",
      writes: "iterations/{it}/tbox.graphml, abox.graphml, with .png, .svg and .pdf exports" },
    { id: "test", cmd: "test", title: "Test", does: "Runs the model, data, consistency and query tests. If all pass, the status becomes tested.",
      writes: "iterations/{it}/results.json" },
  ],
  refactoring: [
    { id: "align-to", tab: "requirements", title: "Choose vocabulary terms",
      does: "Under Requirements, set “align to” on each glossary term that a term of an existing vocabulary replaces (e.g. dcterms:rights)." },
    { id: "align", cmd: "align", title: "Align to vocabularies", does: "Rewrites the TBox, the ABox and the queries with the chosen vocabulary terms.",
      writes: "refactoring/{it}/tbox.ttl, abox.ttl; refactored queries in requirements.yaml" },
    { id: "diagram-refactored", cmd: "diagram", refactored: true, title: "Draw refactored diagrams", does: "Draws the refactored TBox and ABox, in Graffoo.",
      writes: "refactoring/{it}/tbox.graphml, abox.graphml, with .png, .svg and .pdf exports" },
    { id: "test-refactored", cmd: "test", refactored: true, title: "Test refactored version",
      does: "Runs the tests on the refactored TBox and ABox with the refactored queries. If all pass, the status becomes aligned.",
      writes: "refactoring/{it}/results.json" },
  ],
  merge: [
    { id: "merge", cmd: "merge", title: "Merge into current model",
      does: "Adds the refactored TBox to the current model and re-tests every merged iteration with it. Only if all pass are the project files updated and the status set to merged.",
      writes: "project/tbox.ttl, abox.ttl, results.json" },
  ],
  project: [
    { id: "retest", cmd: "merge", project: true, title: "Re-test current model", does: "Rebuilds the current model from the merged iterations and re-tests each of them.",
      writes: "project/results.json" },
    { id: "check", cmd: "check", project: true, title: "Check consistency", does: "Checks the current TBox and ABox for consistency with HermiT (OWL 2 DL)." },
    { id: "docs", cmd: "docs", project: true, title: "Write documentation",
      does: "Builds HTML documentation of the current TBox by uploading project/tbox.ttl to the LODE 2.0 web service (lode.opencitations.net).",
      writes: "project/docs/" },
    { id: "milestones", cmd: "restore", project: true, title: "List milestones",
      does: "Lists the saved states of the project. Restore one from the command line with: samosa restore <name>." },
  ],
};
const outputs = new Map();  // "<iteration or project>/<step id>" -> last run in this session

const el = (tag, props, ...kids) => { const e = Object.assign(document.createElement(tag), props); e.append(...kids); return e; };
const label = (key) => String(key).replace(/_/g, " ");
const announce = (text) => { $("announce").textContent = ""; setTimeout(() => ($("announce").textContent = text), 50); };
// Empty value with the full shape of a schema node, so new items are saved with every key, in template order.
const blank = (kind) => typeof kind === "string" ? "" : Array.isArray(kind) ? [] : Object.fromEntries(Object.entries(kind).map(([k, v]) => [k, blank(v)]));
const dirty = () => {
  const unsaved = JSON.stringify(data) !== clean;
  $("status").textContent = unsaved ? "Unsaved changes" : "";
  $("note-requirements").textContent = unsaved ? "unsaved" : "";
};

// One input bound to obj[key]. obj[key] changes only when the user edits the input.
function field(obj, key, kind, text = label(key)) {
  const v = obj[key] ?? "";
  let input;
  if (kind === "owltype") input = el("select", {}, ...[...new Set(["", ...TYPES, v])].map((t) => el("option", { textContent: t })));
  else if (kind === "text") input = el("input");
  else input = el("textarea", { rows: kind === "code" ? 6 : 2, className: kind, spellcheck: kind === "long" });
  if (kind === "rows") input.placeholder = "one row per line, cells separated by commas";
  input.value = kind === "rows" && Array.isArray(v) ? v.map((r) => (Array.isArray(r) ? r.join(", ") : r)).join("\n") : v;
  input.oninput = () => {
    // ponytail: rows are saved as "a, b" strings, so a cell that itself contains a comma cannot be typed here. Edit the YAML for that.
    obj[key] = kind === "rows" ? input.value.split("\n").map((s) => s.trim()).filter(Boolean) : input.value;
    dirty();
  };
  return el("label", {}, el("span", { textContent: text }), input);
}

function fields(obj, schema) {
  return Object.entries(schema).map(([key, kind]) => {
    if (typeof kind === "string") return field(obj, key, kind);
    if (Array.isArray(kind)) return list(obj, key, kind[0]);
    obj[key] ??= {};
    return el("fieldset", {}, el("legend", { textContent: label(key) }), ...fields(obj[key], kind));
  });
}

function list(obj, key, kind) {
  if (!Array.isArray(obj[key])) obj[key] = obj[key] ? [obj[key]] : [];
  const arr = obj[key], box = el("div", { className: "list" });
  const scalar = typeof kind === "string";
  const flat = !scalar && Object.values(kind).every((k) => k === "text");  // short items (property/value) stay on one line
  const draw = (openAt) => box.replaceChildren(...arr.map((_, i) => {
    const remove = el("button", { type: "button", textContent: "Remove", onclick: () => { arr.splice(i, 1); draw(); dirty(); } });
    if (scalar) return el("div", { className: "row" }, field(arr, i, kind, `${label(key)} ${i + 1}`), remove);
    const value = (arr[i] ??= {});
    if (flat) return el("div", { className: "row" }, ...fields(value, kind), remove);
    const summary = el("summary");
    const title = () => (summary.textContent = Object.keys(kind).slice(0, 2).map((k) => value[k]).filter(Boolean).join(" · ") || "(empty)");
    title();
    return el("details", { open: i === openAt, oninput: title }, summary, el("div", { className: "body" }, ...fields(value, kind), remove));
  }), el("button", { type: "button", textContent: `+ Add ${label(key)}`, onclick: () => { arr.push(blank(kind)); draw(arr.length - 1); dirty(); } }));
  draw();
  return el("fieldset", {}, el("legend", { textContent: label(key) }), box);
}

// ---- Steps ----------------------------------------------------------------

const scopeOf = (step) => (step.project ? "project" : current);

function stepCard(step) {
  const body = [el("h4", { textContent: step.title }), el("p", { textContent: step.does })];
  if (step.writes) body.push(el("p", { className: "small muted" }, "Writes ", el("code", { textContent: step.writes.replaceAll("{it}", current) })));
  const action = step.tab
    ? el("button", { type: "button", onclick: () => showTab(step.tab, true) }, "Open Requirements")
    : el("button", { type: "button", className: "run", onclick: () => run(step) }, "Run",
         el("span", { className: "visually-hidden", textContent: ` ${step.title}` }));
  const result = el("div", { className: "step-result", id: `result-${step.id}` });
  if (!step.tab) paint(step, result);
  return el("li", { className: "step" }, el("div", { className: "step-body" }, ...body), action, result);
}

function paint(step, box = $(`result-${step.id}`)) {
  const o = outputs.get(`${scopeOf(step)}/${step.id}`);
  if (!box) return;
  if (!o) return box.replaceChildren(el("p", { className: "small muted", textContent: "Not run in this session." }));
  if (o.running) return box.replaceChildren(el("p", { className: "small", textContent: "Running…" }));
  box.replaceChildren(
    el("p", { className: "small" }, el("span", { className: `badge ${o.ok ? "pass" : "fail"}`, textContent: o.ok ? "Done" : "Failed" }), ` at ${o.time}`),
    el("pre", { className: o.ok ? "ok" : "fail", tabIndex: 0, textContent: o.text }));
  box.lastChild.setAttribute("aria-label", `Output of ${step.title}`);
}

function setRunning(on) {
  running = on;
  $("main").setAttribute("aria-busy", on);
  document.querySelectorAll("button.run, #save, #new-form button").forEach((b) => b.setAttribute("aria-disabled", on));
}

async function command(cmd, params) {
  const r = await fetch(`/${cmd}?` + new URLSearchParams(params), { method: "POST" });
  const body = await r.json();
  return r.ok ? { ok: body.ok, text: body.output || "(no output)" } : { ok: false, text: JSON.stringify(body.detail) };
}

async function run(step) {
  if (running) return;
  const key = `${scopeOf(step)}/${step.id}`, scope = scopeOf(step);
  const params = step.project ? {} : { iteration: current };
  if (step.refactored) params.refactored = true;
  setRunning(true);
  outputs.set(key, { running: true });
  paint(step);
  announce(`${step.title}: running`);
  let o;
  try {
    o = (await save()) ? await command(step.cmd, params) : { ok: false, text: "The requirements could not be saved: see the Requirements tab." };
  } catch (e) {
    o = { ok: false, text: String(e) };
  }
  outputs.set(key, { ...o, time: new Date().toLocaleTimeString() });
  setRunning(false);
  if (scope === scopeOf(step)) paint(step);  // still showing the same iteration
  announce(`${step.title}: ${o.ok ? "done" : "failed"}`);
  if (current) await select(current);  // draft-abox and align rewrite requirements.yaml; status may have changed
  refreshDocs();
  refreshResults();
}

// ---- Views ----------------------------------------------------------------

async function listIterations() {
  const names = await (await fetch("/iterations")).json();
  $("iterations").replaceChildren(...(names.length
    ? names.map((n) => {
        const b = el("button", { type: "button", textContent: n, onclick: () => go(n) });
        if (n === current) b.setAttribute("aria-current", "page");
        return el("li", {}, b);
      })
    : [el("li", {}, el("em", { textContent: "none yet" }))]));
  $("project-link").toggleAttribute("aria-current", false);
  if (!current && !$("project-view").hidden) $("project-link").setAttribute("aria-current", "page");
  return names;
}

function showTab(name, focus) {
  currentTab = name;
  for (const t of TABS) {
    const on = t === name;
    $(`tab-${t}`).setAttribute("aria-selected", on);
    $(`tab-${t}`).tabIndex = on ? 0 : -1;
    $(`panel-${t}`).hidden = !on;
  }
  if (focus) $(`tab-${name}`).focus();
  fitVisible();
  history.replaceState(null, "", `#${encodeURIComponent(current)}/${name}`);
}

async function select(name, tab) {
  const same = name === current;
  current = name;
  $("welcome").hidden = $("project-view").hidden = true;
  $("iteration-view").hidden = false;
  $("view-title").textContent = name;
  $("raw").href = `/iterations/${name}/requirements.yaml`;
  const r = await fetch(`/iterations/${name}/requirements`, { cache: "no-store" });
  const fresh = (r.ok && (await r.json())) || {};
  const nodes = fields(fresh, SCHEMA);  // also fills missing sections in `fresh`
  if (!same || JSON.stringify(fresh) !== JSON.stringify(data)) {  // unchanged on disk: keep the form, and which items are open
    data = fresh;
    $("form").replaceChildren(...nodes);
  }
  clean = JSON.stringify(data);
  dirty();
  if (!same) for (const phase of ["first", "refactoring", "merge"]) $(`steps-${phase}`).replaceChildren(...STEPS[phase].map(stepCard));
  const status = data.metadata?.status || "draft";
  const rank = Math.max(0, STATUSES.indexOf(status));
  $("view-status").textContent = `Status: ${status}`;
  for (const [phase, needed] of Object.entries(DONE)) $(`note-${phase}`).textContent = rank >= STATUSES.indexOf(needed) ? "done" : "";
  showTab(tab || (same ? currentTab : "requirements"));
  refreshDiagrams();
  refreshResults();
  return listIterations();
}

function showProject() {
  current = null; data = {}; clean = "{}";
  $("welcome").hidden = $("iteration-view").hidden = true;
  $("project-view").hidden = false;
  history.replaceState(null, "", "#project");
  refreshResults();
  return listIterations();
}

// Navigation from the sidebar: save first (no edit is lost), then move focus to the new view's heading.
async function go(target) {
  if (running) return;
  if (!(await save())) return showTab("requirements", true);
  if (target === "project") { await showProject(); $("project-title").focus(); }
  else { await select(target, "requirements"); $("view-title").focus(); }
}

$("tabs").onclick = (e) => { const t = e.target.closest("[role=tab]"); if (t) showTab(t.id.slice(4)); };
$("tabs").onkeydown = (e) => {
  const i = TABS.indexOf(currentTab);
  const j = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: TABS.length - 1 }[e.key];
  if (j === undefined) return;
  e.preventDefault();
  showTab(TABS[(j + TABS.length) % TABS.length], true);
};

// ---- Diagrams -------------------------------------------------------------

const refreshDocs = async () => ($("docs-link").hidden = !(await exists("/project/docs/index.html")));
const exists = async (url) => (await fetch(url, { method: "HEAD", cache: "no-store" })).ok;

// Graffoo diagrams, read from the .graphml files and drawn with Cytoscape. Nodes can only be dragged: "Save layout"
// writes their positions back to the .graphml file, and Python writes its exports again.
const Y = "http://www.yworks.com/xml/graphml", G = "http://graphml.graphdrawing.org/xmlns";
const SHAPES = { roundrectangle: "round-rectangle", parallelogram: "rhomboid", ellipse: "ellipse", rectangle: "rectangle" };
const ARROWS = { delta: ["triangle", "filled"], standard: ["triangle", "filled"], white_delta: ["triangle", "hollow"],
                 circle: ["circle", "filled"], transparent_circle: ["circle", "hollow"], none: ["none", "filled"] };
const PANELS = { tbox: ["iterations", "tbox"], abox: ["iterations", "abox"], refactored: ["refactoring", "tbox"], "refactored-abox": ["refactoring", "abox"] };
const EXPORTS = [["graphml", "GraphML (yEd)"], ["png", "PNG"], ["svg", "SVG"], ["pdf", "PDF"]];
const FONT = { "font-family": "Helvetica, Arial, sans-serif", "font-size": 16 };
const STYLE = [
  { selector: "node", style: { ...FONT, shape: "data(shape)", width: "data(w)", height: "data(h)", label: "data(label)", color: "#000",
      "background-color": "data(fill)", "background-opacity": "data(opacity)", "border-color": "data(border)", "border-width": "data(bw)",
      "text-valign": "center", "text-halign": "center" } },
  { selector: "node[?outside]", style: { "text-halign": "right", "text-margin-x": 4 } },  // individuals: label east of the circle, as in Graffoo
  { selector: "edge", style: { ...FONT, "curve-style": "bezier", width: 1, label: "data(label)", color: "data(color)", "line-color": "data(color)",
      "line-style": "data(line)", "text-background-color": "#fff", "text-background-opacity": 0.8,
      "source-arrow-shape": "data(tail)", "source-arrow-fill": "data(tailFill)", "source-arrow-color": "data(color)",
      "target-arrow-shape": "data(head)", "target-arrow-fill": "data(headFill)", "target-arrow-color": "data(color)" } },
];
const diagrams = {};  // panel id -> { name, xml, cy, dirty, status }

// Cytoscape elements of a Graffoo GraphML file: shapes, colours, arrows and positions as written by `samosa diagram`.
function graffoo(xml) {
  const doc = new DOMParser().parseFromString(xml, "application/xml");
  const y = (e, tag) => e.getElementsByTagNameNS(Y, tag)[0];
  const nodes = [...doc.getElementsByTagNameNS(G, "node")].map((n) => {
    const geo = y(n, "Geometry"), fill = y(n, "Fill"), border = y(n, "BorderStyle"), label = y(n, "NodeLabel");
    const w = +geo.getAttribute("width"), h = +geo.getAttribute("height");
    return { data: { id: n.getAttribute("id"), label: label.textContent.trim(), w, h, shape: SHAPES[y(n, "Shape").getAttribute("type")] ?? "rectangle",
                     fill: fill.getAttribute("color") ?? "#fff", opacity: fill.hasAttribute("color") ? 1 : 0,
                     border: border.getAttribute("color") ?? "#000", bw: border.hasAttribute("color") ? +border.getAttribute("width") : 0,
                     outside: label.getAttribute("modelName") === "eight_pos" },
             position: { x: +geo.getAttribute("x") + w / 2, y: +geo.getAttribute("y") + h / 2 } };  // GraphML: top-left, Cytoscape: centre
  });
  const edges = [...doc.getElementsByTagNameNS(G, "edge")].map((e) => {
    const line = y(e, "LineStyle"), arrows = y(e, "Arrows");
    const [tail, tailFill] = ARROWS[arrows.getAttribute("source")] ?? ARROWS.none;
    const [head, headFill] = ARROWS[arrows.getAttribute("target")] ?? ARROWS.none;
    return { data: { id: e.getAttribute("id"), source: e.getAttribute("source"), target: e.getAttribute("target"),
                     label: y(e, "EdgeLabel")?.textContent.trim() ?? "", color: line.getAttribute("color"),
                     line: line.getAttribute("type") === "dashed" ? "dashed" : "solid", tail, tailFill, head, headFill } };
  });
  return [...nodes, ...edges];
}

// Fit each diagram to its box the first time the box is visible (a hidden tab has no size).
function fitVisible() {
  for (const d of Object.values(diagrams))
    if (d.cy && !d.fitted && d.cy.container().offsetParent) { d.cy.resize(); d.cy.fit(undefined, 20); d.fitted = true; }
}

// Caption controls of a diagram: save layout, fit, status and links to the saved files.
async function controls(id) {
  const d = diagrams[id], [dir, stem] = PANELS[id], base = `/${dir}/${d.name}/${stem}`;
  const items = [];
  if (d.cy) {
    const save = el("button", { type: "button", className: "primary", textContent: "Save layout", onclick: () => saveLayout(id) });
    save.setAttribute("aria-disabled", !d.dirty);
    items.push(save, el("button", { type: "button", textContent: "Fit", onclick: () => d.cy.fit(undefined, 20) }));
  }
  if (d.status) items.push(el("span", { textContent: d.status }));
  for (const [ext, text] of EXPORTS)
    if (d.xml && await exists(`${base}.${ext}`)) items.push(el("a", { href: `${base}.${ext}?${Date.now()}`, target: "_blank", textContent: text }));
  if (diagrams[id] === d) $(`links-${id}`).replaceChildren(...items);
}

async function refreshDiagrams() {
  const name = current;
  for (const [id, [dir, stem]] of Object.entries(PANELS)) {
    const r = await fetch(`/${dir}/${name}/${stem}.graphml`, { cache: "no-store" });
    const xml = r.ok ? await r.text() : null;
    if (name !== current) return;  // another iteration was selected meanwhile
    const old = diagrams[id];
    if (old && old.name === name && old.xml === xml) continue;  // unchanged on disk: keep it, with any unsaved moves
    old?.cy?.destroy();
    const d = (diagrams[id] = { name, xml, dirty: false, status: "" });
    const box = $(`diagram-${id}`);
    box.classList.add("message");
    if (!xml) {
      const step = dir === "refactoring" ? "Draw refactored diagrams" : "Draw diagrams";
      box.textContent = `Not drawn yet: run “${step}”${stem === "abox" ? " once the ABox exists" : ""}.`;
    } else if (!window.cytoscape) {
      box.textContent = "Cytoscape could not be loaded (offline?). Open the PNG or SVG instead.";
    } else {
      box.textContent = "";
      box.classList.remove("message");
      try {
        d.cy = cytoscape({ container: box, elements: graffoo(xml), style: STYLE, layout: { name: "preset" },
                           boxSelectionEnabled: false, autounselectify: true });
        d.cy.on("dragfree", "node", () => { d.dirty = true; d.status = "Unsaved layout"; controls(id); });
      } catch (e) {
        box.classList.add("message");
        box.textContent = `Cannot draw diagram: ${e.message ?? e}`;
      }
    }
    controls(id);
  }
  fitVisible();
}

async function saveLayout(id) {
  const d = diagrams[id], [dir, stem] = PANELS[id];
  if (!d.dirty || running) return;
  const positions = Object.fromEntries(d.cy.nodes().map((n) =>
    [n.id(), { x: n.position("x") - n.data("w") / 2, y: n.position("y") - n.data("h") / 2 }]));
  let o;
  try {
    const r = await fetch(`/iterations/${encodeURIComponent(d.name)}/diagram/${stem}?refactored=${dir === "refactoring"}`,
                          { method: "PUT", body: JSON.stringify(positions), headers: { "Content-Type": "application/json" } });
    const body = await r.json();
    o = r.ok ? body : { ok: false, output: JSON.stringify(body.detail) };
  } catch (e) {
    o = { ok: false, output: String(e) };
  }
  if (o.ok) {
    d.dirty = false;
    d.xml = await (await fetch(`/${dir}/${d.name}/${stem}.graphml`, { cache: "no-store" })).text();  // so the next refresh keeps this view
  }
  d.status = o.ok ? "Layout saved" : `Not saved: ${o.output}`;
  announce(d.status);
  controls(id);
}

// ---- Test results -----------------------------------------------------------

const PHASES = [  // [phase, heading, tests shown for it, tab]
  ["first-version", "First version", ["model", "data", "consistency", "query", "coverage"], "first"],
  ["refactored", "Refactored", ["model", "data", "consistency", "query"], "refactoring"],
  ["merge", "Merge", ["merge", "data", "consistency", "query"], "merge"],
];
const IMPLICIT = ["coverage", "merge"];  // these tests record only problems: no record means pass
const RANK = { PASS: 0, WARN: 1, FAIL: 2 };
const getJSON = async (url) => { const r = await fetch(url, { cache: "no-store" }); return r.ok ? r.json() : null; };
const when = (file) => file.timestamp.replace("T", " ");
const worstOf = (records) => records.reduce((w, r) => (RANK[r.status] > RANK[w] ? r.status : w), "PASS");
const statusBadge = (status, text = status) => el("span", { className: `badge ${status.toLowerCase()}`, textContent: text });
const message = (r) => el("li", {}, statusBadge(r.status), " ", r.message,
  r.explanation ? el("ul", {}, ...r.explanation.map((t) => el("li", { textContent: t }))) : "");

// One clickable badge for a list of records: the worst status, and how many records have it.
function badge(records, title) {
  const worst = worstOf(records);
  const n = records.filter((r) => r.status === worst).length;
  const b = el("button", { type: "button", className: `badge ${worst.toLowerCase()}`, title,
                           textContent: worst === "PASS" ? "PASS" : `${worst} ${n}` });
  b.append(el("span", { className: "visually-hidden", textContent: `, ${title}` }));
  b.onclick = () => {
    document.querySelectorAll("#matrix button.badge, #current-model button.badge").forEach((x) => x.setAttribute("aria-pressed", x === b));
    $("cell-detail").hidden = false;
    $("cell-detail").replaceChildren(...(records.length ? records : [{ status: "PASS", message: "nothing to report" }]).map(message));
  };
  b.setAttribute("aria-pressed", "false");
  return b;
}

function matrixCell(file, name, test) {
  if (!file) return el("td", { className: "muted", textContent: "not run" });
  const records = file.results.filter((r) => r.case === name && r.test === test);
  if (!records.length && !IMPLICIT.includes(test)) return el("td", { className: "muted", textContent: "—" });
  return el("td", {}, badge(records, `${name}, ${test}, ${when(file)}`));
}

function cqCell(file, record) {
  if (!file) return el("td", { className: "muted", textContent: "not run" });
  if (!record) return el("td", { className: "muted", textContent: "—" });
  const lines = [...(record.missing || []).map((row) => `missing: ${row.join(", ")}`),
                 ...(record.unexpected || []).map((row) => `unexpected: ${row.join(", ")}`),
                 ...(record.error ? [`error: ${record.error}`] : [])];
  return el("td", { title: when(file) },
    el("span", { className: "nowrap" }, statusBadge(record.status), record.results == null ? "" : ` ${record.results} row(s)`),
    lines.length ? el("ul", {}, ...lines.map((t) => el("li", { textContent: t }))) : "");
}

// Results of one phase of one iteration: a table of tests with every message, then a table of CQs.
function phaseResults(file, name, phase, heading, tests) {
  if (!file) return [el("p", { className: "muted", textContent: phase === "merge" ? "Not merged yet." : "Not tested yet: run the test step." })];
  const recs = file.results.filter((r) => r.case === name);
  const queries = recs.filter((r) => r.test === "query");
  const rows = tests.map((t) => [t, recs.filter((r) => r.test === t)]);
  if (phase === "merge") rows.unshift(["model (current model)", file.results.filter((r) => r.case === "current model" && r.test === "model")]);
  const row = ([test, rs]) => {
    const none = !rs.length && !IMPLICIT.includes(test) && !test.startsWith("model (");
    const msgs = test === "query"
      ? [el("li", { textContent: `${queries.filter((r) => r.status === "PASS").length} of ${queries.length} competency questions pass (see below)` })]
      : rs.length ? rs.map(message) : [el("li", { textContent: none ? "not run" : "nothing to report" })];
    return el("tr", {}, el("th", { scope: "row", textContent: test }),
      el("td", {}, none ? statusBadge("none", "—") : statusBadge(worstOf(rs))), el("td", {}, el("ul", { className: "messages" }, ...msgs)));
  };
  return [
    el("p", { className: "small" }, `Last run ${when(file)}${file.reason ? ", queries on the OWL 2 RL closure" : ""}: `,
       statusBadge(file.passed ? "PASS" : "FAIL", file.passed ? "PASSED" : "FAILED")),
    el("div", { className: "table-wrap" }, el("table", {}, el("caption", { textContent: `Tests, ${heading.toLowerCase()}` }),
      el("thead", {}, el("tr", {}, ...["Test", "Result", "Messages"].map((h) => el("th", { scope: "col", textContent: h })))),
      el("tbody", {}, ...rows.map(row)))),
    el("div", { className: "table-wrap" }, el("table", {}, el("caption", { textContent: `Competency questions, ${heading.toLowerCase()}` }),
      el("thead", {}, el("tr", {}, ...["CQ", "Question", "Result"].map((h) => el("th", { scope: "col", textContent: h })))),
      el("tbody", {}, ...(queries.length
        ? queries.map((r) => el("tr", {}, el("th", { scope: "row", textContent: r.cq }), el("td", { className: "cq-question", textContent: r.question || "" }), cqCell(file, r)))
        : [el("tr", {}, el("td", { colSpan: 3, className: "muted", textContent: "No CQ results." }))])))),
  ];
}

async function refreshResults() {
  const names = await (await fetch("/iterations")).json();
  const merge = await getJSON("/project/results.json");
  const files = Object.fromEntries(await Promise.all(names.map(async (n) => [n, {
    "first-version": await getJSON(`/iterations/${n}/results.json`),
    refactored: await getJSON(`/refactoring/${n}/results.json`),
    merge: merge?.cases?.includes(n) ? merge : null,
  }])));

  if (current && files[current])
    for (const [phase, heading, tests, tab] of PHASES)
      $(`results-${tab}`).replaceChildren(...phaseResults(files[current][phase], current, phase, heading, tests));

  const model = merge?.results.filter((r) => r.case === "current model" && r.test === "model");
  $("current-model").replaceChildren(...(merge
    ? [`Last merge${merge.iteration ? ` (${merge.iteration})` : ""}: ${when(merge)}, `,
       statusBadge(merge.passed ? "PASS" : "FAIL", merge.passed ? "PASSED" : "FAILED"),
       ". Model test on the current model: ", badge(model, `current model, model, ${when(merge)}`)]
    : ["No merge yet."]));
  $("cell-detail").hidden = true;

  $("matrix").replaceChildren($("matrix").caption,
    el("thead", {},
      el("tr", {}, el("th", { rowSpan: 2, scope: "col", textContent: "Iteration" }),
        ...PHASES.map(([, heading, tests]) => el("th", { colSpan: tests.length, scope: "colgroup", textContent: heading }))),
      el("tr", {}, ...PHASES.flatMap(([, , tests]) => tests.map((t) => el("th", { scope: "col", textContent: t }))))),
    el("tbody", {}, ...names.map((n) => el("tr", {}, el("th", { scope: "row", textContent: n }),
      ...PHASES.flatMap(([phase, , tests]) => tests.map((t) => matrixCell(files[n][phase], n, t)))))));

  const rows = names.flatMap((n) => {
    const byCq = new Map();
    for (const [phase] of PHASES)
      for (const r of files[n][phase]?.results || [])
        if (r.case === n && r.test === "query") (byCq.get(r.cq) || byCq.set(r.cq, { question: r.question }).get(r.cq))[phase] = r;
    return [...byCq].map(([cq, recs]) => el("tr", {}, el("th", { scope: "row", textContent: n }), el("td", { textContent: cq }),
      el("td", { className: "cq-question", textContent: recs.question || "" }), ...PHASES.map(([phase]) => cqCell(files[n][phase], recs[phase]))));
  });
  $("cqs").replaceChildren(el("caption", { textContent: "Competency questions of all iterations" }),
    el("thead", {}, el("tr", {}, ...["Iteration", "CQ", "Question", ...PHASES.map(([, h]) => h)].map((h) => el("th", { scope: "col", textContent: h })))),
    el("tbody", {}, ...(rows.length ? rows : [el("tr", {}, el("td", { colSpan: 3 + PHASES.length, className: "muted", textContent: "No CQ results yet: run a test." }))])));
}

// ---- Saving and startup -----------------------------------------------------

async function save() {
  const body = JSON.stringify(data);
  if (!current || body === clean) return true;
  const r = await fetch(`/iterations/${current}/requirements`, { method: "PUT", body, headers: { "Content-Type": "application/json" } });
  if (!r.ok) {
    $("status").textContent = `Not saved: ${JSON.stringify((await r.json()).detail)}`;
    announce($("status").textContent);
    return false;
  }
  clean = body;
  dirty();
  $("status").textContent = "Saved";
  announce("Requirements saved");
  return true;
}

$("save").onclick = () => !running && save();
$("project-link").onclick = () => go("project");
$("new-form").onsubmit = async (e) => {
  e.preventDefault();
  if (running || !(await save())) return;
  const name = $("new-name").value;
  setRunning(true);
  const o = await command("new", { iteration_name: name }).catch((err) => ({ ok: false, text: String(err) }));
  setRunning(false);
  $("new-msg").hidden = o.ok;
  $("new-msg").textContent = o.ok ? "" : o.text;
  announce(o.ok ? `Iteration ${name} created` : `Could not create iteration ${name}`);
  if (!o.ok) return;
  $("new-name").value = "";
  const names = await (await fetch("/iterations")).json();
  go(names.find((n) => n.endsWith(name)) || names[names.length - 1]);
};
window.onbeforeunload = () => (JSON.stringify(data) !== clean || Object.values(diagrams).some((d) => d.dirty) ? true : undefined);

$("steps-project").replaceChildren(...STEPS.project.map(stepCard));
refreshDocs();
const [hashName, hashTab] = decodeURIComponent(location.hash.slice(1)).split("/");
if (hashName === "project") showProject();
else if (hashName) select(hashName, TABS.includes(hashTab) ? hashTab : "requirements");
else { listIterations(); refreshResults(); }
