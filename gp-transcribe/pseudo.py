"""
Reversible pseudonymisation for the meeting-protocol path — a SEPARATE, self-
contained module (does NOT import or modify gp-claude-proxy). It reuses only the
gliner NER *service* over HTTP.

Why reversible here (unlike the OpenWebUI one-way [PERSON] masking): a meeting
protocol must keep the real names to identify speakers. So we mask names/PII to
GP_<hash> tokens before the (possibly external) LLM sees the text, then restore
the real values in the LLM's output. The external LLM only ever sees tokens
(privacy); the user gets a protocol with real names.

The mapping is kept IN MEMORY for the duration of one protocol operation (mask ->
LLM -> restore is a single synchronous flow), so no persistent vault/DB is needed
— simpler than the Claude gateway, which is stateless across turns.

Token is a deterministic function of the value, so the same name always maps to
the same token within a document (the LLM can reason about "GP_ab12.. said ...").
"""
import os
import re

import requests

GLINER_URL = os.environ.get("GLINER_URL", "http://gliner:8000").rstrip("/") + "/analyze"
GLINER_TIMEOUT = float(os.environ.get("GLINER_TIMEOUT", "120"))

# Same GDPR Art.9/10 + person + vehicle label set as the anonymizer/claude gateway
# (gliner scores depend on the exact label set).
LABELS = [
    "person", "disease", "mental health condition", "criminal offense",
    "political affiliation", "religious belief", "trade union membership",
    "biometric data", "racial or ethnic origin", "sexual orientation",
    "philosophical belief", "vehicle registration number", "license plate",
]
PERSON_MIN = float(os.environ.get("PSEUDO_PERSON_MIN", "0.5"))
# Special-category threshold kept HIGH: the abstract Art.9 labels (philosophical/
# political/religious belief) false-positive on ordinary Lithuanian words — e.g.
# "idėja" (idea) was tagged philosophical-belief @0.48 and masked, then leaked as a
# stray [[GP1]]. Only confident detections (a real disease, plate, etc.) should mask.
OTHER_MIN = float(os.environ.get("PSEUDO_OTHER_MIN", "0.75"))
# By default DON'T mask participant person-names for the meeting protocol: they are
# the whole point of the protocol (identify speakers), low-sensitivity, and the user
# accepted them reaching the correction LLM. Crucially, letting the LLM SEE the names
# lets it normalise their Lithuanian declension ("Martynu Starkumi" -> "Martynas
# Starkus" in the participant list); a masked name is restored in whatever case it
# was spoken, which the LLM can't fix because it never sees it. Special-category PII
# (health/criminal/financial/IDs, GDPR Art.9/10) stays masked regardless.
MASK_PERSON = os.environ.get("PSEUDO_MASK_PERSON", "false").lower() in ("1", "true", "yes")


class MaskUnavailable(Exception):
    """Raised by mask(strict=True) when the NER backend cannot be reached. The
    caller must then NOT send the text onward: for special-category PII (health,
    criminal, biometric — GDPR Art.9/10) silently forwarding unmasked text to an
    external LLM is a data leak, so the egress path fails CLOSED instead."""


def mask(text: str, strict: bool = False):
    """Return (masked_text, mapping{token: real}). Empty mapping if nothing found.
    If gliner is unavailable: strict=False (default) degrades to 'mask nothing'
    (reversible, never a crash — used where the text stays same-origin); strict=True
    raises MaskUnavailable so an external-egress caller can refuse rather than leak."""
    if not text or not text.strip():
        return text, {}
    try:
        r = requests.post(GLINER_URL, json={"text": text, "labels": LABELS}, timeout=GLINER_TIMEOUT)
        r.raise_for_status()
        ents = r.json().get("entities", [])
    except Exception as e:
        if strict:
            raise MaskUnavailable(str(e))
        return text, {}
    spans = []
    for e in ents:
        t = (e.get("text") or "").strip()
        typ = e.get("type", "")
        try:
            sc = float(e.get("score", 1.0))
        except (TypeError, ValueError):
            sc = 1.0
        if typ == "person" and not MASK_PERSON:
            continue                        # B': leave participant names for the LLM to decline
        mn = PERSON_MIN if typ == "person" else OTHER_MIN
        if t and len(t) >= 2 and sc >= mn and e.get("start") is not None:
            spans.append((int(e["start"]), int(e["end"]), t, typ))
    if not spans:
        return text, {}
    # Numbered placeholders [[GP1]], [[GP2]] — an LLM preserves these far more
    # reliably than a random hex hash (which it tends to "correct"). Same value
    # -> same placeholder within a document.
    seen = {}          # raw text -> token
    restore_val = {}   # raw text -> value put back on restore
    for s, en, t, typ in sorted(spans, key=lambda x: x[0]):
        if t not in seen:
            seen[t] = "[[GP%d]]" % (len(seen) + 1)
            # The ASR (svogunas LT) emits lowercase; names are masked BEFORE the
            # LLM so it never capitalises them. Title-case person names on restore
            # so the protocol shows "Arūnas Valinskas", not "arūnas valinskas".
            # First-letter-only (not .title()) preserves any already-correct caps.
            restore_val[t] = _titlecase(t) if typ == "person" else t
    mapping = {seen[t]: restore_val[t] for t in seen}   # token -> restore value
    for s, en, t, typ in sorted(spans, key=lambda x: x[0], reverse=True):
        text = text[:s] + seen[t] + text[en:]
    return text, mapping


def _titlecase(name: str) -> str:
    return " ".join(w[:1].upper() + w[1:] if w else w for w in name.split(" "))


_PH_FUZZY = re.compile(r"\[?\[\s*GP\s*(\d+)\s*\]\]?", re.IGNORECASE)


def _strip_residual(text: str) -> str:
    """Safety net: a raw [[GPn]] must NEVER reach the user. Remove any placeholder
    token still present after restore (an LLM-invented or unmappable one) and tidy
    the leftover spacing/punctuation."""
    if "gp" not in text.lower():
        return text
    text = _PH_FUZZY.sub("", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text.strip()


def restore(text: str, mapping: dict) -> str:
    if not mapping:
        return _strip_residual(text)          # strip any stray placeholder anyway
    # 1) exact replace
    for tok, real in mapping.items():
        text = text.replace(tok, real)
    # 2) fuzzy: an LLM may reformat a placeholder ([[ GP2 ]], [GP2], [[gp2]]).
    #    Map any leftover "[[GP<n>]]"-ish token back by its number; a number with NO
    #    mapping is stripped (return "") rather than left visible.
    if "gp" in text.lower():
        num2real = {}
        for tok, real in mapping.items():
            m = re.search(r"(\d+)", tok)
            if m:
                num2real[m.group(1)] = real
        text = _PH_FUZZY.sub(lambda mm: num2real.get(mm.group(1), ""), text)
    # 3) final safety net — no raw placeholder survives to the user.
    return _strip_residual(text)
