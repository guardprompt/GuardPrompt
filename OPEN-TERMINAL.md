> 🌐 **Language / Kalba:** **English** · [Lietuvių](OPEN-TERMINAL.lt.md)

# Open Terminal — AI agent workspace & presentation studio

Gives the OpenWebUI chat model a **real, sandboxed Linux terminal**. Instead of
describing or simulating work, the agent creates **actual files** — documents,
spreadsheets, PDFs and polished, brand-styled **presentations** — that appear in
the file browser (*Rinkmenos*) ready to download. Everything the model sends still
passes through the GuardPrompt anonymizer first, exactly like ordinary chat.

```
OpenWebUI chat ── run_command ──► open-terminal-proxy ──► open-terminal (sandbox)
      │  (model traffic anonymized                              /home/user
      │   via gp-pipeline)                                      real files ↑
      └─────────────────── file browser (Rinkmenos) ◄──────────────────────┘
```

---

## 1. What it is

- Built on **open-webui/open-terminal** (MIT). The sandbox makes **no LLM calls
  itself** — the chat model drives it through the `run_command` tool — so all
  model traffic stays the single choke point through OpenWebUI → `gp-pipeline`
  (anonymized, incl. tool output).
- A **custom image** bakes a full office/PDF/data toolset at build time so it works
  offline with the egress firewall on: LibreOffice (docx/pptx/xlsx → PDF), pandoc,
  and Python libs (`python-docx`, `openpyxl`, `xlsxwriter`, `reportlab`,
  `weasyprint`, `pandas`, `numpy`, `matplotlib`, `Pillow`, …) plus the deck tooling
  below.
- Files are written to `/home/user`, visible in *Rinkmenos*.

## 2. Architecture & security

- **Role-aware proxy** (`open-terminal-proxy`) sits between OpenWebUI and the
  sandbox; OpenWebUI is registered against the proxy, not the sandbox directly.
  It forwards the authenticated user identity (`X-User-Id`) and enforces
  **admin-only install/privileged commands**: a non-admin `sudo`/`apt`/`pip
  install`/`npm install` is not executed — it is replaced by a policy message the
  model relays ("only an administrator can install software"). Admins pass through.
- **Sandbox confinement** = disposable container + no host mounts + **egress
  firewall** (block-all by default, optional domain whitelist) + no `docker.sock`,
  loopback bind, 4 CPU / 8 GB. (It is not an in-container jail; safety comes from
  isolation + controlled egress.)
- **Synchronous `run_command`.** The proxy blocks until a command finishes and
  returns the full output in one response, so one command costs **one** model
  tool-call instead of a start-then-poll loop. Fewer round-trips = faster and,
  crucially, keeps multi-step work under the point where some models corrupt
  their tool-calling state (see Troubleshooting).
- **Working directory follows the user.** When a developer navigates the file
  browser into a folder, the proxy tracks it (per chat session) and runs the
  model's commands **there**, so generated files land in the folder the user is
  looking at. Use plain relative filenames in code.

## 3. Presentation studio — `gpdeck` & `gpweb`

Raw `python-pptx` produces ugly blank-white slides. Two baked helper libraries make
professional, **brand-styled** decks instead:

| Library | Output | Use when |
|---|---|---|
| **`gpdeck`** | editable **.pptx** (+ `.pdf` via `to_pdf()`) | you need a PowerPoint file to edit |
| **`gpweb`** | designer **.html** (`save_html()`) or **.pdf** (`save()`) | you want a striking, non-editable HTML/PDF |

Both share the same brand and features:

- **Brand** — colours, fonts and logo come from `brand.json` (the organisation's
  identity). Ships with a generic default; the real customer brand is loaded at
  runtime from the sandbox volume (`/home/user/.gpbrand/`), never baked into the
  image or committed to a public repo.
- **Themes** — `corporate` (default), `dark`, `bold`, `minimal`, `emerald`
  (`gpdeck.Deck("name", theme="dark")`).
- **Slide types** — title, section, bullets, two-column/columns, image,
  image_full, quote, closing, plus `kpi`, `agenda`, `comparison`, `timeline`,
  `table`, `icon_grid`.
- **Charts** — offline, brand-coloured: `chart_bar`, `chart_line`, `chart_pie`.
- **Icons** — brand-coloured Lucide set (`gpdeck.icons_available()`).
- **AI images** — `gen_image("prompt")` generates an illustration via the proxy's
  `/genimage` endpoint (the OpenRouter key stays in the proxy, never in the
  sandbox where a user could read it).
- **Official brand kit** — if synced from SharePoint, `gpdeck.kit_images()` /
  `gpdeck.kit_templates()` expose official photos and PPT templates (see §7).
- **"AI GENERATED" label** — every slide is auto-stamped, top-right, for
  transparency. Do not remove it.

```python
import gpweb
w = gpweb.Web("dokumentas", theme="corporate")
w.cover("Title", "Subtitle")
w.bullets("Heading", ["Point one", "Point two", "Point three"])
w.columns("Comparison", "Left", ["a", "b"], "Right", ["c", "d"])
w.closing("Thank you!", "www.example.com")
w.save_html()      # -> dokumentas.html   (self-contained, opens in a browser)
# w.save()         # -> dokumentas.pdf
```

```python
import gpdeck
d = gpdeck.Deck("pristatymas", theme="corporate")
d.title("Title", "Subtitle")
d.kpi("Metrics", [("190", "2024"), ("45", "services")])
chart = d.chart_bar("Growth", {"2022": 120, "2023": 145, "2024": 190})
d.image("Growth", chart, caption="Year on year")
d.image_full(d.gen_image("modern flat corporate illustration, blue"), "Digital", "Fast & secure")
d.closing("Thank you!", "www.example.com")
d.save()           # -> pristatymas.pptx
d.to_pdf()         # -> pristatymas.pdf
```

## 4. Setup

1. **Model capabilities** (OpenWebUI → model): **Terminal ON**, **Code Interpreter
   OFF** (its pyodide engine hijacks code execution and cannot reach the shell),
   **Builtin Tools OFF** (else the model takes a "write note / create task"
   shortcut instead of making a file). Terminal = **Open Terminal**.
2. **System prompt** — paste `open-terminal/SYSTEM-PROMPT.md` into the model's
   *System Prompt* field. It steers the model to `gpdeck`/`gpweb`, forbids
   simulated work, and enforces `ls`-verification after each file.
3. **Model choice** — the agent needs **reliable multi-turn tool calling**. Prefer
   **Claude Haiku/Sonnet** (via the [GuardPrompt Claude proxy](GP-CLAUDE-PROXY.md))
   or **Gemini 2.5 Flash**. Avoid **Gemini 3.x Flash / Flash-Lite** for agent work
   (see Troubleshooting).

## 5. Working directory

Each `run_command` starts a fresh shell (state does not persist between commands),
but the proxy injects the folder the user is browsing as the working directory, so:

- Use **relative filenames** (`gpweb.Web("report")`) — the file lands in the user's
  current folder.
- The model should **not** create its own sub-folders or `cd` around; work in the
  current directory and `ls -la` to confirm each file exists.

## 6. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Provider returns **`400 Corrupted thought signature`** | **Gemini 3.x Flash/Flash-Lite** multi-turn tool-calling bug — it stops emitting a valid `thought_signature` after several tool calls | Switch the agent model to **Gemini 2.5 Flash** or **Claude Haiku**. The synchronous `run_command` (§2) reduces round-trips and helps, but the guaranteed cure is the model. |
| Model **describes** work / writes a "note" instead of a file | Code Interpreter or Builtin Tools left ON, or `run_command` not resolved | Set capabilities as in §4; confirm the terminal is selected in the chat composer. |
| File not in *Rinkmenos*, or scattered across folders | model used absolute `/home/user` paths or its own sub-folder, fighting the working-directory sync | Use relative filenames; the system points the command at the user's folder. |
| Ugly blank-white slides | raw `python-pptx` used | Use `gpdeck`/`gpweb` (the system prompt enforces this). |
| Prompt wants HTML but got PDF | `gpweb.save()` writes PDF | Use `save_html()` for a standalone `.html`. |

## 7. Customer branding & the brand kit

- **Security boundary.** Generic defaults (`brand.default.json`, the deck code, the
  AI-GENERATED label, the icon set) are tracked and publishable. The **real
  customer brand** (`brand.json`, logos) is git-ignored and lives only in the
  sandbox **volume** at `/home/user/.gpbrand/` — it never enters the image, a
  public repo, a knowledge base, or the anonymizer.
- **Brand-kit sync (admin-only).** An optional job mirrors a SharePoint document
  library (official logos / PPT templates / photos) into the volume via Microsoft
  Graph — **not** into any knowledge base and **not** through the anonymizer
  (brand identity is public corporate material; anonymizing it would corrupt it).
  Configured in `.env` / the KB Admin App, triggered by OpenWebUI admins only.
