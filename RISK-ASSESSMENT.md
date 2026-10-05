> 🌐 **Language / Kalba:** **English** · [Lietuvių](RISK-ASSESSMENT.lt.md)

# Risk assessment — Claude for developers via the GuardPrompt proxy

| | |
|---|---|
| **Solution assessed** | `gp-claude-proxy` — a GuardPrompt gateway between the company's Claude clients and Anthropic |
| **Procurement** | claude.ai subscriptions for developers — **Team**, not Pro/Max (see R15) |
| **Date** | 2026-07-17 · updated 2026-07-24 |
| **Status** | Built and **verified live against the real `api.anthropic.com`.** Subscription pass-through works end-to-end (real 200 responses, PII masked in the vault, audit rows written); the shared-API-key mode was verified for gate + masking + owner isolation. A fleet pilot is still advised (R14). |

---

## 1. Summary for the decision-maker

The solution **materially reduces**, but does **not eliminate**, the risk of sensitive data reaching Anthropic.

**What it does:** replaces sensitive *values* (secrets, keys, personal data, customer names) with reversible tokens before egress, and restores them on the way back. The mapping stays in our infrastructure. It can also keep a **pseudonymized audit trail of who sent what** and is watched by a **Zabbix monitoring plane** that alarms if the masking guard ever fails — accountability a personal Claude account cannot give.

**What it does not do — the most important line in this document:**

> **The solution masks values, not code LOGIC.** Algorithms, structure, method names, comments and business logic **do reach Anthropic**. If our intellectual property is the algorithm rather than the constants inside it, this risk is **largely unchanged**.

**Recommendation: proceed with the purchase.**

One blocking condition: **buy Team, not Pro/Max** (R15) — Pro/Max permits Anthropic to train on our data.

One decision for management: **accept R1** (code logic reaches Anthropic) or decline Claude altogether. That is a choice, not an obstacle — the gateway does not change R1 either way (see section 5).

Everything else is a deployment condition that does not block the purchase (section 8).

---

## 2. What actually happens

```
Developer → gp-claude-proxy → api.anthropic.com
   (our machine)  ├─ 68 rules (regex)
                  ├─ gliner NER (person, health, criminal, …)
                  ├─ our own list (customers, domains)
                  └─ Postgres mapping (never leaves)
```

**Illustration — what Anthropic actually sees** (real test output on our own code):

```python
class Pipeline:                                    ← SEES
    def __init__(self):                            ← SEES
        self.name = "GP_db7ada001391 Anonymizer"   ← value masked
        self.AWS = "GP_0472b55b6a55"               ← value masked
        self.DB  = "GP_a3298922c55a"               ← value masked

    def run(self):                                 ← SEES
        headers = {"Authorization": "Bearer GP_9e6be8c56d19"}
        return requests.post(self.DB, headers=headers)   ← LOGIC VISIBLE
```

That is exactly the boundary: **constants hidden, shape not.**

---

## 3. Risk register

Likelihood / Impact: 1 = low, 2 = medium, 3 = high. Level = product.

| ID | Risk | Lik. | Imp. | Level | Control |
|---|---|:--:|:--:|:--:|---|
| **R1** | **Code logic, structure and comments reach Anthropic.** Only values are masked | 3 | 3 | **9** | No technical control. The only fix is inference in our own cloud (Azure/AWS), which we do not have. **Accept or decline the purchase** |
| **R2** | **Sensitive values with no pattern** — internal hostnames, customer names, project code names absent from `GP_CUSTOM_WORDS` — pass through as-is | 3 | 2 | **6** | Populate and maintain `GP_CUSTOM_WORDS` carefully. Periodic review |
| **R3** | **Local transcripts.** Claude Code stores sessions in **plaintext** under `~/.claude/projects/` for 30 days on every laptop | 3 | 1 | **3** | **BitLocker is active on every machine** — a lost/stolen laptop is encrypted at rest, closing the main vector. Remaining: lower `cleanupPeriodDays`; IT policy |
| **R4** | **`gp_vault` table** — one place holding the plaintext of **everything ever masked** | 1 | 3 | **3** | Restrict the DB role; `GP_VAULT_TTL_DAYS=30`; include in backup protection scope |
| **R5** | **Gateway outage stops the whole team.** Fail-closed by design | 2 | 2 | **4** | **Zabbix monitoring in place** — `/metrics` on the proxy + gliner + anonymizer, with `nodata()` source-down triggers, `*_fail_closed_total` alarms and preventive pool/disk/cert forecasting. `GP_FAIL_CLOSED=false` is an emergency switch, **but enabling it sends raw code to Anthropic** |
| **R6** | **gliner is probabilistic** — may miss names or health data | 2 | 2 | **4** | Deterministic regex covers identifiers; gliner only supplements |
| **R7** | **Claude in Slack and on the web cannot use the gateway** (Anthropic-hosted) | 2 | 3 | **6** | **Mandatory:** disable those surfaces for these users |
| **R8** | **Anthropic changes the gateway contract.** Claude Code gains capabilities every release | 2 | 2 | **4** | Headers and fields are treated as **open lists**, not an allowlist. Re-test after Claude Code updates |
| **R9** | **New code to maintain.** The gateway is our responsibility | 3 | 1 | **3** | ~950 lines, test suite exists. Maintained by our team |
| **R10** | **The configuration is not explicitly covered by Anthropic's documentation** (a gateway that modifies content). Realistic worst case: "unsupported configuration" if we ask for help | 1 | 2 | **2** | Rollback is **one variable** (`ANTHROPIC_BASE_URL`) — everything works as before. Ask through normal support when convenient — **not a blocking condition** (see section 7) |
| **R11** | **Masked identifiers degrade Claude's understanding** → weaker advice | 2 | 1 | **2** | Measure after the first month. Narrow `GP_CUSTOM_WORDS` if excessive |
| **R12** | **SafeLine WAF will break this silently.** Claude prompts contain XML tags and code matching XSS rules; a curl test passes while a real session fails | 3 | 1 | **3** | Exempt `/v1/messages` from body inspection. Documented |
| **R13** | **Secrets living in source code.** The gateway closes one path; they remain in git history, clones, laptops. **The code stays on our on-prem GitLab — this is internal exposure (repo access, dev laptops, CI logs, backups), not an external leak** | 3 | 1 | **3** | **Independent work.** The gateway does not solve this and must not be presented as if it does. **On-prem GitLab access control + BitLocker active on every machine** bound it to authorized internal access only |
| **R14** | **Not tested against the real Claude.** Tests used a mock upstream and in-memory storage | 2 | 2 | **4** | Pilot with 1 developer before rollout |
| **R15** | **Pro/Max are consumer plans.** Anthropic **may train on our data** if the developer's personal setting is on, and retention becomes **5 years** instead of 30 days. The company cannot control this centrally | 3 | 3 | **9** | **Buy the Team plan** (commercial terms: no training, 30-day retention). Enterprise if ZDR is needed |

---

## 4. Highest risks in detail

### R1 — code logic reaches Anthropic

Pseudonymization operates on **values**. Function names, control flow, comments, imports, class structure, the algorithm itself — all travel.

If the concern is **customer data in code**, R1 is irrelevant and the solution works.
If the concern is **our own algorithms leaking**, R1 means this solution does not address it.

**The only alternative:** inference in a cloud we rent (Microsoft Foundry "Hosted on Azure", AWS Bedrock, or Google). Then the code physically never reaches Anthropic. **Requires an Azure/AWS subscription, which we do not have.**

Even there, one caveat: the Foundry documentation states that *"content flagged by Anthropic's safety systems egress to Anthropic"* — flagged content still leaves.

### R13 — secrets in source (level 3, not an external leak)

Sensitive information currently lives in the code itself. That means it is already in: git history, every developer's laptop, every clone, CI logs, and backups.

**All of this stays on our on-prem GitLab — nothing leaves our infrastructure.** The exposure is internal: anyone with repository access, CI logs, backups. A lost or stolen laptop is **not** a vector — **BitLocker is active on every machine**, so the disk is encrypted at rest. That leaves a real but bounded hygiene problem for authorized internal access, **not** the public/external exposure the level-9 framing implied — hence level 3, bounded by GitLab access control and full-disk encryption.

The gateway masks it on the way to Claude. **Every other (internal) path stays open.**

This work must be done **regardless of the purchase**. It is not part of this solution and the gateway does not substitute for it.

---

## 5. Risks of NOT deploying

| Scenario | Risk |
|---|---|
| **Developers use Claude on their own** (personal accounts, phones, home machines) | Zero control, zero audit, zero masking. A personal account means **consumer terms** → Anthropic **may train on our code** and retain it for **5 years**. **Worse on every dimension** |
| **No AI tooling at all** | Lost productivity; competitive disadvantage. In practice it becomes the first scenario — a ban does not stop usage, it only drives it into the shadows |
| **Claude without the gateway** | Everything — secrets, customer data, code — travels unprocessed |

The baseline is not "zero risk". The baseline is **either zero control or zero AI**.

### Conclusion

**The gateway is not a risk — it is a risk reduction against every realistic alternative.**

The decision splits into two **independent** questions, and conflating them is the main way to get this wrong:

**1. Do we use Claude at all?**
R1 (code logic reaches Anthropic) belongs here. It applies **equally with and without the gateway** — the gateway neither improves nor worsens it. R1 is **not an argument against the gateway**; it is an argument about using Claude at all.

**2. If we use Claude — with or without the gateway?**
Unambiguous: **with**. It makes nothing worse and masks everything that can be masked without our own cloud. The cost is one service to maintain and first-request latency.

**A ban is not the safe option.** If we do not buy licences, developers will use Claude on personal accounts. That produces the **worst possible combination**: zero masking, zero audit, and — under consumer terms — Anthropic **may train on our code** and retain it for **5 years**. Not buying is **riskier than buying**, not merely slower.

**Recommendation: deploy.** With the Team plan and the conditions in section 8, this is the best available option short of owning cloud infrastructure.

---

## 6. What we verified (evidence)

| Verified | Result |
|---|---|
| Transport, streaming, subscription pass-through | 11/11 tests |
| Reversible pseudonymization on our real code | 11/11 tests |
| Masked code remains valid Python | ✅ (indentation and line count unchanged) |
| Restoration is 1:1 with the original | ✅ |
| Determinism (Anthropic prompt cache survives) | ✅ |
| Isolation between developers | ✅ (dev-b cannot restore dev-a's values) |
| Token split across two stream chunks | ✅ restored |
| gliner latency with the cache | 2.3s → 0.3s (**6.7×**) |
| Fail-closed | ✅ blocks rather than forwarding |
| Transport against the **real** `api.anthropic.com` | ✅ reaches the real endpoint (`request_id` returned; only auth rejects the test key) |
| Persistence in the **real** Postgres vault | ✅ tokens + originals stored and read back through the running container |
| Coverage parity with the anonymizer | ✅ personal code, card, crypto, VAT, company code added; verified masked end-to-end |
| No over-masking of code literals | ✅ ports, timeouts, versions (6-10 digit numbers) left intact |
| **Subscription pass-through against the real Claude** | ✅ real `200` responses through the proxy; **the `429` was a masked system-prompt identity, now fixed** (see GP-CLAUDE-PROXY §4a) |
| **Shared-API-key mode** | ✅ gate rejects bad keys (401), accepts valid ones, masks before forward, owner isolation per gate key — upstream `200` still needs a real `sk-ant-` |
| **Who-sent audit** | ✅ `gp_audit` rows written with sender identity + masked content |
| **Monitoring live** | ✅ Zabbix scrapes all three `/metrics`; triggers `model_on_gpu=0`, `*_fail_closed`, nodata, disk/cert forecasts active |

**What we did NOT verify** (the pilot step, R14):

- Real latency at a 100k-token context
- Long (multi-hour) sessions on the fleet at scale
- Shared-API-key mode returning a real upstream `200` (needs a real Anthropic API key)

---

## 7. R10 — why this is a small risk (a sober look)

An earlier draft of this document recommended "obtain written confirmation from Anthropic before purchase". **That has been dropped as impractical and disproportionate** — a condition that cannot be met does not manage a risk, it freezes the decision.

**What the evidence actually says:**

1. **The gateway configuration itself is officially supported and documented.** Anthropic describes routing subscription traffic through a gateway (`ANTHROPIC_BASE_URL` without a gateway credential) and even specifies what the gateway must forward for it to work.

2. **The line that raised the concern is technical, not legal.** It sits in the **feature pass-through** section and warns about **breakage**, it does not prohibit:

   > *"A gateway that rewrites or redacts request bodies for content inspection **breaks the pairing** the same way stripping does…"*

   The subject is beta headers and their paired body fields: break them and you get `400` errors. **Our gateway does not touch them** — headers are forwarded verbatim, field structure is unchanged, and only text **values** are altered, inside fields that are our own content.

3. **This is our own content, sent from our own infrastructure.** We modify our own code before sending it — that is not circumventing the service or breaching usage limits.

**Realistic worst case:** not a contract breach with penalties, but an **"unsupported configuration"** answer if we open a support ticket. In practice that means we fix our own faults — as we would for any component we own.

**Rollback costs one line.** Unset `ANTHROPIC_BASE_URL` and all three clients connect directly and work normally. No migration, no data loss, no lock-in.

**Proportionate action:** ask through the normal Team support channel when convenient. **Do not block the purchase.**

---

## 8. Recommendation

**Proceed with the purchase, subject to:**

**The only blocking condition:**

0. **Buy the Team plan, not Pro/Max** (R15). Pro/Max are consumer terms: Anthropic may train on our data and retain it for 5 years, and the setting is controlled by each developer personally. Team is commercial terms: no training, 30-day retention. **This is the only item that changes what is being purchased — verify before signing.**

**A decision for management (a choice, not a condition):**

1. **R1 — code logic reaches Anthropic.** Accept, or decline Claude altogether. The gateway changes this neither way (see the conclusion in section 5).

**Deployment conditions (after purchase; they do not block it):**

2. **Start with 1 developer** for a pilot (R14), then expand.
4. **Populate `GP_CUSTOM_WORDS`** before first use (R2).
5. **Disable Claude in Slack/web** for these users (R7).
6. **SafeLine exemption** for `/v1/messages` (R12).
7. **`cleanupPeriodDays`** on developer laptops (R3). BitLocker is already active on every machine.
8. **Start R13 (secrets in code) separately** — not waiting on this solution and not treating it as the fix.

**Do not buy if:** the primary concern is R1 (our algorithms leaking). In that case the only route is an Azure/AWS subscription and inference in our own cloud.

---

## 9. Related documents

- Deployment and configuration: [GP-CLAUDE-PROXY.md](GP-CLAUDE-PROXY.md)
- Architecture: [ARCHITECTURE.md](ARCHITECTURE.md)
- GDPR / AI Act compliance: [COMPLIANCE.md](COMPLIANCE.md)
