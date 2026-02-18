from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict

from backend.models import Ticket
from backend.schemas import TicketSchema

logger = logging.getLogger(__name__)


def extract_ticket_from_body(body_text: str) -> Dict[str, Any] | None:
    """Extract ticket information from a JSON blob embedded in an email body."""
    try:
        json_match = re.search(r"\{.*\}", body_text, re.DOTALL)
        if not json_match:
            return None

        data = json.loads(json_match.group())
        return {
            "name": data.get("name") or data.get("customer_name") or "Customer",
            "email": data.get("email") or data.get("customer_email"),
            "subject": data.get("subject") or "Support Request",
            "message": data.get("message") or data.get("body") or "",
        }
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("JSON PARSE ERROR: %s", exc)
        return None


def serialize_ticket(ticket: Ticket) -> dict:
    """Return the API-facing representation of a Ticket ORM object."""
    return TicketSchema.from_orm(ticket).dict(by_alias=True)
