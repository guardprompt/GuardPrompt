<p align="center">🌐 <a href="101-REASONS.md">English</a> · <b>Lietuvių</b></p>

# 101 priežastis rinktis GuardPrompt

Išsamus, punktais išdėstytas galimybių sąrašas — pirkimo sprendimui, atitikties
peržiūrai ir IT/saugumo skyriui. Žmogišką „ką iš tikrųjų gaunate" versiją rasi
[README.lt.md](README.lt.md).

---

**🔒 Duomenys nepalieka organizacijos**
1. Visa sistema veikia jūsų serveryje (on-premise), ne debesyje.
2. Nė vienas dokumentas ar žinutė neišeina į internetą be jūsų sprendimo.
3. Veikia visiškai atjungtas nuo interneto (air-gapped).
4. Jokios telemetrijos, jokio „phone home".
5. Garsas (balsas, įrašai) transkribuojamas lokaliai — nepalieka mašinos.
6. Vietinis LLM (Ollama) atsakymams be išorinio ryšio.
7. Vietinė vektorinė DB (Qdrant) — RAG be debesies.
8. Vietinė duomenų bazė (PostgreSQL) — pokalbiai jūsų viduje.
9. OCR ir dokumentų konvertavimas lokaliai.
10. Jei nukreipiate į išorinį modelį — tik anonimizuotą srautą, jūsų pasirinktą tiekėją.

**🛡️ Daugiasluoksnis anonimizavimas**
11. Kiekvienas dokumentas ir žinutė nuvalomi prieš apdorojimą.
12. El. paštai.
13. Telefono numeriai (LT ir tarptautiniai).
14. IBAN / banko sąskaitos.
15. Asmens kodai (LT).
16. Kredito kortelės.
17. PVM / įmonių kodai.
18. Pasai ir tapatybės dokumentai.
19. SODRA numeriai.
20. Transporto ir IT identifikatoriai (VIN, MAC, IMEI, valst. numeriai).
21. Kripto adresai ir GPS koordinatės.
22. Paslaptys / raktai / tokenai (secrets scanning).
23. On-prem NER (gliner) BDAR 9/10 str. ypatingoms kategorijoms.
24. Sveikata, kriminalas, politika, religija, profsąjunga, biometrija, etniškumas, lytinis gyvenimas, įsitikinimai.

**🎯 Anonimizavimo kokybė**
25. Vardai atpažįstami net užsienietiški ir sulinksniuoti.
26. Vardai pagaunami net mažosiomis raidėmis.
27. Fail-closed: sutrikus anonimizatoriui — blokuoja, o ne siunčia neapsaugota.
28. Anonimizuojama ir įrankių/terminalo išvestis, ne vien vartotojo tekstas.
29. GPU spartinimas su dinaminiu batching (~70 užkl./s).
30. Grįžtama pseudonimizacija — atsakymas atkuriamas su tikromis reikšmėmis.
31. Kliento vardo allowlist (nepaslepia jūsų pavadinimo).
32. Anonimizavimas pasiekiamas ir per REST API jūsų aplikacijoms.

**⚔️ Prompt-injekcijų gynyba**
33. 4 sluoksnių injekcijų detektorius.
34. Regex + deobfuskacija.
35. Paslėpto teksto aptikimas.
36. Skripto anomalijų aptikimas.
37. Kontrastinė semantinė analizė (15+ kalbų).

**⚖️ BDAR / ES DI reglamentas / auditas**
38. Duomenų rezidavimas — viskas jūsų jurisdikcijoje.
39. BDAR 9/10 str. ypatingų kategorijų dengimas.
40. „Kas ką kada siuntė" audito seka (BDAR 30 str.).
41. ES DI reglamento atitiktis.
42. DI sugeneruotų vaizdų žymėjimas (vandenženklis).
43. Įrodymas VDAI / auditoriams, ne pažadas.
44. Anonimizuojama prieš KIEKVIENĄ išorinį iškvietimą (net token skaičiavimą).
45. Pridedama rizikos vertinimo dokumentacija.

**👨‍💻 Programuotojams (Claude šliuzas)**
46. Claude Code, VS Code, JetBrains per GuardPrompt.
47. Kodas ir duomenys nepasiekia Anthropic atviru tekstu.
48. Kliento vardai, kredencialai, jautrus kodas paslepiami.
49. Audito seka, kas siuntė.
50. Palaiko subscription ir API-key režimus.
51. Skaidrus proxy — klientas veikia be papildomo setup.
52. Vietinis paslapčių apsaugos sluoksnis.

**📄 Dokumentų apdorojimas**
53. PDF → tekstas/markdown.
54. OCR skenams ir seniems archyvams.
55. Lietuvių kalbos OCR.
56. HTML valymas.
57. Paveikslų aprašymas (vietinis vision modelis).
58. Daugiapuslapis palaikymas.

**🔎 Paieška ir žinių bazės (RAG)**
59. Semantinė paieška virš jūsų dokumentų.
60. Cituojami atsakymai su šaltiniais.
61. Daugiakalbis embedding (bge-m3 + reranker) — lietuviška paieška realiai veikia.
62. Pilnatekstė paieška skenuotuose PDF.
63. Kelios žinių bazės su atskira prieiga.
64. Sinchronizacija iš Confluence / Jira / SharePoint.

**🎙️ Susitikimai ir transkripcija**
65. Susitikimo įrašymas naršyklėje (mikrofonas + sistemos garsas).
66. Lietuviškas kalbos-į-tekstą variklis (LIEPA-3).
67. Automatinis anglų kalbos atpažinimas.
68. Automatinis struktūruotas protokolas.
69. Protokolas — kaip užrašas su prikabintu įrašu.
70. Balso įvestis visoje aplikacijoje, lokaliai.

**🖥️ Terminalas / sandbox / kūryba**
71. Tikras terminalas OpenWebUI viduje.
72. Izoliuotas sandbox, per-vartotojo namų izoliacija.
73. Default-deny egress ugniasienė.
74. Paketų diegimas ir sudo — tik administratoriams.
75. Terminalo išvestis anonimizuojama.
76. DI kuria realius failus ir brand'intas prezentacijas.

**💰 Kaštai ir licencijavimas**
77. Vienas variklis visai organizacijai — ne mokestis už vietą.
78. Nereikia ChatGPT/Copilot prenumeratų kiekvienam.
79. Licencijos mechanizmas su graceful režimu.
80. Konfigūracijos snapshot — atkūrimas po perdiegimo.

**⚙️ Diegimas ir infrastruktūra**
81. Docker-based, vienas `docker compose`.
82. Automatiniai diegimo skriptai (Linux + Windows).
83. CPU ir GPU leidimai — pagal jūsų techniką.
84. Veikia offline / air-gapped.
85. Modulinė architektūra — nepriklausomi servisai.
86. OpenAI-suderinamas — keiskite modelį per `.env`.
87. Vietinis vision: Ollama (Ubuntu) / LM Studio (Windows).

**📊 Stebėsena ir patikimumas**
88. Pilna Zabbix stebėsena.
89. Vienodi `/metrics` iš kiekvieno serviso.
90. Standartiniai eksporteriai (host, konteineriai, Postgres, GPU, blackbox).
91. Preventyvūs trigeriai (disko/sertifikato/pool išsekimo prognozė).
92. Atminties nutekėjimo ir kodo-kokybės trigeriai.
93. Startup „warm-up" vartai — jokios lėtos šaltos pradžios.
94. Įrodymas, kad apsaugos veikia.

**🧑‍💼 Administravimas ir prieiga**
95. KB Admin pultas žinių bazių kuravimui.
96. LDAP / Active Directory prisijungimas.
97. Vartotojų / grupių prieigos valdymas.
98. Audito log administravimo veiksmams.

**🎨 Pritaikymas ir ateitis**
99. Per-deployment prekės ženklas (logo, pavadinimas) — white-label.
100. Integruojamas per API į jūsų aplikacijas.
101. Ateičiai atsparus — pridėkite naujus modelius, kai pasirodo.

---

➡️ Grįžti į [README.lt.md](README.lt.md)
