/* Injected into a page only when it is previewed inside the editor (…?__edit=1). Never served otherwise.
   Makes marked elements editable in place and relays what happens to the panel. */
(function () {
  "use strict";
  if (window.parent === window) return;
  const post = (m) => window.parent.postMessage(m, location.origin);

  const style = document.createElement("style");
  style.textContent =
    "[data-ed]{cursor:text}" +
    "[data-ed]:hover{outline:2px dashed rgba(30,77,59,.55);outline-offset:3px}" +
    "[data-ed].ed-selected{outline:2px solid rgba(30,77,59,.45);outline-offset:3px}" +
    "[data-ed].ed-active{outline:2px solid #1e4d3b;outline-offset:3px;background:rgba(30,77,59,.06)}" +
    "[data-ed-sec].ed-hl{outline:3px solid #1e4d3b;outline-offset:-3px}";
  document.head.appendChild(style);

  let active = null, target = null, original = "";
  const idOf = (el) => +el.getAttribute("data-ed");
  const clean = (h) => h.replace(/&nbsp;/g, " ").replace(/(<br\s*\/?>\s*)+$/, "").trim();
  // Typing happens inside a sole inline child (<li><a>Work</a></li>), so new text stays inside the link.
  function editTarget(el) {
    let t = el;
    while (t.childNodes.length === 1 && t.firstChild.nodeType === 1 && t.firstChild.tagName !== "BR") t = t.firstChild;
    return t;
  }

  function start(el) {
    if (active === el) return;
    if (active) finish(true);
    active = el; original = el.innerHTML; target = editTarget(el);
    document.querySelectorAll(".ed-selected").forEach((x) => x.classList.remove("ed-selected"));
    el.classList.add("ed-selected");                       // stays until the panel lets go of it
    el.classList.add("ed-active");
    target.setAttribute("contenteditable", "true");
    target.focus();
    post({ type: "select", id: idOf(el), tag: el.tagName.toLowerCase(), html: original, text: el.textContent.trim(),
      shared: !!el.closest("body > header, body > footer") });
  }
  function finish(save) {
    if (!active) return;
    const el = active, html = clean(el.innerHTML);
    target.removeAttribute("contenteditable");
    el.classList.remove("ed-active");
    active = null; target = null;
    if (!save) { el.innerHTML = original; }
    else if (html !== clean(original)) { post({ type: "edit", id: idOf(el), before: original, after: html }); return; }
    post({ type: "deselect", id: idOf(el) });
  }

  document.addEventListener("click", (e) => {
    const ed = e.target.closest("[data-ed]");
    if (ed) { e.preventDefault(); start(ed); return; }
    const a = e.target.closest("a[href]");
    if (a) {
      e.preventDefault();
      const href = a.getAttribute("href") || "";
      if (href.startsWith("#")) { const t = document.querySelector(href); if (t) t.scrollIntoView({ behavior: "smooth" }); }
      else if (href.startsWith("/")) post({ type: "navigate", path: href });
      return;
    }
    if (active) finish(true);
  }, true);

  document.addEventListener("keydown", (e) => {
    if (!active) return;
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); target.blur(); }
    else if (e.key === "Escape") { e.preventDefault(); finish(false); }
  });
  document.addEventListener("focusout", (e) => {
    if (active && e.target === target) setTimeout(() => { if (active && target === e.target) finish(true); }, 0);
  });
  document.addEventListener("paste", (e) => {                 // plain text only; the page carries no markup from elsewhere
    if (!active) return;
    e.preventDefault();
    document.execCommand("insertText", false, (e.clipboardData || window.clipboardData).getData("text/plain"));
  });

  window.addEventListener("message", (e) => {
    if (e.origin !== location.origin) return;
    const m = e.data || {};
    const byId = (id) => document.querySelector('[data-ed="' + id + '"]');
    if (m.type === "tokens") { for (const k of Object.keys(m.values || {})) document.documentElement.style.setProperty(k, m.values[k]); }
    else if (m.type === "clearTokens") { for (const k of m.names || []) document.documentElement.style.removeProperty(k); }
    else if (m.type === "highlight") {
      document.querySelectorAll(".ed-hl").forEach((x) => x.classList.remove("ed-hl"));
      const s = document.querySelector('[data-ed-sec="' + m.sec + '"]');
      if (s) { s.classList.add("ed-hl"); s.scrollIntoView({ behavior: "smooth", block: "start" }); setTimeout(() => s.classList.remove("ed-hl"), 1600); }
    }
    else if (m.type === "scrollTo") { window.scrollTo(0, m.y || 0); }
    else if (m.type === "unselect") { document.querySelectorAll(".ed-selected").forEach((x) => x.classList.remove("ed-selected")); }
    else if (m.type === "setHtml") { const el = byId(m.id); if (el) { el.innerHTML = m.html; if (el === active) original = m.html; } }
    else if (m.type === "restore") { const el = byId(m.id); if (el) { if (el === active) { active = null; target.removeAttribute("contenteditable"); target = null; el.classList.remove("ed-active"); } el.innerHTML = m.html; } }
  });

  let timer;
  window.addEventListener("scroll", () => { clearTimeout(timer); timer = setTimeout(() => post({ type: "scroll", y: window.scrollY }), 150); }, { passive: true });
  post({ type: "ready", path: location.pathname });
})();
