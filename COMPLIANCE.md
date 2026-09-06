> 🌐 **Language / Kalba:** **English** · [Lietuvių](COMPLIANCE.lt.md)

# GuardPrompt — GDPR & EU AI Act compliance

This document shows **how GuardPrompt supports, through technical measures,** compliance
with the General Data Protection Regulation (GDPR, 2016/679) and the EU Artificial
Intelligence Act (AI Act / Reg. 2024/1689).

> **Important:** GuardPrompt provides **technical measures**. Final legal compliance
> depends on the deployment context, the purpose of use and the organization's processes —
> the data controller is responsible for it. This document is not a legal guarantee or
> a certificate.

---

## 1. Core principle — data does not leave

The whole system runs **on-premise** (on the organization's own server): OpenWebUI, RAG
(Qdrant), the database (PostgreSQL), OCR (Docling), the anonymizer, a local LLM (Ollama)
and **speech-to-text** (a local Lithuanian transcription engine). No documents,
conversations **or audio** are sent to the cloud **unless** an external LLM (e.g.
OpenRouter) is deliberately configured — and even then **every message is anonymized first**
(see section 4). Voice input and meeting recordings are transcribed locally, so raw audio
never leaves the machine; the resulting text is anonymized on the same path as any chat.
If the anonymizer cannot run, the request is **blocked rather than sent unmasked**
(fail-closed), so a service outage can never turn into a silent data leak.

---

## 2. GDPR compliance

| Article | Requirement | How GuardPrompt supports it |
|---|---|---|
| **Art. 5** | Data minimization, purpose limitation, integrity and confidentiality | The anonymizer removes excess personal data before storage/processing; on-prem isolation |
| **Art. 9** | Special categories of data | Masked: **health, mental health, racial/ethnic origin, political opinions, religious and philosophical beliefs, trade-union membership, biometrics, sexual orientation/sex life** |
| **Art. 10** | Data relating to criminal convictions | Crime/criminal-record data masked (`[CRIMINAL]`) |
| **Art. 25** | Data protection by design and by default | Anonymization on by default; "a leak is worse than over-masking"; **fail-closed** |
| **Art. 30** | Records of processing activities | `gp-claude-proxy` can persist a **pseudonymized who-sent-what audit** (`gp_audit`) of every AI request — the sender identity, timestamp and masked content, retained for a configurable period (`GP_AUDIT_TTL_DAYS`) |
| **Art. 32** | Security of processing | On-prem, container isolation, license key, audit log; secrets in `.env`, not in code; **fail-closed anonymization** and a **Zabbix monitoring plane** with preventive + leak triggers and `*_fail_closed` alarms provide continuous assurance the safeguards are operating |
| **Art. 35** | Data Protection Impact Assessment (DPIA) | On-prem architecture and anonymization reduce risk and ease the DPIA |

**Identifiers masked (besides Art. 9/10):** names/surnames, personal code, email, phone,
IBAN, payment card, crypto addresses, IP, addresses, dates, company/VAT/document numbers,
**passport, ID card, SODRA, SWIFT/BIC, court case/contract nr., patient/medical record nr.,
vehicle plates, driver's licence/DQC, registration certificate, VIN, MAC, IMEI, GPS
coordinates**, dev/IT secrets (API keys, tokens, certificates, connection strings).

---

## 3. EU AI Act (2024/1689) compliance

| Article | Requirement / prohibition | How GuardPrompt supports it |
|---|---|---|
| **Art. 5(1)(g)** | Bans biometric categorisation to **infer** race, political opinions, trade-union membership, religious/philosophical beliefs, sex life, sexual orientation | The anonymizer **removes** these attributes → the LLM never sees them → **cannot infer them** (compliance *by design*) |
| **Art. 5(1)(f)** | Bans emotion recognition in the workplace and education | GuardPrompt does **not** perform emotion recognition |
| **Art. 10** | High-risk: data governance and quality | Anonymized, minimized data; KB content curated via `kb-admin` |
| **Art. 12** | Record-keeping (*logging*) | OpenWebUI audit log (`AUDIT_LOG`), anonymizer activity markers, and the optional `gp_audit` record of Claude-proxy usage (pseudonymized content + sender identity) — plus Prometheus metrics retained by Zabbix |
| **Art. 14** | Human oversight | An administrator manages knowledge bases, access and syncing via `kb-admin` |
| **Art. 50(1)** | Transparency — inform that the user is interacting with AI | Handled at the OpenWebUI interface level |
| **Art. 50(2)** | Machine-readable marking of synthetic output | **Gap — see below.** Provenance metadata is currently lost |
| **Art. 50(4)** | Disclosure that content is artificially generated | **Implemented for images** — the official EU mark is burned into every generated picture (below) |

### 3.1 Marking of AI-generated images

Article 50 applies from **2 August 2026**; for systems already on the market the
machine-readable part has until **2 December 2026**. Penalties reach €15 M or 3 % of
global turnover. The Commission's Code of Practice asks for a *layered* solution —
a visible disclosure, machine-readable provenance, invisible watermarking and
fingerprinting; no single technique satisfies it alone.

**What GuardPrompt does today**

Every image produced through the chat is stamped with the European Commission's
official **"AI GENERATED"** mark (the *Fully AI-Generated* icon, published for free
use without attribution). It is applied by the `guardprompt_ai_label` OpenWebUI
filter function:

- burned **into the pixels**, so the mark survives download and resharing — a UI-only
  label would not, and the Code of Practice requires it to remain visible;
- bottom-right corner, ~9.5 % of image width, using the EU semi-transparent variant;
- black or white variant chosen automatically from the brightness behind it, so the
  mark stays legible on any picture;
- idempotent — regenerating or re-processing never double-stamps.

Technical note: the mark is applied in the filter's `stream` hook. It is the only
place it can be done — OpenWebUI passes `outlet` filters a whitelist of message
fields (`id`, `role`, `content`, `info`, `timestamp`, `output`) with the `files`
list holding the picture stripped out, so an `outlet` filter can never reach the
image.

**Known gap — machine-readable provenance (Art. 50(2))**

Images arrive from the model provider carrying a signed C2PA manifest, but that
manifest does not survive: OpenWebUI re-encodes the image before the filter sees
it, and any visible mark would invalidate the signature in any case, because a
C2PA signature covers the pixels. An invalidated manifest is **deliberately not**
carried forward — presenting a broken credential is worse than presenting none.

Closing this gap requires signing our own C2PA manifest (an own certificate plus a
signing service). Planned before the 2 December 2026 deadline. Until then the
deployment satisfies the **visible disclosure** duty but not the machine-readable
one, and this should be stated in any conformity documentation rather than assumed.

---

## 4. Where anonymization runs

The anonymizer is integrated on **several paths**:

1. **KB ingestion** — uploaded documents (Docling OCR → text) are anonymized before they
   enter the knowledge base (Qdrant).
2. **Live chat** — the `gp-pipeline.py` *inlet* filter anonymizes **every user message and
   attached-image OCR** BEFORE sending it to the LLM (including external OpenRouter).
3. **Developer tooling** — `gp-claude-proxy` sits between the company's Claude Code clients
   (Claude Code CLI, the VS Code extension, JetBrains IDEs; and the desktop app in API-key
   mode only) and `api.anthropic.com`. Source code and prompts are pseudonymized before egress; Anthropic receives only opaque tokens
   (`GP_a3298922c55a`). Unlike paths 1 and 2, this one is **reversible** — the model's answer
   is written back into source files, so the mapping must restore on the way in. The mapping
   is held in this deployment's own Postgres and never leaves it. An optional
   **audit** table (`gp_audit`) additionally records *who* sent each request and *when*,
   storing only the already-pseudonymized content — the Art. 30 record of AI usage, kept
   separate from the reversible vault. ([GP-CLAUDE-PROXY.md](GP-CLAUDE-PROXY.md))
4. **Your own applications** — the same anonymizer is exposed as a **REST API** (Bearer key;
   JSON, plain text or file; `/process` for PDF/DOCX/…), so external systems can anonymize
   before archiving, forwarding or any other processing. ([API.md](API.md))

**Fail-closed guarantee:** if anonymization fails or times out, the message is **blocked** —
unprocessed text never reaches the LLM. The same applies if the `gliner` NER service is
unavailable: rather than silently returning text without Art. 9/10 coverage, the request is
blocked with `[PROCESSING DISABLED: ANONYMIZATION SERVICE UNAVAILABLE]` (`ANON_REQUIRE_GLINER`).
An invalid licence blocks the same way (`[PROCESSING DISABLED: LICENSE IS NOT VALID]`).
`gp-claude-proxy` fails closed on the same principle (`GP_FAIL_CLOSED`, default on): a gliner
outage refuses the request rather than forwarding raw source code.

Three technical layers (all controlled via `.env` `ANON_*`, corrected via `ANON_ALLOW_WORDS` /
`ANON_ALLOW_REGEX`):
deterministic regex (identifiers + document numbers + dev/IT secrets) → `gliner` NER
(GDPR Art. 9/10 + AI Act Art. 5(1)(g) categories). Details:
[ARCHITECTURE.md](ARCHITECTURE.md), section "Anonymization coverage".

---

## 5. Limits and responsibility

- GuardPrompt does **not** guarantee 100% detection — unstructured, rare or context-free
  sensitive phrases may slip through. Principle: lean toward over-masking; specific cases
  are handled via the allowlist (`ANON_ALLOW_WORDS` / `ANON_ALLOW_REGEX`) / custom words.
- **Accuracy of masking (Art. 5 quality).** The NER layer can over-label — job titles and
  institutions may be read as names. A shared validation filter (`person_noise.py`, used by
  both the anonymizer and the Claude gateway) rejects such spans, so genuine over-masking is
  minimised without weakening detection of real names. Over-masking never causes a leak.
- Using an external LLM (OpenRouter etc.) is the organization's decision; even then only
  anonymized text is sent, but the controller is responsible for the provider's terms.
- **Prompt injection is bounded, not solved.** A document placed in a knowledge base can
  contain text addressed to the model ("ignore your instructions", "send this to …"). What
  ultimately limits the damage is **capability reduction and anonymization**, not
  detection: no tools and no tool servers are configured, code execution runs browser-side
  (Pyodide, no Jupyter endpoint), so an injected instruction has **nothing to act with** —
  and the model only ever sees anonymized text, so it cannot disclose personal data it
  never received, nor send anything to an address that has already become `[EMAIL]`.
  Four detection layers sit on top of that; anything they identify is replaced with
  `[PROTECTION]` and the document is processed normally rather than rejected:

  | Layer | Where | Catches |
  |---|---|---|
  | Regex + de-obfuscation | anonymizer | literal wording in the languages listed, plus leetspeak, spaced letters, zero-width characters, homoglyphs and base64-encoded payloads |
  | Hidden-text scan | docling extraction | text a reader could not see — white-on-white, ~1 pt, off-page. Language-independent: it never reads the text, only checks whether a human could have |
  | Script anomaly | anonymizer (final pass) | a CJK/Arabic/Devanagari sentence inside a Lithuanian document, whatever it says |
  | Semantic scan | gliner `/injection` | instruction-override intent in ~100 languages, including paraphrase |

  Ordering matters: the script and semantic layers run **after** anonymization is complete,
  on the finished text. When they were interleaved with the masking passes, a marker
  inserted by one layer merged into the next sentence and pushed a real injection back
  under the detection threshold — one guard silently disabling another.

  The semantic layer scores each **sentence** (an injection buried in a 2.5 k-character
  chunk scored 0.40 as a whole against 0.83 alone — chunk-level scanning would look like it
  worked and miss everything) and the score is **contrastive**: similarity to injection
  prototypes minus similarity to ordinary administrative language. Plain similarity was
  unusable — calibrated on a real 606-sentence customer document the closest legitimate
  sentence scored 0.660 against the weakest injection at 0.661. Contrastive scoring moved
  legitimate p99 to 0.035 and produced a workable margin with no false positives on that
  document.

  Honest limits: the regex alone was measured at **1/15** on the same injection translated
  into fifteen languages — it is a speed bump, not a boundary, and must never be presented
  as one. The semantic threshold is calibrated on one corpus and needs re-checking against
  a materially different one (`INJ_THRESHOLD`). Dedicated classifier models were evaluated
  and rejected: the free ones either ignore Lithuanian or flagged 4 of 7 legitimate
  Lithuanian legal texts, and the multilingual generative guard cost ~535 ms per call.
  The residual risk is a misleading **answer**, not data disclosure or an action taken on
  the attacker's behalf.
- Legal compliance (DPIA, contracts, notification, retention periods) is ensured by the
  organization; GuardPrompt provides technical measures to facilitate it.
