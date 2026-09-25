<p align="center">🌐 <b>English</b> · <a href="101-PRIEZASTYS.lt.md">Lietuvių</a></p>

# 101 reasons to choose GuardPrompt

The exhaustive, point-by-point capability list — for the buying decision, a
compliance review, and the IT/security department. For the human "what you
actually get" version, see [README.md](README.md).

---

**🔒 Data never leaves the organization**
1. The whole system runs on your server (on-premise), not in the cloud.
2. No document or message leaves for the internet without your decision.
3. Runs fully disconnected from the internet (air-gapped).
4. No telemetry, no "phone home".
5. Audio (voice, recordings) is transcribed locally — never leaves the machine.
6. Local LLM (Ollama) for answers with no external connection.
7. Local vector DB (Qdrant) — RAG without the cloud.
8. Local database (PostgreSQL) — conversations stay inside.
9. OCR and document conversion run locally.
10. If you route to an external model — only anonymized traffic, to a provider you chose.

**🛡️ Multi-layer anonymization**
11. Every document and message is scrubbed before processing.
12. Emails.
13. Phone numbers (LT and international).
14. IBAN / bank accounts.
15. Personal codes (LT).
16. Credit cards.
17. VAT / company codes.
18. Passports and ID documents.
19. SODRA numbers.
20. Vehicle & IT identifiers (VIN, MAC, IMEI, plates).
21. Crypto addresses and GPS coordinates.
22. Secrets / keys / tokens (secrets scanning).
23. On-prem NER (gliner) for GDPR Art. 9/10 special categories.
24. Health, criminal, political, religious, union, biometric, ethnicity, sex life, beliefs.

**🎯 Anonymization quality**
25. Names recognized even when foreign or inflected.
26. Names caught even in lowercase.
27. Fail-closed: if the anonymizer fails, it blocks rather than sending unprotected.
28. Tool/terminal output is anonymized too, not just user text.
29. GPU acceleration with dynamic batching (~70 req/s).
30. Reversible pseudonymization — the answer is restored with the real values.
31. Customer-name allowlist (won't mask your own name).
32. Anonymization also available via a REST API for your applications.

**⚔️ Prompt-injection defense**
33. 4-layer injection detector.
34. Regex + de-obfuscation.
35. Hidden-text detection.
36. Script-anomaly detection.
37. Contrastive semantic analysis (15+ languages).

**⚖️ GDPR / EU AI Act / audit**
38. Data residency — everything in your jurisdiction.
39. GDPR Art. 9/10 special-category coverage.
40. "Who sent what, when" audit trail (GDPR Art. 30).
41. EU AI Act compliance.
42. Watermarking of AI-generated images.
43. Proof for the regulator / auditors, not a promise.
44. Anonymized before EVERY external call (even token counting).
45. Risk-assessment documentation included.

**👨‍💻 For developers (Claude proxy)**
46. Claude Code, VS Code, JetBrains through GuardPrompt.
47. Code and data never reach Anthropic in the clear.
48. Customer names, credentials, sensitive code are masked.
49. Audit trail of who sent it.
50. Supports subscription and API-key modes.
51. Transparent proxy — the client works with no extra setup.
52. Local secrets-protection layer.

**📄 Document processing**
53. PDF → text/markdown.
54. OCR for scans and old archives.
55. Lithuanian-language OCR.
56. HTML cleaning.
57. Image description (local vision model).
58. Multi-page support.

**🔎 Search & knowledge bases (RAG)**
59. Semantic search over your documents.
60. Cited answers with sources.
61. Multilingual embedding (bge-m3 + reranker) — Lithuanian search actually works.
62. Full-text search inside scanned PDFs.
63. Multiple knowledge bases with separate access.
64. Sync from Confluence / Jira / SharePoint.

**🎙️ Meetings & transcription**
65. Meeting recording in the browser (microphone + system audio).
66. Lithuanian speech-to-text engine (LIEPA-3).
67. Automatic English detection.
68. Automatic structured protocol.
69. The protocol saved as a note with the recording attached.
70. Voice input across the whole app, locally.

**🖥️ Terminal / sandbox / creation**
71. A real terminal inside OpenWebUI.
72. Isolated sandbox, per-user home isolation.
73. Default-deny egress firewall.
74. Package installs and sudo — admins only.
75. Terminal output is anonymized.
76. The AI creates real files and brand-styled presentations.

**💰 Cost & licensing**
77. One engine for the whole organization — not a per-seat fee.
78. No ChatGPT/Copilot subscriptions for everyone.
79. Licence mechanism with a graceful mode.
80. Configuration snapshot — recovery after a reinstall.

**⚙️ Deployment & infrastructure**
81. Docker-based, a single `docker compose`.
82. Automated install scripts (Linux + Windows).
83. CPU and GPU editions — for your hardware.
84. Works offline / air-gapped.
85. Modular architecture — independent services.
86. OpenAI-compatible — swap the model via `.env`.
87. Local vision: Ollama (Ubuntu) / LM Studio (Windows).

**📊 Monitoring & reliability**
88. Full Zabbix observability.
89. Uniform `/metrics` from every service.
90. Standard exporters (host, containers, Postgres, GPU, blackbox).
91. Preventive triggers (disk/cert/pool exhaustion forecasting).
92. Memory-leak and code-quality triggers.
93. Startup "warm-up" gate — no slow cold start.
94. Proof that the guardrails work.

**🧑‍💼 Administration & access**
95. KB Admin console for curating knowledge bases.
96. LDAP / Active Directory sign-in.
97. User / group access control.
98. Audit log for administrative actions.

**🎨 Customization & future**
99. Per-deployment branding (logo, name) — white-label.
100. Integrable via API into your applications.
101. Future-proof — add new models as they appear.

---

➡️ Back to [README.md](README.md)
