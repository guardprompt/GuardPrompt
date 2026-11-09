/* GuardPrompt Office Add-in — task pane.
 *
 * Same idea as the browser side panel (browser-extension/sidepanel.js): it talks ONLY
 * to the configured OWUI instance and every request goes through the gp-pipeline inlet,
 * which anonymizes the content BEFORE it reaches the external LLM. The one difference is
 * WHERE the text comes from: instead of the web page DOM, Office.js reads the Word
 * document / Outlook mail, and writes the result back into it.
 *
 * AUTH: the add-in is served from the OWUI/guardproxy origin, so /api calls are
 * same-origin and the OWUI session cookie rides along (credentials:'include') — no token
 * handling, exactly like the side panel. If served cross-origin the cookie is NOT sent;
 * host it under the OWUI domain (see README).
 */
"use strict";

const BASE = ((typeof window !== "undefined" && window.GP_OWUI_BASE) || "").replace(/\/+$/, "");
const MODEL_FILTER = (typeof window !== "undefined" && window.GP_MODEL_FILTER) || "";

let HOST = null;          // Office.HostType.Word | Office.HostType.Outlook
let MODEL = "";
let ABORT = null;         // AbortController for the in-flight request

const $ = (id) => document.getElementById(id);
function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function addMsg(role, text) {
  const el = document.createElement("div");
  el.className = "msg " + (role === "user" ? "u" : role === "error" ? "err" : "a");
  el.innerHTML = esc(text);
  $("log").appendChild(el);
  $("log").scrollTop = $("log").scrollHeight;
  return el;
}
function api(path, opts = {}) {
  return fetch(`${BASE}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
}

/* ---------- Office.js: read/write the host document ---------------------------- */

// Selected text (Word: the selection; Outlook: selected body text, or the whole body
// when nothing is selected — e.g. "prepare a reply" needs the full incoming mail).
function getSelectedText() {
  return new Promise((resolve, reject) => {
    if (HOST === Office.HostType.Word) {
      Word.run(async (ctx) => {
        const sel = ctx.document.getSelection();
        sel.load("text");
        await ctx.sync();
        resolve(sel.text || "");
      }).catch(reject);
    } else if (HOST === Office.HostType.Outlook) {
      const item = Office.context.mailbox.item;
      // Compose vs read: in read mode getSelectedDataAsync may be empty → fall back to
      // the full body so the model has the incoming message to reply to.
      Office.context.mailbox.item.getSelectedDataAsync(Office.CoercionType.Text, (r) => {
        const picked = r.status === Office.AsyncResultStatus.Succeeded ? (r.value && r.value.data) : "";
        if (picked && picked.trim()) return resolve(picked);
        item.body.getAsync(Office.CoercionType.Text, (b) =>
          resolve(b.status === Office.AsyncResultStatus.Succeeded ? (b.value || "") : ""));
      });
    } else {
      reject(new Error("Nepalaikoma programa"));
    }
  });
}

// Put the result back. Word: replace the selection. Outlook: replace the selection in a
// compose window, or open a reply pre-filled with the draft when in read mode.
function applyResult(text, op) {
  return new Promise((resolve, reject) => {
    if (HOST === Office.HostType.Word) {
      Word.run(async (ctx) => {
        ctx.document.getSelection().insertText(text, Word.InsertLocation.replace);
        await ctx.sync();
        resolve();
      }).catch(reject);
    } else if (HOST === Office.HostType.Outlook) {
      const item = Office.context.mailbox.item;
      const isCompose = item.itemType === Office.MailboxEnums.ItemType.Message && !!item.body.setSelectedDataAsync && item.displayReplyForm === undefined;
      if (op === "reply" && typeof item.displayReplyForm === "function") {
        // Read mode: open a reply draft pre-filled with the answer (user reviews + sends).
        item.displayReplyForm({ htmlBody: esc(text).replace(/\n/g, "<br>") });
        resolve();
      } else {
        item.body.setSelectedDataAsync(text, { coercionType: Office.CoercionType.Text }, (r) =>
          r.status === Office.AsyncResultStatus.Succeeded ? resolve() : reject(new Error(r.error && r.error.message)));
      }
    } else {
      reject(new Error("Nepalaikoma programa"));
    }
  });
}

/* ---------- LLM call (through OWUI → gp-pipeline anonymizes) -------------------- */

const OP_PROMPTS = {
  anon:    "Grąžink žemiau esantį tekstą be jokių pakeitimų (tik patikrinu anonimizaciją).",
  rewrite: "Perrašyk žemiau esantį tekstą oficialesniu, aiškiu dalykiniu stiliumi. Grąžink TIK perrašytą tekstą.",
  reply:   "Parašyk mandagų, dalykišką atsakymą į žemiau esantį laišką. Grąžink TIK atsakymo tekstą.",
  summary: "Trumpai apibendrink žemiau esantį tekstą lietuviškai (svarbiausi punktai). Grąžink TIK santrauką.",
};

async function loadModels() {
  const sel = $("model");
  sel.innerHTML = "";
  try {
    const r = await api("/api/models");
    if (r.status === 401 || r.status === 403) { addMsg("error", `Neprisijungta prie OWUI (${BASE || "same-origin"}). Prisijunk naršyklėje ir bandyk vėl.`); return; }
    if (!r.ok) throw new Error("HTTP " + r.status);
    const data = await r.json();
    const list = data.data || data.models || data || [];
    for (const m of list) {
      const id = m.id || m.name; if (!id) continue;
      const name = m.name || id;
      if (MODEL_FILTER && !(String(id).includes(MODEL_FILTER) || String(name).includes(MODEL_FILTER))) continue;
      const o = document.createElement("option"); o.value = id; o.textContent = name; sel.appendChild(o);
    }
    sel.disabled = !!(MODEL_FILTER && sel.options.length === 1);
    if (!sel.options.length) { addMsg("error", "Nerasta modelio pagal žymę „" + MODEL_FILTER + "“ — patikrink prieigą OWUI."); return; }
    MODEL = sel.value = sel.options[0].value;
    sel.onchange = () => { MODEL = sel.value; };
  } catch (e) {
    addMsg("error", "Nepavyko gauti modelių: " + (e.message || e));
  }
}

async function ask(instruction, content) {
  if (ABORT) return;                                   // one at a time
  ABORT = new AbortController();
  $("stop").classList.remove("hidden");
  document.querySelectorAll(".act,#send").forEach((b) => (b.disabled = true));
  const think = addMsg("assistant", "…");
  try {
    // gp-pipeline anonymizes `content` before the external LLM; the answer comes back
    // de-anonymized (reversible map) for the user, same as the side panel.
    const body = {
      model: MODEL,
      messages: [
        { role: "system", content: "Tu esi Regitros dokumentų asistentas. Atsakyk lietuviškai, dalykiškai." },
        { role: "user", content: `${instruction}\n\n---\n${content}` },
      ],
      stream: false,
    };
    const r = await api("/api/chat/completions", { method: "POST", body: JSON.stringify(body), signal: ABORT.signal });
    if (!r.ok) throw new Error("HTTP " + r.status);
    const d = await r.json();
    const answer = (d.choices && d.choices[0] && d.choices[0].message && d.choices[0].message.content) || "(tuščias atsakymas)";
    think.innerHTML = esc(answer);
    return answer;
  } catch (e) {
    if (e.name === "AbortError") think.innerHTML = esc("⏹ Sustabdyta.");
    else think.className = "msg err", (think.innerHTML = esc("Klaida: " + (e.message || e)));
    return null;
  } finally {
    ABORT = null;
    $("stop").classList.add("hidden");
    document.querySelectorAll(".act,#send").forEach((b) => (b.disabled = false));
  }
}

/* ---------- wiring -------------------------------------------------------------- */

async function runOp(op, customInstruction) {
  let content;
  try { content = await getSelectedText(); }
  catch (e) { return addMsg("error", "Nepavyko perskaityti teksto: " + (e.message || e)); }
  if (!content || !content.trim()) return addMsg("error", "Pažymėk tekstą (arba atidaryk laišką).");

  const instruction = customInstruction || OP_PROMPTS[op] || OP_PROMPTS.rewrite;
  addMsg("user", (customInstruction ? customInstruction : $(`[data-op="${op}"]`) ? document.querySelector(`[data-op="${op}"]`).textContent : op));
  const answer = await ask(instruction, content);
  if (answer == null) return;

  // "anon" is a visibility check only — never writes back. The others offer to apply.
  if (op !== "anon" && op !== "summary") {
    try { await applyResult(answer, op); }
    catch (e) { addMsg("error", "Nepavyko įrašyti atgal: " + (e.message || e)); }
  }
}

// "Naudok mano dokumentus" — the Track C flow. Gets the user's SSO token (silent, reuses
// their existing M365 sign-in), sends {question, sso_token} to guardproxy /_gp/m365, which
// runs gp-m365 (OBO → Graph search of THEIR mail/files → anonymize → LLM → de-anon).
async function useMyDocuments() {
  const question = $("q").value.trim();
  if (!question) return addMsg("error", "Parašyk klausimą (ką ieškot dokumentuose).");
  if (typeof OfficeRuntime === "undefined" || !OfficeRuntime.auth || !OfficeRuntime.auth.getAccessToken)
    return addMsg("error", "SSO nepalaikomas šioje aplinkoje (reikia naujesnio Office / manifesto WebApplicationInfo).");

  addMsg("user", "🔎 " + question);
  $("q").value = "";
  const think = addMsg("assistant", "Ieškau jūsų dokumentuose…");
  document.querySelectorAll(".act,#send").forEach((b) => (b.disabled = true));
  try {
    // Silent token from the user's existing Office sign-in (no second login).
    const ssoToken = await OfficeRuntime.auth.getAccessToken({ allowSignInPrompt: true, allowConsentPrompt: true });
    const r = await api("/_gp/m365", { method: "POST", body: JSON.stringify({ question, sso_token: ssoToken }) });
    if (r.status === 401 || r.status === 403) { think.className = "msg err"; think.innerHTML = esc("Neprisijungta prie OWUI — prisijunk naršyklėje."); return; }
    if (!r.ok) throw new Error("HTTP " + r.status + " " + (await r.text()).slice(0, 160));
    const d = await r.json();
    think.innerHTML = esc(d.answer || "(tuščias atsakymas)");
    if (Array.isArray(d.sources) && d.sources.length) {
      const src = document.createElement("div");
      src.className = "src";
      src.innerHTML = "Šaltiniai: " + d.sources.map((s) =>
        s.web_url ? `<a href="${esc(s.web_url)}" target="_blank">${esc(s.title || s.source)}</a>` : esc(s.title || s.source)
      ).join(" · ");
      think.appendChild(src);
    }
  } catch (e) {
    think.className = "msg err";
    // 13xxx = Office SSO error codes (consent needed, not signed in, etc.).
    think.innerHTML = esc("Nepavyko: " + (e.message || e));
  } finally {
    document.querySelectorAll(".act,#send").forEach((b) => (b.disabled = false));
  }
}

Office.onReady((info) => {
  HOST = info.host;
  loadBrand();
  loadModels();
  document.querySelectorAll(".act[data-op]").forEach((b) =>
    b.addEventListener("click", () => runOp(b.getAttribute("data-op"))));
  $("useDocs").addEventListener("click", useMyDocuments);
  $("send").addEventListener("click", () => {
    const t = $("q").value.trim(); if (!t) return; $("q").value = "";
    runOp("custom", t);
  });
  $("stop").addEventListener("click", () => { if (ABORT) ABORT.abort(); });
});

async function loadBrand() {
  // White-label: same brand.json the login page + side panel use.
  try {
    const r = await api("/_gp/brand.json");
    if (!r.ok) return;
    const b = await r.json();
    if (b && b.name) $("brandName").textContent = b.name + " AI";
    if (b && b.color) document.documentElement.style.setProperty("--gp-accent", String(b.color));
    if (b && b.logo) {
      const img = $("brandLogo");
      img.onload = () => (img.style.display = "inline");
      img.onerror = () => (img.style.display = "none");
      img.src = /^https?:/i.test(b.logo) ? b.logo : BASE + b.logo;
    }
  } catch (e) { /* keep baked title */ }
}
