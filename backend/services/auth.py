from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any, Dict, Tuple

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

SESSION_COOKIE_NAME = "support_session"
SESSION_DURATION_SECONDS = 60 * 60 * 8
PUBLIC_PATHS = {"/", "/login", "/session"}
PUBLIC_PREFIXES = ("/static", "/docs", "/openapi")

COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").strip().lower() not in {
    "false",
    "0",
    "no",
}
COOKIE_SAMESITE = "none"

SECRET_KEY = os.getenv("SESSION_SECRET", "dev-secret")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")


def create_session_token(user: str) -> str:
    payload = {"user": user, "exp": int(time.time()) + SESSION_DURATION_SECONDS}
    data = json.dumps(payload, separators=(",", ":"))
    sig = hmac.new(SECRET_KEY.encode(), data.encode(), hashlib.sha256).digest()
    token = (
        base64.urlsafe_b64encode(data.encode()).decode()
        + "."
        + base64.urlsafe_b64encode(sig).decode()
    )
    logger.info("create_session_token: generated token for %s", user)
    return token


def decode_session_token(token: str | None) -> Dict[str, Any] | None:
    if not token:
        return None
    try:
        logger.info(
            "decode_session_token: raw_token_preview=%s len=%s",
            (token[:200] + "...") if isinstance(token, str) and len(token) > 200 else token,
            len(token) if token is not None else 0,
        )
        parts = token.split(".")
        logger.info("decode_session_token: parts_count=%s", len(parts))
        if len(parts) != 2:
            logger.info("decode_session_token: invalid token parts")
            return None
        data_b64, sig_b64 = parts
        data = base64.urlsafe_b64decode(data_b64.encode())

        sig = None
        hex_chars = set("0123456789abcdefABCDEF")
        is_hex = len(sig_b64) % 2 == 0 and all(c in hex_chars for c in sig_b64)
        if is_hex:
            try:
                sig = bytes.fromhex(sig_b64)
                logger.info("decode_session_token: signature decoded as hex")
            except Exception:
                logger.info("decode_session_token: failed hex decode, trying base64")
        if sig is None:
            try:
                sig = base64.urlsafe_b64decode(sig_b64.encode())
                logger.info("decode_session_token: signature decoded as base64")
            except Exception:
                logger.info("decode_session_token: signature decoding failed")
                return None

        expected = hmac.new(SECRET_KEY.encode(), data, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, sig):
            logger.info("decode_session_token: signature mismatch")
            if SECRET_KEY == "dev-secret":
                try:
                    payload = json.loads(data.decode())
                    if payload.get("exp", 0) < time.time():
                        logger.info("decode_session_token: token expired")
                        return None
                    logger.warning(
                        "decode_session_token: accepting unsigned token in dev mode"
                    )
                    return payload
                except Exception:
                    return None
            return None

        payload = json.loads(data.decode())
        if payload.get("exp", 0) < time.time():
            logger.info("decode_session_token: token expired")
            return None
        return payload
    except Exception:  # pragma: no cover - defensive logging
        logger.exception("decode_session_token: exception while decoding token")
        return None


def cookie_settings_for_host(hostname: str | None) -> Tuple[bool, str]:
    secure_flag = COOKIE_SECURE
    try:
        if hostname and hostname.lower() in {"127.0.0.1", "localhost"}:
            secure_flag = False
    except Exception:
        secure_flag = COOKIE_SECURE

    samesite_value = COOKIE_SAMESITE if secure_flag else "lax"
    return secure_flag, samesite_value