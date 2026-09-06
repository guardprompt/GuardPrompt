"""
title: GuardPrompt — kas nusiųsta į modelį
author: guardprompt
version: 1.2
description: Po/prie atsakymo parodo, kas (anonimizuota) iškeliavo į LLM, kad vartotojui
    būtų akivaizdu, jog jautri informacija buvo paslėpta. Trumpam tekstui rodo visą
    nusiųstą variantą; ilgam — santrauką (kiek ir kokių reikšmių paslėpta), kad status
    eilutė neišsipūstų. NATIVE FUNCTION — dedama per Workspace → Functions ir įjungiama
    kaip „Global" (tik native funkcijos gauna __event_emitter__ ir gali rodyti UI).
required_open_webui_version: 0.5.0
"""

import re
import os
import time
import hashlib
import logging
import requests
from collections import Counter
from typing import Optional
from pydantic import BaseModel, Field

log = logging.getLogger("gp_show_sent")

# Modulio-lygio (dalinamas tarp Filter instancijų — OpenWebUI gali instancijuoti
# filtrą per-request, tad instancijos laukas dedup'ui nepatikimas).
# (chat_key, turinio_hash) -> paskutinio emit laikas.
_RECENT: dict = {}


class Filter:
    class Valves(BaseModel):
        # Turi būti DIDESNIS už GuardPrompt pipeline priority (0), kad ši funkcija
        # matytų jau paslėptą tekstą, jei filtrai vykdomi vienoje grandinėje.
        priority: int = Field(default=10)
        # Rodyti tik kai realiai kažkas paslėpta (yra [ŽYMĖ]) — kitaip be triukšmo.
        only_when_masked: bool = Field(default=True)
        # Iki tiek simbolių rodom inline; virš — antraštė + išskleidžiamas tekstas.
        preview_chars: int = Field(default=600)
        # Kiek daugiausia nusiųsto teksto rodom išskleidžiamame bloke (apsauga nuo
        # milžiniškų dokumentų; virš — apkarpom su „…(sutrumpinta)").
        max_show_chars: int = Field(default=50000)
        # Atsarginis kelias: jei pipeline žymos NĖRA, funkcija pati kviečia
        # anonimizatorių vien rodymui. Tai LĖTA (dviguba anonimizacija su gliner) —
        # numatyta IŠJUNGTA. Įjunk tik jei pastaba nerodoma (žyma nepropaguoja).
        selfanon_fallback: bool = Field(default=False)
        max_selfanon_chars: int = Field(default=8000)
        anon_api_url: str = Field(default="http://anonymizer:8005/api/anonimize")
        # Greitas dublis (du beveik vienalaikiai inlet kvietimai vienam UI request'ui)
        # slopinamas, jei tas pats turinys tam pačiam pokalbiui emit'intas per tiek
        # sekundžių. Regeneracija įvyksta vėliau (vartotojo paspaudimas) → praeina.
        dedup_window_s: float = Field(default=4.0)

    def __init__(self):
        self.valves = self.Valves()
        # Ta pati nematoma žymė, kurią palieka GuardPrompt pipeline. Jei ją matome —
        # pipeline jau paslėpė turinį, ir mums nereikia kviesti anonimizatoriaus.
        self.MARK = "​‌⁣"
        self.TAG_RE = re.compile(r"\[[A-ZĄČĘĖĮŠŲŪŽ_]{2,}\]")
        self.ANON_KEY = os.getenv("ANON_API_KEY", "")

    def _user_text(self, body: dict) -> str:
        for msg in reversed(body.get("messages", [])):
            if isinstance(msg, dict) and msg.get("role") == "user":
                c = msg.get("content", "")
                if isinstance(c, list):
                    return " ".join(
                        it.get("text", "") for it in c
                        if isinstance(it, dict) and it.get("type") == "text"
                    ).strip()
                return str(c or "").strip()
        return ""

    def _anon(self, text: str) -> str:
        try:
            headers = {"Authorization": f"Bearer {self.ANON_KEY}"} if self.ANON_KEY else {}
            r = requests.post(
                self.valves.anon_api_url,
                files={"text": (None, text, "text/plain; charset=utf-8")},
                headers=headers, timeout=30,
            )
            if r.ok and r.text.strip():
                return r.text.strip()
        except Exception:
            pass
        return ""

    def _brand(self) -> str:
        # Skydo emoji — sėdi INLINE su tekstu. Paveikslėlio (markdown/<img>)
        # SĄMONINGAI nenaudojam: OpenWebUI markdown paveikslėlį renderina bloku, o
        # raw <img> HTML išvalo; be to persistuotas logo_url valve gali įdumpinti
        # milžinišką data-URI į atsakymą. Todėl fiksuota — jokio valve.
        return "🛡️ "

    def _note_md(self, masked: str) -> Optional[str]:
        tags = self.TAG_RE.findall(masked)
        if self.valves.only_when_masked and not tags:
            return None
        brand = self._brand()
        n = len(tags)
        compact = " ".join(masked.split())

        # Trumpas: viena eilutė — logotipas + „Į modelį nusiųsta: …". Be blockquote
        # (jis temoje piešia negražias kabutes) ir be skirtuko. Mažas markdown
        # paveikslėlis sėdi inline su tekstu.
        if len(compact) <= self.valves.preview_chars:
            return f"{brand}**Į modelį nusiųsta:** `{compact}`\n\n"

        # Ilgas: antraštės eilutė PATI yra išskleidimo varnelė (summary). Jokio
        # atskiro „rodyti…" teksto ir jokios naujos eilutės — vartotojas paspaudžia
        # antraštę ir pamato VISĄ nusiųstą tekstą. (Trikampį naršyklė deda summary
        # kairėje; perkelti į galą reikėtų CSS, kurio įterpti negalim.)
        by_tag = ", ".join(f"{t}×{c}" for t, c in Counter(tags).most_common())
        full = masked.strip()
        if len(full) > self.valves.max_show_chars:
            full = full[:self.valves.max_show_chars] + "\n…(sutrumpinta)"
        summary = f"{brand}Į modelį nusiųsta — paslėpta {n} reikšm. ({by_tag})"
        details = (f"<details>\n<summary>{summary}</summary>\n\n"
                   "```\n" + full + "\n```\n\n</details>")
        return f"{details}\n\n"

    async def inlet(self, body: dict, __event_emitter__=None,
                    __user__: Optional[dict] = None, __metadata__: Optional[dict] = None) -> dict:
        if __event_emitter__ is None:
            return body
        meta = __metadata__ or body.get("metadata") or {}

        if meta.get("task"):
            return body

        text = self._user_text(body)
        if not text:
            return body

        if self.MARK in text:
            masked = text.replace(self.MARK, "").strip()      # pipeline jau paslėpė — GREITA
        elif self.valves.selfanon_fallback and len(text) <= self.valves.max_selfanon_chars:
            masked = self._anon(text)                         # LĖTA — tik jei įjungta
        else:
            log.warning("[gp-show] no MARK, self-anon off -> nothing shown (head=%r)", text[:40])
            return body

        note = self._note_md(masked) if masked else None
        if not note:
            return body

        # Laiko-lango dedup: UI vienam request'ui kartais kviečia inlet du kartus
        # beveik vienu metu → dvi vienodos pastabos. Slopinam antrą, jei tas pats
        # turinys tam pačiam pokalbiui emit'intas per < dedup_window_s. Regeneracija
        # (vartotojo paspaudimas, vėliau) — praeina.
        now = time.time()
        chat_key = str(body.get("chat_id") or meta.get("chat_id")
                       or meta.get("session_id") or "_")
        dkey = (chat_key, hashlib.sha256(masked.encode("utf-8")).hexdigest()[:16])
        if now - _RECENT.get(dkey, 0.0) < self.valves.dedup_window_s:
            return body                                        # greitas dublis — slopinam
        _RECENT[dkey] = now
        if len(_RECENT) > 1000:
            for k in [k for k, v in _RECENT.items() if now - v > 60]:
                _RECENT.pop(k, None)

        await __event_emitter__({"type": "message", "data": {"content": note}})
        return body
