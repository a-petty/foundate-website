/* The editor panel. Talks to serve.py over /__api/ and to the preview page (overlay.js) by postMessage. */
(function () {
  "use strict";
  const $ = (s, el) => (el || document).querySelector(s);
  const frame = $("#frame");
  const api = {
    async get(p) { return done(await fetch("/__api/" + p)); },
    async post(p, body) {
      return done(await fetch("/__api/" + p, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || {}) }));
    },
  };
  async function done(r) {
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || r.statusText);
    return j;
  }
  const S = { pages: [], page: "/", tokens: [], edits: {}, branch: "", changed: [], sel: null, same: [], scrollY: 0,
    reloading: false };

  // --- status ------------------------------------------------------------------------------------
  let statusTimer;
  function status(msg, kind) {
    const el = $("#status");
    el.textContent = msg; el.className = "status " + (kind || "");
    clearTimeout(statusTimer);
    if (kind !== "err") statusTimer = setTimeout(() => { el.textContent = ""; el.className = "status"; }, 6000);
  }
  const fail = (e) => status(e.message || String(e), "err");

  // --- git badge ---------------------------------------------------------------------------------
  function renderGit() {
    const n = S.changed.length;
    const g = $("#git");
    g.textContent = S.branch + (n ? " · " + n + " changed" : "");
    g.classList.toggle("dirty", n > 0);
    const c = $("#changes-count");
    c.hidden = !n; c.textContent = n;
  }
  async function refreshStatus() {
    try { const d = await api.get("diff"); S.branch = d.branch; S.changed = d.changed; renderGit(); renderDiff(d); }
    catch (e) { fail(e); }
  }

  // --- tabs --------------------------------------------------------------------------------------
  document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll(".tabs button").forEach((x) => x.classList.toggle("active", x === b));
    document.querySelectorAll(".tab").forEach((t) => { t.hidden = t.id !== "tab-" + b.dataset.tab; });
    if (b.dataset.tab === "changes") refreshStatus();
  }));

  // --- pages and the preview ---------------------------------------------------------------------
  function renderPages() {
    const sel = $("#page");
    sel.innerHTML = "";
    for (const p of S.pages) {
      const o = document.createElement("option");
      o.value = p.path; o.textContent = p.label + "  " + p.path;
      sel.appendChild(o);
    }
    sel.value = S.page;
  }
  $("#page").addEventListener("change", (e) => loadPage(e.target.value));

  async function loadPage(path, keepScroll) {
    S.page = path;
    $("#page").value = path;
    $("#open-plain").href = path;
    clearSelection();
    if (!keepScroll) S.scrollY = 0;
    S.reloading = true;
    frame.src = path + "?__edit=1&t=" + Date.now();
    try { renderSections(await api.get("page?path=" + encodeURIComponent(path))); } catch (e) { fail(e); }
  }

  function renderSections(info) {
    const ul = $("#sections");
    ul.innerHTML = "";
    const secs = info.sections;
    secs.forEach((s, i) => {
      const li = document.createElement("li");
      li.className = s.hidden ? "hidden" : "";
      const label = document.createElement("span");
      label.className = "label"; label.textContent = s.label; label.title = s.label + (s.anchor ? "  #" + s.anchor : "");
      label.addEventListener("click", () => send({ type: "highlight", sec: s.id }));
      li.appendChild(label);
      if (s.shared) { const t = document.createElement("span"); t.className = "tag"; t.textContent = "all pages"; li.appendChild(t); }
      const eye = btn(s.hidden ? "◌" : "●", s.hidden ? "Show this section" : "Hide this section", () => sectionAction(s.id, s.hidden ? "show" : "hide"));
      eye.classList.add("eye");
      li.appendChild(eye);
      const up = btn("↑", "Move up", () => sectionAction(s.id, "up"));
      const down = btn("↓", "Move down", () => sectionAction(s.id, "down"));
      const movable = secs.filter((x) => x.movable);
      const k = movable.indexOf(s);
      up.disabled = !s.movable || k <= 0;
      down.disabled = !s.movable || k < 0 || k >= movable.length - 1;
      li.appendChild(up); li.appendChild(down);
      ul.appendChild(li);
    });
  }
  function btn(text, title, onClick) {
    const b = document.createElement("button");
    b.type = "button"; b.className = "icon"; b.textContent = text; b.title = title;
    b.addEventListener("click", onClick);
    return b;
  }
  async function sectionAction(id, action) {
    try {
      const info = await api.post("section", { path: S.page, index: id, action });
      renderSections(info);
      status({ hide: "Hidden; it stays in the file.", show: "Shown.", up: "Moved up.", down: "Moved down." }[action], "ok");
      loadPage(S.page, true);
      refreshStatus();
    } catch (e) { fail(e); }
  }

  // --- messages from the preview -----------------------------------------------------------------
  function send(m) { if (frame.contentWindow) frame.contentWindow.postMessage(m, location.origin); }
  window.addEventListener("message", (e) => {
    if (e.origin !== location.origin) return;
    const m = e.data || {};
    if (m.type === "ready") {
      if (S.reloading && S.scrollY) send({ type: "scrollTo", y: S.scrollY });
      S.reloading = false;
      if (Object.keys(S.edits).length) send({ type: "tokens", values: S.edits });
    } else if (m.type === "scroll") { S.scrollY = m.y || 0; }
    else if (m.type === "navigate") { if (S.pages.some((p) => p.path === m.path)) loadPage(m.path); }
    else if (m.type === "select") { showSelection(m); }
    else if (m.type === "deselect") { if (S.sel && S.sel.id === m.id && !S.sel.pending) clearSelection(); }
    else if (m.type === "edit") { saveText(m.id, m.before, m.after); }
  });

  // --- text ----------------------------------------------------------------------------------------
  async function showSelection(m) {
    S.sel = { id: m.id, tag: m.tag, html: m.html, pending: false };
    $("#selection").hidden = false;
    $("#sel-tag").textContent = "<" + m.tag + ">";
    $("#sel-where").textContent = m.shared ? "in the header or footer, which every page shares" : "";
    $("#sel-text").value = m.html.trim();
    $("#sel-everywhere-wrap").hidden = true;
    S.same = [];
    try {
      const r = await api.get("same?path=" + encodeURIComponent(S.page) + "&index=" + m.id);
      S.same = r.pages || [];
      if (S.same.length && S.sel && S.sel.id === m.id) {
        $("#sel-everywhere-wrap").hidden = false;
        $("#sel-everywhere").checked = true;
        $("#sel-everywhere-label").textContent = "Also change the identical text on " +
          S.same.map((p) => p.label).join(", ") + ".";
      }
    } catch (e) { /* the page only */ }
  }
  function clearSelection() {
    S.sel = null; S.same = [];
    $("#selection").hidden = true;
  }
  function everywhereChecked() { return S.same.length > 0 && $("#sel-everywhere").checked; }
  async function elementAction(id, action, everywhere) {
    try {
      const r = await api.post("element", { path: S.page, index: id, action, everywhere });
      const n = r.changed.length;
      status({ remove: "Removed", up: "Moved up", down: "Moved down" }[action] + (n > 1 ? " on " + n + " pages." : "."), "ok");
      clearSelection();
      loadPage(S.page, true);
      refreshStatus();
    } catch (e) { fail(e); }
  }
  $("#sel-up").addEventListener("click", () => { if (S.sel) elementAction(S.sel.id, "up", everywhereChecked()); });
  $("#sel-down").addEventListener("click", () => { if (S.sel) elementAction(S.sel.id, "down", everywhereChecked()); });
  $("#sel-remove").addEventListener("click", () => {
    if (!S.sel) return;
    const ev = everywhereChecked();
    if (confirm("Remove this <" + S.sel.tag + "> from the page" + (ev ? " and from the other pages that carry it" : "") + "?")) {
      elementAction(S.sel.id, "remove", ev);
    }
  });
  async function saveText(id, before, after) {
    const everywhere = everywhereChecked();
    if (!after.replace(/<[^>]*>/g, "").trim()) {                 // emptied: that means remove it
      if (confirm("The text is empty. Remove this element from the page" + (everywhere ? " and from the other pages that carry it" : "") + "?")) {
        return elementAction(id, "remove", everywhere);
      }
      send({ type: "restore", id, html: before });
      if (S.sel && S.sel.id === id) $("#sel-text").value = before.trim();
      return;
    }
    if (S.sel && S.sel.id === id) S.sel.pending = true;
    try {
      const r = await api.post("text", { path: S.page, index: id, before, after, everywhere });
      const n = r.changed.length;
      status(n ? "Saved on " + n + " page" + (n === 1 ? "" : "s") + "." : "No change.", "ok");
      if (r.skipped && r.skipped.length) status("Saved here; skipped " + r.skipped.map((s) => s.file).join(", ") + ".", "ok");
      send({ type: "setHtml", id, html: after });
      if (S.sel && S.sel.id === id) { S.sel.html = after; S.sel.pending = false; $("#sel-text").value = after.trim(); }
      refreshStatus();
    } catch (e) {
      fail(e);
      send({ type: "restore", id, html: before });
      if (S.sel && S.sel.id === id) S.sel.pending = false;
    }
  }
  $("#sel-save").addEventListener("click", () => {
    if (!S.sel) return;
    const after = $("#sel-text").value;
    if (after.trim() === S.sel.html.trim()) { status("No change.", ""); return; }
    saveText(S.sel.id, S.sel.html, after);
  });
  $("#sel-cancel").addEventListener("click", () => { if (S.sel) send({ type: "restore", id: S.sel.id, html: S.sel.html }); clearSelection(); });

  // --- design tokens -------------------------------------------------------------------------------
  const GROUPS = [["color", "Colors"], ["px", "Sizes"], ["clamp", "Responsive sizes (min px, vw, max px)"],
    ["number", "Numbers"], ["font", "Fonts"], ["text", "Other"]];
  function renderTokens() {
    const box = $("#tokens");
    box.innerHTML = "";
    for (const [kind, title] of GROUPS) {
      const items = S.tokens.filter((t) => t.kind === kind || (kind === "color" && t.kind === "rgb"));
      if (!items.length) continue;
      const h = document.createElement("h2"); h.textContent = title; box.appendChild(h);
      const g = document.createElement("div"); g.className = "group";
      for (const t of items) g.appendChild(tokenRow(t));
      box.appendChild(g);
    }
    updateTokenButtons();
  }
  function tokenRow(t) {
    const row = document.createElement("div");
    row.className = "token"; row.dataset.name = t.name;
    row.innerHTML = '<span class="name"></span><span class="uses"></span><div class="ctl"></div>';
    $(".name", row).textContent = t.name.replace(/^--/, "");
    $(".name", row).title = t.name;
    $(".uses", row).textContent = t.uses ? "used " + t.uses + "×" : "unused";
    const ctl = $(".ctl", row);
    const value = S.edits[t.name] !== undefined ? S.edits[t.name] : t.value;
    const set = (v) => { setEdit(t.name, v, t.value); row.classList.toggle("changed", v !== t.value); };
    if (t.kind === "color" || t.kind === "rgb") {
      const rgb = t.kind === "rgb";                       // "30,77,59": a triple used inside rgba(var(--x), alpha)
      const ok = rgb ? /^\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}$/ : /^#[0-9a-fA-F]{3,8}$/;
      const c = el("input", { type: "color", value: rgb ? rgbToHex(value) : hex6(value) });
      const x = el("input", { type: "text", value, maxlength: rgb ? 13 : 9, spellcheck: false });
      c.addEventListener("input", () => { x.value = rgb ? hexToRgb(c.value) : c.value; set(x.value); });
      x.addEventListener("input", () => { const v = x.value.trim(); if (ok.test(v)) { c.value = rgb ? rgbToHex(v) : hex6(v); set(v); } });
      ctl.append(c, x);
      if (rgb) ctl.append(el("span", { className: "unit", textContent: "r,g,b" }));
    } else if (t.kind === "px") {
      const n = parseFloat(value);
      const r = el("input", { type: "range", min: 0, max: Math.max(Math.ceil(n * 2), 48), step: 1, value: n });
      const x = el("input", { type: "number", min: 0, step: 1, value: n });
      r.addEventListener("input", () => { x.value = r.value; set(r.value + "px"); });
      x.addEventListener("input", () => { r.value = x.value; set(x.value + "px"); });
      ctl.append(r, x, el("span", { className: "unit", textContent: "px" }));
    } else if (t.kind === "clamp") {
      const m = value.match(/clamp\(\s*(-?[\d.]+)px\s*,\s*(-?[\d.]+)vw\s*,\s*(-?[\d.]+)px\s*\)/);
      const a = el("input", { type: "number", step: 1, value: m[1] });
      const b = el("input", { type: "number", step: 0.1, value: m[2] });
      const c = el("input", { type: "number", step: 1, value: m[3] });
      const upd = () => set("clamp(" + a.value + "px," + b.value + "vw," + c.value + "px)");
      [a, b, c].forEach((i) => i.addEventListener("input", upd));
      ctl.append(a, el("span", { className: "unit", textContent: "px min" }), b, el("span", { className: "unit", textContent: "vw" }),
        c, el("span", { className: "unit", textContent: "px max" }));
    } else if (t.kind === "number") {
      const x = el("input", { type: "number", step: 0.05, value });
      x.addEventListener("input", () => set(x.value));
      ctl.append(x);
    } else {
      const x = el("input", { type: "text", value, spellcheck: false });
      x.addEventListener("input", () => set(x.value));
      ctl.append(x);
    }
    row.classList.toggle("changed", value !== t.value);
    return row;
  }
  function el(tag, props) { const e = document.createElement(tag); Object.assign(e, props); return e; }
  function hex6(h) {
    h = h.replace("#", "");
    if (h.length === 3 || h.length === 4) h = h.split("").map((c) => c + c).join("");
    return "#" + h.slice(0, 6);
  }
  const rgbToHex = (s) => "#" + s.split(",").map((n) => Math.min(255, +n.trim()).toString(16).padStart(2, "0")).join("");
  const hexToRgb = (h) => { const x = hex6(h).slice(1); return [0, 2, 4].map((i) => parseInt(x.slice(i, i + 2), 16)).join(","); };
  function setEdit(name, value, original) {
    if (value === original) delete S.edits[name]; else S.edits[name] = value;
    send(value === original ? { type: "clearTokens", names: [name] } : { type: "tokens", values: { [name]: value } });
    updateTokenButtons();
  }
  function updateTokenButtons() {
    const n = Object.keys(S.edits).length;
    $("#tokens-save").disabled = !n;
    $("#tokens-reset").disabled = !n;
    $("#tokens-save").textContent = n ? "Save " + n + " to styles.css" : "Save to styles.css";
  }
  $("#tokens-save").addEventListener("click", async () => {
    try {
      const r = await api.post("tokens", { values: S.edits });
      S.tokens = r.tokens; S.edits = {};
      renderTokens();
      status("Saved to docs/styles.css.", "ok");
      refreshStatus();
    } catch (e) { fail(e); }
  });
  $("#tokens-reset").addEventListener("click", () => {
    send({ type: "clearTokens", names: Object.keys(S.edits) });
    S.edits = {};
    renderTokens();
  });

  // --- changes -----------------------------------------------------------------------------------
  function renderDiff(d) {
    $("#diff-stat").textContent = d.stat.trim() || "Nothing changed since the last commit.";
    $("#diff").textContent = d.diff;
  }
  $("#commit").addEventListener("click", async () => {
    try {
      const r = await api.post("commit", { message: $("#commit-msg").value });
      $("#commit-msg").value = "";
      status("Committed " + r.sha + " on " + r.branch + ".", "ok");
      refreshStatus();
    } catch (e) { fail(e); }
  });
  $("#discard").addEventListener("click", async () => {
    if (!S.changed.length) { status("Nothing to discard.", ""); return; }
    if (!confirm("Throw away every uncommitted change in docs/ (" + S.changed.length + " file(s))?")) return;
    try {
      await api.post("discard");
      S.edits = {};
      const st = await api.get("state");
      S.tokens = st.tokens; renderTokens();
      status("Discarded.", "ok");
      loadPage(S.page, true);
      refreshStatus();
    } catch (e) { fail(e); }
  });
  $("#publish").addEventListener("click", async () => {
    if (!confirm("Push branch " + S.branch + " to GitHub and open a pull request?")) return;
    const out = $("#publish-result");
    out.textContent = "Pushing…";
    try {
      const r = await api.post("publish");
      out.innerHTML = (r.existing ? "Pull request already open: " : "Pull request opened: ") +
        '<a href="' + r.url + '" target="_blank" rel="noopener"></a>';
      $("a", out).textContent = r.url;
      status("Pushed " + r.branch + ".", "ok");
    } catch (e) { out.textContent = ""; fail(e); }
  });

  // --- viewport ----------------------------------------------------------------------------------
  document.querySelectorAll(".viewports button").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll(".viewports button").forEach((x) => x.classList.toggle("active", x === b));
    const w = +b.dataset.w;
    frame.style.width = w ? w + "px" : "100%";
  }));

  // --- start -------------------------------------------------------------------------------------
  (async function start() {
    try {
      const st = await api.get("state");
      S.pages = st.pages; S.tokens = st.tokens; S.branch = st.branch; S.changed = st.changed;
      renderPages(); renderTokens(); renderGit();
      const first = location.hash.slice(1);
      loadPage(S.pages.some((p) => p.path === first) ? first : "/");
    } catch (e) { fail(e); }
  })();
})();
