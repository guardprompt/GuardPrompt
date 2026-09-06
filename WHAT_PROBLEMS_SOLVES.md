> 🌐 **Language / Kalba:** **English** · [Lietuvių](WHAT_PROBLEMS_SOLVES.lt.md)

# What Problems GuardPrompt Solves
GuardPrompt is built to address real, recurring challenges inside organizations that handle sensitive information, large volumes of documents, and strict compliance requirements. This document outlines the practical problems GuardPrompt solves and the value it delivers.

**The one-line version:** every reason your organization currently says *"we
can't use AI"* — data leaving the building, GDPR/NIS2 exposure, no audit trail,
untrusted content, per-seat cost — GuardPrompt turns into *"we can, on our own
terms."* It is a complete, self-hosted AI platform, not a single tool.

---

## 1. Sensitive information cannot be safely sent to cloud AI
Organizations work with personal data, contracts, procedures, HR files, logs, internal reports, and regulatory documents.  
Sending such content to cloud LLM providers (OpenAI, Google, Anthropic) creates compliance risks.

**GuardPrompt solves this by:**
- processing original documents locally,
- anonymizing sensitive data using an on-prem LLM,
- ensuring that only *de-identified* text may be used externally (if the organization chooses to).

This enables safe AI adoption under GDPR, NIS2, and internal security policies.

---

## 2. Need for consistent, automated anonymization of documents
Manual anonymization is:
- slow,
- inconsistent,
- error-prone,
- expensive.

**GuardPrompt provides local anonymization** (deterministic regex + on-prem NER) that removes:
- names (incl. foreign & inflected forms), addresses, contacts,
- identifiers: personal code, email, phone, IBAN, card, crypto, IP, company/VAT/doc numbers,
- document numbers: passport, ID card, SODRA, SWIFT/BIC, court case / contract, patient / medical record, product & license keys,
- vehicle & IT data: license plates (LT + foreign/vanity), driver's license, vehicle registration / tech passport, MAC, VIN, IMEI, GPS coordinates,
- developer / IT secrets: cloud & SaaS tokens (AWS/GitHub/OpenAI/Slack/Google/Stripe/JWT), PEM private keys & certificates, SSH keys, connection strings with credentials, Bearer / config key=value secrets,
- **GDPR Art. 9/10 special categories + EU AI Act Art. 5(1)(g)**: health, mental health, criminal record, political affiliation, religious & philosophical belief, trade-union membership, biometric data, racial/ethnic origin, sexual orientation, whistleblower. Removing these means the LLM cannot infer or categorise on sensitive attributes — AI Act compliance by design.

Everything is toggle-able per category and correctable via an allowlist.
Anonymization happens before any external use — a leak is treated as worse than over-masking.

---

## 3. Employees struggle to find information across many internal documents
Knowledge is buried in:
- PDFs,
- scanned files,
- Word documents,
- SharePoint,
- email attachments,
- intranet portals.

Employees lose hours searching or re-reading documents.

**GuardPrompt turns all documents into a searchable AI knowledge base** powered by semantic RAG.

---

## 4. There is no internal AI assistant trained on the organization's documents
Cloud AI agents cannot access internal files (or are unsafe to do so).

**GuardPrompt provides a private AI assistant** that:
- answers questions based on internal documents,
- explains rules, policies, and procedures,
- summarizes long documents,
- compares different versions,
- extracts key points and obligations.

This boosts productivity and decision-making.

---

## 5. High cost of individual AI subscriptions (ChatGPT, Copilot, etc.)
Purchasing a subscription for each employee quickly becomes expensive.

**GuardPrompt replaces dozens or hundreds of subscriptions with one internal AI engine**, resulting in significantly lower cost per employee with unlimited usage.

---

## 6. Organizations need full control over their AI infrastructure
Cloud AI tools do not provide:
- control over data storage,
- control over access,
- auditability,
- ability to run offline,
- reproducible behavior.

GuardPrompt is fully on-premise:
- no telemetry,
- no external API calls,
- works in air-gapped environments,
- complete audit and governance.

---

## 7. Reduces knowledge bottlenecks (“ask the expert” problem)
Many processes depend on a few key experts.  
When they are away, workflows slow down.

**GuardPrompt democratizes access to knowledge**, ensuring consistent answers without overloading specialists.

---

## 8. Faster onboarding and training of new employees
New employees struggle to find relevant documents and understand processes.

With GuardPrompt they can ask:
- “How do we handle incident reporting?”
- “What is the procurement process?”
- “Explain the difference between versions of this policy.”

Onboarding time decreases significantly.

---

## 9. Ensures consistent answers across the organization
Without a central knowledge engine:
- each person interprets rules differently,
- outdated versions circulate,
- misunderstandings create risk.

GuardPrompt always answers using **official, indexed documents**, ensuring consistency.

---

## 10. Decreases mistakes in critical processes
Mistakes often occur when:
- people use outdated versions of procedures,
- employees miss important clauses,
- instructions are unclear.

GuardPrompt makes relevant rules explicit and easy to verify.

---

## 11. Enables full-text search inside scanned PDFs and legacy documents
Traditional search fails on:
- scanned PDFs,
- poor OCR files,
- tabular data,
- multi-page mixes of text and images.

GuardPrompt reconstructs text through modern OCR and parsing, making archives searchable.

---

## 12. Eliminates manual comparison of document versions
Changing policies and procedures require careful reading.

GuardPrompt can answer:
- “What changed since version 2.1?”
- “Summarize differences between two documents.”

Saving hours of manual work for auditors, legal teams, and compliance departments.

---

## 13. Improves communication between departments
Information silos cause delays and misunderstandings.

GuardPrompt provides a **single unified knowledge base**, reducing friction between teams.

---

## 14. Reduces repetitive questions to senior staff
Experts often receive the same questions repeatedly.

GuardPrompt handles these queries, freeing senior employees for higher-value tasks.

---

## 15. Works offline (air-gapped environments)
Essential for:
- government institutions,
- defense and law enforcement,
- critical infrastructure,
- sensitive IT systems.

GuardPrompt requires no internet connection.

---

## 16. Facilitates audit and regulatory responses
Auditors often need to locate specific requirements quickly.

GuardPrompt allows instant semantic search across thousands of documents.

---

## 17. Future-proof and integrable
Because the system is modular, it can integrate with:
- SharePoint,
- Confluence,
- document management systems,
- local directories,
- future AI models.

This makes GuardPrompt adaptable to evolving needs.

---

## 18. Developers leak source code and customer data to AI coding tools
AI coding assistants (Claude Code, Copilot, Cursor) are now indispensable — and a
massive, invisible exfiltration path. Every prompt can carry customer names,
credentials, connection strings, personal codes and proprietary source straight
to a cloud model.

**GuardPrompt provides a Claude proxy** that sits between the developer's tools
and Anthropic, replacing sensitive values with **reversible** tokens on the way
out and restoring them on the way back — the developer sees real code, Anthropic
never does, and the mapping never leaves your infrastructure. It works with the
Claude Code CLI, the VS Code extension and JetBrains IDEs in either
subscription-passthrough or shared-API-key mode (the desktop app in shared-API-key
mode only), and writes a **pseudonymized audit record of who sent what**
(GDPR Art. 30). This is the difference between
banning AI coding tools and adopting them safely.

---

## 19. Documents and prompts carry hidden attacks (prompt injection)
An uploaded PDF or a pasted block of text can contain instructions aimed at the
AI itself — "ignore your rules", hidden white-on-white text, obfuscated
payloads — hijacking the assistant into leaking data or misbehaving.

**GuardPrompt neutralizes prompt-injection** with a 4-layer detector (regex +
de-obfuscation, hidden-text, script-anomaly, and contrastive semantic scoring)
that runs *after* anonymization and replaces hostile spans with `[PROTECTION]`
rather than rejecting the document. Malicious instructions are defused; the
legitimate content still gets processed.

---

## 20. No visibility, no proof the AI is behaving
"Is the anonymizer actually running? Is anything leaking? Is a service about to
run out of disk, memory, or a certificate?" Most self-hosted AI stacks cannot
answer these questions until something breaks.

**GuardPrompt ships with full observability** — a Zabbix monitoring stack that
scrapes uniform `/metrics` from every service, with **preventive triggers** that
forecast disk / certificate / connection-pool exhaustion before it happens, and
**memory-leak and code-quality triggers** (rising-floor detection, event-loop
lag, connection bloat, fail-closed alarms). One trigger, `model_on_gpu=0`, would
have caught a real performance regression during build-out. You get proof the
guardrails are up, not just a promise.

---

## 21. Meeting notes require sending audio to the cloud

Transcribing meetings, calls or dictations normally means uploading the audio to a
cloud speech-to-text service — the most sensitive raw data (voices, names and numbers
spoken aloud) leaves the organization **before** anonymization can even run, and the
minutes then have to be written by hand.

**GuardPrompt benefit:** meetings are recorded and transcribed **entirely
on-premise** by a local Lithuanian speech-to-text engine — the audio never leaves the
machine. The transcript is anonymized like any other text and turned into a
structured **meeting protocol** automatically, saved with the recording attached.
Minutes are produced in minutes, with **zero audio egress**.

## 22. Interactive tools and terminals leak command output to AI

When users run commands or tools whose output is fed back to the model, that output
(file contents, hostnames, credentials) can reach an external LLM unfiltered.

**GuardPrompt benefit:** an optional **sandboxed terminal** runs with a default-deny
egress firewall and admin-only privilege escalation, and its output is anonymized on
the same path as chat — so even interactive tooling cannot leak sensitive data.

## Summary Table

| Problem | GuardPrompt Benefit |
|--------|----------------------|
| Sensitive data risks | Local anonymization + controlled external use |
| Hard to find information | Semantic search & AI answers |
| No internal AI assistant | Private RAG-based assistant |
| Expensive individual AI subscriptions | Centralized, cost-efficient AI engine |
| Need full control | Fully on-prem, auditable, offline-capable |
| Knowledge bottlenecks | Democratizes access to expertise |
| Slow onboarding | AI explains documents and processes |
| Version confusion | Automated comparison & summaries |
| Scanned PDF limitations | Modern OCR & extraction |
| Cross-team inconsistency | Unified knowledge base |
| Audit pressure | Instant answers from official docs |
| Developers leaking code/data to AI tools | Claude proxy — reversible masking + who-sent audit |
| Malicious prompt injection in documents | 4-layer injection defense → `[PROTECTION]` |
| Meeting audio sent to cloud transcription | On-prem transcription + auto-protocol, zero audio egress |
| Tools/terminals leaking command output | Sandboxed terminal, output anonymized before any model |
| No proof the guardrails work | Zabbix monitoring with preventive & leak triggers |

---

# It is written to be clear for:
- decision makers,
- IT/security teams,
- compliance/legal teams,
- technical readers.

