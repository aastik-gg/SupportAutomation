import logging

from fastapi import Body, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Ticket
from backend.schemas import (
    CreateTicketPayload,
    LoginRequest,
    SendReplyPayload,
    UpdateReplyPayload,
)
from backend.services.ai import generate_reply
from backend.services.auth import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    SESSION_COOKIE_NAME,
    SESSION_DURATION_SECONDS,
    cookie_settings_for_host,
    create_session_token,
    decode_session_token,
)
from backend.services.gmail import fetch_emails, send_email
from backend.services.tickets import serialize_ticket

logger = logging.getLogger(__name__)


def login(payload: LoginRequest, request: Request):
    if not ADMIN_PASSWORD:
        raise HTTPException(
            status_code=500,
            detail="ADMIN_PASSWORD is not configured. Set the environment variable before logging in.",
        )
    if payload.username != ADMIN_USERNAME or payload.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_session_token(payload.username)
    logger.info(
        "login: created token preview=%s",
        (token[:32] + "...") if isinstance(token, str) else "(not-str)",
    )
    response = JSONResponse({"message": "ok"})

    host = request.url.hostname if request.url else None
    secure_flag, samesite_value = cookie_settings_for_host(host)

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=SESSION_DURATION_SECONDS,
        expires=SESSION_DURATION_SECONDS,
        samesite=samesite_value,
        secure=secure_flag,
    )
    return response


def logout(request: Request):
    secure_flag, samesite_value = cookie_settings_for_host(
        request.url.hostname if request.url else None
    )
    response = JSONResponse({"message": "logged out"})
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        samesite=samesite_value,
        secure=secure_flag,
    )
    return response


def session_status(request: Request):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    payload = decode_session_token(token)
    if not payload:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "user": payload.get("user"),
        "expires": payload.get("exp"),
    }


def get_tickets(db: Session = Depends(get_db)):
    tickets = db.query(Ticket).order_by(Ticket.created_at.desc()).all()
    serialized = [serialize_ticket(t) for t in tickets]
    pending = [t for t in serialized if t["status"] != "resolved"]
    resolved = [t for t in serialized if t["status"] == "resolved"]
    return {"inbox": pending, "sent": resolved}


def post_ticket(payload: CreateTicketPayload, db: Session = Depends(get_db)):
    ticket = Ticket(
        name=(payload.name or "Customer"),
        email=payload.email,
        subject=(payload.subject or "Support Request"),
        message=(payload.message or "")[:1000],
        ai_reply="",
        status="pending",
        gmail_message_id=None,
        created_at=None,
    )
    ticket.ai_reply = generate_reply(
        {"name": ticket.name, "subject": ticket.subject, "message": ticket.message}
    )

    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return serialize_ticket(ticket)
def sync_emails(db: Session = Depends(get_db)):
    new_tickets = fetch_emails(db)
    return {"new_tickets": [serialize_ticket(t) for t in new_tickets]}


def update_reply(ticket_id: int, payload: UpdateReplyPayload, db: Session = Depends(get_db)):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    reply_text = (payload.reply or "").strip()
    ticket.ai_reply = reply_text
    ticket.status = "edited" if reply_text else "pending"
    db.commit()
    db.refresh(ticket)
    return serialize_ticket(ticket)


def send_reply(ticket_id: int, payload: SendReplyPayload = Body(...), db: Session = Depends(get_db)):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        return {"error": "not found"}

    # Require explicit confirmation only for manually edited replies.
    # Allow sending AI-generated (`pending`) tickets without an explicit confirm flag.
    if ticket.status == "edited" and not payload.confirm:
        raise HTTPException(status_code=400, detail="Send action not confirmed")

    if not (ticket.ai_reply and ticket.ai_reply.strip()):
        raise HTTPException(status_code=400, detail="No reply available to send")

    if ticket.status not in ("edited", "pending"):
        raise HTTPException(
            status_code=400,
            detail="Ticket is not in a sendable state",
        )

    if not send_email(ticket.email, ticket.subject, ticket.ai_reply or ""):
        return {"error": "failed"}

    ticket.status = "resolved"
    db.commit()
    return {"message": "sent"}


def spa_fallback(full_path: str):
    if "." in full_path:
        raise HTTPException(status_code=404, detail="Not Found")
    from backend.main import _spa_index_response

    return _spa_index_response()
