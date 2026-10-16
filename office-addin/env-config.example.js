// TEMPLATE — do NOT put a real client value here (this file is committed).
// The real env-config.js is generated per-deployment from .env (same pattern as the
// browser-extension) and is gitignored, so a client's host/brand never reaches the
// shared repo. If env-config.js is missing, taskpane.js falls back to same-origin.
//
// IMPORTANT: the add-in is served FROM the OWUI/guardproxy origin (e.g.
// https://chat.example.com/officeaddin/), so leaving GP_OWUI_BASE empty makes every
// /api call same-origin and the OWUI session cookie rides along automatically — no
// token handling, exactly like the browser side panel.
window.GP_OWUI_BASE = "";                 // empty = same-origin (recommended)
window.GP_MODEL_FILTER = "gp-browser";    // model id the pane locks to (no leaky picks)
