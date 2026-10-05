// TEMPLATE — do NOT put a real client value here (this file is committed).
// The real env-config.js is generated per-deployment from .env by gen-env-config.sh
// (DOCLING_PUBLIC_HOST -> GP_OWUI_BASE, GP_BROWSER_MODEL_ID -> GP_MODEL_FILTER) and is
// gitignored, so a client's host/brand never reaches the shared repo. If env-config.js is
// missing, sidepanel.js falls back to neutral defaults.
window.GP_OWUI_BASE = "https://chat.example.com"; // OWUI base URL for this deployment
window.GP_MODEL_FILTER = "gp-browser";            // model id the panel locks to
