from __future__ import annotations

import logging
import os
from threading import Lock
from typing import Any, Dict

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency
    from google import genai  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    genai = None

DEFAULT_REPLY = (
    "Thanks for reaching out. We received your message and will respond shortly."
)
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash")


def _init_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY not set; falling back to DEFAULT_REPLY")
        return None
    if genai is None:
        logger.warning(
            "google-genai package is unavailable; install google-genai and set GEMINI_API_KEY"
        )
        return None
    try:
        return genai.Client(api_key=api_key)
    except Exception as exc:  # pragma: no cover - diagnostic logging only
        logger.warning("Gemini client init failed (%s); using DEFAULT_REPLY", exc)
        return None


_client_lock = Lock()
_client = _init_client()


def _get_client():
    global _client
    if _client is not None:
        return _client

    with _client_lock:
        if _client is None:
            _client = _init_client()
    return _client


def generate_reply(ticket: Dict[str, Any]) -> str:
    try:
        client = _get_client()
        if client is None:
            logger.warning("generate_reply: Gemini model unavailable; returning default reply")
            return DEFAULT_REPLY

        prompt = f"""
You are a professional SaaS customer support agent.
Write a helpful, short and polite email reply.
Customer name: {ticket['name']}
Subject: {ticket['subject']}
Message: {ticket['message']}
Reply only with the email text.
Company name is "Nayyar Analytics".
"""
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[{"role": "user", "parts": [{"text": prompt}]}],
        )

        # google-genai responses expose output_text convenience
        reply_text = (getattr(response, "output_text", "") or "").strip()

        if not reply_text and getattr(response, "candidates", None):
            parts: list[str] = []
            for candidate in response.candidates:
                content = getattr(candidate, "content", None)
                content_parts = getattr(content, "parts", None) if content else None
                if not content_parts:
                    continue
                for part in content_parts:
                    text = getattr(part, "text", "")
                    if text:
                        parts.append(text.strip())
                if parts:
                    break
            reply_text = "\n".join(parts).strip()

        if not reply_text:
            logger.warning("generate_reply: Gemini returned empty text; falling back to default")
            return DEFAULT_REPLY

        preview = reply_text.replace("\n", " ")[:120]
        logger.info("AI reply generated for '%s': %s", ticket["subject"], preview)
        return reply_text
    except Exception as exc:
        logger.exception("AI ERROR while generating reply")
        return DEFAULT_REPLY
