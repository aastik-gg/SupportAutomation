"""Helper service layer consolidating shared backend utilities."""

from .auth import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    COOKIE_SAMESITE,
    COOKIE_SECURE,
    PUBLIC_PATHS,
    PUBLIC_PREFIXES,
    SESSION_COOKIE_NAME,
    SESSION_DURATION_SECONDS,
    cookie_settings_for_host,
    create_session_token,
    decode_session_token,
)
from .ai import DEFAULT_REPLY, generate_reply
from .gmail import fetch_emails, send_email
from .tickets import extract_ticket_from_body, serialize_ticket

__all__ = [
    "ADMIN_PASSWORD",
    "ADMIN_USERNAME",
    "COOKIE_SAMESITE",
    "COOKIE_SECURE",
    "PUBLIC_PATHS",
    "PUBLIC_PREFIXES",
    "SESSION_COOKIE_NAME",
    "SESSION_DURATION_SECONDS",
    "cookie_settings_for_host",
    "create_session_token",
    "decode_session_token",
    "DEFAULT_REPLY",
    "generate_reply",
    "fetch_emails",
    "send_email",
    "extract_ticket_from_body",
    "serialize_ticket",
]
