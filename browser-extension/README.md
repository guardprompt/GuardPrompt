# GuardPrompt for Browser

Minimal Chrome/Edge (Manifest V3) side-panel extension: ask the GuardPrompt AI
about the current web page or a text selection, from any tab.

## Why our own (vs a third-party one)

- **Anonymization is automatic.** Page content is sent as a normal OpenWebUI chat
  message to `/api/chat/completions`, so the `gp-pipeline` inlet masks PII **before**
  anything reaches an external LLM. There is no direct-to-model path to leak through.
- **No stored passwords.** It reuses the browser's existing OWUI session cookie
  (`credentials: 'include'`). The user just logs into OWUI once in the browser.
- **Minimal permissions.** `sidePanel`, `activeTab`, `scripting`, `storage`, and a
  single `host_permissions` entry for the OWUI host. No `<all_urls>`, no telemetry.

## How it works

1. Click the toolbar icon → the side panel opens (this click grants `activeTab`).
2. It lists models from `GET /api/models`.
3. Pick **Pažymėtas** (selection) or **Visas puslapis** (full page), type a question.
4. The panel reads the page via `chrome.scripting.executeScript` (selection +
   `document.body.innerText`, capped at 20k chars) and POSTs it to
   `/api/chat/completions` with `stream:false`.

## Install (developer / load unpacked)

1. `chrome://extensions` (or `edge://extensions`) → enable **Developer mode**.
2. **Load unpacked** → select this `browser-extension/` folder.
3. Log into OWUI (`https://chat.example.com`) in the same browser.
4. Click the GuardPrompt toolbar icon → the panel opens.
5. If the OWUI host differs, set it via the ⚙️ gear (stored in `chrome.storage.local`).

## Configuration

- Default OWUI base URL: `https://chat.example.com` (edit in `manifest.json`
  `host_permissions` **and** the gear settings; both must match for cookies to be sent).
- To read pages on internal domains without re-clicking the icon per tab, add those
  hosts to `host_permissions` (widens scope — do it deliberately).

## Centralized deployment (admin — force install + locked config)

Employees do NOT configure anything. The admin force-installs the extension and pushes
the config via enterprise policy; the extension reads it from `chrome.storage.managed`
(read-only) and hides the ⚙️ settings entirely (see `managed_schema.json` keys
`baseUrl`, `modelFilter`).

**1. Get a stable extension ID** (force-install needs one; load-unpacked IDs are random):
- **Chrome Web Store, private/unlisted** (recommended): upload the folder as a zip,
  restrict visibility to your Google Workspace domain, note the extension ID.
- **or self-host**: add a `"key"` to `manifest.json` (deterministic ID), pack a `.crx`,
  host the `.crx` + an `update.xml`, and use the update URL in the force-install policy.

**2a. Google Admin Console** (managed Chrome / ChromeOS / managed browsers):
- Devices → Chrome → Apps & extensions → Users & browsers → add by ID →
  Installation policy = **Force install**.
- In "Policy for extensions" paste:
  ```json
  { "baseUrl": { "Value": "https://chat.example.com" },
    "modelFilter": { "Value": "gp-browser" } }
  ```

**2b. Windows GPO / Registry** (Chrome shown; Edge = `...\Policies\Microsoft\Edge\...`):
- Force install:
  `HKLM\SOFTWARE\Policies\Google\Chrome\ExtensionInstallForcelist`
  → value `1` = `"<EXT_ID>;https://clients2.google.com/service/update2/crx"`
  (or your self-hosted update URL).
- Locked config (managed storage):
  `HKLM\SOFTWARE\Policies\Google\Chrome\3rdparty\extensions\<EXT_ID>\policy`
  → `baseUrl` (REG_SZ) = `https://chat.example.com`
  → `modelFilter` (REG_SZ) = `gp-browser`

Result: extension auto-installed for every user, pinned to the `gp-browser` model,
pointing at the right OWUI host, with **no user-editable settings**. To change it,
the admin updates the policy centrally.

## Security notes / TODO before wider rollout

- **VERIFY anonymization fires on this path.** Send a name + personal code via the
  extension and confirm the proxy/LLM received the masked version (same check as the
  normal chat). The inlet should run because `gp-pipeline` is a global (`["*"]`) filter,
  but confirm on your deployment.
- Cloudflare Access: the fetch carries the CF Access cookie too; the user must have a
  valid CF session or the API call is redirected to login and fails.
- No icons bundled yet (uses the default). Add `icons/` + `manifest.icons` for polish.
- No streaming yet (whole answer at once) — fine for an MVP; add SSE later.
- Not published to a store; distribute internally as an unpacked/CRX with the org policy.
