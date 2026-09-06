// GuardPrompt side panel. Talks ONLY to the configured OWUI instance, using the
// browser's existing OWUI session cookie (credentials: 'include'). Page content is
// sent as a normal OWUI chat message, so the gp-pipeline inlet anonymizes it before
// anything reaches an external LLM — the whole reason to build our own extension.

// OWUI base is baked from .env DOCLING_PUBLIC_HOST at build (env-config.js) — no
// per-machine config. An enterprise policy (managed.baseUrl) still overrides it.
const DEFAULT_BASE = (typeof window !== "undefined" && window.GP_OWUI_BASE) || "";
// Baked from .env GP_BROWSER_MODEL_ID (env-config.js -> window.GP_MODEL_FILTER); admin
// policy overrides. Neutral fallback; the real per-deployment id comes from .env.
const DEFAULT_MODEL_FILTER = (typeof window !== "undefined" && window.GP_MODEL_FILTER) || "gp-browser";
const MAX_CTX = 20000; // cap page text so we don't post a whole huge DOM

const $ = (id) => document.getElementById(id);
let BASE = DEFAULT_BASE;
let MODEL_FILTER = "";

async function loadCfg() {
  // Config comes ONLY from the system: enterprise policy (chrome.storage.managed),
  // set centrally by the admin, falling back to the baked defaults. There is NO
  // user-editable settings UI — the employee configures nothing.
  let managed = {};
  try { managed = (await chrome.storage.managed.get(["baseUrl", "modelFilter"])) || {}; } catch (e) {}
  BASE = (managed.baseUrl || DEFAULT_BASE).replace(/\/+$/, "");
  MODEL_FILTER = (managed.modelFilter || DEFAULT_MODEL_FILTER || "").trim();
}

function esc(s) {
  return (s || "").replace(/[<>&]/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" }[c]));
}

function addMsg(role, text) {
  const el = document.createElement("div");
  el.className = "msg " + (role === "user" ? "u" : role === "error" ? "err" : "a");
  el.innerHTML = esc(text);
  $("log").appendChild(el);
  $("log").scrollTop = $("log").scrollHeight;
  return el;
}

async function api(path, opts = {}) {
  return fetch(`${BASE}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
}

async function loadBrand() {
  // White-label: pull the deployment's name + logo from brand.json (same file the
  // login page uses), so the panel matches the client brand automatically. Falls
  // back to the baked "GuardPrompt AI" title if unavailable.
  try {
    const r = await api("/_gp/brand.json");
    if (!r.ok) return;
    const b = await r.json();
    if (b && b.name) $("brandName").textContent = b.name + " AI";
    // Optional per-deployment accent for the primary button (white-label). Set "color"
    // (any CSS color) in brand.json to match the client brand; otherwise stays neutral.
    if (b && b.color) { try { document.documentElement.style.setProperty("--gp-accent", String(b.color)); } catch (e) {} }
    if (b && b.logo) {
      const img = $("brandLogo");
      // Show the full logo AND the name together in one row.
      img.onload = () => { img.style.display = "inline"; };
      img.onerror = () => { img.style.display = "none"; };
      img.src = /^https?:/i.test(b.logo) ? b.logo : BASE + b.logo;
    }
  } catch (e) {
    /* keep the baked title */
  }
}

// ONE OpenWebUI chat per panel session (owned by the logged-in user via the session
// cookie) — created on the first exchange, APPENDED to on every next one. Admins see
// it in OWUI's chat history: who did what, all in a single conversation.
let _chatId = null;
const _chatMsgs = []; // full ordered message objects, threaded via parent/children

async function saveChat(question, answer, model) {
  try {
    const now = Math.floor(Date.now() / 1000);
    const uid = crypto.randomUUID();
    const aid = crypto.randomUUID();
    const prevId = _chatMsgs.length ? _chatMsgs[_chatMsgs.length - 1].id : null;
    if (prevId) {
      const p = _chatMsgs.find((m) => m.id === prevId);
      if (p) p.childrenIds = [uid];
    }
    _chatMsgs.push(
      { id: uid, parentId: prevId, childrenIds: [aid], role: "user", content: question, timestamp: now },
      { id: aid, parentId: uid, childrenIds: [], role: "assistant", content: answer,
        model: model, modelName: model, modelIdx: 0, timestamp: now }
    );
    const history = { messages: {}, currentId: aid };
    for (const m of _chatMsgs) history.messages[m.id] = m;
    const chat = {
      title: "[GuardPrompt AI] " + (_chatMsgs[0].content || "").slice(0, 60),
      models: [model],
      messages: _chatMsgs,
      history,
      timestamp: now * 1000,
    };
    if (!_chatId) {
      const r = await api("/api/v1/chats/new", { method: "POST", body: JSON.stringify({ chat }) });
      if (r.ok) { const d = await r.json(); _chatId = d?.id || (d?.chat && d.chat.id) || null; }
      else console.warn("[GuardPrompt AI] chat new HTTP " + r.status);
    } else {
      const r = await api("/api/v1/chats/" + _chatId, { method: "POST", body: JSON.stringify({ chat }) });
      if (!r.ok) console.warn("[GuardPrompt AI] chat update HTTP " + r.status);
    }
  } catch (e) {
    console.warn("[GuardPrompt AI] chat save failed:", e); // non-fatal
  }
}

// Conversation memory: prior Q/A (clean, not the big page-context prompt) so the
// model has context of earlier turns. Capped to keep the request small.
const CONVO = [];
const CONVO_MAX = 12;
function remember(q, a) {
  CONVO.push({ role: "user", content: q }, { role: "assistant", content: a || "" });
  while (CONVO.length > CONVO_MAX) CONVO.shift();
}

let LOGIN_TAB_OPENED = false;
// No valid session/token -> OPEN the OWUI login page in a new tab so the user can sign in
// (once per session, to avoid spawning tabs on repeated 401s), and tell them.
function loginHint() {
  addMsg("error", `Neprisijungta prie ${BASE}. Atidariau prisijungimo langą — prisijunk ir bandyk vėl.`);
  if (!LOGIN_TAB_OPENED && BASE) {
    LOGIN_TAB_OPENED = true;
    try { chrome.tabs.create({ url: BASE, active: true }); } catch (e) {}
  }
}

async function loadModels() {
  const sel = $("model");
  sel.innerHTML = "";
  try {
    const r = await api("/api/models");
    if (r.status === 401 || r.status === 403) return loginHint();
    if (!r.ok) throw new Error("HTTP " + r.status);
    const data = await r.json();
    const list = data.data || data.models || data || [];
    for (const m of list) {
      const id = m.id || m.name;
      if (!id) continue;
      const name = m.name || id;
      // Lock to the designated model when a marker is set: hides every other model
      // so an employee can't accidentally pick a wrong/leaky one.
      if (MODEL_FILTER && !(String(id).includes(MODEL_FILTER) || String(name).includes(MODEL_FILTER))) continue;
      const o = document.createElement("option");
      o.value = id;
      o.textContent = name;
      sel.appendChild(o);
    }
    // One allowed model -> lock the picker so it can't be changed.
    sel.disabled = !!(MODEL_FILTER && sel.options.length === 1);
    if (!sel.options.length) {
      addMsg("error", MODEL_FILTER
        ? "Nerasta modelio pagal žymę „" + MODEL_FILTER + "“ — patikrink žymę arba modelio prieigą OWUI."
        : "Nerasta modelių (patikrink prieigą).");
    }
  } catch (e) {
    addMsg("error", "Nepavyko gauti modelių: " + e.message);
  }
}

// Runs IN the page (serialized by chrome.scripting) — no outer references allowed.
// Writes `text` into the focused editable element. Human-in-the-loop: only ever
// called when the USER clicks an apply button, never automatically.
function writeToPage(payload) {
  const { text, mode } = payload;
  const ed = (t) => t && (t.isContentEditable || /^(textarea|input)$/i.test(t.tagName || ""));
  // Clicking a side-panel button blurs the page, so document.activeElement is
  // usually <body> by now. Fall back to the last editable element the tracker
  // remembered (see installTracker).
  const el = ed(document.activeElement) ? document.activeElement : window.__gpLastEditable;
  if (!ed(el)) return { ok: false, reason: "nėra įsiminto redaguojamo lauko" };
  const tag = el.tagName ? el.tagName.toLowerCase() : "";
  // Snapshot for Undo before we mutate anything.
  const before = /^(textarea|input)$/i.test(tag) ? el.value : (el.isContentEditable ? el.innerHTML : null);
  const isField =
    tag === "textarea" ||
    (tag === "input" && /^(text|search|url|email|tel|number|)$/.test((el.type || "text")));
  const fire = (node) => {
    node.dispatchEvent(new Event("input", { bubbles: true }));
    node.dispatchEvent(new Event("change", { bubbles: true }));
  };

  if (isField) {
    const s = el.selectionStart ?? el.value.length;
    const e = el.selectionEnd ?? el.value.length;
    if (mode === "replace") {
      el.value = el.value.slice(0, s) + text + el.value.slice(e);
      const p = s + text.length;
      el.setSelectionRange(p, p);
    } else {
      // insert at caret end, keep any selected text
      el.value = el.value.slice(0, e) + text + el.value.slice(e);
      const p = e + text.length;
      el.setSelectionRange(p, p);
    }
    fire(el);
    return { ok: true, target: tag, before };
  }

  if (el && el.isContentEditable) {
    el.focus();
    const sel = window.getSelection();
    // Restore the range the tracker saved — focus was lost when the panel button
    // was clicked, so the live selection is otherwise gone.
    if (window.__gpLastRange) {
      try {
        sel.removeAllRanges();
        const r = window.__gpLastRange.cloneRange();
        if (mode === "insert") r.collapse(false);
        sel.addRange(r);
      } catch (e) {}
    } else if (mode === "insert" && sel && sel.rangeCount) {
      sel.collapseToEnd();
    }
    if (text === "") {
      document.execCommand("delete", false); // deterministic delete of the selection
    } else {
      // insertText replaces the selection (or inserts at caret) AND fires the input
      // events rich editors listen to. Deprecated but still works in Chrome.
      const ok = document.execCommand("insertText", false, text);
      if (!ok && sel && sel.rangeCount) {
        const range = sel.getRangeAt(0);
        range.deleteContents();
        range.insertNode(document.createTextNode(text));
      }
    }
    fire(el);
    return { ok: true, target: "contenteditable", before };
  }

  // Fallback: replace the current page selection (visual only on a plain page).
  const sel = window.getSelection();
  if (sel && sel.rangeCount && !sel.isCollapsed) {
    const range = sel.getRangeAt(0);
    range.deleteContents();
    range.insertNode(document.createTextNode(text));
    return { ok: true, target: "selection" };
  }
  return { ok: false, reason: "no editable field focused" };
}

// Injected once per page: remember the last editable element the user focused, so
// we can still write to it after the side panel steals focus. Also grabs the
// currently-focused field at install time (covers "focused before opening panel").
function installTracker() {
  const ed = (t) => t && (t.isContentEditable || /^(textarea|input)$/i.test(t.tagName || ""));
  if (ed(document.activeElement)) window.__gpLastEditable = document.activeElement;
  if (window.__gpTrack) return true;
  window.__gpTrack = true;
  document.addEventListener(
    "focusin",
    (e) => { if (ed(e.target)) window.__gpLastEditable = e.target; },
    true
  );
  // Remember the last selection range inside a contenteditable, so "Pakeisti
  // pažymėtą" can restore it after the side panel steals focus (blur drops the
  // live selection). Textareas keep selectionStart/End on the element themselves.
  document.addEventListener(
    "selectionchange",
    () => {
      const s = window.getSelection();
      if (!s || !s.rangeCount) return;
      let n = s.anchorNode;
      n = n && (n.nodeType === 1 ? n : n.parentElement);
      const host = n && n.closest && n.closest('[contenteditable=""],[contenteditable="true"]');
      if (host) { window.__gpLastEditable = host; window.__gpLastRange = s.getRangeAt(0).cloneRange(); }
    },
    true
  );
  return true;
}

function grabPage() {
  const selection = (window.getSelection && window.getSelection().toString()) || "";
  // Shadow-aware visible text: many modern SPAs (mail.ru octavius, Gmail bits) render
  // content inside Web Component SHADOW ROOTS, which document.body.innerText does NOT
  // traverse — so a plain read returns only the nav chrome. We walk the tree, descending
  // into every open shadowRoot, skipping hidden/script/style nodes, collecting text.
  let text = "";
  try {
    const parts = [];
    const MAX = 200000; // hard cap so a huge DOM can't hang the walk
    let count = 0;
    const walk = (node) => {
      if (count > MAX || parts.length > 20000) return;
      if (!node) return;
      if (node.nodeType === 3) { // text node
        const t = node.nodeValue ? node.nodeValue.replace(/\s+/g, " ").trim() : "";
        if (t) { parts.push(t); count += t.length; }
        return;
      }
      if (node.nodeType !== 1) return; // elements only past here
      const el = node;
      const tag = el.tagName;
      if (tag === "SCRIPT" || tag === "STYLE" || tag === "NOSCRIPT" || tag === "TEMPLATE") return;
      // Only skip display:none (truly unrendered, non-overridable). Do NOT skip on
      // visibility:hidden — a hidden wrapper can have visibility:visible children (mail.ru
      // does this on the reading pane), and skipping would drop the actual email body.
      try {
        const cs = getComputedStyle(el);
        if (cs && cs.display === "none") return;
      } catch (e) {}
      if (el.shadowRoot) { for (const c of el.shadowRoot.childNodes) walk(c); }
      for (const c of el.childNodes) walk(c);
    };
    walk(document.body);
    text = parts.join(" ");
  } catch (e) {
    text = (document.body ? document.body.innerText : "") || "";
  }
  if (!text) text = (document.body ? document.body.innerText : "") || "";
  // Collect + tag visible clickable elements so the model can ask us to click one by
  // number (data-gpref). The tricky part on app UIs (webmail, React lists) is avoiding
  // the big CONTAINER (role=grid/list) and tagging the actual ROWS: we (1) skip
  // container roles, (2) include row/listitem roles, and (3) drop any candidate that is
  // an ANCESTOR of another candidate, keeping the innermost — so a message row wins over
  // the list wrapper. Runs at capture time; the tag persists for the click.
  const clickables = [];
  try {
    const q = 'a[href],button,[role="button"],[role="link"],[role="row"],' +
              '[role="listitem"],[role="option"],[role="menuitem"],[role="tab"],' +
              '[role="gridcell"],[role="article"],li[tabindex],[onclick],' +
              'input:not([type="hidden"]),textarea,select,' +
              '[contenteditable=""],[contenteditable="true"],[role="textbox"],' +
              '[tabindex]';
    const CONTAINER = /^(grid|list|listbox|table|rowgroup|tablist|navigation|main|banner|toolbar|menu|menubar|tree|treegrid|group|application|document|region|dialog|tabpanel|feed|search|form)$/;
    const found = [];
    for (const el of document.querySelectorAll(q)) {
      const r = el.getBoundingClientRect();
      if (r.width < 4 || r.height < 4) continue; // skip hidden
      const role = (el.getAttribute("role") || "").toLowerCase();
      if (CONTAINER.test(role)) continue; // skip wrappers that hold many items
      found.push(el);
    }
    // "Primary" = a whole actionable row/link/button. We keep the OUTERMOST primary and
    // drop everything inside it, so a message row (an <a> wrapping icons/spans) is ONE
    // numbered entry with its full subject — not a scatter of inner bits. Non-primary
    // candidates survive only if they're not inside a primary (standalone controls).
    const PRIMARY = 'a[href],button,[role="button"],[role="link"],[role="row"],' +
                    '[role="listitem"],[role="option"],[role="menuitem"],[role="tab"],[role="article"]';
    const isPrimary = (el) => { try { return el.matches(PRIMARY); } catch (e) { return false; } };
    const inPrimaryAncestor = (el) => {
      for (const o of found) { if (o !== el && isPrimary(o) && o.contains(el)) return true; }
      return false;
    };
    const leaves = found.filter((el) => {
      if (inPrimaryAncestor(el)) return false; // represented by an outer row/link
      if (!isPrimary(el)) {
        // non-primary: drop if it merely wraps other candidates (a container-ish div)
        for (const o of found) { if (o !== el && el.contains(o)) return false; }
      }
      return true;
    });
    // Rich label incl. form fields: for inputs/selects/textarea use placeholder, aria-label,
    // and the associated <label> so the agent can target empty fields (search boxes, forms).
    const labelFor = (el) => {
      let s = el.getAttribute("aria-label") || el.getAttribute("placeholder") || el.title || "";
      if (!s && el.id) { try { const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]'); if (l) s = l.innerText; } catch (e) {} }
      if (!s) { try { const l = el.closest && el.closest("label"); if (l) s = l.innerText; } catch (e) {} }
      return s;
    };
    let i = 0;
    for (const el of leaves) {
      if (i >= 150) break;
      const tag = (el.tagName || "").toLowerCase();
      const isField = tag === "input" || tag === "textarea" || tag === "select";
      // Rich-text editor body (compose/reply message area): contenteditable or role=textbox.
      // Label it distinctly as [turinys] so the model targets the BODY, not To/Subject.
      const isBody = tag === "textarea" || el.isContentEditable ||
        el.getAttribute("contenteditable") === "true" || el.getAttribute("contenteditable") === "" ||
        el.getAttribute("role") === "textbox";
      let t = (el.innerText || el.value || el.getAttribute("aria-label") || el.title || "").trim();
      if (isBody && tag !== "input" && tag !== "select") {
        const lab = (labelFor(el) || "").trim();
        t = "[turinys] " + (lab || "teksto laukas (kūnas)");
      } else if (isField) {
        const lab = (labelFor(el) || "").trim();
        const kind = tag === "select" ? "select" : (el.type || "text");
        t = ("[" + kind + "] " + (lab || el.value || "laukas")).trim();
      }
      t = t.replace(/\s+/g, " ").slice(0, 80);
      if (!t) continue;
      el.setAttribute("data-gpref", String(i));
      clickables.push({ i: i, t: t });
      i++;
    }
  } catch (e) {}
  return {
    selection: selection.trim(),
    text: text.trim(),
    url: location.href,
    title: document.title,
    clickables: clickables,
  };
}

// Google Docs/Sheets/Slides render the document on a CANVAS — the text is NOT in the DOM,
// so grabPage() only sees menus/toolbars and the agent wrongly concludes the doc is "empty".
// The reliable text source is the built-in export endpoint. It MUST be fetched from the
// EXTENSION context (this side panel), NOT from the page: the export 302-redirects to
// *.googleusercontent.com, and an in-page fetch to that cross-origin host is blocked by CORS
// (ACAO:* vs credentials:include). Extension-page fetches with host_permissions bypass CORS
// and still send the user's Google cookies. Returns the REAL document text, or a diagnostic.
async function fetchDocExport(pageUrl) {
  try {
    // id lives in /d/<id>/; the URL can carry a /u/<n>/ user segment
    // (docs.google.com/document/u/0/d/<id>/edit) — match TYPE and id separately.
    const id = (String(pageUrl || "").match(/\/d\/([\w-]+)/) || [])[1];
    if (!id) return null;
    let url = null, kind = "";
    if (pageUrl.indexOf("/document/") >= 0)          { url = "https://docs.google.com/document/d/" + id + "/export?format=txt"; kind = "doc"; }
    else if (pageUrl.indexOf("/spreadsheets/") >= 0) { url = "https://docs.google.com/spreadsheets/d/" + id + "/export?format=csv"; kind = "sheet"; }
    else if (pageUrl.indexOf("/presentation/") >= 0) { url = "https://docs.google.com/presentation/d/" + id + "/export/txt"; kind = "slides"; }
    if (!url) return null;
    const ac = new AbortController();
    const to = setTimeout(() => { try { ac.abort(); } catch (e) {} }, 8000);
    let r;
    try { r = await fetch(url, { credentials: "include", signal: ac.signal }); }
    finally { clearTimeout(to); }
    if (!r.ok) return { kind: kind, ok: false, status: r.status };
    // Not signed in → redirects to accounts.google.com and returns an HTML login page (200).
    if (/accounts\.google|ServiceLogin/.test(r.url || "")) return { kind: kind, ok: false, status: "auth-redirect" };
    const ctype = (r.headers.get("content-type") || "").toLowerCase();
    if (ctype.indexOf("text/html") >= 0) return { kind: kind, ok: false, status: "html(neprisijungta?)" };
    let t = (await r.text()).replace(/\r/g, "").replace(/\n{3,}/g, "\n\n").trim();
    return { kind: kind, ok: true, text: t.slice(0, 200000) };
  } catch (e) { return { ok: false, error: String((e && e.message) || e) }; }
}

// ---- Real input via CDP (chrome.debugger) ----------------------------------
// Hardened canvas editors (Google Docs/Sheets/Slides) IGNORE synthetic DOM events — they
// only accept genuine browser-level input. chrome.debugger + the CDP Input domain injects
// real events (the same mechanism Playwright/Puppeteer use to type into Google Docs). Used
// only when normal DOM fill won't reach the target (canvas apps).
function cdpSend(tabId, method, params) {
  return new Promise((res, rej) => {
    chrome.debugger.sendCommand({ tabId: tabId }, method, params || {}, (r) => {
      const e = chrome.runtime.lastError;
      if (e) rej(new Error(e.message)); else res(r);
    });
  });
}
function cdpAttach(tabId) {
  return new Promise((res, rej) => {
    chrome.debugger.attach({ tabId: tabId }, "1.3", () => {
      const e = chrome.runtime.lastError;
      if (e && !/already attached/i.test(e.message)) rej(new Error(e.message)); else res();
    });
  });
}
function cdpDetach(tabId) {
  return new Promise((res) => { chrome.debugger.detach({ tabId: tabId }, () => { void chrome.runtime.lastError; res(); }); });
}
// Type `text` into whatever is focused, via real input. `enter` presses Enter first (e.g. to
// dismiss a dialog / start editing). Returns {ok} or {ok:false,reason}.
async function cdpType(tabId, text) {
  try {
    await cdpAttach(tabId);
    try {
      // insertText commits the whole string at once (like an IME/paste) — canvas editors
      // accept it and it's far faster than key-by-key.
      await cdpSend(tabId, "Input.insertText", { text: String(text == null ? "" : text) });
      return { ok: true };
    } finally { await cdpDetach(tabId); }
  } catch (e) { try { await cdpDetach(tabId); } catch (_) {} return { ok: false, reason: (e && e.message) || String(e) }; }
}
// Real mouse click at viewport (x,y) via CDP — synthetic DOM events are ignored by many
// hardened widgets; this is a genuine browser click at the point (what actually reaches the
// site's handler / canvas). moveNewTabToCurrent handles any tab it spawns.
async function cdpClick(tabId, x, y) {
  try {
    await cdpAttach(tabId);
    try {
      const base = { x: x, y: y, button: "left", buttons: 1, clickCount: 1 };
      await cdpSend(tabId, "Input.dispatchMouseEvent", { type: "mouseMoved", x: x, y: y });
      await cdpSend(tabId, "Input.dispatchMouseEvent", Object.assign({ type: "mousePressed" }, base));
      await cdpSend(tabId, "Input.dispatchMouseEvent", Object.assign({ type: "mouseReleased" }, base));
      return { ok: true };
    } finally { await cdpDetach(tabId); }
  } catch (e) { try { await cdpDetach(tabId); } catch (_) {} return { ok: false, reason: (e && e.message) || String(e) }; }
}
// Page func: scroll the tagged element into view and return its viewport-center coords, for
// a CDP click. Returns {ok,x,y,label}.
function refCenterFn(ref) {
  const el = document.querySelector('[data-gpref="' + ref + '"]');
  if (!el) return { ok: false };
  try { el.scrollIntoView({ block: "center", inline: "center" }); } catch (e) {}
  let r; try { r = el.getBoundingClientRect(); } catch (e) { return { ok: false }; }
  if (!r || r.width < 2 || r.height < 2) return { ok: false };
  return { ok: true, x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2),
    label: (el.innerText || el.value || el.getAttribute("aria-label") || "").trim().replace(/\s+/g, " ").slice(0, 60) };
}

// Copy the current selection via a real Ctrl+C (CDP key events). On canvas editors (Google
// Docs) the selection isn't in the DOM, so window.getSelection() is empty — but the app DOES
// put the selected text on the clipboard when copied. Pair with readClipboardInTab().
async function cdpCopy(tabId) {
  try {
    await cdpAttach(tabId);
    try {
      const K = (type, key, code, vk, mods) => cdpSend(tabId, "Input.dispatchKeyEvent", { type: type, key: key, code: code, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk, modifiers: mods || 0 });
      await K("keyDown", "Control", "ControlLeft", 17, 2);
      await K("keyDown", "c", "KeyC", 67, 2);
      await K("keyUp", "c", "KeyC", 67, 2);
      await K("keyUp", "Control", "ControlLeft", 17, 0);
      return { ok: true };
    } finally { await cdpDetach(tabId); }
  } catch (e) { try { await cdpDetach(tabId); } catch (_) {} return { ok: false, reason: (e && e.message) || String(e) }; }
}
// Read the clipboard from within the (focused) tab — extension has clipboardRead permission.
async function readClipboardInTab(tabId) {
  try {
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId: tabId },
      func: async () => { try { return await navigator.clipboard.readText(); } catch (e) { return null; } },
    });
    return result || "";
  } catch (e) { return ""; }
}
// Get the user's current selection on a canvas editor (Google Docs): copy it, then read the
// clipboard. Returns the selected text, or "" if nothing/failed.
async function getDocSelection(tabId) {
  const c = await cdpCopy(tabId);
  if (!c || !c.ok) return "";
  await new Promise((r) => setTimeout(r, 200));
  return (await readClipboardInTab(tabId)).trim();
}

// Runs IN the page (isolated world) — READ ONLY. Resolves the element tagged
// data-gpref=<ref> to its label and, if it's (or sits inside) an anchor, its absolute
// http(s) href. clickInPage uses the href to navigate the CURRENT tab directly — no
// click, no new tab, no flash. This covers most "open X" targets, incl. webmail message
// rows (they're anchors). Returns href="" when there's nothing to navigate to.
function readRef(ref) {
  const el = document.querySelector('[data-gpref="' + ref + '"]');
  if (!el) return { ok: false, reason: "elementas #" + ref + " nerastas" };
  const label = (el.innerText || el.value || el.getAttribute("aria-label") || "").trim().replace(/\s+/g, " ").slice(0, 60);
  let href = "";
  try {
    const a = el.matches && el.matches("a[href]") ? el : (el.closest && el.closest("a[href]"));
    if (a && /^https?:/i.test(a.href)) href = a.href;
  } catch (e) {}
  // Small diagnostic string, surfaced only when a click fails (helps see what was hit).
  let diag = "";
  try {
    const anyA = el.closest && el.closest("a");
    diag = "tag=" + (el.tagName || "?") +
      " role=" + (el.getAttribute("role") || "-") +
      " anchor=" + (anyA ? (anyA.getAttribute("href") || "(no-href)") : "none") +
      " html=" + (el.outerHTML || "").slice(0, 180).replace(/\s+/g, " ");
  } catch (e) {}
  return { ok: true, text: label, href, diag };
}

// Runs IN the page: extract the MAIN content block (readability-lite) — the largest
// text-dense, low-link region — so we get an opened item's actual body, not ads/nav/
// toolbars. Generic: scores every block by text*(1-linkDensity), penalizes ad/nav-ish
// classes, boosts content-ish ones. Returns "" if nothing convincing (caller falls back).
function mainContentFn() {
  const deep = (el) => {
    // visible text incl. open shadow roots, honoring display:none only
    let out = "";
    const w = (n) => {
      if (!n) return;
      if (n.nodeType === 3) { out += " " + (n.nodeValue || ""); return; }
      if (n.nodeType !== 1) return;
      const t = n.tagName;
      if (t === "SCRIPT" || t === "STYLE" || t === "NOSCRIPT") return;
      try { const cs = getComputedStyle(n); if (cs && cs.display === "none") return; } catch (e) {}
      if (n.shadowRoot) for (const c of n.shadowRoot.childNodes) w(c);
      for (const c of n.childNodes) w(c);
    };
    w(el);
    return out.replace(/\s+/g, " ").trim();
  };
  const cand = document.querySelectorAll('article,[role="main"],main,section,div,td,li');
  let best = "", bestScore = 0;
  for (const el of cand) {
    let r; try { r = el.getBoundingClientRect(); } catch (e) { continue; }
    if (!r || r.width < 120 || r.height < 30) continue;
    const cid = (((el.getAttribute && el.getAttribute("class")) || "") + " " + (el.id || "")).toLowerCase();
    if (/(nav|menu|\bads?\b|advert|promo|banner|sidebar|footer|header|rekl|cookie|subscribe)/.test(cid)) continue;
    const txt = deep(el);
    const len = txt.length;
    if (len < 60 || len > 60000) continue;
    // Drop ad blocks by their tell-tale labels (works across locales): "Реклама", the
    // Russian ad-id "ERID", "О рекламодателе", "Advertisement", "Sponsored".
    if (/\b(erid|advertisement|sponsored)\b|реклам|рекламодател/i.test(txt)) continue;
    let linkLen = 0;
    try { el.querySelectorAll("a").forEach((a) => { linkLen += (a.innerText || "").length; }); } catch (e) {}
    const linkDensity = len ? Math.min(1, linkLen / len) : 1;
    let score = len * (1 - linkDensity);
    if (/article|main|content|message|letter|body|post|mail|read/.test(cid)) score *= 1.5;
    if (score > bestScore) { bestScore = score; best = txt; }
  }
  return best;
}

// Runs IN the page: pick the message/article BODY from a curated list of known content
// containers used by major webmail/CMS clients (mail.ru, Gmail, Outlook, Roundcube, …).
// This is like an ad-block list but inverted — reliable CONTENT selectors. Shadow-aware,
// skips ad-labelled blocks. Returns "" if none match (caller falls back to Readability).
function pickKnownBody() {
  const deep = (el) => {
    let out = "";
    const w = (n) => {
      if (!n) return;
      if (n.nodeType === 3) { out += " " + (n.nodeValue || ""); return; }
      if (n.nodeType !== 1) return;
      const t = n.tagName;
      if (t === "SCRIPT" || t === "STYLE" || t === "NOSCRIPT") return;
      try { const cs = getComputedStyle(n); if (cs && cs.display === "none") return; } catch (e) {}
      if (n.shadowRoot) for (const c of n.shadowRoot.childNodes) w(c);
      for (const c of n.childNodes) w(c);
    };
    w(el);
    return out.replace(/\s+/g, " ").trim();
  };
  const SELS = [
    '[class*="letter-body__body-content"]', '[class*="letter-body_body-content"]',
    '[class*="letter-body__body"]', '[class*="letter-body"]',   // mail.ru octavius
    ".a3s",                                                       // Gmail message body
    "#messagebody", ".message-htmlpart", ".rcmBody",             // Roundcube
    ".allowTextSelection", ".ReadingPaneContents", ".rps_",      // Outlook Web
    '[aria-label*="Message body" i]', '[aria-label*="message content" i]',
  ];
  for (const sel of SELS) {
    let els;
    try { els = document.querySelectorAll(sel); } catch (e) { continue; }
    let best = "";
    for (const el of els) {
      const t = deep(el);
      if (/\b(erid|advertisement|sponsored)\b|реклам|рекламодател|объявление скрыто/i.test(t)) continue;
      if (t.length > best.length) best = t;
    }
    if (best.length > 40) return best.slice(0, 8000);
  }
  return "";
}

// Runs IN the page (isolated world): extract the main content with Mozilla Readability
// (the Firefox Reader Mode engine) — robustly drops ads/nav/sidebars, returns the article
// body. Requires readability.js injected first (chrome.scripting files). Parses a CLONE
// (Readability mutates the doc). Returns {ok,text} or {ok:false} to fall back.
function runReadability() {
  try {
    if (typeof Readability !== "function") return { ok: false, reason: "no-lib" };
    const clone = document.cloneNode(true);
    const art = new Readability(clone).parse();
    const text = art && art.textContent ? art.textContent.replace(/\s+/g, " ").trim() : "";
    if (text.length > 40) return { ok: true, title: (art.title || ""), text };
    return { ok: false, reason: "empty" };
  } catch (e) { return { ok: false, reason: e.message }; }
}

// Runs IN the page (isolated world) — READ ONLY. Finds the on-screen element whose
// visible text (or aria-label) contains `want`, picks the TIGHTEST match (shortest
// text, i.e. the leaf that actually holds the label), then climbs to the nearest
// ACTIONABLE ancestor (row / link / button). Tags it data-gpref="__txt" so the normal
// click/navigate path can act on it. This is how we open list items (webmail messages
// etc.) that carry no clickable attribute of their own — the model just names the
// visible text it wants, which it already sees in the page content.
function resolveByText(wantRaw) {
  const norm = (s) => (s || "").toLowerCase().replace(/\s+/g, " ").trim();
  const want = norm(wantRaw);
  if (!want) return { ok: false, reason: "nėra teksto" };
  // Tokens the model gave us (drop tiny words) — used for fuzzy overlap when the exact
  // string isn't in one element (e.g. the model merged sender + subject, which live in
  // separate spans, or truncated the text).
  const wantTok = want.split(" ").filter((w) => w.length >= 3);
  const need = Math.max(2, Math.ceil(wantTok.length * 0.5));
  const SEL = 'a[href],button,[role="button"],[role="link"],[role="row"],' +
              '[role="listitem"],[role="option"],[role="menuitem"],[role="tab"],' +
              '[role="gridcell"],[role="article"],[onclick],[tabindex]';
  const isAct = (el) => { try { return !!(el.matches(SEL) || el.closest(SEL)); } catch (e) { return false; } };
  let best = null, bestScore = 0, bestLen = Infinity, bestAct = false;
  const nodes = document.body ? document.body.querySelectorAll("*") : [];
  for (const el of nodes) {
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) continue; // visible only
    const t = norm(el.innerText || el.getAttribute("aria-label") || "");
    if (!t || t.length > 500) continue;
    let score = 0;
    if (t.includes(want)) score = 10000; // exact contains — always wins
    else { for (const w of wantTok) if (t.includes(w)) score++; if (score < need) continue; }
    const actionable = isAct(el);
    // Prefer: higher overlap; then ACTIONABLE (a real link/button, not a heading with the
    // same text — so "Apsauga" hits the nav link, not the section title); then TIGHTEST.
    const better = score > bestScore ||
      (score === bestScore && actionable && !bestAct) ||
      (score === bestScore && actionable === bestAct && t.length < bestLen);
    if (better) { best = el; bestScore = score; bestLen = t.length; bestAct = actionable; }
  }
  if (!best) return { ok: false, reason: "nerasta pagal tekstą: " + want };
  const act = (best.closest && best.closest(SEL)) || best;
  act.setAttribute("data-gpref", "__txt");
  const label = (act.innerText || act.getAttribute("aria-label") || "").trim().replace(/\s+/g, " ").slice(0, 60);
  let href = "";
  try {
    const a = act.matches && act.matches("a[href]") ? act : (act.closest && act.closest("a[href]"));
    if (a && /^https?:/i.test(a.href)) href = a.href;
  } catch (e) {}
  let diag = "";
  try {
    diag = "tag=" + (act.tagName || "?") + " role=" + (act.getAttribute("role") || "-") +
      " href=" + (href || "-") + " html=" + (act.outerHTML || "").slice(0, 160).replace(/\s+/g, " ");
  } catch (e) {}
  return { ok: true, text: label, href, diag };
}

// Runs IN the page (isolated world). Clicks the element tagged data-gpref=<ref> like a
// real user (full pointer+mouse sequence, so the site's OWN handler fires). Used only
// when there is NO href to navigate to directly. Same-tab enforcement for any tab this
// spawns is done browser-side by moveNewTabToCurrent().
function clickByRef(ref) {
  const el = document.querySelector('[data-gpref="' + ref + '"]');
  if (!el) return { ok: false, reason: "elementas #" + ref + " nerastas" };
  const label = (el.innerText || el.value || el.getAttribute("aria-label") || "").trim().replace(/\s+/g, " ").slice(0, 60);

  // Neutralize target="_blank" on the element AND any ancestor link (attr + property).
  try {
    let n = el;
    for (let d = 0; n && d < 6; d++, n = n.parentElement) {
      if (n.tagName === "A") {
        try { n.target = "_self"; } catch (e) {}
        try { if (n.getAttribute("target")) n.setAttribute("target", "_self"); } catch (e) {}
      }
    }
  } catch (e) {}
  try { el.scrollIntoView({ block: "center" }); } catch (e) {}
  const o = { bubbles: true, cancelable: true, view: window, button: 0 };
  const seq = ["pointerover", "pointerenter", "mouseover", "mousemove",
               "pointerdown", "mousedown", "focus", "pointerup", "mouseup", "click"];
  for (const t of seq) {
    try {
      if (t === "focus") { if (typeof el.focus === "function") el.focus(); continue; }
      const Ctor = t.indexOf("pointer") === 0 && typeof PointerEvent !== "undefined" ? PointerEvent : MouseEvent;
      el.dispatchEvent(new Ctor(t, o));
    } catch (e) {}
  }
  if (typeof el.click === "function") { try { el.click(); } catch (e) {} }
  // Some app buttons (e.g. mail.ru "Reply") attach their handler to the TOPMOST element at
  // the click point (an inner span/icon), not the element we resolved — a plain el.click()
  // on the wrapper does nothing. Also fire the full sequence on document.elementFromPoint
  // at the element's centre, which is what a real click would hit.
  try {
    const r = el.getBoundingClientRect();
    const cx = Math.round(r.left + r.width / 2), cy = Math.round(r.top + r.height / 2);
    const hit = document.elementFromPoint(cx, cy);
    if (hit && hit !== el) {
      const o2 = { bubbles: true, cancelable: true, view: window, button: 0, clientX: cx, clientY: cy };
      for (const t of seq) {
        try {
          if (t === "focus") { if (typeof hit.focus === "function") hit.focus(); continue; }
          const C = t.indexOf("pointer") === 0 && typeof PointerEvent !== "undefined" ? PointerEvent : MouseEvent;
          hit.dispatchEvent(new C(t, o2));
        } catch (e) {}
      }
      if (typeof hit.click === "function") { try { hit.click(); } catch (e) {} }
    }
  } catch (e) {}
  return { ok: true, text: label };
}

async function applyToPage(text, mode) {
  try {
    const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    if (!tab || !tab.id) return { ok: false, reason: "nėra aktyvios kortelės" };
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: writeToPage,
      args: [{ text, mode }],
    });
    return result || { ok: false, reason: "nėra atsako iš puslapio" };
  } catch (e) {
    return { ok: false, reason: e.message + " (canvas redaktoriai, pvz. Google Docs, nepalaikomi)" };
  }
}

// Browser-level same-tab enforcement: after the click, if the site spawns a new tab
// (via window.open, target=_blank, ctrl-click, anything), grab that tab's real URL,
// load it into the ORIGINAL tab, and close the new one. Works on ANY site regardless
// of how it opened the tab — no page injection, no CSP, no MAIN world. The new tab may
// start as about:blank and get its URL set a moment later (the SPA window.open pattern),
// so we also watch onUpdated until a real http(s) URL appears.
function moveNewTabToCurrent(origTabId, timeoutMs = 4000) {
  return new Promise((resolve) => {
    let done = false;
    let updListener = null;
    const isReal = (u) => !!u && u !== "about:blank" && /^(https?|file):/i.test(u);
    const grab = (t) => (t && (t.url || t.pendingUrl)) || "";
    function cleanup() {
      try { chrome.tabs.onCreated.removeListener(onCreated); } catch (e) {}
      if (updListener) { try { chrome.tabs.onUpdated.removeListener(updListener); } catch (e) {} }
      clearTimeout(timer);
    }
    function finish(v) { if (done) return; done = true; cleanup(); resolve(v); }
    function move(newId, url) {
      chrome.tabs.update(origTabId, { url, active: true }).catch(() => {});
      chrome.tabs.remove(newId).catch(() => {});
      finish({ moved: true, url });
    }
    function onCreated(t) {
      if (t.openerTabId !== origTabId) return; // not spawned by our click
      const newId = t.id;
      const first = grab(t);
      if (isReal(first)) return move(newId, first);
      // URL not resolved yet — wait for it on this tab.
      updListener = (id, info) => {
        if (id !== newId) return;
        const u = info.url || grab(info) || "";
        if (isReal(u)) move(newId, u);
      };
      chrome.tabs.onUpdated.addListener(updListener);
    }
    chrome.tabs.onCreated.addListener(onCreated);
    const timer = setTimeout(() => finish({ moved: false }), timeoutMs);
  });
}

// Given a resolved target (info has {ok,href,text,diag}, and the page element is tagged
// data-gpref=<tag>): if it's an anchor, navigate the current tab straight to href (no
// click, no new tab, no flash); otherwise click it, with moveNewTabToCurrent as the
// browser-level same-tab fallback for JS window.open opens.
async function actOnResolved(tab, info, tag) {
  if (!info || !info.ok) return info || { ok: false, reason: "neatpažinta" };
  // NOTE: we deliberately do NOT navigate straight to info.href. On SPAs (mail.ru etc.)
  // a full load of a message URL destroys the app and serves a stripped page with no
  // content. We must CLICK the element so the site's OWN handler renders it in place
  // (same tab, no reload). Same-tab enforcement for anything that DOES spawn a tab is
  // handled by moveNewTabToCurrent (fallback only).
  moveNewTabToCurrent(tab.id);
  let result;
  // PRIMARY: real click via CDP (Input.dispatchMouseEvent) at the element's centre. Synthetic
  // DOM events are ignored by many hardened apps; a genuine browser click is what reliably
  // reaches their handlers. Fall back to the synthetic click if CDP is unavailable/fails.
  try {
    const [{ result: c }] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: refCenterFn, args: [tag] });
    if (c && c.ok) {
      const cc = await cdpClick(tab.id, c.x, c.y);
      if (cc && cc.ok) return { ok: true, text: c.label, diag: info.diag, sameTab: true };
    }
  } catch (e) { /* fall through to synthetic */ }
  try {
    const [{ result: r }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id }, func: clickByRef, args: [tag],
    });
    result = r || { ok: false, reason: "nėra atsako iš puslapio" };
  } catch (e) {
    result = { ok: false, reason: e.message };
  }
  if (result && !result.diag) result.diag = info.diag;
  return result;
}

async function clickInPage(ref) {
  try {
    const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    if (!tab || !tab.id) return { ok: false, reason: "nėra aktyvios kortelės" };
    let info;
    try {
      const [{ result: r }] = await chrome.scripting.executeScript({
        target: { tabId: tab.id }, func: readRef, args: [ref],
      });
      info = r || { ok: false, reason: "nėra atsako iš puslapio" };
    } catch (e) {
      info = { ok: false, reason: e.message };
    }
    return await actOnResolved(tab, info, ref);
  } catch (e) {
    return { ok: false, reason: e.message };
  }
}

// Open a list item by text, retrying while a virtualized list finishes rendering (after a
// fresh nav the rows may not be in the DOM yet, so a single try can miss them).
async function openItemWithRetry(text, tries = 5) {
  let last = { ok: false, reason: "nerasta" };
  for (let i = 0; i < tries; i++) {
    const r = await clickTextInPage(text);
    if (r && r.ok) return r;
    last = r || last;
    await new Promise((res) => setTimeout(res, 600));
    try { await captureContext(); } catch (e) {} // nudge/allow the list to render
  }
  return last;
}

// Click/open by VISIBLE TEXT (robust for list items with no clickable attribute — the
// model names the subject/label it sees, we find it and climb to the actionable row).
async function clickTextInPage(text) {
  try {
    const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    if (!tab || !tab.id) return { ok: false, reason: "nėra aktyvios kortelės" };
    let info;
    try {
      const [{ result: r }] = await chrome.scripting.executeScript({
        target: { tabId: tab.id }, func: resolveByText, args: [text],
      });
      info = r || { ok: false, reason: "nėra atsako iš puslapio" };
    } catch (e) {
      info = { ok: false, reason: e.message };
    }
    return await actOnResolved(tab, info, "__txt");
  } catch (e) {
    return { ok: false, reason: e.message };
  }
}

// Runs IN the page: click a toolbar button by EXACT label (e.g. "Переслать" vs "Ответить").
// Fuzzy resolveByText can climb to the whole toolbar and mis-click a neighbour; this picks
// the SMALLEST element whose own text/aria-label EXACTLY equals one of the labels.
function clickExactFn(payload) {
  const labels = (payload.labels || []).map((x) => String(x).toLowerCase().replace(/\s+/g, " ").trim());
  const norm = (s) => String(s || "").toLowerCase().replace(/\s+/g, " ").trim();
  // Scan ALL elements (not just button/role/a) — many webmail toolbars render actions
  // as plain <span>/<div> with no role/onclick/tabindex, so a narrow selector misses them.
  // Match on the element's own text OR aria-label/title, then pick the LEAF-most match
  // (fewest descendants) so we hit the actual label, not an ancestor toolbar container.
  const all = document.querySelectorAll("*");
  let best = null, bestKids = Infinity, bestLen = Infinity;
  for (const el of all) {
    const tag = (el.tagName || "").toLowerCase();
    if (tag === "script" || tag === "style" || tag === "svg" || tag === "path") continue;
    let r; try { r = el.getBoundingClientRect(); } catch (e) { continue; }
    if (!r || r.width < 4 || r.height < 4) continue;
    const t = norm(el.innerText || el.textContent);
    const a = norm(el.getAttribute && (el.getAttribute("aria-label") || el.title));
    const hit = labels.indexOf(t) !== -1 || labels.indexOf(a) !== -1;
    if (!hit) continue;
    const kids = el.querySelectorAll("*").length;   // leaf-most wins
    const len = (t || a).length;
    if (kids < bestKids || (kids === bestKids && len < bestLen)) { best = el; bestKids = kids; bestLen = len; }
  }
  if (!best) return { ok: false, reason: "nerastas mygtukas" };
  try { best.scrollIntoView({ block: "center" }); } catch (e) {}
  const o = { bubbles: true, cancelable: true, view: window, button: 0 };
  const fire = (el) => { for (const ty of ["pointerover", "mouseover", "mousemove", "pointerdown", "mousedown", "focus", "pointerup", "mouseup", "click"]) {
    try { if (ty === "focus") { el.focus && el.focus(); continue; } const C = ty.indexOf("pointer") === 0 && typeof PointerEvent !== "undefined" ? PointerEvent : MouseEvent; el.dispatchEvent(new C(ty, o)); } catch (e) {}
  } try { el.click && el.click(); } catch (e) {} };
  fire(best);
  // The real click handler is often on a parent/overlay: also click whatever is on top at
  // the element's center (bubbles up to the handler wherever it lives).
  try {
    const rr = best.getBoundingClientRect();
    const cx = rr.left + rr.width / 2, cy = rr.top + rr.height / 2;
    const top = document.elementFromPoint(cx, cy);
    if (top && top !== best) fire(top);
  } catch (e) {}
  return { ok: true, text: (best.innerText || best.getAttribute("aria-label") || "").trim().slice(0, 40) };
}
async function clickExactInPage(labels) {
  try {
    const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    if (!tab || !tab.id) return { ok: false };
    const [{ result }] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: clickExactFn, args: [{ labels }] });
    return result || { ok: false };
  } catch (e) { return { ok: false, reason: e.message }; }
}

// Runs IN the page: collect same-host page links (for site crawling). Cleans off hashes,
// drops non-page assets (pdf/img/zip/…), mailto/tel, and cross-host links. Returns unique
// {url,text}. Generic — no site-specific selectors.
function collectLinksFn() {
  const host = location.host;
  const out = [], seen = {};
  const anchors = document.querySelectorAll("a[href]");
  for (const a of anchors) {
    let u; try { u = new URL(a.getAttribute("href"), location.href); } catch (e) { continue; }
    if (u.host !== host) continue;
    if (!/^https?:$/.test(u.protocol)) continue;
    u.hash = "";
    const s = u.href;
    if (/\.(pdf|jpe?g|png|gif|svg|webp|zip|rar|docx?|xlsx?|pptx?|mp4|mp3|wav|webm|ico|css|js)(\?|$)/i.test(s)) continue;
    if (seen[s]) continue; seen[s] = 1;
    const t = (a.innerText || a.title || "").replace(/\s+/g, " ").trim().slice(0, 60);
    out.push({ url: s, text: t });
  }
  return out;
}

// Runs IN the page: type `text` into a SPECIFIC field tagged data-gpref=<ref> (input,
// textarea, select, or contenteditable). Generic form-filling for any site.
function fillFn(payload) {
  const { ref, text } = payload;
  const el = document.querySelector('[data-gpref="' + ref + '"]');
  if (!el) return { ok: false, reason: "laukas #" + ref + " nerastas" };
  const tag = (el.tagName || "").toLowerCase();
  const fire = (n) => { n.dispatchEvent(new Event("input", { bubbles: true })); n.dispatchEvent(new Event("change", { bubbles: true })); };
  try { el.focus(); } catch (e) {}
  try { el.scrollIntoView({ block: "center" }); } catch (e) {}
  if (tag === "select") {
    const want = String(text || "").toLowerCase().trim();
    let picked = null;
    for (const o of el.options) { if ((o.text || "").toLowerCase().trim() === want || (o.value || "").toLowerCase() === want) { picked = o; break; } }
    if (!picked) for (const o of el.options) { if ((o.text || "").toLowerCase().includes(want)) { picked = o; break; } }
    if (!picked) return { ok: false, reason: "nėra tinkamos parinkties" };
    el.value = picked.value; fire(el); return { ok: true, target: "select" };
  }
  if (tag === "input" || tag === "textarea") {
    el.value = text == null ? "" : String(text); fire(el); return { ok: true, target: tag };
  }
  // contenteditable / role=textbox rich editors (webmail compose bodies, mail.ru etc.)
  const editable = el.isContentEditable || el.getAttribute("contenteditable") === "true" ||
    el.getAttribute("contenteditable") === "" || el.getAttribute("role") === "textbox";
  if (editable) {
    const t = text == null ? "" : String(text);
    try {
      el.focus();
      // Clear the body, then insert ONLY the draft — predictable, clean result (avoids
      // landing inside a quoted original's markup). execCommand fires the input events
      // rich editors rely on; textContent is the fallback.
      const sel = window.getSelection();
      try { const range = document.createRange(); range.selectNodeContents(el); sel.removeAllRanges(); sel.addRange(range); document.execCommand("delete", false); } catch (e) {}
      const ok = document.execCommand("insertText", false, t);
      if (!ok) el.textContent = t;
    } catch (e) { try { el.textContent = t; } catch (e2) {} }
    fire(el);
    return { ok: true, target: "contenteditable" };
  }
  return { ok: false, reason: "elementas #" + ref + " nėra teksto laukas" };
}

// Runs IN the page: find the compose/reply BODY (the LARGEST visible editable — role=
// textbox / contenteditable / textarea; To/Subject are small inputs so they lose) and
// write the draft into it (clear first, clean insert). Deterministic — no ref guessing.
function fillComposeBody(payload) {
  const t = payload && payload.text != null ? String(payload.text) : "";
  const cands = document.querySelectorAll('[role="textbox"],[contenteditable="true"],[contenteditable=""],textarea');
  let best = null, bestA = 0;
  for (const el of cands) {
    let r; try { r = el.getBoundingClientRect(); } catch (e) { continue; }
    if (!r || r.width < 80 || r.height < 40) continue;
    try { const cs = getComputedStyle(el); if (cs && (cs.display === "none" || cs.visibility === "hidden")) continue; } catch (e) {}
    const a = r.width * r.height;
    if (a > bestA) { bestA = a; best = el; }
  }
  if (!best) return { ok: false, reason: "nerastas laiško kūno laukas" };
  try { best.focus(); best.scrollIntoView({ block: "center" }); } catch (e) {}
  const fire = (n) => { n.dispatchEvent(new Event("input", { bubbles: true })); n.dispatchEvent(new Event("change", { bubbles: true })); };
  // TEXTAREA: prepend draft, keep existing (quoted) text below.
  if (/^textarea$/i.test(best.tagName)) { best.value = t + "\n\n" + (best.value || ""); fire(best); return { ok: true, target: "textarea" }; }
  // CONTENTEDITABLE: PREPEND the draft as line-divs before the existing content (the quoted
  // original), so nothing is deleted. contenteditable stores each line as a block, so we
  // build one div per line (empty line -> <br>), then a blank separator, then leave the
  // quote in place.
  try {
    const frag = document.createDocumentFragment();
    for (const line of t.split("\n")) {
      const d = document.createElement("div");
      if (line) d.textContent = line; else d.innerHTML = "<br>";
      frag.appendChild(d);
    }
    const sep = document.createElement("div"); sep.innerHTML = "<br>";
    frag.appendChild(sep);
    best.insertBefore(frag, best.firstChild);
    fire(best);
    return { ok: true, target: "contenteditable" };
  } catch (e) {
    // Fallback: caret to very start + insertText (keeps existing content after it).
    try {
      const sel = window.getSelection();
      const range = document.createRange();
      range.setStart(best, 0); range.collapse(true);
      sel.removeAllRanges(); sel.addRange(range);
      const ok = document.execCommand("insertText", false, t + "\n\n");
      if (!ok) best.textContent = t + "\n\n" + (best.textContent || "");
    } catch (e2) { try { best.textContent = t + "\n\n" + (best.textContent || ""); } catch (e3) {} }
    fire(best);
    return { ok: true, target: "contenteditable" };
  }
}

// Runs IN the page: put a recipient email into the "To/Кому" field (input or chips box),
// firing input + Enter so the client turns it into a recipient chip. Best-effort — the
// human verifies the recipient before sending anyway.
function fillRecipientFn(payload) {
  const email = payload && payload.email ? String(payload.email) : "";
  if (!email) return { ok: false, reason: "nėra el. pašto" };
  // labelRe: which recipient field to target — default To/Кому; CC/BCC pass their own.
  let labRe; try { labRe = payload && payload.labelRe ? new RegExp(payload.labelRe, "i") : /кому|\bto\b|komu|gav[ėe]j|получател|recipient|адрес/; } catch (e) { labRe = /кому|\bto\b/i; }
  const named = !!(payload && payload.labelRe);
  let el = named ? null : document.querySelector('input[type="email"]');
  if (!el) {
    const cands = document.querySelectorAll('input:not([type="hidden"]),[role="textbox"],[contenteditable="true"]');
    for (const i of cands) {
      let r; try { r = i.getBoundingClientRect(); } catch (e) { continue; }
      if (!r || r.width < 40 || r.height < 10) continue;
      const lab = (((i.getAttribute("aria-label") || "") + " " + (i.getAttribute("placeholder") || "") + " " + (i.getAttribute("name") || "")).toLowerCase());
      if (labRe.test(lab)) { el = i; break; }
    }
  }
  if (!el && !named) { // fallback: first small visible text input in the compose header
    for (const i of document.querySelectorAll('input[type="text"],input:not([type])')) {
      let r; try { r = i.getBoundingClientRect(); } catch (e) { continue; }
      if (r && r.width > 60 && r.height > 10 && r.top < 400) { el = i; break; }
    }
  }
  if (!el) return { ok: false, reason: "nerastas Kam/To laukas" };
  try { el.focus(); el.scrollIntoView({ block: "center" }); } catch (e) {}
  // Clear any EXISTING recipient chips first (e.g. an accidentally prefilled sender) so a
  // forward goes ONLY to the intended address. Best-effort: click chip-remove controls in
  // the recipient row, and clear backspace-style.
  try {
    const row = el.closest('[class*="head"],[class*="recipient"],[class*="field"],[class*="rcpt"],[class*="to"]') || el.parentElement || document;
    const removers = row.querySelectorAll('[aria-label*="удалить" i],[aria-label*="remove" i],[aria-label*="pašalinti" i],[title*="удалить" i],[title*="remove" i],[class*="chip"] button,[class*="token"] button,[class*="pill"] button,[class*="recipient"] button');
    let n = 0;
    removers.forEach((rm) => { try { const r = rm.getBoundingClientRect(); if (r.width > 2 && r.height > 2 && n < 20) { rm.click(); n++; } } catch (e) {} });
  } catch (e) {}
  const isInput = /^(input|textarea)$/i.test(el.tagName);
  if (isInput) { el.value = email; } else { el.textContent = email; }
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
  // turn it into a chip (many webmail need Enter)
  for (const ty of ["keydown", "keypress", "keyup"]) {
    try { el.dispatchEvent(new KeyboardEvent(ty, { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true })); } catch (e) {}
  }
  return { ok: true, target: el.tagName };
}

async function fillRecipientInPage(email, labelRe) {
  try {
    const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    if (!tab || !tab.id) return { ok: false, reason: "nėra kortelės" };
    const [{ result }] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: fillRecipientFn, args: [{ email, labelRe }] });
    return result || { ok: false, reason: "nėra atsako" };
  } catch (e) { return { ok: false, reason: e.message }; }
}

// Reveal CC/BCC (click the toggle) then fill that named recipient field.
async function addCcBcc(kind, email) {
  const toggles = kind === "cc" ? ["Копия", "Cc", "CC", "Kopija", "Copy"] : ["Скрытая", "Bcc", "BCC", "Nematoma", "Скрытая копия"];
  await clickExactInPage(toggles);
  await new Promise((r) => setTimeout(r, 400));
  const labelRe = kind === "cc" ? "копи|\\bcc\\b|copy|kopij" : "скрыт|\\bbcc\\b|hidden|nematom";
  return fillRecipientInPage(email, labelRe);
}

async function fillComposeInPage(text) {
  try {
    const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    if (!tab || !tab.id) return { ok: false, reason: "nėra kortelės" };
    const [{ result }] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: fillComposeBody, args: [{ text }] });
    return result || { ok: false, reason: "nėra atsako" };
  } catch (e) { return { ok: false, reason: e.message }; }
}

// Runs IN the page: press a key (Enter/Tab/Escape/…) on a field or the active element —
// e.g. submit a search box. Full keydown/keypress/keyup, plus a form submit for Enter.
function pressKeyFn(payload) {
  const { key, ref } = payload;
  const el = (ref != null && document.querySelector('[data-gpref="' + ref + '"]')) || document.activeElement || document.body;
  const k = key || "Enter";
  const map = { Enter: 13, Tab: 9, Escape: 27, ArrowDown: 40, ArrowUp: 38 };
  const code = map[k] || 0;
  try { el.focus && el.focus(); } catch (e) {}
  for (const type of ["keydown", "keypress", "keyup"]) {
    try {
      const ev = new KeyboardEvent(type, { key: k, code: k, keyCode: code, which: code, bubbles: true, cancelable: true });
      el.dispatchEvent(ev);
    } catch (e) {}
  }
  if (k === "Enter") {
    try { const f = el.form || (el.closest && el.closest("form")); if (f) { if (f.requestSubmit) f.requestSubmit(); else f.submit(); } } catch (e) {}
  }
  return { ok: true };
}

async function fillInPage(ref, text) {
  try {
    const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    if (!tab || !tab.id) return { ok: false, reason: "nėra kortelės" };
    const [{ result }] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: fillFn, args: [{ ref, text }] });
    return result || { ok: false, reason: "nėra atsako" };
  } catch (e) { return { ok: false, reason: e.message }; }
}
async function pressKey(key, ref) {
  try {
    const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    if (!tab || !tab.id) return { ok: false, reason: "nėra kortelės" };
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: pressKeyFn, args: [{ key, ref }] });
    return { ok: true };
  } catch (e) { return { ok: false, reason: e.message }; }
}

// Restore a snapshot (Undo). Runs IN the page.
function restoreFn(p) {
  const el = window.__gpLastEditable;
  if (!el) return { ok: false };
  if (/^(textarea|input)$/i.test(el.tagName || "")) el.value = p.before;
  else el.innerHTML = p.before;
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
  return { ok: true };
}

async function restorePage(before) {
  try {
    const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: restoreFn, args: [{ before }] });
  } catch (e) {
    addMsg("error", "Atšaukti nepavyko: " + e.message);
  }
}

function addUndo(el, before) {
  if (before == null) return;
  const bar = document.createElement("div");
  bar.className = "actions";
  const b = document.createElement("button");
  b.className = "mini";
  b.textContent = "↩ Atšaukti";
  b.addEventListener("click", () => restorePage(before));
  bar.appendChild(b);
  el.appendChild(bar);
}

// Pull the {op,text} action out of the model reply (tolerates code fences / prose).
// Extract the FIRST balanced {...} object (string-aware), so trailing junk or a stray extra
// brace the model sometimes appends (…"max":5}}) doesn't break parsing.
function firstJsonObject(s) {
  const i = s.indexOf("{");
  if (i < 0) return null;
  let depth = 0, inStr = false, esc = false;
  for (let j = i; j < s.length; j++) {
    const ch = s[j];
    if (inStr) { if (esc) esc = false; else if (ch === "\\") esc = true; else if (ch === '"') inStr = false; continue; }
    if (ch === '"') inStr = true;
    else if (ch === "{") depth++;
    else if (ch === "}") { depth--; if (depth === 0) return s.slice(i, j + 1); }
  }
  return null;
}
function parseAction(raw) {
  if (!raw) return null;
  let s = String(raw).trim().replace(/^```(json)?/i, "").replace(/```$/, "").trim();
  // Prefer the balanced object; fall back to a greedy match for odd cases.
  const cand = firstJsonObject(s) || (s.match(/\{[\s\S]*\}/) || [])[0];
  if (!cand) return null;
  try {
    const o = JSON.parse(cand);
    if (o && typeof o.op === "string") return o;
  } catch (e) {}
  // Lenient fallback: models often emit op=answer/note with RAW (unescaped) newlines inside
  // the "text" value, which is invalid JSON so JSON.parse throws. Extract op + common string
  // fields by regex so a good answer isn't shown as raw JSON.
  return looseParseAction(cand);
}
// Regex-extract {op, text/instruction/question/url/...} from JSON that JSON.parse rejected
// (usually because of unescaped newlines in a long text value).
function looseParseAction(s) {
  const op = (s.match(/"op"\s*:\s*"([a-zA-Z_]+)"/) || [])[1];
  if (!op) return null;
  const o = { op: op };
  // The main free-text field: take everything from "text":" to the LAST quote before the
  // closing brace, un-escaping \" and \n. Handles multi-line unescaped bodies.
  const bodyKey = /"(text|instruction|question|note)"\s*:\s*"/.exec(s);
  if (bodyKey) {
    const start = bodyKey.index + bodyKey[0].length;
    const rest = s.slice(start);
    const end = rest.lastIndexOf('"');
    if (end > 0) {
      o[bodyKey[1]] = rest.slice(0, end).replace(/\\"/g, '"').replace(/\\n/g, "\n").replace(/\\t/g, "\t").trim();
    }
  }
  for (const k of ["url", "which", "cc", "bcc", "to", "email", "fromText", "key", "dir", "goal"]) {
    const m = new RegExp('"' + k + '"\\s*:\\s*"([^"\\\\]*)"').exec(s);
    if (m) o[k] = m[1];
  }
  const num = /"(nth|count|max)"\s*:\s*(\d+)/.exec(s);
  if (num) o[num[1]] = parseInt(num[2], 10);
  return o;
}

// Skill-learning: after a successful task, offer to package the working action sequence
// into a reusable, generalized OWUI skill (the model writes the recipe; we POST it to the
// skills library). Next time a similar task can self-select this learned skill.
function addLearnButton(el, goal, trajectory, model) {
  const acts = (trajectory || []).filter((a) => a && a.op && !["answer", "done", "finish", "note"].includes(a.op));
  if (acts.length < 1) return; // nothing procedural worth learning
  const bar = document.createElement("div");
  bar.className = "actions";
  const b = document.createElement("button");
  b.className = "mini";
  b.textContent = "🎓 Išmokti";
  b.title = "Išsaugoti šią veiksmų seką kaip pakartojamą skill (OWUI biblioteka)";
  b.addEventListener("click", async () => {
    b.disabled = true; b.textContent = "mokausi…";
    const savedMention = ACTIVE_MENTION; ACTIVE_MENTION = "";
    try {
      const steps = acts.map((a, i) => (i + 1) + ". " + a.op +
        (a.text ? " (" + String(a.text).slice(0, 40) + ")" : a.fromText ? " (fromText:" + a.fromText + (a.nth ? ",nth:" + a.nth : "") + ")" : a.to ? " (" + a.to + ")" : a.ref != null ? " (#" + a.ref + ")" : "")).join("\n");
      const p = "Iš šios SĖKMINGOS naršyklės-agento užduoties sukurk PAKARTOJAMĄ, GENERALIZUOTĄ skill (receptą).\n" +
        "UŽDUOTIS: «" + goal + "»\nATLIKTI VEIKSMAI:\n" + steps + "\n\n" +
        "Grąžink TIK JSON (be jokio kito teksto): {\"id\":\"trumpas-kebab-id\",\"name\":\"Pavadinimas\",\"description\":\"kada naudoti, 1 sakinys\",\"content\":\"glaustos GENERALIZUOTOS instrukcijos su mūsų op'ais (click/fill/read_items/draft_reply/forward/navigate/back/answer), be konkrečių reikšmių, + saugos taisyklė: nesiųsti/netrinti (spaudžia žmogus)\"}";
      const out = await askLLM(model, p);
      let sk = null; try { const m = (out.raw || "").match(/\{[\s\S]*\}/); if (m) sk = JSON.parse(m[0]); } catch (e) {}
      if (!sk || !sk.id || !sk.content) { b.textContent = "⚠ nepavyko sukurti"; return; }
      sk.id = String(sk.id).toLowerCase().replace(/[^a-z0-9_-]/g, "-").replace(/^-+|-+$/g, "").slice(0, 40) || "learned-skill";
      const form = { id: sk.id, name: sk.name || sk.id, description: sk.description || "", content: sk.content, meta: { tags: ["learned"] } };
      let r = await api("/api/v1/skills/create", { method: "POST", body: JSON.stringify(form) });
      if (r.status === 400) r = await api("/api/v1/skills/id/" + sk.id + "/update", { method: "POST", body: JSON.stringify(form) });
      if (r.ok) { SKILLS_CACHE = null; b.textContent = "✓ išmokta: " + sk.id; }
      else if (r.status === 401 || r.status === 403) b.textContent = "⚠ nėra teisių (workspace.skills)";
      else b.textContent = "⚠ HTTP " + r.status;
    } catch (e) { b.textContent = "⚠ " + e.message; }
    finally { ACTIVE_MENTION = savedMention; }
  });
  bar.appendChild(b);
  el.appendChild(bar);
}

function addActions(el, text) {
  // Answers only get "Kopijuoti" — edit ops auto-apply to the page (with Undo), so
  // manual insert/replace buttons here just confused users on Q&A replies.
  if (!text) return;
  const bar = document.createElement("div");
  bar.className = "actions";
  const b = document.createElement("button");
  b.className = "mini";
  b.textContent = "Kopijuoti";
  b.addEventListener("click", () => navigator.clipboard.writeText(text).catch(() => {}));
  bar.appendChild(b);
  el.appendChild(bar);
}

async function injectTracker() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    if (tab && tab.id) {
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: installTracker });
    }
  } catch (e) {
    /* chrome:// and store pages can't be injected — ignore */
  }
}

// Heuristic: are we sitting on a login / auth page? (Session expired, or a back-nav
// walked into an OAuth redirect.) If so the agent must STOP, not keep clicking.
function looksLikeAuth(ctx) {
  const u = (ctx.url || "").toLowerCase();
  if (/\/(auth|login|signin|sign-in|logon)(\/|\?|#|$)/.test(u)) return true;
  if (/id\.vk\.|o2\.mail\.ru\/login|accounts\.google|login\.(microsoft|live)|okta\.|auth0\./.test(u)) return true;
  const t = (ctx.text || "").toLowerCase();
  if (t.length < 500 && /(sign in|log in|prisijung|prisijunkite|войти|вход в|password|slaptažod|passwort)/.test(t)) return true;
  return false;
}

async function captureContext() {
  await injectTracker();
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab || !tab.id) throw new Error("nėra aktyvios kortelės");
  if (/^(chrome|edge|about|chrome-extension|devtools|view-source):/i.test(tab.url || "")) {
    throw new Error("puslapis neprieinamas (naršyklės vidinis: " + (tab.url || "") + ")");
  }
  // Read ALL frames, not just the top document: webmail (mail.ru, Gmail, Outlook) renders
  // the message BODY inside an <iframe>, which top-level body.innerText can't see. The
  // extension has host permissions, so it can inject into sub-frames (even cross-origin)
  // and pull their text. Main frame (frameId 0) provides selection + clickables; sub-frame
  // text is appended so the model actually gets the email body.
  let results;
  try {
    results = await chrome.scripting.executeScript({
      target: { tabId: tab.id, allFrames: true },
      func: grabPage,
    });
  } catch (e) {
    // allFrames can fail on some pages — fall back to the top frame only.
    results = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: grabPage });
  }
  const main = (results.find((r) => r.frameId === 0) || results[0] || {}).result || {};
  let extra = "";
  for (const r of results) {
    if (r.frameId === 0 || !r.result || !r.result.text) continue;
    if (r.result.text.length < 15) continue; // skip trivial ad/tracker frames
    extra += "\n\n[rėmelio turinys]\n" + r.result.text;
  }
  main.text = ((main.text || "") + extra).trim();
  main.url = main.url || tab.url || "";
  return main;
}

// Capture, but WAIT for the page to stop changing — after opening an item (esp. an SPA
// message view) the body loads asynchronously, so an immediate read catches transitional
// content. Re-reads every ~600ms until the text length settles (±8%) and is non-trivial,
// or maxWait elapses. This is what lets the agent actually SEE the opened email body.
// Strip the boilerplate that every view shares (nav/chrome/skip-links) by removing the
// longest common prefix with a baseline (the list view). What remains is the item's OWN
// content — critical so two opened records don't look "identical" (their bodies both
// begin with the same ~800 chars of navigation). Generic, no site specifics.
function stripCommon(base, text) {
  if (!base || !text) return text || "";
  let i = 0; const n = Math.min(base.length, text.length);
  while (i < n && base[i] === text[i]) i++;
  const rest = text.slice(i).replace(/^\S*/, "").trim(); // drop the partial word at the cut
  return rest.length > 20 ? rest : text; // if almost nothing left, keep original
}

// After opening a list item, the small body region can lag (URL changes first, the body
// div re-renders a moment later) while overall page text looks "stable". So poll the KNOWN
// body extractor until it yields non-trivial content that DIFFERS from the previous item's
// body (or times out) — this is what stops us re-reading the previous email's content.
async function readBodyChanged(tabId, prevBody, maxMs = 6000) {
  const start = Date.now();
  let body = "";
  let sawKnown = false;
  while (Date.now() - start < maxMs) {
    try {
      const [{ result }] = await chrome.scripting.executeScript({ target: { tabId }, func: pickKnownBody });
      body = result || "";
    } catch (e) {}
    if (body) sawKnown = true;
    if (body.length > 40 && body !== prevBody) return body; // new known body rendered
    // Not a known-body layout (e.g. a product/article page) — don't hang; let the caller
    // fall back to Readability quickly.
    if (!sawKnown && Date.now() - start > 1500) return "";
    await new Promise((r) => setTimeout(r, 350));
  }
  return body;
}

async function captureStable(maxWaitMs = 8000) {
  const start = Date.now();
  let best = await captureContext();
  let bestLen = (best.text || "").length;
  let stableRounds = 0;
  // Keep re-reading; the body of an opened item loads LATE, so we track the LARGEST
  // capture seen and only stop once it stops growing (2 quiet rounds) or we time out.
  // Returning the max — not the first "stable" read — is what catches late content.
  while (Date.now() - start < maxWaitMs) {
    await new Promise((r) => setTimeout(r, 500));
    const c = await captureContext();
    const len = (c.text || "").length;
    if (len > bestLen) { best = c; bestLen = len; stableRounds = 0; }
    else { stableRounds++; }
    if (stableRounds >= 2 && bestLen > 200) break;
  }
  // Google Docs/Sheets/Slides: body is on a canvas (not in the DOM) — grabPage only saw the
  // UI chrome. Fetch the REAL text via the export endpoint HERE (once, on the final result)
  // from the extension context (bypasses the googleusercontent CORS wall). Applied AFTER the
  // length-based loop so a shorter doc-text can't be discarded in favour of longer UI chrome.
  const durl = best.url || "";
  if (/^https:\/\/docs\.google\.com\/(document|spreadsheets|presentation)\//.test(durl)) {
    try {
      const doc = await fetchDocExport(durl);
      if (!doc) best._docExportInfo = "null (URL be /d/<id>? " + durl.slice(0, 60) + ")";
      else if (doc.ok && doc.text && doc.text.trim().length > 0) { best.text = "[DOKUMENTO TEKSTAS]\n" + doc.text; best._docExport = true; best._docExportInfo = "ok " + doc.text.length; }
      else if (doc.ok) best._docExportInfo = "dokumentas tikrai tuščias";
      else best._docExportFail = best._docExportInfo = "fail " + (doc.status || doc.error || "?");
    } catch (e) { best._docExportFail = best._docExportInfo = "klaida: " + ((e && e.message) || e); }
  }
  return best;
}

// ---- Agent loop ------------------------------------------------------------
// The panel is an AGENT, not a one-shot: it perceives the page, picks ONE action,
// applies it, RE-perceives, and repeats until the model returns a final answer. This is
// what lets it do multi-step tasks ("open each of the 3 newest emails and summarise")
// generically on any site — not just single clicks/edits.
const MAX_STEPS = 15;

// Irreversible / outward-facing action controls the AGENT must NOT click on its own — a
// human presses these. Matched against the control's visible label (multilingual). The
// agent may OPEN a reply/compose form and FILL a draft, but the actual Send/Submit/Delete
// is handed off to the user.
const DANGEROUS_RE = /^(\s*)(siųsti|si[ųu]sti žinut[ęe]|send|send now|send message|отправить|отправ\w*|надіслати|submit|pateikti|delete|ištrinti|trinti|удалить|удалить навсегда|переместить в корзину|move to trash|publish|paskelbti|опубликовать|confirm|patvirtinti|подтвердить|pay|apmokėti|mokėti|оплатить|buy|pirkti|купить|order now|užsakyti dabar)(\b|\s|$)/i;

// Wait for the tab to settle after an action: resolve on load "complete" (+a short
// render delay) or a timeout (SPA soft-nav fires no load event).
function waitSettle(tabId, ms = 1600) {
  return new Promise((resolve) => {
    let done = false;
    const fin = () => { if (done) return; done = true; try { chrome.tabs.onUpdated.removeListener(l); } catch (e) {} clearTimeout(t); resolve(); };
    const l = (id, info) => { if (id === tabId && info.status === "complete") { clearTimeout(t); setTimeout(fin, 500); } };
    chrome.tabs.onUpdated.addListener(l);
    const t = setTimeout(fin, ms);
  });
}

// Agent run state + abort (for the Stop button). CURRENT_ABORT aborts the in-flight LLM
// fetch; AGENT_ABORT stops the loop between steps.
let RUNNING = false;
let AGENT_ABORT = false;
let CURRENT_ABORT = null;
// The tab the conversation is anchored to (the doc/page we last worked on). Used so a
// follow-up question doesn't read a tab the user happened to switch to.
let WORK_TAB_ID = null;
// The chosen OWUI skill, injected each turn via a <$id> mention (OWUI expands it to the
// skill's full recipe server-side). Set per task by pickSkill().
let ACTIVE_MENTION = "";
let SKILLS_CACHE = null;

// Fetch the thematic skill manifest (id + description) from OWUI (admin-curated library).
async function loadSkills() {
  if (SKILLS_CACHE) return SKILLS_CACHE;
  try {
    const r = await api("/api/v1/skills/");
    if (r.ok) {
      const d = await r.json();
      SKILLS_CACHE = (Array.isArray(d) ? d : (d.data || [])).map((s) => ({ id: s.id, name: s.name, description: s.description || "" }));
    } else SKILLS_CACHE = [];
  } catch (e) { SKILLS_CACHE = []; }
  return SKILLS_CACHE;
}

// Self-selection: ask the model which skill best fits the task (one cheap call), so the
// agent follows a proven recipe instead of improvising each time.
// Deterministic host → app-skill map. Known app URLs ALWAYS route to their skill (no model
// guess), so the same site can't flip between google-docs/summarize/web-research run to run.
const HOST_SKILL = [
  [/docs\.google\.com\/spreadsheets/, "google-sheets"],
  [/docs\.google\.com\/(document|presentation)/, "google-docs"],
  [/drive\.google\.com/, "google-drive"],
  [/mail\.google\.com/, "gmail"],
  [/calendar\.google\.com/, "google-calendar"],
  [/outlook\.(office|office365|live)\.com|outlook\.com/, "outlook365"],
  [/teams\.microsoft\.com|teams\.live\.com/, "teams"],
  [/[\w-]+\.sharepoint\.com|onedrive\.live\.com/, "sharepoint"],
];
async function pickSkill(goal, model, site) {
  const sk = await loadSkills();
  if (!sk.length) return null;
  // 1) Deterministic app routing by URL — reliable, consistent, zero model cost.
  const url = String(site || "");
  for (const [re, id] of HOST_SKILL) {
    if (re.test(url) && sk.find((s) => s.id === id)) return id;
  }
  // 2) Otherwise let the model pick a generic/task skill.
  const manifest = sk.map((s) => "- " + s.id + ": " + (s.description || s.name)).join("\n");
  const p = "SVETAINĖ (dabartinė): " + (site || "?") + "\n\nTurimi įgūdžiai (skills):\n" + manifest +
    "\n\nUŽDUOTIS: «" + goal + "»\n\nParink VIENĄ tinkamiausią skill id. SVARBU: programai skirtą skill " +
    "(gmail, outlook365, sharepoint, teams, word-online, excel-online, google-drive/docs/sheets/calendar) " +
    "rink TIK jei DABARTINĖ SVETAINĖ atitinka tą programą (spręsk pagal URL, ne pagal žodžius užduotyje — " +
    "pvz. gavėjo el. pašto domenas @gmail.com NEREIŠKIA, kad esi Gmail). Priešingu atveju rink bendrą " +
    "(email, lists, forms, web-research, ...). Atsakyk TIK id (vienu žodžiu) arba 'none'.";
  try {
    const out = await askLLM(model, p);
    const id = (out.raw || "").trim().toLowerCase().replace(/[^a-z0-9_-]/g, "");
    return sk.find((s) => s.id === id) ? id : null;
  } catch (e) { return null; }
}

function setRunning(on) {
  RUNNING = on;
  const s = $("send"), st = $("stop");
  if (s) s.classList.toggle("hidden", on);
  if (st) st.classList.toggle("hidden", !on);
}
function stopAgent() {
  AGENT_ABORT = true;
  try { if (CURRENT_ABORT) CURRENT_ABORT.abort(); } catch (e) {}
  if (PENDING_ASK) { const r = PENDING_ASK; PENDING_ASK = null; r(null); }
}

// Universal "ask the user" mechanism. op=ask pauses the agent, shows a question, and waits
// for the user's next input (captured by send() below instead of starting a new run). Used
// generically — e.g. to agree scope/limits before a large job, or to clarify an ambiguous
// task. Resolves to the user's text, or null if the run is stopped while waiting.
let PENDING_ASK = null;
function askUser(question) {
  return new Promise((resolve) => {
    addMsg("assistant", "❓ " + question);
    PENDING_ASK = resolve;
    try { $("q").focus(); } catch (e) {}
  });
}

async function askLLM(model, prompt, opts) {
  const controller = new AbortController();
  CURRENT_ABORT = controller;
  // isolate: skip conversation history — used for composing (a reply/forward draft) so stale
  // data from earlier turns (e.g. a previous recipient's email) can't leak into the new text.
  const hist = opts && opts.isolate ? [] : CONVO;
  // noSkill: skip the active-skill mention. Internal synthesis/compose calls want PLAIN prose
  // — with the skill injected, the model copies its "return ONE JSON op" rule and emits
  // {"op":"answer",...} instead of the text we asked for.
  const mention = opts && opts.noSkill ? "" : ACTIVE_MENTION;
  const r = await api("/api/chat/completions", {
    method: "POST",
    body: JSON.stringify({ model, messages: [...hist, { role: "user", content: mention + prompt }], stream: false }),
    signal: controller.signal,
  });
  CURRENT_ABORT = null;
  if (r.status === 401 || r.status === 403) return { authFail: true };
  if (!r.ok) throw new Error("HTTP " + r.status);
  const data = await r.json();
  return { raw: data?.choices?.[0]?.message?.content ?? data?.message?.content ?? "" };
}

// Defensive: if a synthesis/compose reply still comes back as an agent JSON op (```json
// {"op":"answer","text":"…"}```), unwrap it to the plain text so we never show raw JSON.
function unwrapAnswer(s) {
  let t = String(s || "").trim();
  const f = t.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (f) t = f[1].trim();
  if (t.charAt(0) === "{" && /"op"\s*:/.test(t)) {
    const cand = firstJsonObject(t) || t;
    try { const o = JSON.parse(cand); if (o && typeof o.text === "string") return o.text.trim(); } catch (e) {}
  }
  return String(s || "").trim();
}

function scrollFn(dir) {
  const d = dir === "up" ? -1 : 1;
  window.scrollBy(0, d * Math.round((window.innerHeight || 600) * 0.85));
  return { ok: true };
}
async function doScroll(dir) {
  try {
    const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    if (tab && tab.id) await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: scrollFn, args: [dir || "down"] });
  } catch (e) {}
}
// Go back IN THE PAGE (history.back) rather than chrome.tabs.goBack: SPA routers listen
// to popstate and return to the previous in-app view (the list) with NO full reload.
// chrome.tabs.goBack instead walked the document history out of the app (into an OAuth
// page, then chrome://) — avoid it.
function historyBackFn() { try { window.history.back(); return { ok: true }; } catch (e) { return { ok: false }; } }
async function goBack() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    if (tab && tab.id) {
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: historyBackFn });
      await waitSettle(tab.id);
    }
  } catch (e) {}
}

// A small muted progress line ("▸ …") for each agent step.
function addStep(text) {
  const el = document.createElement("div");
  el.className = "muted";
  el.style.margin = "2px 0 2px 4px";
  el.textContent = "▸ " + text;
  $("log").appendChild(el);
  $("log").scrollTop = $("log").scrollHeight;
  return el;
}

// Human-in-the-loop consent. The agent may freely read and navigate the CURRENT site,
// but clicking a link that leaves it (a different host — typically a link INSIDE an
// email body) needs the user's explicit OK first. Resolves true only if the user clicks
// "Taip".
function askConsent(url) {
  return new Promise((resolve) => {
    const box = addMsg("assistant", "⚠ Agentas nori atidaryti nuorodą už šios svetainės ribų:\n" + url + "\nLeisti?");
    const bar = document.createElement("div");
    bar.className = "actions";
    const yes = document.createElement("button");
    yes.className = "mini";
    yes.textContent = "Taip, atidaryti";
    const no = document.createElement("button");
    no.className = "mini";
    no.textContent = "Ne";
    let answered = false;
    const done = (v) => { if (answered) return; answered = true; bar.remove(); resolve(v); };
    yes.addEventListener("click", () => done(true));
    no.addEventListener("click", () => done(false));
    bar.appendChild(yes);
    bar.appendChild(no);
    box.appendChild(bar);
    $("log").scrollTop = $("log").scrollHeight;
  });
}

function sameHost(a, b) {
  try { return new URL(a).host === new URL(b).host; } catch (e) { return true; }
}

// Fold Lithuanian diacritics + lowercase, so search matches regardless of accents/case.
function foldLt(s) {
  return String(s || "").toLowerCase()
    .replace(/ą/g, "a").replace(/č/g, "c").replace(/ę/g, "e").replace(/ė/g, "e")
    .replace(/į/g, "i").replace(/š/g, "s").replace(/ų/g, "u").replace(/ū/g, "u").replace(/ž/g, "z");
}
// LOCAL retrieval over a large document (no LLM cost): find where the QUERY terms occur and
// return only the surrounding passages. Keeps big docs cheap — we send ~10K of relevant text
// to the model, not the whole 50K+. Lithuanian-aware (diacritics folded, stems matched to
// cover inflections: "hibridinį" → stem "hibrid" matches "hibridinis/hibridinio/…").
const _DOC_STOP = new Set(["kas","apie","yra","kaip","kur","kada","kodel","koks","kokia","kokie","kokiu","kiek","parasyta","dokumente","dokumentas","dokumento","dokumenta","tekste","tekstas","noriu","reikia","prasau","what","about","does","say","how","the","this","that","from","with"]);
function docExcerpts(fullText, query, cap) {
  cap = cap || 12000;
  const text = String(fullText || "");
  if (text.length <= cap) return { text: text, retrieved: false };
  const words = foldLt(query).split(/[^a-z0-9]+/).filter((w) => w.length >= 4 && !_DOC_STOP.has(w));
  if (!words.length) return { text: text.slice(0, cap), retrieved: false, noQuery: true };
  const stems = words.map((w) => (w.length > 6 ? w.slice(0, 6) : w));
  const fold = foldLt(text);
  const hits = [];
  for (const st of stems) {
    let i = 0;
    while (hits.length < 400 && (i = fold.indexOf(st, i)) !== -1) { hits.push(i); i += st.length; }
  }
  if (!hits.length) return { text: text.slice(0, cap), retrieved: false, noHits: true };
  hits.sort((a, b) => a - b);
  const W = 500, ranges = [];
  for (const h of hits) {
    const s = Math.max(0, h - W), e = Math.min(text.length, h + W);
    const last = ranges[ranges.length - 1];
    if (last && s <= last[1] + 80) last[1] = Math.max(last[1], e);
    else ranges.push([s, e]);
  }
  let out = "";
  for (const [s, e] of ranges) {
    if (out.length >= cap) break;
    out += (out ? "\n…\n" : "") + text.slice(s, Math.min(e, s + (cap - out.length)));
  }
  return { text: out, retrieved: true, hitCount: hits.length };
}

function buildAgentPrompt(goal, notes, ctx) {
  const sel = (ctx.selection || "").trim();
  // Large exported document text: don't dump the whole thing (burns tokens, doesn't scale).
  // Retrieve only the passages relevant to the goal locally (free), send just those.
  let page, docNote = "";
  if (ctx._docExport && (ctx.text || "").length > 14000) {
    // Completeness questions ("everything/list all/summarize") need broad coverage — raise
    // the excerpt budget so all matching passages fit; targeted questions stay cheap.
    const wantsAll = /\b(visk|vis[aąų]|visi|visus|visos|surašyk|surasyk|išvardin|isvardin|apibendrin|santrauk|everything|\ball\b|\blist\b|summ)/i.test(goal || "");
    const ex = docExcerpts(ctx.text, goal, wantsAll ? 40000 : 12000);
    page = ex.text;
    docNote = ex.retrieved ? "\n(TURINYS = svarbiausios dokumento ištraukos pagal užklausą; „…“ = praleista)\n"
      : ex.noHits ? "\n(dokumente nerasta tiesioginių užklausos atitikmenų — rodoma pradžia; jei reikia, patikslink)\n" : "";
  } else {
    page = (ctx.text || "").slice(0, MAX_CTX);
  }
  const clk = (ctx.clickables || []).map((c) => `[${c.i}] ${c.t}`).join("\n");
  return (
    "Tu esi naršyklės AGENTAS bet KURIAME puslapyje. Gali skaityti puslapį, atidaryti/spausti elementus, " +
    "grįžti atgal, slinkti ir redaguoti tekstą, kad ĮVYKDYTUM UŽDUOTĮ per kelis žingsnius. Būk UNIVERSALUS: " +
    "nesiremk konkrečios svetainės ypatumais — remkis TURINIU ir ELEMENTAIS, kuriuos matai.\n" +
    "Tekste gali pasitaikyti žymių GP_xxxx arba [PERSON]/[EMAIL]/[ID]/[ADDRESS]/[PHONE] — tai UŽMASKUOTI " +
    "tikri duomenys; laikyk juos normaliomis reikšmėmis, cituok kaip yra (bus automatiškai atstatyti). " +
    "SVARBU: vartotojui NIEKADA nekalbėk apie pačias žymes, „maskavimą“ ar techninius tokenus — rašyk natūraliai, tarsi matytum tikras reikšmes.\n\n" +
    "UŽDUOTIS: «" + goal + "»\n\n" +
    (notes.length ? "KĄ JAU PADAREI / SUŽINOJAI (tavo pastabos):\n" + notes.map((n, i) => (i + 1) + ". " + n).join("\n") + "\n\n" : "") +
    "DABARTINIS PUSLAPIS: «" + (ctx.title || "") + "»\n" +
    "URL: " + (ctx.url || "") + "\n" +
    (sel ? "PAŽYMĖTA: «" + sel + "»\n" : "") +
    "TURINYS: «" + page + "»" + docNote + "\n" +
    (clk ? "ELEMENTAI (spaudžiami) — [nr] tekstas:\n" + clk + "\n" : "") +
    "\nGrąžink TIK JSON (VIENĄ veiksmą, jokio kito teksto):\n" +
    '{"op":"read_items","fromText":"Admin","nth":3,"note":"..."} — REKOMENDUOJAMA „N-tam nuo X“: perskaityti VIENĄ įrašą — N-tą (1-based, iš viršaus) tarp tų, kurių eilutė prasideda „X“ (siuntėjas/požymis). Sistema PATI suskaičiuoja — TU NESKAIČIUOK. („trečias nuo Admin“ = fromText:"Admin", nth:3.)\n' +
    '{"op":"read_items","fromText":"Admin","count":2,"note":"..."} — arba PIRMUS N tokių įrašų (count).\n' +
    '{"op":"read_items","refs":[NR,NR],"note":"..."} — arba KONKRETŪS numeriai iš ELEMENTŲ (skirtingos eilutės).\n' +
    '{"op":"read_items","items":["tekstas1"],"note":"..."} — arba pagal matomą tekstą. Įrašai SKIRTINGI.\n' +
    '{"op":"click","text":"matomas tekstas","note":"...","final":false} — atidaryti/spausti VIENĄ elementą pagal matomą tekstą\n' +
    '{"op":"click","ref":NR,"note":"..."}                — arba pagal numerį iš ELEMENTŲ (mygtukams, ikonoms)\n' +
    '{"op":"fill","ref":NR,"text":"įvedamas tekstas","note":"..."} — įrašyti tekstą į lauką (paieška, forma; NR iš ELEMENTŲ, laukai pažymėti [text]/[email]/[select]…)\n' +
    '{"op":"key","key":"Enter","ref":NR,"note":"..."}    — paspausti klavišą (pvz. Enter paieškai patvirtinti); ref nebūtinas\n' +
    '{"op":"type","text":"...","note":"..."} — RAŠYTI tekstą į DOKUMENTĄ / canvas redaktorių (Google Docs/Sheets/Slides), kur įprastas fill neveikia. Dokumentas turi būti atidarytas ir fokusuotas.\n' +
    '{"op":"ask","question":"klausimas vartotojui"} — PAKLAUSTI vartotojo ir SUSTOTI kol atsakys (atsakymą gausi kaip pastabą). Naudok prieš PLATŲ/MASINĮ/ILGĄ darbą apimčiai/riboms suderinti arba užduočiai patikslinti.\n' +
    '{"op":"crawl","goal":"ką tikrinti/rinkti","max":N} — APEITI KELIS/VISUS svetainės puslapius: sistema PATI apvaikšto tos pačios svetainės puslapius, perskaito kiekvieną ir susintetina atsakymą pagal VISUS. „max“ = kiek puslapių — jei vartotojas nurodė skaičių („10 puslapių“), imk JĮ; jei sakė „visą svetainę/visus“ be skaičiaus — pirma op=ask. Naudok „praskenuoti visą svetainę“, „N puslapių“, „ar kur nors yra…“. NEATSAKYK iš vieno puslapio.\n' +
    '{"op":"navigate","url":"https://…","note":"..."}    — nueiti tiesiai į URL (tame pačiame tabe)\n' +
    '{"op":"back","note":"..."}                          — grįžti į ankstesnį rodinį\n' +
    '{"op":"scroll","dir":"down|up","note":"..."}        — paslinkti, kad pamatytum daugiau\n' +
    '{"op":"replace|insert|delete","text":"...","final":false} — redaguoti PAŽYMĖTĄ/aktyvų teksto lauką (grąžink GALUTINĮ tekstą)\n' +
    '{"op":"draft_reply","instruction":"ko atsakyti","which":"reply|all","cc":"email","bcc":"email"} — atsakymui ruošti: sistema atidaro atsakymo (ar „atsakyti visiems“ kai which=all) langą, PARAŠO laišką, įrašo į kūną, pridėti CC/BCC jei nurodyta, ir SUSTOJA (Siųsti spaudžia žmogus). which/cc/bcc nebūtini.\n' +
    '{"op":"forward","to":"email","cc":"email","bcc":"email","note":"nebūtina"} — PERSIŲSTI: atidaro persiuntimą, įrašo gavėją (+cc/bcc/note), SUSTOJA (Siųsti spaudžia žmogus).\n' +
    '{"op":"answer","text":"galutinis atsakymas / rezultatas"} — BAIGTI ir pateikti rezultatą\n\n' +
    "TAISYKLĖS (universalios, tinka bet kuriai svetainei):\n" +
    "- SIEK REZULTATO GREIČIAUSIAI, mažiausiu žingsnių skaičiumi. Kelis įrašus skaityk VIENU op=read_items.\n" +
    "- GOOGLE DOCS KŪRIMAS/RAŠYMAS: naujo dokumento NEKURK ieškodamas mygtuko (užstringa) — op=navigate į https://docs.google.com/document/create (tuščias dokumentas atsidaro ir fokusuojasi). Tekstą į jį rašyk op=type (NE fill/replace — Docs yra canvas). Analogiškai skaitymą sistema paima pati (matai „[DOKUMENTO TEKSTAS]“).\n" +
    "- PERCEPCIJOS SĄŽININGUMAS: jei TURINYJE matai TIK meniu/įrankių juostas/tuštumą (o dokumentas ar programa akivaizdžiai turėtų turėti turinį — pvz. canvas programos: Excel tinklelis, Figma), NEMELUOK, kad „tuščia“ ar „nėra teksto“. Vietoj to op=answer sąžiningai: kad šios programos turinio naršyklėje perskaityti nepavyksta, ir pasiūlyk atsisiųsti/eksportuoti. (Google Docs/Sheets/Slides tekstą sistema PATI paima per eksportą — ten TURINYS jau tikras, žymėtas „[DOKUMENTO TEKSTAS]“, tad juo remkis.)\n" +
    "- Po kiekvieno veiksmo gausi ATNAUJINTĄ puslapį ir savo pastabas. Į „note“ surašyk, ką sužinojai iš DABARTINIO turinio, kad nepamirštum.\n" +
    "- Kai užduotis PILNAI įvykdyta — op=answer. NENAUDOK answer kol dar reikia žingsnių. Jei VIENAS veiksmas viską atlieka — pridėk \"final\":true.\n" +
    "- PASIRINKIMAS: rinkis įrašus TIK iš to, ką matai TURINYJE/ELEMENTUOSE. Eilė = iš viršaus žemyn. Antraštę/pavadinimą imk unikalų.\n" +
    "- KIEKIS TIKSLIAI: skaityk BŪTENT tiek, kiek prašoma, NE daugiau. „N-tą/trečią laišką“ = TIK VIENAS įrašas. „paskutinius N / N laiškų“ = lygiai N. „visus“ = kiek matai.\n" +
    "- „N-tą nuo X“ arba „N laiškų nuo X“: NESKAIČIUOK PATS (klysti lengva). Naudok read_items su „fromText“:„X“ ir „nth“:N (vienam N-tam) arba „count“:N (pirmiems N). Sistema pati atrenka teisingai. Pvz. „trečią laišką nuo Admin“ → {\"op\":\"read_items\",\"fromText\":\"Admin\",\"nth\":3}.\n" +
    "- POŽYMIO FILTRAS: kai prašoma filtruoti pagal požymį (autorių/siuntėją, datą, būseną, tipą), tas požymis dažnai yra šalia įrašo (gretima eilutė/stulpelis, arba ELEMENTO teksto pradžioje, pvz. „Admin …“). Įtrauk TIK sutampančius; kitų NEIMK, net jei jie pirmesni. Filtruotam sąrašui GERIAUSIA naudoti read_items su „refs“ — ELEMENTUOSE aiškiai matai kiekvienos eilutės numerį ir jos tekstą (su siuntėju), tad rink SKIRTINGŲ tinkamų eilučių numerius. Jei sutampančių mažiau nei prašyta — imk kiek yra ir pažymėk tai atsakyme.\n" +
    "- ATIDARIUS įrašą kitame žingsnyje matysi jo turinį. Jei jau esi įrašo VIDUJE — neatidarinėk to paties, skaityk ir užsirašyk. Jei sąrašas VIS DAR matomas — atidaryk kitą tiesiogiai (be „back“). „back“ naudok tik kai sąrašo nebematai; niekada ne kelis kartus iš eilės.\n" +
    "- DABARTINĮ PUSLAPĮ JAU MATAI (žr. TURINYS) — jo NEREIKIA „skaityti“ jokiu veiksmu. Kad įsimintum, tiesiog perkelk svarbų turinį į „note“ ir tęsk. read_items NENAUDOK dabartinio puslapio pastraipoms/sekcijoms — jis skirtas TIK atidaryti įrašus/puslapius, kurių DAR NEMATAI.\n" +
    "- APIMTIES DERINIMAS (universalu): op=ask naudok TIK kai apimtis NEAIŠKI IR gali būti didelė — pvz. „visą svetainę“, „visus laiškus/failus“ BE skaičiaus. TADA paklausk kiek/kaip giliai. BET jei vartotojas JAU nurodė skaičių ar aiškią ribą („10 puslapių“, „3 laiškus“, „paskutinius 5“) — NEKLAUSK, tiesiog daryk su ta riba (pvz. crawl{max:10}). NIEKADA neklausk akivaizdžių dalykų, kuriuos vartotojas jau pasakė. Neaiškiam TURINIUI (ką tikrinti) irgi neklausk, jei jis aiškus iš užduoties.\n" +
    "- „patikrink/praskenuok/peržiūrėk N PUSLAPIŲ (ar yra …)“ = KELIŲ PUSLAPIŲ apžvalga → op=crawl{max:N}. NESPAUSK vieno meniu punkto ir NEATSAKINĖK iš vieno puslapio — net jei užduotyje minimas turinys (kontaktai, kainos) sutampa su meniu punktu. crawl pats apeis N puslapių ir ras.\n" +
    "- VISA SVETAINĖ / DAUG PUSLAPIŲ: kai prašoma „patikrinti/praskenuoti VISĄ svetainę“, „visus puslapius“, „ar KUR NORS yra…“, ar surinkti duomenis iš daugelio puslapių — naudok op=crawl (sistema pati apeina puslapius ir susintetina). Kiek puslapių („max“): jei vartotojas nurodė skaičių — imk JĮ ir daryk iškart; jei „visą/visus“ be skaičiaus — pirma op=ask. VIENAS puslapis TAM NEUŽTENKA.\n" +
    "- NARŠYMAS GILIAU / KELI PUSLAPIAI: kai reikia aplankyti KELIS puslapius ar produktus (pvz. „kokius produktus siūlo“), naudok read_items su tų puslapių NUORODŲ tekstais arba refs (pvz. meniu punktai APSAUGA, ANPR, KASIOPĖJA) — sistema PATI atidarys kiekvieną puslapį, perskaitys ir grįš, tada susintetins. NEATSAKYK po vieno puslapio. (read_items veikia bet kokiems atidaromiems dalykams: laiškams, produktams, puslapiams — svarbu, kad „items“/„refs“ būtų NUORODOS/eilutės, ne pastraipos.)\n" +
    "- Jei reikia sekti nuorodą po vieną (ne paketu): užsirašyk dabartinį puslapį į „note“, op=click nuorodą, kitą žingsnį užsirašyk naują puslapį, op=back, sek kitą — ir tik surinkus VISKĄ, op=answer.\n" +
    "- ATSAKYMO RUOŠIMAS — GERIAUSIA: naudok op=draft_reply su „instruction“ (ką atsakyti). Sistema pati atidaro langą, parašo laišką, įrašo ir sustoja. NEREIKIA pačiam rašyti teksto ar rinkti laukų.\n" +
    "- (Jei draft_reply netinka) rankinis būdas — PRIVALOMI 3 žingsniai iš eilės, NEPRALEISK: (1) op=click atidaryk atsakymo langą („Ответить“/„Reply“/„Atsakyti“); (2) KITAME žingsnyje ELEMENTUOSE rasi laiško KŪNO lauką, pažymėtą „[turinys]“ — op=fill su BŪTENT to „[turinys]“ lauko „ref“. Į „text“ įrašyk PILNĄ, PARAŠYTĄ atsakymo laišką (mandagus kreipimasis, turinys pagal užklausą ir originalo laišką, parašas) — NE užduoties/instrukcijos tekstą („Paruošk atsakymą…“ NĖRA atsakymas!). NErašyk į „Кому/To“ ar „Тема/Subject“. Jei „[turinys]“ nematyti — op=replace. Tekstas PRIVALO atsirasti KŪNE; (3) tik PO to op=answer „juodraštis paruoštas — paspausk Siųsti pats“. DRAUDŽIAMA sakyti „juodraštis paruoštas“, jei dar NEATLIKAI op=fill/op=replace — vien atidaryti langą NEUŽTENKA. NIEKADA nespausk Siųsti/Отправить/Send (blokuojama; spaudžia žmogus).\n" +
    "- SAUGA: negrįžtamų/išeinančių veiksmų mygtukų (Siųsti/Отправить/Send/Submit/Ištrinti/Удалить/Delete/Apmokėti/Publikuoti/Patvirtinti) agentas NESPAUDŽIA — juos paspaudžia žmogus. Nuorodas į KITAS svetaines (cross-origin) — tik gavus vartotojo sutikimą (sistema paklaus). Tos pačios svetainės nuorodas sek laisvai."
  );
}

async function runAgent(goal, model) {
  AGENT_ABORT = false;
  setRunning(true);
  ACTIVE_MENTION = "";
  const TRAJECTORY = []; // recorded steps, for optional skill-learning
  try {
  // CONTEXT ANCHOR: a follow-up ("is that all?", "kas dar?") means the SAME page as the last
  // turn. But the user may have switched the active tab meanwhile (e.g. to check OpenRouter
  // budget) — reading that tab gives nonsense. If this looks like a follow-up (no explicit
  // navigation/new-target intent) and the tab we worked on last is still open, switch back
  // to it before perceiving.
  try {
    const navIntent = /\b(atidaryk|atidaryti|atverk|eik|nueik|grįžk|grizk|open|go to|navigate|http|www\.|\.com|\.lt|\.org|gmail|outlook|sharepoint|teams|drive|calendar|paštas|pastas|svetain)\b/i.test(goal || "") || /\b(sukurk|create|new doc|naują dok)\b/i.test(goal || "");
    const [act] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    if (WORK_TAB_ID && act && act.id !== WORK_TAB_ID && !navIntent) {
      let t = null; try { t = await chrome.tabs.get(WORK_TAB_ID); } catch (e) {}
      if (t) { try { await chrome.tabs.update(WORK_TAB_ID, { active: true }); await waitSettle(WORK_TAB_ID, 800); addStep("↩ tęsiu ankstesnį puslapį: " + ((t.title || t.url || "").slice(0, 50))); } catch (e) {} }
    }
  } catch (e) {}
  // Self-select a thematic skill (recipe) for this task, grounded in the CURRENT SITE (URL)
  // so a keyword in the goal (e.g. a @gmail.com recipient) can't mis-route to the wrong app.
  try {
    let site = "";
    try { const [t] = await chrome.tabs.query({ active: true, lastFocusedWindow: true }); site = ((t && t.url) || "") + " | " + ((t && t.title) || ""); } catch (e) {}
    const sid = await pickSkill(goal, model, site);
    if (sid) { ACTIVE_MENTION = "<$" + sid + ">\n"; addStep("🧩 skill: " + sid); }
  } catch (e) {}
  const notes = [];
  let lastSig = "", repeat = 0;
  for (let step = 0; step < MAX_STEPS; step++) {
    if (AGENT_ABORT) { addMsg("assistant", "⏹ Sustabdyta."); return; }
    let ctx;
    try { ctx = await captureStable(); }
    catch (e) { addMsg("error", "Nepavyko nuskaityti puslapio (" + e.message + ")."); return; }

    // Bailed onto a login page (session expired / back-nav walked out of the app).
    if (step > 0 && looksLikeAuth(ctx)) {
      addMsg("error", "Pateko į prisijungimo puslapį — matyt sesija baigėsi arba atsijungei. Prisijunk iš naujo naršyklėje ir kartok užduotį.");
      return;
    }

    if (step === 0) {
      // Canvas selection: on Google Docs the highlighted text is NOT in the DOM, so a
      // question about "the selected text" would otherwise read the whole doc. If the goal
      // is about a selection and we're on a Google editor, grab the real selection via copy.
      const wantsSel = /pažymėt|pazymet|pažymet|selected|selection|\bšį\b|\bsi\b|šiame|siame|ši[ąa] pastraip|si[ąa] pastraip|this (text|selection|paragraph|part)|šitą|sita/i.test(goal || "");
      if (wantsSel && !((ctx.selection || "").trim()) && /^https:\/\/docs\.google\.com\/(document|presentation)\//.test(ctx.url || "")) {
        try {
          const [tb] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
          if (tb && tb.id) {
            const sel2 = await getDocSelection(tb.id);
            if (sel2 && sel2.length > 1 && sel2.length < (ctx.text || "").length) {
              ctx.selection = sel2; ctx.text = "[PAŽYMĖTAS TEKSTAS]\n" + sel2; ctx._docExport = false; ctx._selFocus = true;
            }
          }
        } catch (e) {}
      }
      const sel = (ctx.selection || "").trim();
      const page = (ctx.text || "").slice(0, MAX_CTX);
      if (ctx._selFocus) addStep("🔖 Pažymėtas tekstas nuskaitytas (" + sel.length + " simb.)");
      addStep("📄 " + (ctx.title || "(be pavadinimo)") + " — " +
        (sel ? sel.length + " simb. (pažymėta)" : page.length + " simb. (puslapis)"));
      if (ctx._docExport) addStep("📥 Google dokumentas nuskaitytas per eksportą (" + (ctx._docExportInfo || "") + ")");
      else if (ctx._docExportInfo && !ctx._selFocus) addStep("⚠ Google eksportas: " + ctx._docExportInfo);
    }

    let out;
    const thinking = addMsg("assistant", "…");
    try { out = await askLLM(model, buildAgentPrompt(goal, notes, ctx)); }
    catch (e) {
      if (AGENT_ABORT || (e && e.name === "AbortError")) { thinking.remove(); addMsg("assistant", "⏹ Sustabdyta."); return; }
      thinking.className = "msg err"; thinking.textContent = "Klaida: " + e.message; return;
    }
    if (out.authFail) { thinking.remove(); return loginHint(); }

    const action = parseAction(out.raw);
    if (action && action.op) TRAJECTORY.push({ op: action.op, text: action.text, ref: action.ref, fromText: action.fromText, nth: action.nth, to: action.to, dir: action.dir });

    // Final answer (or unparseable) -> show and stop.
    if (!action || action.op === "answer" || action.op === "done" || action.op === "finish") {
      const txt = action ? (action.text || "(atlikta)") : (out.raw || "(tuščias atsakymas)");
      thinking.textContent = txt;
      addActions(thinking, txt);
      addLearnButton(thinking, goal, TRAJECTORY, model);
      saveChat(goal, txt, model);
      remember(goal, txt);
      $("log").scrollTop = $("log").scrollHeight;
      return;
    }

    // Loop guard: same action repeated -> bail out.
    const sig = action.op + "|" + (action.text || action.ref || action.dir || "");
    repeat = sig === lastSig ? repeat + 1 : 0; lastSig = sig;
    if (repeat >= 2) { thinking.className = "msg err"; thinking.textContent = "Užstrigau kartodamas tą patį veiksmą — sustoju."; return; }

    // Show the model's note AND store it — this running memory is what lets the agent
    // recall earlier email bodies to summarise them at the end. Without storing, it forgets.
    thinking.remove();
    if (action.note) { addStep(action.note); notes.push(action.note); }

    // Batch read: open each named item in turn, collect its content — no back-and-forth.
    // The list stays visible (2-pane webmail), so after opening item i we just click item
    // i+1. Contents go into notes so the model can summarise them in one final answer.
    if ((action.op === "read_items" || action.op === "read") && (Array.isArray(action.items) || Array.isArray(action.refs) || action.fromText)) {
      const settle = async () => { const [t] = await chrome.tabs.query({ active: true, lastFocusedWindow: true }); if (t && t.id) await waitSettle(t.id); };
      const _seen = new Set();
      const dedupe = (arr) => arr.map((x) => String(x || "").trim())
        .filter((x) => { if (!x) return false; const k = x.toLowerCase(); if (_seen.has(k)) return false; _seen.add(k); return true; });
      let items;
      // DETERMINISTIC selection for "Nth from X" / "N from X": the model gives fromText (the
      // sender/attribute at the row start) + nth (1-based) OR count; the EXTENSION filters
      // the list rows and picks — no model counting (Gemini miscounts filtered ordinals).
      if (action.fromText) {
        const pref = String(action.fromText).toLowerCase().trim();
        const match = (t) => { const s = (t || "").toLowerCase().trim(); return s.startsWith(pref) || s.replace(/^[a-zа-яё0-9]\s+/i, "").startsWith(pref); };
        const rows = (ctx.clickables || []).filter((c) => match(c.t));
        let picked;
        if (action.nth != null) { const idx = parseInt(action.nth, 10) - 1; picked = (idx >= 0 && rows[idx]) ? [rows[idx]] : []; }
        else { const n = Math.max(1, parseInt(action.count || 1, 10)); picked = rows.slice(0, n); }
        items = dedupe(picked.map((c) => c.t));
        addStep("atrinkta pagal „" + action.fromText + "“" + (action.nth != null ? " (nr." + action.nth + ")" : (" (" + items.length + ")")) +
          (items.length ? "" : " — nerasta"));
      } else if (Array.isArray(action.refs) && action.refs.length) {
        const [tt] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
        const uniq = [...new Set(action.refs.map((x) => String(x)))].slice(0, 12);
        items = [];
        for (const ref of uniq) {
          try {
            const [{ result: info }] = await chrome.scripting.executeScript({ target: { tabId: tt.id }, func: readRef, args: [ref] });
            if (info && info.ok && info.text) items.push(info.text);
          } catch (e) {}
        }
        items = dedupe(items);
      } else {
        items = dedupe((action.items || []).slice(0, 12));
      }
      // Direct link-nav does NOT render mail.ru bodies (proven: len~1000 boilerplate); the
      // SPA renders the body only on a real CLICK. So: click the row (body loads), read,
      // then history.back (fast in-page popstate, NOT a reload) to restore the list.
      // Baseline = the current LIST view text; each opened item's body has this shared
      // nav/chrome stripped so records are actually distinguishable.
      let baseText = "";
      let listUrl = "";
      try { const bc = await captureContext(); baseText = bc.text || ""; listUrl = bc.url || ""; } catch (e) {}
      // Return to the list between items. history.back() is unreliable on some SPAs
      // (mail.ru ignores popstate → stays in the message), so re-navigate to the saved
      // LIST url instead (the inbox loads normally — only message urls render stripped).
      const toList = async () => {
        try {
          const [t] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
          if (t && t.id && listUrl) { await chrome.tabs.update(t.id, { url: listUrl, active: true }); await waitSettle(t.id); }
          else { await goBack(); }
        } catch (e) { await goBack(); }
      };
      const collected = [];
      const openedKeys = new Set();
      let prevBody = "";
      for (const item of items) {
        if (AGENT_ABORT) { addMsg("assistant", "⏹ Sustabdyta."); return; }
        addStep("skaitau: " + item.slice(0, 60));
        const r = await openItemWithRetry(item);
        await settle();
        if (!(r && r.ok)) { addStep("⚠ nepavyko: " + item.slice(0, 50)); collected.push({ item, body: "(nepavyko atidaryti)" }); continue; }
        const [tb0] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
        // 1) Known content container, WAITING until the body actually changed from the last
        // item (the reading pane lags the URL). 2) Readability, 3) lite, 4) nav-stripped.
        let body = (await readBodyChanged(tb0.id, prevBody)).slice(0, 4000);
        if (body.length < 40) {
          try {
            await chrome.scripting.executeScript({ target: { tabId: tb0.id }, files: ["readability.js"] });
            const [{ result: art }] = await chrome.scripting.executeScript({ target: { tabId: tb0.id }, func: runReadability });
            if (art && art.ok && art.text) body = art.text.slice(0, 4000);
          } catch (e) {}
        }
        if (body.length < 40) {
          try {
            const [{ result: mc }] = await chrome.scripting.executeScript({ target: { tabId: tb0.id }, func: mainContentFn });
            body = (mc || "").slice(0, 4000);
          } catch (e) {}
        }
        if (body.length < 40) {
          let c; try { c = await captureStable(); } catch (e) { c = { text: "" }; }
          const raw = (c.text || "").replace(/\s+/g, " ").trim();
          body = stripCommon(baseText, raw).slice(0, 4000);
        }
        // Skip if this resolved to the SAME record we already read (identical body).
        const key = body.slice(0, 120);
        if (body && openedKeys.has(key)) { addStep("(tas pats įrašas — praleista)"); await toList(); continue; }
        openedKeys.add(key);
        prevBody = body;
        addStep("perskaityta (" + body.length + " simb.)");
        collected.push({ item, body });
        await toList(); // back to the list (reliable re-nav) for the next item
      }
      // Synthesize the final result RIGHT HERE from the gathered contents — do NOT loop
      // back (the model would otherwise re-issue read_items and hit the loop-guard).
      const synth = addMsg("assistant", "…");
      const synPrompt =
        "UŽDUOTIS: «" + goal + "»\n\n" +
        "SURINKTAS ĮRAŠŲ TURINYS (naudok TIK jį):\n" +
        collected.map((c, i) => "### " + (i + 1) + ". " + c.item + "\n" + c.body).join("\n\n") + "\n\n" +
        "Įvykdyk užduotį iš šio turinio (apibendrink; jei prašoma — paruošk atsakymo projektą ir pan.). " +
        "Rašyk aiškiai žmogui, be JSON, be papildomų veiksmų. GP_xxxx/[PERSON] cituok kaip yra (bus atstatyta).";
      let out;
      try { out = await askLLM(model, synPrompt, { isolate: true, noSkill: true }); }
      catch (e) {
        if (AGENT_ABORT || (e && e.name === "AbortError")) { synth.remove(); addMsg("assistant", "⏹ Sustabdyta."); return; }
        synth.className = "msg err"; synth.textContent = "Klaida: " + e.message; return;
      }
      if (out.authFail) { synth.remove(); return loginHint(); }
      const txt = unwrapAnswer(out.raw) || "(tuščias atsakymas)";
      synth.textContent = txt;
      addActions(synth, txt);
      saveChat(goal, txt, model);
      remember(goal, txt);
      $("log").scrollTop = $("log").scrollHeight;
      return;
    }

    if (action.op === "click") {
      const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
      if (!tab || !tab.id) { addStep("⚠ nėra aktyvios kortelės"); return; }
      // Resolve the target first (without acting) so we can gate cross-site links.
      let info;
      try {
        const [{ result: r }] = (action.text && String(action.text).trim())
          ? await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: resolveByText, args: [action.text] })
          : await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: readRef, args: [action.ref] });
        info = r || { ok: false, reason: "nėra atsako iš puslapio" };
      } catch (e) { info = { ok: false, reason: e.message }; }
      const tag = (action.text && String(action.text).trim()) ? "__txt" : action.ref;
      const label = (info && info.text) || action.text || ("#" + action.ref);

      // SAFETY: never let the agent press an irreversible / outward action (Send, Submit,
      // Delete, Pay, Publish…). A human must do that. Hand off and stop.
      if (info && info.ok && DANGEROUS_RE.test(String(label).trim())) {
        addStep("⛔ „" + String(label).slice(0, 40) + "“ — šį veiksmą (siųsti/ištrinti/patvirtinti) turi atlikti ŽMOGUS. Nepaspaudžiau.");
        addMsg("assistant", "Paruošiau, bet mygtuką „" + String(label).slice(0, 40) + "“ paspausk PATS — agentas negali siųsti/trinti už tave.");
        saveChat(goal, "STOP: reikia žmogaus veiksmo — " + label, model);
        remember(goal, "Sustota: „" + label + "“ turi paspausti žmogus.");
        return;
      }

      // Consent gate: a link leaving the current site (e.g. a link inside an email) is
      // only clicked with the user's explicit OK. Same-site navigation (opening a
      // message, going back) proceeds automatically.
      if (info && info.ok && info.href && !sameHost(info.href, tab.url || "")) {
        const ok = await askConsent(info.href);
        if (!ok) { addStep("⛔ praleista (be sutikimo): " + info.href); notes.push("Vartotojas neleido atidaryti nuorodos: " + info.href); continue; }
      }

      const res = await actOnResolved(tab, info, tag);
      addStep(res && res.ok ? "atidaryta: " + label + (res.sameTab ? " ✓" : "")
                            : "⚠ nepavyko atidaryti: " + label + " (" + ((res && res.reason) || "?") + ")");
      notes.push(res && res.ok ? "Paspaudžiau/atidariau: " + label : "Nepavyko atidaryti: " + label);
      const [tab2] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
      if (tab2 && tab2.id) await waitSettle(tab2.id);
      if (action.final) { saveChat(goal, "atidaryta: " + label, model); remember(goal, "atidaryta: " + label); return; }
      continue;
    }
    // Deterministic REPLY DRAFTING: the extension opens the reply form, COMPOSES the draft
    // with a focused LLM call (from the email + instruction), fills the body, and STOPS —
    // the human presses Send. Removes the model's flaky inline compose/field-pick.
    if (action.op === "draft_reply" || action.op === "reply" || action.op === "compose_reply") {
      const instruction = action.instruction || action.text || goal;
      const emailCtx = (ctx.text || "").slice(0, 6000); // the email we're replying to
      const which = (action.which || "reply").toLowerCase();
      // 1) open the right compose form (reply / reply-all)
      const openLabels = /all|visiem|всем/.test(which)
        ? ["Ответить всем", "Reply all", "Reply to all", "Atsakyti visiems", "Allen antworten"]
        : ["Ответить", "Atsakyti", "Reply", "Antworten", "Répondre"];
      addStep("atidarau " + (/all/.test(which) ? "„atsakyti visiems“" : "atsakymo") + " langą");
      const orr = await clickExactInPage(openLabels);
      let opened = !!(orr && orr.ok);
      { const [tb] = await chrome.tabs.query({ active: true, lastFocusedWindow: true }); if (tb && tb.id) await waitSettle(tb.id, 1800); }
      if (!opened) { addStep("⚠ neradau atsakymo mygtuko"); notes.push("Nepavyko atidaryti atsakymo lango"); continue; }
      // 1b) optional CC / BCC
      if (action.cc) { const r = await addCcBcc("cc", String(action.cc)); addStep(r && r.ok ? "CC: " + action.cc : "⚠ CC nepavyko"); }
      if (action.bcc) { const r = await addCcBcc("bcc", String(action.bcc)); addStep(r && r.ok ? "BCC: " + action.bcc : "⚠ BCC nepavyko"); }
      // 2) compose the draft with a focused call (clean, not inline JSON)
      addStep("rašau juodraštį…");
      const composePrompt =
        "Parašyk MANDAGŲ atsakymo el. laišką TA PAČIA kalba kaip originalas. Originalus laiškas:\n«" +
        emailCtx + "»\n\nKO reikia atsakyti / užduotis: «" + instruction + "»\n\n" +
        "Grąžink TIK galutinį laiško tekstą: kreipimasis, turinys, ir pabaigoje mandagus atsisveikinimas (pvz. „Pagarbiai,“ / „С уважением,“) BE vardo ir BE el. pašto adreso — parašą užbaigs žmogus. " +
        "NEKARTOK užduoties teksto, NERAŠYK jokių pastabų, antraščių, temos, paaiškinimų ar kabučių. " +
        "NEPRASIMANYK vardų, pavardžių, el. pašto adresų, telefonų — jei nėra originale, nerašyk. " +
        "GP_xxxx/[PERSON] cituok kaip yra (bus atstatyta).";
      let out;
      try { out = await askLLM(model, composePrompt, { isolate: true, noSkill: true }); }
      catch (e) {
        if (AGENT_ABORT || (e && e.name === "AbortError")) { addMsg("assistant", "⏹ Sustabdyta."); return; }
        addMsg("error", "Nepavyko sukurti juodraščio: " + e.message); return;
      }
      if (out.authFail) return loginHint();
      const draft = unwrapAnswer(out.raw);
      if (!draft) { addMsg("error", "Tuščias juodraštis."); return; }
      // 3) fill the body deterministically
      const res = await fillComposeInPage(draft);
      if (res && res.ok) {
        const m = addMsg("assistant", "✅ Juodraštis įrašytas į atsakymo langą. Peržiūrėk ir paspausk Siųsti PATS (agentas nesiunčia).\n\n— — —\n" + draft);
        addActions(m, draft);
        saveChat(goal, "Paruoštas atsakymo juodraštis:\n" + draft, model);
        remember(goal, "Paruoštas atsakymo juodraštis (žmogus siunčia).");
      } else {
        const m = addMsg("assistant", "Juodraštį paruošiau, bet neradau kur įrašyti (" + ((res && res.reason) || "?") + "). Va tekstas — įklijuok pats:\n\n" + draft);
        addActions(m, draft);
      }
      return;
    }

    // Deterministic FORWARD: open the forward form, fill the recipient (and optional note),
    // then STOP — the human verifies the recipient and presses Send.
    if (action.op === "forward") {
      const to = action.to || action.email || "";
      const note = action.note || action.text || "";
      addStep("atidarau persiuntimo langą");
      const fr = await clickExactInPage(["Переслать", "Persiųsti", "Peradresuoti", "Forward", "Weiterleiten", "Transférer"]);
      let opened = !!(fr && fr.ok);
      { const [tb] = await chrome.tabs.query({ active: true, lastFocusedWindow: true }); if (tb && tb.id) await waitSettle(tb.id, 1800); }
      if (!opened) { addMsg("error", "Neradau Переслать/Forward mygtuko."); return; }
      let rmsg = "";
      if (to) {
        const rr = await fillRecipientInPage(to);
        rmsg = rr && rr.ok ? "Gavėjas įrašytas: " + to : "⚠ nepavyko įrašyti gavėjo (" + ((rr && rr.reason) || "?") + ") — įrašyk ranka: " + to;
        addStep(rmsg);
      }
      if (action.cc) { const r = await addCcBcc("cc", String(action.cc)); addStep(r && r.ok ? "CC: " + action.cc : "⚠ CC nepavyko"); }
      if (action.bcc) { const r = await addCcBcc("bcc", String(action.bcc)); addStep(r && r.ok ? "BCC: " + action.bcc : "⚠ BCC nepavyko"); }
      if (note) { await fillComposeInPage(note); addStep("pridėta pastaba"); }
      addMsg("assistant", "✅ Persiuntimas paruoštas" + (to ? " gavėjui " + to : "") + ". PATIKRINK gavėją ir paspausk Siųsti PATS (agentas nesiunčia)." + (rmsg.startsWith("⚠") ? "\n" + rmsg : ""));
      saveChat(goal, "Paruoštas persiuntimas: " + to, model);
      remember(goal, "Paruoštas persiuntimas gavėjui " + to + " (žmogus siunčia).");
      return;
    }

    if (action.op === "back") { addStep("grįžta atgal"); notes.push("Grįžau į ankstesnį puslapį (sąrašą)"); await goBack(); continue; }
    if (action.op === "scroll") { addStep("slenka " + (action.dir || "down")); await doScroll(action.dir); await new Promise((r) => setTimeout(r, 400)); continue; }

    if (action.op === "fill") {
      const res = await fillInPage(action.ref, action.text || "");
      addStep(res && res.ok ? "įvesta į #" + action.ref + ": „" + String(action.text || "").slice(0, 40) + "“"
                            : "⚠ nepavyko įvesti (#" + action.ref + "): " + ((res && res.reason) || "?"));
      notes.push(res && res.ok ? "Įvedžiau „" + String(action.text || "").slice(0, 60) + "“ į lauką #" + action.ref : "Nepavyko įvesti į #" + action.ref);
      const [tb] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
      if (tb && tb.id) await waitSettle(tb.id, 900);
      if (action.final) { saveChat(goal, "fill #" + action.ref, model); remember(goal, "fill #" + action.ref); return; }
      continue;
    }
    // CANVAS TYPING: type text into the focused editor via real CDP input. Needed for
    // Google Docs/Sheets/Slides where synthetic DOM fill is ignored (canvas). The doc must
    // already be focused (opening a doc / navigating to …/create focuses it automatically).
    if (action.op === "type") {
      const [tb] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
      if (!tb || !tb.id) { addMsg("error", "Nėra aktyvaus tab."); return; }
      addStep("rašau (canvas): „" + String(action.text || "").slice(0, 40) + "“");
      const res = await cdpType(tb.id, action.text || "");
      addStep(res && res.ok ? "įrašyta ✓" : "⚠ rašymas nepavyko: " + ((res && res.reason) || "?"));
      notes.push(res && res.ok ? "Įrašiau tekstą į dokumentą (canvas)." : "Nepavyko įrašyti (canvas): " + ((res && res.reason) || "?"));
      if (tb.id) await waitSettle(tb.id, 900);
      if (action.final) { saveChat(goal, "type", model); remember(goal, "type į canvas"); return; }
      continue;
    }
    if (action.op === "key") {
      await pressKey(action.key || "Enter", action.ref);
      addStep("klavišas: " + (action.key || "Enter"));
      notes.push("Paspaudžiau klavišą " + (action.key || "Enter"));
      const [tb] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
      if (tb && tb.id) await waitSettle(tb.id);
      continue;
    }
    // Deterministic SITE CRAWL: visit many same-host pages (breadth-first from the current
    // page + its links), extract each page's main text, then answer the task across ALL of
    // them in one synthesis call. General primitive for any "check/collect across the whole
    // site / all pages" task (PII audit, product listing, contacts, prices…) — the model
    // can't reliably walk a whole site one op at a time, so the extension does it.
    if (action.op === "crawl" || action.op === "scan_site") {
      // No product cap — the page count comes from the user (agreed via op=ask). Only a
      // technical runaway backstop so a missing/huge value can't hang the tab forever.
      const RUNAWAY = 500;
      const max = Math.min(Math.max(parseInt(action.max, 10) || RUNAWAY, 1), RUNAWAY);
      const task = action.goal || action.note || goal;
      const [tab0] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
      if (!tab0 || !tab0.id) { addMsg("error", "Nėra aktyvaus tab."); return; }
      const startUrl = tab0.url || "";
      let baseHost = ""; try { baseHost = new URL(startUrl).host; } catch (e) {}
      const queue = [startUrl];
      const seen = {}; seen[startUrl.replace(/#.*$/, "")] = 1;
      const results = [];
      addStep("skenuoju svetainę " + baseHost + " (iki " + max + " psl.)");
      for (let i = 0; i < queue.length && results.length < max; i++) {
        if (AGENT_ABORT) { addMsg("assistant", "⏹ Sustabdyta."); return; }
        const url = queue[i];
        try { await chrome.tabs.update(tab0.id, { url, active: true }); await waitSettle(tab0.id, 2500); }
        catch (e) { continue; }
        let text = "", title = "";
        try {
          const [{ result }] = await chrome.scripting.executeScript({ target: { tabId: tab0.id }, func: mainContentFn });
          text = result || "";
        } catch (e) {}
        try { const [t2] = await chrome.tabs.query({ active: true, lastFocusedWindow: true }); title = (t2 && t2.title) || ""; } catch (e) {}
        results.push({ url, title, text: text.slice(0, 1500) });
        addStep("• " + (title || url).slice(0, 60) + " (" + text.length + " simb.)");
        if (queue.length < max * 3) {
          try {
            const [{ result: links }] = await chrome.scripting.executeScript({ target: { tabId: tab0.id }, func: collectLinksFn });
            for (const l of (links || [])) { const k = l.url.replace(/#.*$/, ""); if (!seen[k]) { seen[k] = 1; queue.push(l.url); } }
          } catch (e) {}
        }
      }
      try { await chrome.tabs.update(tab0.id, { url: startUrl, active: true }); await waitSettle(tab0.id); } catch (e) {}
      if (!results.length) { addMsg("error", "Nepavyko apeiti puslapių."); return; }
      addStep("apėjau " + results.length + " psl., analizuoju…");
      const corpus = results.map((r, i) => "[" + (i + 1) + "] " + r.url + (r.title ? " (" + r.title + ")" : "") + ":\n" + r.text).join("\n\n");
      const synth =
        "Užduotis: «" + task + "».\n\nApėjau " + results.length + " šios svetainės puslapius, štai jų turinys:\n\n" + corpus +
        "\n\nAtsakyk į užduotį remdamasis VISAIS puslapiais, glaustai, lietuviškai. " +
        "SVARBU: atsakyme NIEKADA nemink jokių techninių žymių (GP_xxxx, [PERSON], [EMAIL] ir pan.), nekalbėk apie „maskavimą“ ar „žymes“ — rašyk žmogui natūraliai. " +
        "Vidinei analizei: žymės GP_xxxx arba [PERSON]/[EMAIL]/[ID]/[ADDRESS]/[PHONE] reiškia tikrus asmens duomenis — jų buvimas puslapyje reiškia, kad ten YRA asmens duomenų (nurodyk KURIUOSE URL ir kokio TIPO — pvz. „el. paštas“, „vardas“, „telefonas“ — bet NEcituok pačios žymės). Jei tokių nė viename puslapyje nėra — sakyk paprastai, kad asmens duomenų nerasta.";
      let out;
      try { out = await askLLM(model, synth, { isolate: true, noSkill: true }); }
      catch (e) { if (AGENT_ABORT || (e && e.name === "AbortError")) { addMsg("assistant", "⏹ Sustabdyta."); return; } addMsg("error", "Analizė nepavyko: " + e.message); return; }
      if (out.authFail) return loginHint();
      const ans = unwrapAnswer(out.raw) || "(tuščias atsakymas)";
      addMsg("assistant", ans + "\n\n— — —\nApėjau puslapius:\n" + results.map((r) => "• " + r.url).join("\n"));
      saveChat(goal, ans, model);
      remember(goal, "Apėjau " + results.length + " puslapius. " + ans.slice(0, 120));
      return;
    }

    if (action.op === "navigate" && action.url) {
      const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
      if (tab && tab.id) {
        if (!sameHost(action.url, tab.url || "")) {
          const ok = await askConsent(action.url);
          if (!ok) { addStep("⛔ navigacija atmesta: " + action.url); notes.push("Vartotojas neleido eiti į " + action.url); continue; }
        }
        try { await chrome.tabs.update(tab.id, { url: action.url, active: true }); await waitSettle(tab.id); } catch (e) {}
        addStep("nuėjau į: " + action.url.slice(0, 70));
        notes.push("Nuėjau į " + action.url);
      }
      if (action.final) { saveChat(goal, "navigate " + action.url, model); remember(goal, "navigate " + action.url); return; }
      continue;
    }

    if (action.op === "replace" || action.op === "insert" || action.op === "delete") {
      const map = { replace: "replace", insert: "insert", delete: "replace" };
      const text = action.op === "delete" ? "" : (action.text || "");
      const res = await applyToPage(text, map[action.op]);
      if (res && res.ok) { const s = addStep(action.op === "delete" ? "ištrinta" : action.op === "insert" ? "įterpta" : "pakeista"); addUndo(s, res.before); }
      else {
        addStep("⚠ tiesiogiai redaguoti nepavyko: " + ((res && res.reason) || "?"));
        // No DOM-editable target (e.g. Google Docs canvas). NEVER lose the composed text:
        // show it with a Copy button. On a canvas app it can also be typed in via CDP.
        if (text && action.op !== "delete") {
          const [tb] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
          const onCanvas = /^https:\/\/docs\.google\.com\/(document|presentation)\//.test((tb && tb.url) || "");
          const m = addMsg("assistant", (onCanvas
            ? "Šis redaktorius (Google Docs) neleidžia taikytis į konkrečią vietą per naršyklę. Štai paruoštas tekstas — įklijuok kur reikia, arba paprašyk „įrašyk į dokumentą“ (įrašysiu dokumento gale):\n\n"
            : "Nepavyko įrašyti tiesiogiai į lauką. Štai paruoštas tekstas — įklijuok pats:\n\n") + text);
          addActions(m, text);
          saveChat(goal, text, model);
          remember(goal, "Paruošiau tekstą (redaguoti tiesiogiai nepavyko): " + text.slice(0, 80));
          return;
        }
      }
      if (action.final) { saveChat(goal, action.op + ": " + text, model); remember(goal, action.op + ": " + text); return; }
      continue;
    }

    // Universal ASK: pause and ask the user (scope/limits before a big job, or to clarify).
    if (action.op === "ask" || action.op === "clarify" || action.op === "confirm_scope") {
      const q = action.question || action.text || action.note || "Patikslink užduotį.";
      addStep("klausiu vartotojo");
      const reply = await askUser(q);
      if (reply === null || AGENT_ABORT) { addMsg("assistant", "⏹ Sustabdyta."); return; }
      notes.push("Paklausiau vartotojo: „" + q.slice(0, 80) + "“. Atsakymas: „" + reply + "“.");
      continue;
    }

    // Pure observation / thinking op (note already stored above) — keep going.
    if (["note", "think", "observe", "read", "wait", "none", "continue"].includes(action.op)) {
      continue;
    }

    addMsg("error", "Nežinomas veiksmas: " + action.op + " — sustoju.");
    return;
  }
  addMsg("error", "Pasiekta žingsnių riba (" + MAX_STEPS + ") — sustojau. Patikslink užduotį arba dalink mažesniais žingsniais.");
  } finally {
    setRunning(false);
    CURRENT_ABORT = null;
    PENDING_ASK = null;
    // Remember the tab we ended on = the page this conversation is about, so the next
    // follow-up anchors back to it even if the user switched tabs.
    try { const [t] = await chrome.tabs.query({ active: true, lastFocusedWindow: true }); if (t && t.id) WORK_TAB_ID = t.id; } catch (e) {}
  }
}

// Diagnostic: list ALL frames of the current tab (via webNavigation) with each frame's
// URL and how much text we can actually read from it. Reveals whether an item's body
// lives in a frame we CAN'T inject (sandboxed / uninjectable) — the mail.ru body case.
async function dumpFrames() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    if (!tab || !tab.id) return addMsg("error", "nėra kortelės");
    const frames = await chrome.webNavigation.getAllFrames({ tabId: tab.id });
    let results = [];
    try {
      results = await chrome.scripting.executeScript({
        target: { tabId: tab.id, allFrames: true },
        func: () => ({ len: (document.body ? document.body.innerText : "").length }),
      });
    } catch (e) {}
    const gotByFrame = {};
    for (const r of results) gotByFrame[r.frameId] = r.result ? r.result.len : -1;
    addMsg("assistant", "Frames (" + frames.length + "):");
    for (const f of (frames || [])) {
      const readable = f.frameId in gotByFrame ? gotByFrame[f.frameId] : "BLOCKED";
      addStep("frame#" + f.frameId + " innerText=" + readable + " url=" + (f.url || "").slice(0, 90));
    }
    // Deep (shadow-aware) read length — should be MUCH larger than innerText if the body
    // is in a shadow root.
    try {
      const ctx = await captureStable();
      addStep("DEEP read len=" + ((ctx.text || "").length) +
        " «" + (ctx.text || "").slice(0, 220) + "»");
    } catch (e) {}
  } catch (e) {
    addMsg("error", "gpframes klaida: " + e.message);
  }
}

async function send() {
  // If the agent is waiting on an op=ask, this input IS the answer — feed it back, don't
  // start a new run.
  if (PENDING_ASK) {
    const ans = $("q").value.trim();
    if (!ans) return;
    $("q").value = "";
    addMsg("user", ans);
    const r = PENDING_ASK; PENDING_ASK = null;
    r(ans);
    return;
  }
  if (RUNNING) return; // a task is already running — use Stop first
  const goal = $("q").value.trim();
  if (!goal) return;
  const model = $("model").value;
  $("q").value = "";
  if (goal.toLowerCase() === "gpframes") { addMsg("user", goal); return dumpFrames(); }
  if (!model) return addMsg("error", "Pasirink modelį.");
  addMsg("user", goal);
  await runAgent(goal, model);
}

$("send").addEventListener("click", send);
$("stop").addEventListener("click", stopAgent);
$("q").addEventListener("keydown", (e) => {
  // Enter sends; Shift+Enter (or Ctrl/Cmd+Enter) inserts a newline.
  if (e.key === "Enter" && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
    e.preventDefault();
    send();
  }
});

// Anonymization self-test: send known PII, ask the model to echo it verbatim. On a
// ONE-WAY model the echo shows what the LLM actually received — masked = OK. (Not
// valid for a REVERSIBLE model: it restores tokens in the response, so the echo
// would show real values by design — verify those in gp-openai-proxy logs instead.)
async function testAnon() {
  const model = $("model").value;
  if (!model) return addMsg("error", "Pasirink modelį.");
  const sample =
    "Jonas Petraitis, el. paštas jonas.petraitis@example.lt, asmens kodas 39001011234, tel. +37060012345";
  addMsg("user", "🧪 Anonimizacijos testas");
  const pending = addMsg("assistant", "…");
  const prompt =
    "Pakartok ŽODIS Į ŽODĮ (verbatim) tekstą tarp žymių, nieko nekeisdamas ir neaiškindamas:\n<<<" +
    sample + ">>>";
  try {
    const r = await api("/api/chat/completions", {
      method: "POST",
      body: JSON.stringify({ model, messages: [{ role: "user", content: prompt }], stream: false }),
    });
    if (r.status === 401 || r.status === 403) { pending.remove(); return loginHint(); }
    if (!r.ok) throw new Error("HTTP " + r.status);
    const data = await r.json();
    const echo = data?.choices?.[0]?.message?.content ?? data?.message?.content ?? "";
    const leaks = ["Petraitis", "39001011234", "jonas.petraitis@example.lt", "37060012345"];
    const leaked = leaks.filter((x) => echo.includes(x));
    pending.className = "msg " + (leaked.length ? "err" : "a");
    pending.textContent = leaked.length
      ? "⚠ LLM gavo tikrus duomenis: " + leaked.join(", ") +
        "\n(jei modelis GRĮŽTAMAS — tai normalu; tikrink gp-openai-proxy loge)\n\nGrąžino:\n" + echo
      : "✓ Anonimizacija veikia — LLM gavo užmaskuotą tekstą:\n" + echo;
  } catch (e) {
    pending.className = "msg err";
    pending.textContent = "Testo klaida: " + e.message;
  }
  $("log").scrollTop = $("log").scrollHeight;
}

$("test").addEventListener("click", testAnon);

(async function init() {
  await loadCfg();
  loadBrand(); // async, non-blocking — brand name/logo from brand.json
  await loadModels();
  injectTracker(); // start remembering the page's focused field right away
})();
