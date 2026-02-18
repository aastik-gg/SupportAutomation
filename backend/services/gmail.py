from __future__ import annotations

import base64
import logging
from datetime import datetime
from email import message_from_bytes
from email.header import decode_header
from pathlib import Path
from typing import List

from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastapi import HTTPException
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlalchemy.orm import Session

from backend.models import Ticket
from backend.services.ai import generate_reply
from backend.services.tickets import extract_ticket_from_body

load_dotenv()

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]
CREDENTIALS_PATH = BASE_DIR / "credentials.json"
TOKEN_PATH = BASE_DIR / "token.json"


def gmail_service():
    if not TOKEN_PATH.exists():
        raise RuntimeError(
            "Gmail token file is missing. Provide GMAIL_TOKEN_JSON in the environment."
        )
    if not CREDENTIALS_PATH.exists():
        raise RuntimeError(
            "Gmail credentials file is missing. Provide GMAIL_CREDENTIALS_JSON in the environment."
        )
    try:
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH))
    except Exception as exc:  # pragma: no cover - defensive logging
        raise RuntimeError("Failed to load Gmail OAuth token") from exc
    return build("gmail", "v1", credentials=creds)


def send_email(to_email: str, subject: str, body: str) -> bool:
    try:
        service = gmail_service()
        message = base64.urlsafe_b64encode(
            _build_mime_message(to_email.strip(), subject, body).as_bytes()
        ).decode()
        service.users().messages().send(userId="me", body={"raw": message}).execute()
        return True
    except Exception as exc:
        logger.error("EMAIL ERROR: %s", exc)
        return False


def fetch_emails(db: Session) -> List[Ticket]:
    try:
        service = gmail_service()
    except RuntimeError as exc:
        logger.error("GMAIL CONFIG ERROR: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    try:
        results = service.users().messages().list(
            userId="me", q="in:inbox -from:me newer_than:30d", maxResults=10
        ).execute()
    except Exception as exc:
        logger.error("GMAIL LIST ERROR: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to list Gmail messages")

    messages = results.get("messages", [])
    new_tickets: List[Ticket] = []

    for msg in messages:
        gmail_message_id = msg.get("id")
        if not gmail_message_id:
            continue

        existing = (
            db.query(Ticket).filter(Ticket.gmail_message_id == gmail_message_id).first()
        )
        if existing:
            continue

        email_msg = _fetch_raw_message(service, gmail_message_id)
        if email_msg is None:
            continue

        subject = _decode_subject(email_msg)
        body = _extract_body(email_msg)

        parsed = extract_ticket_from_body(body)
        if not parsed:
            logger.info(
                "Skipped email %s because no ticket JSON was found", gmail_message_id
            )
            continue

        ticket = Ticket(
            name=parsed["name"],
            email=parsed["email"],
            subject=parsed["subject"] or subject,
            message=(parsed["message"] or "")[:1000],
            ai_reply="",
            status="pending",
            gmail_message_id=gmail_message_id,
            created_at=datetime.utcnow(),
        )

        ticket.ai_reply = generate_reply(
            {
                "name": ticket.name,
                "subject": ticket.subject,
                "message": ticket.message,
            }
        )

        db.add(ticket)
        db.commit()
        db.refresh(ticket)
        new_tickets.append(ticket)

    return new_tickets


def _build_mime_message(to_email: str, subject: str, body: str):
    from email.mime.text import MIMEText  # local import to avoid global dependency cost

    message = MIMEText(body)
    message["to"] = to_email
    message["subject"] = f"Re: {subject}"
    return message


def _fetch_raw_message(service, gmail_message_id: str):  # pragma: no cover - API call
    try:
        msg_data = service.users().messages().get(
            userId="me", id=gmail_message_id, format="raw"
        ).execute()
        raw_msg = base64.urlsafe_b64decode(msg_data["raw"])
        return message_from_bytes(raw_msg)
    except Exception as exc:
        logger.error("GMAIL MESSAGE ERROR: %s", exc)
        return None


def _decode_subject(email_msg) -> str:
    raw_subject = email_msg.get("subject", "(No Subject)")
    decoded_parts = decode_header(raw_subject)
    return "".join(
        part.decode(enc or "utf-8") if isinstance(part, bytes) else part
        for part, enc in decoded_parts
    )


def _extract_body(email_msg) -> str:
    for part in email_msg.walk():
        if part.get_content_type() == "text/plain":
            return part.get_payload(decode=True).decode(errors="ignore")
        if part.get_content_type() == "text/html":
            html = part.get_payload(decode=True).decode(errors="ignore")
            return BeautifulSoup(html, "html.parser").get_text("\n")
    return ""
