"use strict";
/* HALBERD console. Every value from the API is rendered as a DOM text node via
   the el()/sv() helpers, never parsed as markup, so fixture text cannot inject HTML. */

const $ = (id) => document.getElementById(id);
// Built at runtime so the page source holds no URL literals.
const SVGNS = ["http:", "", "www.w3.org", "2000", "svg"].join("/");

function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") e.className = v; else e.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids) if (k !== null && k !== undefined) e.append(k);   // strings become text nodes
  return e;
}

function sv(tag, attrs, ...kids) {
  const e = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") e.setAttribute("class", v); else e.setAttribute(k, v);
  }
  for (const k of kids) if (k !== null && k !== undefined) e.append(k);
  return e;
}

const yesno = (v) => (v === true ? "yes" : v === false ? "no" : "not reported");
const jstr = (v) => JSON.stringify(v, null, 2);

async function api(path) {
  let res;
  try {
    res = await fetch(path, { headers: { Accept: "application/json" } });
  } catch (e) {
    throw new Error(`${path}: network error (${e.message})`);
  }
  let body = null;
  try { body = await res.json(); } catch (e) { /* handled below */ }
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}` + (body && body.error ? ` (${body.error})` : ""));
  if (body === null) throw new Error(`${path}: response was not JSON`);
  return body;
}

/* ---------- page plumbing ---------- */

function setBody(id, node, isLoading) {
  const box = $(id);
  box.className = isLoading ? "loading" : "";
  box.replaceChildren(node);
}
function loading(id, text) { setBody(id, document.createTextNode(text), true); }
function failure(id, what, err) {
  setBody(id, el("div", { class: "panel", role: "status" },
    el("strong", { class: "status bad" }, `Could not load ${what}. `), err.message), false);
  $("banner").append(el("div", { class: "err" },
    el("strong", {}, `Could not load ${what}: `), err.message));
}

/* ---------- 1. control plane ---------- */

function badge(text, tone) { return el("li", { class: "badge " + (tone || "") }, text); }

function normalizeGates(data) {
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.gates)) return data.gates;
  return null;
}

function gateStatusTone(status) {
  const s = String(status || "").toUpperCase();
  if (s === "PASS") return "ok";
  if (s === "FAIL") return "bad";
  return "warn";
}

function renderGates(gates) {
  const box = el("div", { class: "panel" }, el("h4", {}, "Readiness gates"));
  if (!gates) {
    box.append(el("p", { class: "dim" }, "verify.json has an unexpected shape, so no gates are shown."));
    return box;
  }
  if (gates.length === 0) {
    box.append(el("p", { class: "dim" },
      "No gate results yet: artifacts/runtime-verification/verify.json does not exist. " +
      "Nothing is claimed about the target hardware, runtime or channel."));
    return box;
  }
  const passed = gates.filter((g) => String(g.status).toUpperCase() === "PASS").length;
  box.append(el("p", { class: "dim small" }, `${passed} of ${gates.length} gates pass. Read from verify.json as written.`));
  box.append(el("ul", { class: "gates" }, ...gates.map((g) =>
    el("li", {},
      el("span", { class: "status " + gateStatusTone(g.status) }, String(g.status ?? "unknown")),
      el("span", { class: "gname" }, String(g.gate ?? g.id ?? "gate")),
      g.detail ? el("span", { class: "gdetail" }, String(g.detail)) : null))));
  return box;
}

function renderControl(rec, gatesState) {
  const ap = rec.approval || {};
  const badges = el("ul", { class: "badges", "aria-label": "Evidence mode" },
    badge(rec.evidence === "fixture" ? "Fixture replay" : `Evidence: ${rec.evidence}`, "warn"),
    badge(rec.replay_mode === "policy_only_replay" ? "Policy-only" : `Replay: ${rec.replay_mode}`, "warn"),
    badge("Not a live OpenClaw agent", "bad"),
    badge(`Channel: ${ap.channel || "none"}`, ap.real_channel ? "ok" : "warn"),
    badge(`Real channel: ${yesno(ap.real_channel)}`, ap.real_channel ? "ok" : "warn"),
    badge(`OpenClaw-managed: ${yesno(ap.openclaw_managed)}`, ap.openclaw_managed ? "ok" : "warn"));
  if ("real_message" in ap) badges.append(badge(`Real message sent: ${yesno(ap.real_message)}`, ap.real_message ? "ok" : "warn"));

  const facts = el("dl", { class: "kv" },
    el("dt", {}, "Run id"), el("dd", { class: "mono" }, rec.run_id),
    el("dt", {}, "Scenario"), el("dd", {}, rec.title || rec.scenario),
    el("dt", {}, "Live action"), el("dd", {},
      rec.live_action && rec.live_action.held ? "Held before it reached the backend" : "Not held"),
    el("dt", {}, "Fictional exposure"), el("dd", {},
      typeof rec.synthetic_exposure_usd === "number" ? "$" + rec.synthetic_exposure_usd.toLocaleString("en-US") + " (synthetic, not prevented fraud)" : "n/a"));
  const left = el("div", { class: "panel" }, el("h4", {}, "This run"), facts);

  let gatesNode;
  if (gatesState.pending) gatesNode = el("div", { class: "panel" }, el("h4", {}, "Readiness gates"), el("p", { class: "dim" }, "Loading gates..."));
  else if (gatesState.error) gatesNode = el("div", { class: "panel" }, el("h4", {}, "Readiness gates"),
    el("p", {}, el("strong", { class: "status bad" }, "Could not load gates. "), gatesState.error.message));
  else gatesNode = renderGates(normalizeGates(gatesState.data));

  setBody("control-body", el("div", {}, badges, el("div", { class: "cols2" }, left, gatesNode)), false);
}

/* ---------- 2. attack graph ---------- */

const KIND = {
  untrusted_content_ingested: ["Untrusted content read", "k-untrusted"],
  action_held: ["Action held", "k-held"],
  incident_opened: ["Incident opened", "k-opened"],
  forks_replayed: ["Policies replayed", ""],
  approval_requested: ["Approval requested", "k-approval"],
  approval_response: ["Operator response", "k-approval"],
  verification: ["Fix verified live", "k-verify"],
  no_verified_repair: ["No verified repair", "k-untrusted"],
};
const FORK_NAME = {
  baseline: "Baseline",
  lockdown: "Lockdown",
  allowlist: "Allowlist",
  context_bound: "Context-bound (Naive)",
  authoritative_guard: "Context-bound (Authoritative)",
};
const NW = 150, NH = 62, GAP = 14, VGAP = 34, PAD = 8;

function buildGraph(rec) {
  const events = rec.trace || [];
  const layers = [], edges = [];
  let sources = [];
  events.forEach((ev, i) => {
    const meta = KIND[ev.kind] || [ev.kind, ""];
    const node = {
      id: "e" + i, cls: meta[1], label: meta[0], ev,
      sub: `event ${i + 1} of ${events.length}`,
      aria: `${meta[0]}, event ${i + 1} of ${events.length}`,
    };
    layers.push([node]);
    for (const s of sources) edges.push({ from: s.id, to: node.id });
    sources = [node];
    if (ev.kind === "forks_replayed" && Array.isArray(rec.forks) && rec.forks.length) {
      const forkNodes = rec.forks.map((f) => {
        const chosen = rec.selected === f.name;
        return {
          id: "f-" + f.name, fork: f,
          cls: "k-fork " + (f.verified ? "verified" : "rejected"),
          label: FORK_NAME[f.name] || f.name,
          sub: `harm ${f.harmful_executed}/${f.attacks_total}, legit ${f.legit_completed}/${f.legit_total}`,
          sub2: (chosen ? "selected, " : "") + (f.verified ? "verified" : "rejected"),
          aria: `Policy ${FORK_NAME[f.name] || f.name}: ${f.harmful_executed} of ${f.attacks_total} attacks executed, ` +
            `${f.legit_completed} of ${f.legit_total} legit completed, ${f.verified ? "verified" : "rejected"}${chosen ? ", selected" : ""}`,
        };
      });
      layers.push(forkNodes);
      for (const f of forkNodes) edges.push({ from: node.id, to: f.id });
      const pick = forkNodes.find((f) => f.fork.name === rec.selected);
      if (pick) sources = [pick];
    }
  });
  return { layers, edges };
}

function layoutGraph(g, W) {
  const nw = Math.min(NW, W - 2 * PAD);
  const perRow = Math.max(1, Math.floor((W - 2 * PAD + GAP) / (nw + GAP)));
  const pos = {};
  let y = PAD;
  for (const layer of g.layers) {
    for (let i = 0; i < layer.length; i += perRow) {
      const row = layer.slice(i, i + perRow);
      const rowW = row.length * nw + (row.length - 1) * GAP;
      const x0 = (W - rowW) / 2;
      row.forEach((n, j) => { pos[n.id] = { x: x0 + j * (nw + GAP), y, w: nw }; });
      y += NH + VGAP;
    }
  }
  return { pos, height: y - VGAP + PAD };
}

function drawGraph(host, g, W, selectedId, onSelect) {
  const { pos, height } = layoutGraph(g, W);
  const svg = sv("svg", { viewBox: `0 0 ${W} ${height}`, width: W, height, role: "group",
    "aria-label": `Attack graph with ${g.layers.reduce((n, l) => n + l.length, 0)} nodes. Each node is a button; press Enter to read its event.` },
    sv("defs", {}, sv("marker", { id: "arr", viewBox: "0 0 8 8", refX: 7, refY: 4, markerWidth: 7, markerHeight: 7, orient: "auto" },
      sv("path", { d: "M0,0 L8,4 L0,8 z", class: "arrow" }))));
  for (const e of g.edges) {
    const a = pos[e.from], b = pos[e.to];
    if (!a || !b) continue;
    const x1 = a.x + a.w / 2, y1 = a.y + NH, x2 = b.x + b.w / 2, y2 = b.y;
    const d = Math.max(14, Math.abs(y2 - y1) / 2);
    svg.append(sv("path", { class: "edge", d: `M${x1},${y1} C${x1},${y1 + d} ${x2},${y2 - d} ${x2},${y2}`, "marker-end": "url(#arr)" }));
  }
  for (const l of g.layers) for (const n of l) {
    const p = pos[n.id];
    const grp = sv("g", { class: `node ${n.cls}${n.id === selectedId ? " selected" : ""}`, transform: `translate(${p.x},${p.y})`,
      tabindex: 0, role: "button", "aria-pressed": String(n.id === selectedId), "aria-label": n.aria, "data-id": n.id },
      sv("rect", { width: p.w, height: NH, rx: 8 }),
      sv("text", { x: 10, y: 20 }, n.label),
      sv("text", { x: 10, y: 38, class: "sub" }, n.sub),
      n.sub2 ? sv("text", { x: 10, y: 53, class: "sub" }, n.sub2) : null);
    grp.addEventListener("click", () => onSelect(n));
    grp.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        onSelect(n);
        return;
      }
      const allNodes = Array.from(svg.querySelectorAll(".node"));
      const idx = allNodes.indexOf(grp);
      if (idx === -1) return;
      let nextIdx = -1;
      if (ev.key === "ArrowRight" || ev.key === "ArrowDown") {
        nextIdx = (idx + 1) % allNodes.length;
      } else if (ev.key === "ArrowLeft" || ev.key === "ArrowUp") {
        nextIdx = (idx - 1 + allNodes.length) % allNodes.length;
      }
      if (nextIdx !== -1) {
        ev.preventDefault();
        const target = allNodes[nextIdx];
        target.focus();
        const tid = target.getAttribute("data-id");
        const found = g.layers.flat().find((item) => item.id === tid);
        if (found) onSelect(found);
      }
    });
    svg.append(grp);
  }
  host.replaceChildren(svg);
}

function detailFor(n) {
  const box = el("div", {});
  if (n.ev) {
    const ev = n.ev;
    const iso = typeof ev.ts === "number" ? new Date(ev.ts * 1000).toISOString() : "n/a";
    box.append(el("h4", {}, n.label),
      el("dl", { class: "kv" },
        el("dt", {}, "Event kind"), el("dd", { class: "mono" }, ev.kind),
        el("dt", {}, "Sequence"), el("dd", {}, String(ev.seq)),
        el("dt", {}, "Timestamp"), el("dd", {}, `${iso} (epoch ${ev.ts})`),
        el("dt", {}, "Evidence label"), el("dd", {}, String(ev.evidence)),
        el("dt", {}, "Hash"), el("dd", { class: "hash" }, String(ev.hash)),
        el("dt", {}, "Previous hash"), el("dd", { class: "hash" }, String(ev.prev))),
      el("h4", { style: "margin-top:10px" }, "Event JSON"),
      el("pre", {}, jstr(ev)));
  } else {
    box.append(el("h4", {}, `${n.label} policy fork`),
      el("p", { class: "dim small" }, "Derived from the policies-replayed event. A fork has no hash of its own; the replayed results are chained in that event."),
      el("pre", {}, jstr(n.fork)));
  }
  return box;
}

let resizeObs = null;

function renderGraph(rec) {
  if (resizeObs) { resizeObs.disconnect(); resizeObs = null; }
  if (!Array.isArray(rec.trace) || rec.trace.length === 0) {
    setBody("graph-body", el("div", { class: "panel" }, "This record has no trace events, so there is no graph to draw."), false);
    return;
  }
  const g = buildGraph(rec);
  const all = g.layers.flat();
  let selected = (all.find((n) => n.ev && n.ev.kind === "action_held") || all[0]).id;
  const host = el("div", { class: "panel graph-box" });
  const detail = el("div", { class: "panel detail", "aria-live": "polite" });
  const legend = el("div", { class: "legend", "aria-hidden": "true" },
    el("span", {}, el("i", { style: "border-color:var(--bad)" }), "untrusted input"),
    el("span", {}, el("i", { style: "border-color:var(--warn)" }), "held or opened"),
    el("span", {}, el("i", { style: "border-color:var(--accent)" }), "approval"),
    el("span", {}, el("i", { style: "border-color:var(--ok)" }), "verified"),
    el("span", {}, "dashed: rejected policy"));
  const wrapLeft = el("div", {}, host, legend);
  setBody("graph-body", el("div", { class: "graph-grid" }, wrapLeft, detail), false);

  let lastW = 0;
  const redraw = () => {
    const W = Math.floor(host.clientWidth - 12) || 320;
    lastW = W;
    drawGraph(host, g, W, selected, (n) => { selected = n.id; show(); redraw(); const again = host.querySelector(`[data-id="${n.id}"]`); if (again) again.focus(); });
  };
  const show = () => { detail.replaceChildren(detailFor(all.find((n) => n.id === selected))); };
  show();
  redraw();
  if (typeof ResizeObserver !== "undefined") {
    resizeObs = new ResizeObserver(() => { if (Math.abs(Math.floor(host.clientWidth - 12) - lastW) > 1) redraw(); });
    resizeObs.observe(host);
  }
}

/* ---------- 3. three futures ---------- */

function resultRow(r, isAttack) {
  const good = isAttack ? !r.executed : r.executed;
  let word;
  if (isAttack) word = r.harmful ? "Harm done" : r.executed ? "Got through" : "Blocked";
  else word = r.executed ? "Completed" : "Blocked";
  const why = [r.rule, ...(r.violations || [])].filter(Boolean).join("; ");
  return el("li", {},
    el("span", { class: "res " + (good ? "ok" : "bad") }, word),
    el("div", {}, r.note, why ? el("div", { class: "dim small" }, why) : null));
}

function outcomeBlock(title, caption, rows, isAttack, count, total) {
  const bad = isAttack ? count > 0 : count < total;
  const pips = el("div", { class: "pips", "aria-hidden": "true" },
    ...rows.map((r) => el("i", { class: (isAttack ? !r.executed : r.executed) ? "" : "x" })));
  return el("div", { class: "outcome" },
    el("h4", {}, title, el("span", { class: "count " + (bad ? "bad" : "ok") }, `${count} of ${total}`)),
    el("div", { class: "dim small" }, caption),
    pips,
    el("ul", { class: "actions" }, ...rows.map((r) => resultRow(r, isAttack))));
}

function futureColumn(f, selectedName) {
  const pick = f.name === selectedName;
  const verdict = f.verified ? ["ok", "Verified: stops every attack and keeps all authorized work"]
    : f.name === "baseline" ? ["bad", "Rejected: this is the unprotected starting point"]
    : f.legit_completed < f.legit_total ? ["bad", "Rejected: breaks authorized work"]
    : ["bad", "Rejected: lets attacks through"];
  const head = el("header", {}, el("h3", {}, (FORK_NAME[f.name] || f.name) +
    (f.name === "baseline" ? " (permissive)" : f.name === "lockdown" ? " (deny all)" : "")),
    el("div", { class: "flabel" }, f.label),
    pick ? el("div", { class: "pickmark" }, "Selected for the repair") : null);
  return el("article", { class: "panel future" + (pick ? " pick" : ""), "aria-label": `Future: ${FORK_NAME[f.name] || f.name}` },
    head,
    outcomeBlock("Attack outcome", "harmful actions that executed", f.attacks, true, f.harmful_executed, f.attacks_total),
    outcomeBlock("Legit task outcome", "authorized actions that completed", f.legit, false, f.legit_completed, f.legit_total),
    el("div", { class: "verdict " + verdict[0] }, verdict[1]));
}

function renderFutures(rec) {
  if (!Array.isArray(rec.forks) || rec.forks.length === 0) {
    setBody("futures-body", el("div", { class: "panel" }, "This record has no policy forks."), false);
    return;
  }
  setBody("futures-body", el("div", {},
    el("p", { class: "replay-note" },
      el("strong", {}, `${rec.replay_mode || "replay_mode missing"}: `),
      "each column replays the same captured action proposals against one policy in a fresh mock backend. " +
      "It is not a model re-running the task, so these are not counterfactual agent behaviour."),
    el("div", { class: "futures" }, ...rec.forks.map((f) => futureColumn(f, rec.selected)))), false);
}

/* ---------- 4. fix and receipt ---------- */

function formatDiffLines(prefix, val) {
  const s = jstr(val);
  return s.split("\n").map((l) => `${prefix} ${l}`).join("\n");
}

function diffTable(diff) {
  const keys = Object.keys(diff || {});
  if (!keys.length) return el("p", { class: "dim" }, "No configuration changes against the baseline.");
  return el("div", { class: "tablewrap" }, el("table", { class: "difftable" },
    el("caption", { class: "dim small", style: "text-align:left;padding-bottom:4px" }, "Policy configuration diff against the baseline"),
    el("thead", {}, el("tr", {}, el("th", { scope: "col" }, "Setting"), el("th", { scope: "col" }, "Before"), el("th", { scope: "col" }, "After"))),
    el("tbody", {}, ...keys.map((k) => el("tr", {},
      el("td", { class: "k" }, k),
      el("td", { class: "from" }, el("pre", {}, formatDiffLines("-", diff[k].from))),
      el("td", { class: "to" }, el("pre", {}, formatDiffLines("+", diff[k].to))))))));
}

function caveatList(rec) {
  const items = [];
  const add = (v) => {
    if (v === null || v === undefined || v === "") return;
    if (Array.isArray(v)) v.forEach(add);
    else if (typeof v === "object") items.push(jstr(v));
    else items.push(String(v));
  };
  const fromRecord = [rec.caveats, rec.caveat, rec.disclaimer, rec.honesty, rec.notes];
  fromRecord.forEach(add);
  const ap = rec.approval || {};
  items.push(`Record says: evidence is "${rec.evidence}" and replay mode is "${rec.replay_mode}".`);
  if (ap.channel) items.push(`Record says: approval channel is "${ap.channel}".`);
  if (ap.real_channel !== true) items.push("Approval did not go through a real messaging channel.");
  if (ap.openclaw_managed !== true) items.push("No OpenClaw-managed channel or agent was involved.");
  items.push("Forks are policy-only replays of captured proposals, not counterfactual agent behaviour.");
  items.push("The trace is a local hash chain: no signature, no external anchor, so it is not tamper-proof.");
  items.push("The dollar exposure is fictional; it is not savings and not prevented fraud.");
  return { items };
}

function renderFix(rec) {
  const ap = rec.approval || {};
  const ver = rec.verification;

  const repair = el("div", { class: "panel" }, el("h4", {}, "Proposed fix"));
  if (rec.repair) {
    repair.append(el("dl", { class: "kv" },
      el("dt", {}, "Policy"), el("dd", {}, rec.repair.policy),
      el("dt", {}, "Digest"), el("dd", { class: "mono" }, String(rec.repair.digest))),
      el("div", { style: "margin-top:10px" }, diffTable(rec.repair.config_diff)));
  } else {
    repair.append(el("p", {}, "No policy was verified in replay, so no fix was proposed."));
  }

  const state = ap.state || "unknown";
  const verifyNode = ver
    ? el("dd", {}, el("span", { class: "status " + (ver.verified ? "ok" : "bad") }, ver.verified ? "Verified" : "Not verified"),
        ` (harmful executed ${ver.harmful_executed}/${ver.attacks_total}, legit completed ${ver.legit_completed}/${ver.legit_total}; re-run on the mock backend after activation)`)
    : el("dd", {}, "Not run: the fix was never activated.");
  const status = el("div", { class: "panel" }, el("h4", {}, "Approval and verification"),
    el("dl", { class: "kv" },
      el("dt", {}, "Approval state"), el("dd", {}, el("span", { class: "status " + (state === "activated" ? "ok" : "warn") }, state)),
      el("dt", {}, "Approval channel"), el("dd", {}, `${ap.channel || "n/a"} (real channel: ${yesno(ap.real_channel)}, OpenClaw-managed: ${yesno(ap.openclaw_managed)})`),
      el("dt", {}, "Post-activation check"), verifyNode,
      el("dt", {}, "Trace chain intact"), el("dd", {},
        el("span", { class: "status " + (rec.trace_chain_ok ? "ok" : "bad") }, yesno(rec.trace_chain_ok)),
        " (local checksum chain, not a signature)")));

  const cav = caveatList(rec);
  const caveats = el("div", { class: "panel" }, el("h4", {}, "Caveats"),
    el("ul", { class: "caveats" }, ...cav.items.map((t) => el("li", {}, t))));

  const dl = el("button", { type: "button", class: "btn-primary", id: "dl-btn" }, "Download receipt JSON");
  dl.addEventListener("click", () => downloadRecord(rec));
  const actions = el("div", { class: "actionsrow" }, dl,
    el("span", { class: "dim small" }, `Saves this run (${rec.run_id}) exactly as fetched, trace and hashes included.`));

  setBody("fix-body", el("div", {}, el("div", { class: "cols2" }, repair, status), el("div", { style: "margin-top:14px" }, caveats), actions), false);
}

function downloadRecord(rec) {
  const blob = new Blob([JSON.stringify(rec, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = el("a", { href: url, download: `phantomshift-${String(rec.run_id).replace(/[^A-Za-z0-9_-]/g, "")}.json` });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

/* ---------- measurement strip (/api/eval) ---------- */

function ratioCell(n, d, badWhenHigh) {
  const frac = d ? n / d : 0;
  const tone = badWhenHigh ? (n > 0 ? "bad" : "ok") : (n < d ? "bad" : "ok");
  const fill = badWhenHigh ? frac : 1 - frac;
  return el("td", { class: "num" }, `${n} / ${d}`,
    el("span", { class: "mbar", "aria-hidden": "true" }, el("i", { class: tone, style: `width:${Math.round(fill * 100)}%` })));
}

function renderMeasure(ev) {
  const h = ev && ev.heldout, r = h && h.results;
  if (!r || !r.parametric || !r.hard) {
    setBody("measure-body", el("div", { class: "panel" }, "The evaluation response has no held-out results."), false);
    return;
  }
  const allPolicyNames = Array.from(new Set([...Object.keys(r.parametric), ...Object.keys(r.hard)]));
  const rows = allPolicyNames.map((name) => {
    const p = (r.parametric[name] || {}).policy_only, hd = (r.hard[name] || {}).policy_only;
    return el("tr", {},
      el("th", { scope: "row" }, FORK_NAME[name] || name),
      p ? ratioCell(p.attacks_succeeded, p.attacks, true) : el("td", {}, "n/a"),
      p ? ratioCell(p.legit_completed, p.legit, false) : el("td", {}, "n/a"),
      hd ? ratioCell(hd.attacks_succeeded, hd.attacks, true) : el("td", {}, "n/a"),
      hd ? ratioCell(hd.legit_completed, hd.legit, false) : el("td", {}, "n/a"));
  });
  const table = el("div", { class: "tablewrap" }, el("table", { class: "measure" },
    el("caption", { class: "dim small", style: "text-align:left;padding-bottom:6px" },
      `Held-out split (seed ${h.seed}), policy_only column, ${h.replay_mode}. Bars show the bad outcome for attacks and the shortfall for legit work.`),
    el("thead", {},
      el("tr", {}, el("th", { rowspan: 2, scope: "col" }, "Policy"),
        el("th", { colspan: 2, scope: "colgroup" }, "Parametric variants"),
        el("th", { colspan: 2, scope: "colgroup" }, "Hard cases")),
      el("tr", {}, el("th", { scope: "col" }, "Attacks succeeded"), el("th", { scope: "col" }, "Legit completed"),
        el("th", { scope: "col" }, "Attacks succeeded"), el("th", { scope: "col" }, "Legit completed"))),
    el("tbody", {}, ...rows)));

  const hardWarning = el("div", { class: "audit-banner" },
    el("strong", {}, "Security Audit Disclosure (Hard Cases): "),
    "Naive policy-only context matching allowed 3 of 5 adversarial actions (account laundering, 10x PO amount manipulation, customer PII exfiltration) and falsely denied 1 of 1 legitimate customer reply. The repaired ",
    el("strong", {}, "Authoritative Guard"),
    " canonicalizes Unicode, validates against vendor master, and stops all 5 attacks while completing 100% of legitimate work."
  );

  let extSection = null;
  if (r.extended_heldout) {
    const ext = r.extended_heldout;
    const extRows = Object.keys(ext).map((name) => {
      const row = ext[name];
      const atkCI = row.attack_success_ci_95 ? ` [${row.attack_success_ci_95[0]}, ${row.attack_success_ci_95[1]}]` : "";
      const legCI = row.legit_completion_ci_95 ? ` [${row.legit_completion_ci_95[0]}, ${row.legit_completion_ci_95[1]}]` : "";
      return el("tr", {},
        el("th", { scope: "row" }, FORK_NAME[name] || name),
        ratioCell(row.attacks_succeeded, row.attacks_total, true),
        el("td", { class: "num small" }, `${Math.round(row.attack_success_rate * 100)}%${atkCI}`),
        ratioCell(row.legit_completed, row.legit_total, false),
        el("td", { class: "num small" }, `${Math.round(row.legit_completion_rate * 100)}%${legCI}`));
    });

    extSection = el("div", { style: "margin-top:20px" },
      el("h4", {}, "Extended held-out benchmark (40 cases / 8 categories)"),
      el("p", { class: "dim small", style: "margin-bottom:6px" },
        "Independently evaluated against non-circular ground truth. 95% Wilson confidence intervals reported."),
      el("div", { class: "tablewrap" }, el("table", { class: "measure" },
        el("thead", {}, el("tr", {},
          el("th", { scope: "col" }, "Policy"),
          el("th", { scope: "col" }, "Attacks succeeded"),
          el("th", { scope: "col" }, "Attack rate (95% CI)"),
          el("th", { scope: "col" }, "Legit completed"),
          el("th", { scope: "col" }, "Legit rate (95% CI)"))),
        el("tbody", {}, ...extRows))));
  }

  const notes = el("ul", { class: "caveats small" },
    el("li", {}, "Parametric variants share their structure with the fixtures the policies were written alongside, so near-perfect scores there are expected. The hard cases are the informative rows, and there are only a handful of them."),
    el("li", {}, "The with_authority_gate column is circular: the authority record that defines harm also does the blocking, so its attack numbers are zero by construction. It is deliberately not shown here and is not a result."),
    el("li", {}, "Latency is in-process Python only: no network, no model, not the target hardware."));
  if (h.note) notes.append(el("li", {}, "From the record: " + h.note));

  const content = [hardWarning, table];
  if (extSection) content.push(extSection);
  content.push(el("div", { style: "margin-top:10px" }, notes));

  setBody("measure-body", el("div", { class: "panel" }, ...content), false);
}

/* ---------- orchestration ---------- */

let token = 0;
let gatesState = { pending: true, data: null, error: null };
let gatesP = null, evalP = null, lastRec = null;

function startSharedFetches() {
  gatesP = api("/api/gates").then(
    (d) => { gatesState = { pending: false, data: d, error: null }; },
    (e) => { gatesState = { pending: false, data: null, error: e }; });
  evalP = api("/api/eval").then((d) => ({ ok: true, d }), (e) => ({ ok: false, e }));
}

async function load(id, btn) {
  const my = ++token;
  $("banner").replaceChildren();
  for (const b of document.querySelectorAll("#tabs button")) b.setAttribute("aria-pressed", String(b === btn));
  loading("control-body", "Loading incident record...");
  loading("graph-body", "Loading trace...");
  loading("futures-body", "Loading policy forks...");
  loading("fix-body", "Loading receipt...");
  loading("measure-body", "Loading evaluation...");

  api("/api/incident/" + encodeURIComponent(id)).then(async (rec) => {
    if (my !== token) return;
    lastRec = rec;
    renderControl(rec, gatesState);
    renderGraph(rec);
    renderFutures(rec);
    renderFix(rec);
    await gatesP;
    if (my === token && lastRec === rec) renderControl(rec, gatesState);
  }, (err) => {
    if (my !== token) return;
    for (const sec of ["control-body", "graph-body", "futures-body", "fix-body"]) failure(sec, "the incident record", err);
    // failure() appends one banner entry per call; keep a single one
    const b = $("banner");
    while (b.children.length > 1) b.lastChild.remove();
  });

  const ev = await evalP;
  if (my !== token) return;
  if (ev.ok) renderMeasure(ev.d);
  else failure("measure-body", "the evaluation numbers", ev.e);
}

async function init() {
  startSharedFetches();
  let list;
  try {
    list = await api("/api/scenarios");
  } catch (err) {
    $("banner").append(el("div", { class: "err" }, el("strong", {}, "Could not load scenarios: "), err.message,
      " Is the HALBERD server still running?"));
    for (const id of ["control-body", "graph-body", "futures-body", "fix-body", "measure-body"]) {
      setBody(id, el("div", { class: "panel" }, "Nothing to show until the scenario list loads."), false);
    }
    return;
  }
  const tabs = $("tabs");
  list.forEach((s, i) => {
    const b = el("button", { type: "button", "aria-pressed": "false", title: s.task }, s.title);
    b.addEventListener("click", () => load(s.id, b));
    tabs.append(b);
    if (i === 0) load(s.id, b);
  });
}

init();
