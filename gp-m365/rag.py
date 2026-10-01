"""The cheap RAG loop — the heart of gp-m365.

DEFAULT is one pass, one LLM call:
    search (Graph, free) -> fetch top docs -> injection-scan -> ANONYMIZE
      -> rerank (local, free) -> ONE LLM call on a few fragments -> de-anonymize

The agentic multi-round loop (LLM decides follow-up searches) is a CAPPED fallback
(config.MAX_ITERS) for genuinely multi-hop questions — not the default, because it costs
tokens. All the "find/select" work is done by FREE local tools (Graph search + reranker),
so the paid external LLM sees only a handful of small, anonymized fragments.

Nothing fetched is ever stored. The reversible pseudonym map lives only for the request
(and the shared Vault for token->value), so no personal document text is persisted.
"""
import httpx

import re

import config
import graph

# Stopwords stripped from a question to build a Graph SEARCH query — done LOCALLY (not via
# the anonymizing LLM, which would mask the very names/topics we need to search for). Keeps
# names, subjects, dates; drops question/filler words. LT + EN.
_STOP = set((
    "ar as aš tu jis ji mes jus jūs turiu turi turime turejau nauju naujų naujas nauji "
    "laisku laiškų laiskas laiškas laiskai laiškai laiska laišką is iš apie mano tavo musu mūsų "
    "kokie koks kokia kada kur kaip ka ką ko yra buvo bus bei ir arba man mane su be per prie nuo "
    "iki uz už tik dar jau labai prašau prasau noriu surask rask parodyk apibendrink apibendrinti "
    "sarasa sąrašą visus visas kiek the a an do i have has any new email emails mail from about my me "
    "our is are was were what when where how which who show find search summarize list all give me"
).split())


def _search_query(question: str) -> str:
    """Turn a natural question into a Graph search query: keep content words (names, topics),
    drop stopwords. Falls back to the whole question if nothing is left."""
    words = re.findall(r"[0-9A-Za-zĄČĘĖĮŠŲŪŽąčęėįšųūž]+", question)
    kw = [w for w in words if w.lower() not in _STOP and len(w) > 2]
    return " ".join(kw) if kw else question


class AnonUnavailable(Exception):
    """Raised when masking can't run. The caller FAILS CLOSED — never calls the LLM."""


class Masker:
    """Per-request REVERSIBLE pseudonymizer. Calls gliner /analyze for NER spans and swaps
    each into a GP_<TYPE>_<n> token, keeping a map so the final answer is de-anonymized for
    the user. One instance per /answer so the same person/id gets the SAME token across all
    fetched docs + the question.

    Reuse note: production should share gp-openai-proxy's Vault (cross-session tokens, TTL-
    pruned). This self-contained masker is enough to test the pipeline end-to-end now.
    """
    def __init__(self):
        self.map: dict[str, str] = {}     # token -> original (fullest form, for restore)
        self._rev: dict[str, str] = {}    # entity KEY -> token
        self._n: dict[str, int] = {}      # type -> counter

    @staticmethod
    def _key(typ: str, orig: str) -> str:
        # PERSON coreference: map name inflections/variants to ONE token so a question's
        # "iš Donato" and an email's "Donatas Kalvaitis" share a token and the LLM matches
        # them. Key = diacritics-folded lowercase 5-char prefix of the FIRST name word.
        if typ.startswith("PERSON"):
            import unicodedata
            base = (orig.strip().split() or [orig])[0]
            base = "".join(c for c in unicodedata.normalize("NFKD", base) if not unicodedata.combining(c)).lower()
            return "PERSON:" + base[:5]
        return typ + ":" + orig.lower()

    async def mask(self, client: httpx.AsyncClient, text: str) -> str:
        if not text.strip():
            return text
        try:
            r = await client.post(config.NER_URL, json={"text": text}, timeout=config.HTTP_TIMEOUT)
            r.raise_for_status()
            ents = r.json().get("entities", [])
        except Exception as e:
            if config.FAIL_CLOSED:
                raise AnonUnavailable(str(e))     # never send raw text on
            return text
        # Replace right-to-left so earlier offsets stay valid.
        for e in sorted(ents, key=lambda x: x["start"], reverse=True):
            orig = e["text"]
            typ = str(e["type"]).upper().replace(" ", "_")
            key = self._key(typ, orig)
            tok = self._rev.get(key)
            if not tok:
                self._n[typ] = self._n.get(typ, 0) + 1
                tok = f"GP_{typ}_{self._n[typ]}"
                self.map[tok] = orig
                self._rev[key] = tok
            elif len(orig) > len(self.map.get(tok, "")):
                self.map[tok] = orig          # keep the fullest form for a clean restore
            text = text[: e["start"]] + tok + text[e["end"]:]
        return text

    def restore(self, text: str) -> str:
        # Longest token first so GP_X_1 doesn't clobber GP_X_10.
        for tok in sorted(self.map, key=len, reverse=True):
            text = text.replace(tok, str(self.map[tok]))
        return text


async def _injection_scan(client: httpx.AsyncClient, text: str) -> str:
    """Fetched M365 docs are UNTRUSTED — a doc could carry a prompt-injection. gliner
    /injection flags injected sentences; replace them with [PROTECTION] before the LLM.
    Best-effort — a scan outage must not drop the whole answer."""
    if not text.strip():
        return text
    try:
        r = await client.post(config.INJECTION_URL, json={"text": text}, timeout=config.HTTP_TIMEOUT)
        r.raise_for_status()
        spans = r.json().get("spans", [])
    except Exception:
        return text
    # spans are [start,end,text] (or dicts) with offsets into the original — redact by text.
    for sp in spans:
        frag = sp[2] if isinstance(sp, (list, tuple)) and len(sp) > 2 else (sp.get("text") if isinstance(sp, dict) else None)
        if frag and frag in text:
            text = text.replace(frag, "[PROTECTION]")
    return text


async def _rerank(client: httpx.AsyncClient, query: str, chunks: list[str]) -> list[str]:
    """Local reranker picks the few fragments that matter (free, no tokens). If no reranker
    is configured (RERANKER_URL empty) or it's unavailable, fall back to the first
    MAX_FRAGMENTS chunks — still cheap, just less precise."""
    if not config.RERANKER_URL or len(chunks) <= config.MAX_FRAGMENTS:
        return chunks[: config.MAX_FRAGMENTS]
    try:
        r = await client.post(config.RERANKER_URL,
                              json={"query": query, "documents": chunks, "top_n": config.MAX_FRAGMENTS},
                              timeout=config.HTTP_TIMEOUT)
        r.raise_for_status()
        idxs = [d["index"] for d in r.json().get("results", [])]
        return [chunks[i] for i in idxs][: config.MAX_FRAGMENTS]
    except Exception:
        return chunks[: config.MAX_FRAGMENTS]


def _chunk(text: str) -> list[str]:
    """Split a document into reranker-sized pieces (cap per chunk). Cheap char-window."""
    n = config.MAX_FRAGMENT_CHARS
    return [text[i:i + n] for i in range(0, min(len(text), config.MAX_DOC_BYTES), n)]


_SYS = (
    "Tu esi Regitros asistentas, dirbantis vartotojo Microsoft 365 (paštas, failai, Teams). "
    "ŠALTINIAI žemiau = vartotojo laiškai / failai / atidarytas puslapis; kiekvienas su antrašte "
    "[Šaltinis N: ...]. Atsakyk lietuviškai.\n"
    "TAISYKLĖS:\n"
    "1) Vardus atpažink pagal linksnius (iš Donato = nuo Donatas Kalvaitis; Jono = Jonas).\n"
    "2) Jei atsakymas YRA šaltiniuose — pateik jį; nesakyk kad nėra, jei yra.\n"
    "3) Jei vartotojas PRAŠO PARAŠYTI / ATSAKYTI / PARUOŠTI laišką ar tekstą (pvz. „atsakyk "
    "jam kad ne“, „parašyk atsakymą“) — SUKURK to laiško juodraštį lietuviškai, mandagų, "
    "remdamasis laišku, į kurį atsakoma (žr. šaltinius ir pokalbį). Grąžink TIK juodraščio "
    "tekstą. NEsakyk kad trūksta informacijos — tu turi kontekstą pokalbyje.\n"
    "4) Kai remiesi šaltiniu, nurodyk [Šaltinis N]. Cituok TIK tuos, kuriuos realiai naudoji.\n"
    "5) Pokalbio istorija žemiau padeda supimti „jam“, „į šį laišką“, „tą žmogų“."
)


async def _llm_answer(client: httpx.AsyncClient, question_masked: str, srcs: list[dict],
                      history: list[dict], owui_cookie: str = "") -> str:
    """The ONE paid call. Everything is ALREADY anonymized. Goes through OWUI AS THE USER
    (cookie forwarded by guardproxy). `srcs` are per-document (aligned to [Šaltinis N]);
    `history` is prior masked turns so 'reply to him' resolves. Non-streaming."""
    context = "\n\n".join(f"[Šaltinis {i+1}: {s.get('title','')}]\n{s.get('text','')}"
                          for i, s in enumerate(srcs))
    messages = [{"role": "system", "content": _SYS}]
    messages += history[-6:]                       # recent turns for pronoun/context resolution
    messages.append({"role": "user", "content": f"{question_masked}\n\n=== ŠALTINIAI ===\n{context}"})
    body = {"model": config.LLM_MODEL, "messages": messages, "stream": False}
    headers = {"Cookie": owui_cookie} if owui_cookie else {}
    r = await client.post(config.LLM_URL, json=body, headers=headers, timeout=config.LLM_TIMEOUT)
    r.raise_for_status()
    d = r.json()
    return (d.get("choices") or [{}])[0].get("message", {}).get("content", "")


async def answer(client: httpx.AsyncClient, question: str, sso_token: str, user_key: str,
                 graph_token: str = "", page_context: str = "", product: str = "",
                 owui_cookie: str = "", history: list | None = None) -> dict:
    """Run the cheap RAG pass end-to-end. Returns {answer, sources, llm_calls}.

    graph_token: a delegated Graph token the caller already holds (browser extension) — used
    directly. If empty, exchange sso_token via OBO. page_context: the current MS-product page
    text (extra source, so the answer covers what's on screen too). product: scope hint.

    Fail-closed: if anonymization is unavailable, raises AnonUnavailable BEFORE any LLM call.
    """
    if not graph_token:
        graph_token = await graph.obo_token(sso_token, user_key)
    masker = Masker()                      # one reversible map for the whole request

    # 1. FREE: find candidates the user can see (delegated). Search on KEYWORDS extracted
    # from the question (names/topics), not the whole sentence — a full LT question matches
    # nothing in Graph's keyword index. Scoped by product if given.
    sq = _search_query(question)
    hits = await graph.search(graph_token, sq, config.SEARCH_HITS, product)
    # For mail, ALSO pull the recent inbox directly — keyword search can't answer "mail from
    # X" / "summarize my inbox" (the words aren't in the body), but the actual list can.
    recent = []
    if product in ("outlook", "", "teams", "m365"):     # mail-bearing / generic scopes
        recent = await graph.recent_messages(graph_token, config.SEARCH_HITS)
    # Merge (recent first), dedupe by id.
    seen, hits2 = set(), []
    for h in recent + hits:
        hid = h.get("id")
        if hid in seen:
            continue
        seen.add(hid); hits2.append(h)
    hits = hits2[: max(config.TOP_DOCS, 8)]
    print(f"[gp-m365] query={sq!r} product={product or 'all'} search={len(hits2)} recent={len(recent)} used={len(hits)}", flush=True)

    # 2. Build ONE entry per source (aligned to [Šaltinis N]), each injection-scanned +
    # anonymized, capped. Nothing fetched is ever stored.
    srcs = []
    if page_context.strip():
        pc = await masker.mask(client, await _injection_scan(client, page_context))
        srcs.append({"title": "Atidarytas puslapis", "source": "page", "web_url": "",
                     "text": pc[: config.MAX_FRAGMENT_CHARS * 2]})
    for h in hits:
        raw = await graph.fetch(graph_token, h)
        if not raw.strip():
            raw = h.get("snippet", "")
        combined = (str(h.get("title") or "") + "\n" + raw).strip()   # title carries sender
        if not combined:
            continue
        masked = await masker.mask(client, await _injection_scan(client, combined))
        srcs.append({"title": h.get("title"), "source": h.get("source"),
                     "web_url": h.get("web_url"), "text": masked[: config.MAX_FRAGMENT_CHARS * 2]})

    if not srcs:
        return {"answer": "Pagal jūsų dokumentus nieko tinkamo nerasta.", "sources": [], "llm_calls": 0}

    # 3. Mask the question + prior turns with the SAME map (so 'iš Donato' ↔ email sender,
    # and 'jam'/'į šį laišką' resolve against history).
    q_masked = await masker.mask(client, question)
    hist_masked = []
    for m in (history or [])[-6:]:
        c = m.get("content", "")
        hist_masked.append({"role": m.get("role", "user"),
                            "content": await masker.mask(client, c) if c else ""})

    # 4. ONE paid LLM call (all anonymized). Sources carry titles → citations map to docs.
    masked_answer = await _llm_answer(client, q_masked, srcs, hist_masked, owui_cookie)

    # 5. Keep only the sources the answer actually CITED ([Šaltinis N]); if none, keep all.
    cited = {int(n) for n in re.findall(r"Šaltinis\s+(\d+)", masked_answer)}
    shown = [srcs[i - 1] for i in sorted(cited) if 1 <= i <= len(srcs)] or srcs
    return {
        "answer": masker.restore(masked_answer),
        "sources": [{"title": s["title"], "source": s["source"], "web_url": s["web_url"]} for s in shown],
        "llm_calls": 1,
    }
