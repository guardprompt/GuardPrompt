"""
title: GuardPrompt Anonymizer
author: guardprompt
version: 1.0
license: MIT
description: Anonimizuoja vartotojo zinutes ir OCR nuotraukas pries siunčiant i LLM.
"""

from typing import List, Optional
from pydantic import BaseModel
import requests
import base64
import os
import re
import hmac
import hashlib
import logging


# Invisible characters used to encode the "already anonymized by us" mark.
_ZW_ALPHABET = ("​", "‌", "⁣", "⁤", "⁢", "﻿")


def _derive_anon_mark(secret: str) -> str:
    """Unforgeable, invisible, stable 'already processed by us' flag.

    The old mark was a fixed public constant. The skip-check only tests whether the
    mark is PRESENT, so an attacker could embed that exact sequence in an uploaded
    document, a fetched web page, or tool output and make the pipeline skip masking
    the ENTIRE message — raw PII straight to the external LLM. Deriving the mark
    from a per-deployment secret nobody outside knows makes it unforgeable, while
    staying invisible (zero-width) and stable so history dedup still works. All
    components share it via GP_ANON_MARK_SECRET in .env.
    """
    h = hmac.new(secret.encode("utf-8"), b"gp-anon-mark-v1", hashlib.sha256).digest()
    return "".join(_ZW_ALPHABET[b % len(_ZW_ALPHABET)] for b in h[:24])


_LEGACY_ANON_MARK = "​‌⁣"
_MARK_SECRET = os.getenv("GP_ANON_MARK_SECRET", "").strip()
# Unforgeable when a secret is set; otherwise fall back to the legacy constant AND
# strip it from inbound text (see Pipeline._detrust) so a forged mark cannot skip
# masking.
ANON_MARK = _derive_anon_mark(_MARK_SECRET) if _MARK_SECRET else _LEGACY_ANON_MARK
MARK_FORGEABLE = not _MARK_SECRET
if MARK_FORGEABLE:
    logging.warning("[GuardPrompt] GP_ANON_MARK_SECRET not set — the anonymization "
                    "skip-mark is forgeable; inbound marks will be stripped and text "
                    "re-anonymized (safe but slower). Set the secret to close this.")


class Pipeline:

    class Valves(BaseModel):
        pipelines: List[str] = ["*"]
        priority: int = 0
        # FAIL-CLOSED: if anonymization fails/times out, block the message instead
        # of sending raw text to the LLM. Set False only if you accept the leak risk.
        fail_closed: bool = True

    def __init__(self):
        self.type = "filter"
        self.name = "GuardPrompt Anonymizer"
        self.valves = self.Valves()
        self.ANON_API_URL = "http://anonymizer:8005/api/anonimize"
        # Must match one of ANON_API_KEYS in the anonymizer's .env. Empty means
        # the anonymizer runs with its API open, which is the default.
        self.ANON_API_KEY = os.getenv("ANON_API_KEY", "")
        # Models that route through the REVERSIBLE gp-openai-proxy (it does its own
        # mask+restore, returning real values). For these, SKIP the one-way masking
        # here — running both would double-mask and the reversible tokens would not
        # restore. EMPTY (default) => every model is masked exactly as before.
        self.SKIP_MODELS = [m.strip() for m in os.getenv("GP_PIPELINE_SKIP_MODELS", "").split(",") if m.strip()]
        self.DOCLING_URL = "http://docling-serve:8001/convert"
        self.ANON_TIMEOUT = 30
        self.ANON_RETRIES = 1
        self.DOCLING_TIMEOUT = 60
        self.ANON_MARK = ANON_MARK
        self.BACKEND_URL = "http://open-webui-dk:8080"
        self.BLOCK_MSG = (
            "[GuardPrompt: \u017Einut\u0117 u\u017Eblokuota \u2014 anonimizavimo servisas \u0161iuo metu "
            "nepasiekiamas, tod\u0117l jautri informacija nebuvo pa\u0161alinta. "
            "Pabandykite dar kart\u0105 v\u0117liau.]"
        )

    async def on_startup(self):
        logging.info("[GuardPrompt] Pipeline paleistas")

    async def on_shutdown(self):
        pass

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.ANON_API_KEY}"} if self.ANON_API_KEY else {}

    def _detrust(self, text: str) -> str:
        # When the mark is forgeable (no GP_ANON_MARK_SECRET) an attacker could
        # embed it in content to skip masking. Strip it from untrusted inbound text
        # so masking always runs; re-anonymizing already-masked text is idempotent.
        if MARK_FORGEABLE and text:
            return text.replace(self.ANON_MARK, "")
        return text

    def _anon_call(self, text: str) -> str:
        if not text or not text.strip():
            return text
        text = self._detrust(text)
        if self.ANON_MARK in text:
            return text
        # NOTE: no "[TAG] already present -> skip" check here. It bypassed
        # anonymization for ANY bracketed token ([section]/[ERROR]/[TODO]...),
        # leaking raw text. Dedup is handled by ANON_MARK above; re-running
        # the anonymizer on already-masked text is idempotent.
        last_err = None
        for _ in range(1 + self.ANON_RETRIES):
            try:
                r = requests.post(
                    self.ANON_API_URL,
                    files={"text": (None, text, "text/plain; charset=utf-8")},
                    headers=self._auth_headers(),
                    timeout=self.ANON_TIMEOUT
                )
                if r.ok:
                    out = r.text.strip()
                    if out:
                        return out
                    last_err = "empty response"
                else:
                    last_err = f"HTTP {r.status_code}"
            except Exception as e:
                last_err = str(e)
        # All attempts failed. FAIL-CLOSED: never leak raw text to the LLM.
        logging.warning(
            f"[GuardPrompt] Anon FAILED ({last_err}) — "
            f"fail-{'closed' if self.valves.fail_closed else 'open'}"
        )
        if self.valves.fail_closed:
            return self.BLOCK_MSG + self.ANON_MARK
        return text

    def _docling_ocr(self, image_blob: bytes, filename: str = "image.png") -> str:
        try:
            r = requests.post(
                self.DOCLING_URL,
                files={"file": (filename, image_blob, "image/png")},
                timeout=self.DOCLING_TIMEOUT
            )
            if r.ok:
                return r.json().get("markdown", "").strip()
            logging.warning(f"[GuardPrompt] OCR klaida {r.status_code}")
        except Exception as e:
            logging.warning(f"[GuardPrompt] OCR exception: {e}")
        return ""

    def _is_uuid(self, s: str) -> bool:
        return bool(re.match(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
            s.strip(), re.I
        ))

    def _is_public_http_url(self, url: str) -> bool:
        """SSRF guard: allow only http/https resolving to a PUBLIC IP. Blocks the
        internal Docker hosts (open-webui-dk, postgres, gliner...), loopback,
        link-local and cloud metadata (169.254.169.254) so a user-supplied image
        URL cannot reach internal services."""
        try:
            import ipaddress
            import socket
            from urllib.parse import urlparse
            p = urlparse(url)
            if p.scheme not in ("http", "https") or not p.hostname:
                return False
            port = p.port or (443 if p.scheme == "https" else 80)
            for _fam, _t, _pr, _c, sockaddr in socket.getaddrinfo(
                    p.hostname, port, proto=socket.IPPROTO_TCP):
                ip = ipaddress.ip_address(sockaddr[0])
                if not ip.is_global or ip.is_reserved:
                    return False
            return True
        except Exception:
            return False

    def _fetch_image(self, url: str, token: str) -> bytes:
        try:
            if self._is_uuid(url):
                # Trusted internal backend (fixed host) — the user's own token is
                # required here and never leaves the internal network.
                r = requests.get(
                    f"{self.BACKEND_URL}/api/v1/files/{url}/content",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10
                )
                if r.ok:
                    return r.content
            elif url.startswith("http"):
                # Arbitrary user-supplied URL. NEVER attach the user's OpenWebUI
                # token (would exfiltrate it to any host), and block non-public
                # targets (SSRF into internal services / cloud metadata).
                if not self._is_public_http_url(url):
                    logging.warning("[GuardPrompt] atmestas ne-viešas nuotraukos URL (SSRF apsauga)")
                    return b""
                # allow_redirects=False: the public-IP check above validates only
                # THIS URL; a 3xx could redirect to an internal host / cloud
                # metadata (169.254.169.254), which requests would otherwise follow
                # unchecked. Reject redirects outright (matches gp-transcribe).
                r = requests.get(url, timeout=10, allow_redirects=False)
                if 300 <= r.status_code < 400:
                    logging.warning("[GuardPrompt] atmestas nuotraukos URL redirect (SSRF apsauga)")
                    return b""
                if r.ok:
                    return r.content
        except Exception as e:
            logging.warning(f"[GuardPrompt] Nuotraukos klaida: {e}")
        return b""

    def _process_tool_message(self, msg: dict) -> dict:
        # Tool / terminal output flows back to the LLM as role="tool". It is
        # NOT user text, but it can carry raw PII (command output, file
        # contents, hostnames, tokens) that must be masked before it reaches
        # the model — especially an external one (OpenRouter et al.). Same
        # anonymizer + MARK dedup as user text; fail-closed via _anon_call.
        content = msg.get("content", "")
        if isinstance(content, str):
            content = self._detrust(content)
            if content.strip() and self.ANON_MARK not in content:
                anon = self._anon_call(content)
                final = (anon if anon else content).strip()
                if self.ANON_MARK not in final:
                    final += self.ANON_MARK
                msg["content"] = final
        elif isinstance(content, list):
            new_items = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    t = self._detrust(item.get("text", ""))
                    if t and t.strip() and self.ANON_MARK not in t:
                        a = self._anon_call(t)
                        f = (a if a else t).strip()
                        if self.ANON_MARK not in f:
                            f += self.ANON_MARK
                        item = {**item, "text": f}
                new_items.append(item)
            msg["content"] = new_items
        return msg

    def _process_message(self, msg: dict, token: str) -> dict:
        role = msg.get("role")
        if role == "tool":
            return self._process_tool_message(msg)
        if role != "user":
            return msg

        content = msg.get("content", "")
        ocr_texts = []

        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "image_url":
                    img = item.get("image_url", {})
                    url = img.get("url", "") if isinstance(img, dict) else str(img)
                    if url.startswith("data:image"):
                        try:
                            blob = base64.b64decode(url.split(",", 1)[1])
                            ocr = self._docling_ocr(blob)
                            if ocr:
                                ocr_texts.append(ocr)
                        except Exception as e:
                            logging.warning(f"[GuardPrompt] base64 err: {e}")
                    elif url:
                        blob = self._fetch_image(url, token)
                        if blob:
                            ocr = self._docling_ocr(blob)
                            if ocr:
                                ocr_texts.append(ocr)

            user_text = " ".join(
                item.get("text", "") for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ).strip()

            msg["content"] = [
                item for item in content
                if not (isinstance(item, dict) and item.get("type") in ("image_url", "input_image"))
            ]
        else:
            user_text = str(content).strip() if content else ""

        parts = []
        if ocr_texts:
            parts.append("Textual content of the attached image:\n" + "\n\n".join(ocr_texts))
        if user_text:
            parts.append(user_text)

        combined = "\n\n".join(parts).strip()
        if not combined:
            combined = "[Vartotojas pateike nuotrauka]"

        combined = self._detrust(combined)
        anon = self._anon_call(combined)
        final = (anon if anon else combined).strip()
        if self.ANON_MARK not in final:
            final += self.ANON_MARK

        msg["content"] = final
        msg["files"] = []
        return msg

    async def inlet(self, body: dict, user: Optional[dict] = None) -> dict:
        model = (body or {}).get("model", "") or ""
        if self.SKIP_MODELS and any(model == s or model.startswith(s) for s in self.SKIP_MODELS):
            return body  # reversible gp-openai-proxy does mask+restore for this model
        token = (user or {}).get("token", "")
        messages = body.get("messages", [])
        if isinstance(messages, list):
            body["messages"] = [self._process_message(msg, token) for msg in messages]
        return body