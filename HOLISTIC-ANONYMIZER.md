# Holistic anonymizer — architecture

> Status: **BUILT on dev, behind flags — not yet prod-default** (2026-09). Both engines
> pass `pii-lab/holistic_testset.py` **24/24, 0 leaks**, plus a broader real-document
> regression. See **[As built](#as-built-2026-09)** for the deviations from this design
> (whole-document special gate, structural stage dropped, allowlist-token fix).

## Problem

The current anonymizer masks **every detected span independently** (regex + gliner NER +
special-category dict). It over-fires, which actively breaks the product:

- **Chat / RAG:** false positives in the query or KB content (e.g. `Regitroje`→`[POLITICAL]`,
  `policijoje`→…) shift the embedding → **no KB answer** for employees.
- **DEV proxy (SQL/code):** field **labels** (`Pavardė`, `Kraujo grupė`, `Pažymėjimo numeris`),
  **placeholder** values (`Pavardenis`, `1970-01-01`, `00000000`), and **code identifiers**
  (`firstName`, `bloodGroup: string`) are masked → devs can't use the model for code.

Root cause: no understanding of **context, structure, validity, or identifiability** — a token
that *looks* like PII is masked even when it carries no personal information.

The user rejected the "simple path" (per-service exceptions / allowlists). This is a **holistic**
redesign: one engine that decides by signals + understanding, not word-lists.

## Four classes (the core taxonomy)

| Class | Examples | Rule | Leak philosophy |
|---|---|---|---|
| **0. Secrets / credentials** | API keys, tokens, JWT, private keys, passwords, connection strings | **ALWAYS mask**, aggressive. Never gated. | leak = critical → over-mask OK |
| **1. Direct personal IDs** | asmens kodas, phone, email, IBAN, plate, passport | Mask **iff the value VALIDATES** (checksum/format) | strong, but validated |
| **2. Personal / quasi / special** | names, city, title, Art.9/10 (health, criminal…) | **HOLISTIC** (scoring + context + verify) | proportionate |
| **3. Non-sensitive** | field labels, code identifiers, generic nouns | **never mask** | — |

**Classes 0 and 1 are unconditional floors.** The holistic relaxation touches **class 2 only** —
so secrets/tokens/keys and validated direct IDs are never weakened.

## Per-class mechanics

### Class 0 — Secrets (always-on, highest priority, runs FIRST)
- **Format regexes:** provider prefixes (`sk-`, `AKIA`, `ghp_`, `xoxb-`, …), JWT `eyJ…`,
  `-----BEGIN … KEY-----`, `Bearer …`, connection strings, passwords in URLs. (Extend
  `anonymizer/secrets_regexes.py`.)
- **Entropy detector:** unknown-format high-entropy strings (≥ threshold) → mask, so custom
  keys without a known prefix are still caught.
- Placeholder secrets (`YOUR_API_KEY`, low-entropy/canonical) may pass; **when in doubt, mask**.

### Class 1 — Direct IDs (always-on, validated)
- Every direct-ID regex gains a **validator**: LT asmens kodas **checksum**, IBAN checksum,
  phone/plate format, email shape. A match that fails validation (`00000000000`, `1970-01-01`
  as a doc number, `00000000`) is treated as a **placeholder → keep**.
- Validation is what kills most DEV placeholder noise deterministically (no LLM needed).

### Class 2 — Personal / quasi / special (the holistic engine)
Three cooperating layers (A scoring backbone, B verification, C structure):

**C — Structural parse (cheap, always).** Recognise document shape and tag each token's ROLE:
`label`/`key`, `value`, `code-identifier`/`type`, `table-cell`, `prose`. PII logic applies to
**values in a personal-data context**, never to labels/keys/code. (`Kraujo grupė` = label →
skip; `bloodGroup: string` = code → skip.)

**A — Multi-signal risk SCORE (cheap, always).** Per candidate, combine signals into one score:
- gliner NER confidence
- validation result (class-1 style, for embedded IDs)
- **structural role** (label/code → strong negative; value → neutral/positive)
- **context / combination** — direct ID or a full name present in the same **paragraph** window
- **placeholder likelihood** (canonical dummies, epoch dates, repeated chars)
- entity type base weight
Mask when `score ≥ HIGH`; keep when `score ≤ LOW`; **gray band** `(LOW, HIGH)` → send to B.

**B — Local-LLM verification (sparing).** Only the **gray-band** candidates, **batched into ONE
local-LLM call per document**, asked "is this real PII about an identifiable person, or a
label/placeholder/code?" (few-shot, reuses the docling harm-check pattern + local model). Often
**zero** calls per document. A load knob can disable B (fall back to A-only) under GPU pressure.

**Combination rule (inside A):** a name/quasi/special value masks only when its paragraph also
contains (a) a direct ID, or (b) a name+surname pair, or (c) enough quasi-identifiers to single
out a person. Isolated `Jonas`, lone `diabetas`, `Regitra` → keep.

### Class 3 — Non-sensitive
Falls out of A/C automatically (label/code role, no identifying context) → never masked. No
exception list required.

## Windows & context
- **Lone-name gate** window = **paragraph** (split on blank line / double newline). Not sentence
  (would miss name-top + phone-bottom); a lone given name masks only when its paragraph carries a
  stronger identifier.
- **Special-category person-gate** window = **WHOLE DOCUMENT** (as built — see below). The design
  first assumed a paragraph window here too, but the anonymizer segments prose into sentence-level
  paragraphs, so a paragraph window dropped Art.9/10 values whose person sat in a neighbouring
  sentence — an under-mask **leak**. leak-worse-than-over-mask → the special gate keeps every
  special span if a person appears **anywhere** in the document.

## Reversibility (unchanged)
- Reversible paths (proxies, extension) keep the vault (`GP_xxxx` restored to the user).
- KB ingestion path keeps its token scheme. The engine only changes **which** spans are masked,
  not the token/restore machinery.

## Performance / resource design (why it stays fast)
| Layer | Cost | When |
|---|---|---|
| C structural parse | ~1–5 ms (string) | always |
| regex + gliner NER | **as today** (NER already the cost) | always |
| A scoring | ~µs (arithmetic) | always |
| B LLM verify | 0.5–2 s, ONE batched call | **gray band only; often 0** |

Levers: gray-band width (narrow = fewer B calls), **fast-path skip B** when no gray candidates,
verdict **cache**, **B on/off under load**. Per path: KB ingestion = B free (offline); chat = B
gated; DEV proxy = mostly A/C, B rarely (code resolved structurally).

## Acceptance criteria (`pii-lab/holistic_testset.py`, 24 cases)
- Class 0: every secret masked (7/7).
- Class 1: valid IDs masked, placeholders kept (6/6).
- Class 2: full names / person-linked special masked; isolated names/terms, orgs kept (7/7).
- Class 3: all labels/code/generic kept (4/4).
Target: 100% on class 0/1 (safety), ≥ the current baseline on class 2/3 with the DEV/RAG FPs gone.

## Integration points (from the code map)

**Two engines share the regex modules + gliner, opposite reversibility:**
- **Engine A (one-way, OWUI/RAG/chat):** `anonymizer/dk_anonymizer.py` — `_anonymize_text_impl()`
  (`:1523`), FastAPI at `anonymizer:8005`; non-reversible `[TAG]`. Called by `pipelines/gp-pipeline.py`
  over HTTP. **This is the RAG/chat path.**
- **Engine B (reversible, DEV proxy/extension):** `gp-openai-proxy/pseudonymizer.py` — `pseudonymize()`;
  reversible `GP_xxxxxxxxxxxx` + Postgres vault (`store.py`). **This is the DEV path.**

**The two seams where "mask every span independently" lives (spans still `(start,end,tag[,score])`
before the blind right-to-left apply):**
- Engine A: `gp_special.py:301-398` — spans assembled WITH gliner scores, then merged/applied
  (`:397-398`). **Insert the scoring/gating pass here.**
- Engine B: `pseudonymizer.py:235-266` — `found` list (regex + NER, with priority) before merge.
  **Insert here for the DEV path.**

**Confirmed gaps to fix (grounded):**
1. **No validation ANYWHERE** — asmens kodas = `\b\d{11}\b` (`dk_anonymizer.py:1273`, no checksum);
   IBAN no mod-97; credit card no Luhn; phone format-only. → placeholder `00000000000` is masked
   today. **Add validators** (Class 1) — biggest deterministic DEV win.
2. **Special-category dictionaries mask bare category stems with NO person gate** —
   `HEALTH_RE`/`CRIMINAL_RE`/`RELIGION_RE`/… via `_add_dict` (`gp_special.py:175-217, 267-272,
   363-374`). `katalikas`, `hepatitas` masked standalone. → **person-context gate** (Class 2).
3. **No structural role** — regex `.sub()` in the segment loop (`dk_anonymizer.py:1620-1679`) and
   dict/NER spans mask labels/code too. → **structural parse** (Class 3).
4. **No combination logic** — every span independent (confirmed). → **A scoring** (Class 2).

**Reversibility untouched:** the engine changes only WHICH spans are selected; the `[TAG]` /
`GP_xxx` + vault (`store.py`) token/restore machinery is not modified. Allowlist protect/restore
(`protect_allowlist :105` / `restore_allowlist :1717`) stays. Secrets (`secrets_regexes.py`,
default-on, runs first at `:1560/1566`) stay always-on — **not gated**.

## Staged build order (each tested against pii-lab before the next)
1. **Validators (Class 1)** — checksum/format on direct-ID regexes. Deterministic, safe, high value
   (kills `00000000`, epoch dates, invalid codes). Shared module used by both engines.
2. **Structural role (Class 3)** — label/key/code vs value; skip labels/code. Deterministic.
3. **Special-category person-gate (Class 2)** — dict/NER special masked only with person context.
4. **Combination scoring (Class 2)** — names/quasi gated by paragraph-window identifiers.
5. **B local-LLM verify (gray zone)** — optional, batched, load-gated.

## Rollout
1. Build engine + runner against `pii-lab` (offline; no prod).
2. Show test results (all 4 classes) for review.
3. Enable per path behind a flag: KB ingestion first (offline, safest), then chat, then DEV proxy.
4. Compare masked output vs current on a real sample before flipping prod default.

## As built (2026-09)

What actually shipped to dev, and where it diverged from the design above.

### Result
- **Engine A** (`dk_anonymizer.py` + `gp_special.py`) — holistic set **24/24**, 0 leaks. Baseline
  was 14/24 (8 FPs, **0 leaks** — confirmed the diagnosis: an FP machine, not a leak risk;
  class-3/DEV was 0/4).
- **Engine B** (`gp-openai-proxy/pseudonymizer.py` + `nerclient.py`) — **24/24**, 0 leaks.
- Broader real-document regression clean (the two residual "fails" are test-expectation artifacts,
  not masking defects: a kept conviction **verb** while `[PERSON]`/`[CRIMINAL]`/`[HEALTH]` are all
  masked = not a leak; and a case/declension mismatch in a `must_keep` assertion).

### Deviations from the design
1. **Structural role (Class 3 / stage 2) was NOT needed.** The class-3 DEV false positives were
   gliner special-category / plate **over-tags on generic words** (`kodas`, `pažymėjimas`, `VP`,
   label stems), not a structural-role problem. They are killed by the **person-gate + plate-digit
   filter**, so no document-structure parser was built. `firstName: string`, field labels and
   placeholders now survive without a structural layer.
2. **Special-category gate is whole-document, not paragraph** (see [Windows & context](#windows--context)).
3. **B (local-LLM gray-band verify) not built.** Stages 1/3/4 (validators + person-gate +
   plate-digit filter + lone-name gate) reached 24/24 with 0 leaks deterministically, so the
   optional LLM layer was left unbuilt — keeps latency/GPU cost at "today's speed".

### Key fixes found in regression
- **Direct-ID validators** (`anonymizer/validators.py`, shared): LT asmens-kodas checksum, IBAN
  mod-97, Luhn, placeholder detection. **Country-agnostic** (`kodas gali būti ne tik LT`): keep
  placeholders; mask if LT-valid **OR** id-context (label `asmens kodas`/`a.k.`/`ID`/country kw,
  catches foreign codes) **OR** person nearby. Kills `00000000000`, epoch dates, dummy numbers.
- **Plate-digit filter** — gliner tags digit-less generic words (`kodas`, `pažymėjimas`) as a
  plate. Drop a `license plate`/`vehicle registration number` span whose digit-run is empty or a
  placeholder. Present in both engines **and** in `gp-transcribe/pseudo.py`.
- **Allowlist-token vs NER (`Regitra`→`[PLATE]`)** — Engine A's `protect_allowlist` swaps an
  allowlisted term for a `[[ALLOW_n]]` token *before* gliner; gliner then reads the bare token as a
  structured code and re-masks it (destroying the token, so restore can't bring the term back).
  `PLACEHOLDER_RE` missed it (double bracket + digit). Fix: `ALLOW_TOKEN_RE = \[\[ALLOW_\d+\]\]`
  added to the protected zones in `gliner_special_pass` — an allowlisted value is **never**
  re-masked by NER under any label. Engine B has no allowlist-token stage → unaffected.
- **Titled lone surname leaked (`Ponas Kazlauskas`→unmasked)** — gliner tags the whole
  "Ponas Kazlauskas" as one person span; the title trim leaves a *lone* surname, which the
  lone-name gate then drops as a weak identifier (no other ID in the paragraph) → under-mask.
  Fix: `_TITLE_BEFORE_RE` (`pon-`/`gerb`/`dr`/`prof`/`daktar`/`p.`) — a courtesy title immediately
  before a lone name reopens the gate. A title is never a given name, so no new FP. Added to
  **both** engines' lone-name gate.

### Tool-call restore leak (reversible proxies) — `GP_…tsx` filename on disk
Colleagues saw a masked token as a real filename (`GP_06d4261c61d9.tsx`) — "it doesn't decode
back what it hid." A coding agent puts a masked filename/identifier into a `write_file` **tool-call
`arguments`**, but the OpenAI proxy's response restore covered only `content` + `reasoning`, **not
`tool_calls[].function.arguments`** → the token reached the caller and landed on disk. The request
side was safe (`bodywalk.walk_request` masks tool-call arguments, so nothing leaked upstream) — the
gap was purely the missing restore on the way back. **This is not a "don't mask filenames" case:**
masking a person-name filename before the external LLM is correct; with the restore fixed the round
trip completes (`Jonas Petraitis.tsx` → token upstream → `Jonas Petraitis.tsx` back on disk). Fix in
`gp-openai-proxy/app.py`: restore `tool_calls[].function.arguments` (+ legacy `function_call`) in
both the non-stream and streaming paths (streaming uses a per-tool-call-index partial-token tail).
`gp-claude-proxy` never had the bug — it restores the whole payload string (non-stream) and walks
all strings recursively (stream), so `tool_use.input` was already covered; its `app.py` is
transport-specific, **not** lockstep with the OpenAI one (only `pseudonymizer`/`nerclient` are).

### Adversarial capitalization sweep (the recurring PERSON/PLATE mis-ID)
58 probes for capitalized words that are **not** names: sentence-initial common words, ALL-CAPS
(`DĖMESIO`, `SVARBU`), acronyms (`PVM`, `GPS`, `ABS`, `BDAR`, `API`), cities/months, version/code
strings (`v2.0`, `COVID-19`, `GPT-4`), name↔common-word homographs (`Viltis`, `Aušra`, `Rūta`,
`Laukas`, `Vytis`, `Žalgiris`), brands (`Excel`, `Windows`, `Toyota`, `Tesla`), declined institution
(`Regitrą`, `Regitros`), titles/roles, **adjacent-caps common pairs** (`Naujas Projektas`, `Vidaus
Reikalų Ministerija` — the sharpest name+surname trap), and plate-like caps (`kategorija B`, `serija
AB`, `Kodas ABC`, `Tipas EU`). **Result: 0 false positives.** The lone-name gate (single caps token
kept unless a stronger identifier shares the paragraph), `NOISE_HEAD_RE` (title/role/institution
stems), and the plate-digit filter cover all of it — no per-word list. Verified two-sided: real
persons (name+surname, name+health) still mask, so the gate is not merely permissive.

### All five anonymization paths covered
1. Engine A `dk_anonymizer.py` (chat/RAG) ✅ 24/24
2. `gp-openai-proxy` (SQL/PLSQL DEV) ✅ 24/24
3. `gp-openai-proxy-browser` (extension) — same `./gp-openai-proxy` source ✅
4. `gp-claude-proxy` (Claude gateway) — lockstep copy of engine B ✅ 24/24
5. `gp-transcribe/pseudo.py` (meeting protocol) — separate gliner-only masker, `MASK_PERSON=false`
   (participant names intentionally kept), person-gate N/A; **plate-digit filter added** ✅

### Flags (all default-on, per engine)
`ANON_SPECIAL_PERSON_GATE` / `GP_SPECIAL_PERSON_GATE`, `ANON_LONE_NAME_GATE` / `GP_LONE_NAME_GATE`.

### Ship notes
- `anonymizer/validators.py` travels: publish.ps1's pyarmor loop globs every `anonymizer/*.py` and
  **aborts the publish** if any source `.py` is missing from the obfuscated output. On dev it also
  reaches the three proxies via the `./anonymizer:/rules:ro` bind-mount (import verified).
- **Prod-deploy check:** the proxies mount the *obfuscated* `anonymizer/` at `/rules`; confirm the
  obfuscated `validators.py` imports there without a pyarmor dual-runtime clash (validators.py is
  public-algorithm code, no crown-jewel IP — shipping it plaintext is an option if the mount ever
  fails to import).
