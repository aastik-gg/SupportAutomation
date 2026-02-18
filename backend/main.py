# ======================== main.py ========================
import base64
import json
import re
import hmac
import hashlib
import logging
import time
from pathlib import Path

from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from datetime import datetime
from typing import List
import os
from dotenv import load_dotenv
import google.generativeai as genai
from email.mime.text import MIMEText
from email import message_from_bytes
from email.header import decode_header
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from bs4 import BeautifulSoup
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

try:
    from .database import Base, engine, get_db
    from .models import Ticket
    from .schemas import TicketSchema
except ImportError:  # pragma: no cover
    from backend.database import Base, engine, get_db
    from backend.models import Ticket
    from backend.schemas import TicketSchema

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
STATIC_DIR = BASE_DIR / "static"
CREDENTIALS_PATH = BASE_DIR / "credentials.json"
TOKEN_PATH = BASE_DIR / "token.json"

ENV_PATH = ROOT_DIR / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)
else:
    logger.info("No .env file found at %s; relying on environment variables.", ENV_PATH)


def _write_secret_file(env_key: str, target_path: Path):
    """Write Gmail credential JSON from env vars when files are missing."""
    if target_path.exists():
        return

    raw_value = os.getenv(env_key)
    if not raw_value:
        return

    data = raw_value.strip()
    try:
        decoded = base64.b64decode(data)
        # heuristic: assume base64 if decode produced printable json
        if decoded.strip().startswith(b"{"):
            data = decoded.decode()
    except Exception:
        pass

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(data)


_write_secret_file("GMAIL_CREDENTIALS_JSON", CREDENTIALS_PATH)
_write_secret_file("GMAIL_TOKEN_JSON", TOKEN_PATH)

# CREATE APP FIRST
app = FastAPI()

# CORS
DEFAULT_FRONTEND_ORIGINS = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://support-automation.vercel.app",
    "https://supportautomation.onrender.com",
}

ENV_FRONTEND_ORIGINS = {
    origin.strip()
    for origin in (os.getenv("FRONTEND_ORIGINS") or "").split(",")
    if origin.strip()
}

FRONTEND_ORIGINS = sorted(DEFAULT_FRONTEND_ORIGINS | ENV_FRONTEND_ORIGINS)

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ---------------- AI SETUP ----------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
    if GEMINI_API_KEY:
        logger.info("Using GOOGLE_API_KEY for Gemini configuration.")
MODEL_NAME = "models/gemini-2.5-flash"
model = None

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(
        model_name=MODEL_NAME,
        safety_settings=[
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUAL", "threshold": "BLOCK_NONE"},
            {
                "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                "threshold": "BLOCK_NONE",
            },
        ],
    )
else:
    logger.warning(
        "Gemini API key is not set; configure GEMINI_API_KEY or GOOGLE_API_KEY for AI replies."
    )

DEFAULT_REPLY = "Thank you for contacting support. Our team will get back to you shortly."

if engine is not None:
    Base.metadata.create_all(bind=engine)
else:
    logger.warning(
        "DATABASE_URL is not configured; database tables cannot be created."
    )

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
if not ADMIN_PASSWORD:
    logger.warning("ADMIN_PASSWORD is not configured; login is currently disabled.")

SESSION_SECRET = os.getenv("SESSION_SECRET")
if not SESSION_SECRET:
    if ADMIN_PASSWORD:
        logger.warning(
            "SESSION_SECRET not set; using ADMIN_PASSWORD as the session secret."
        )
        SESSION_SECRET = ADMIN_PASSWORD
    else:
        SESSION_SECRET = base64.urlsafe_b64encode(os.urandom(32)).decode()
        logger.warning(
            "SESSION_SECRET and ADMIN_PASSWORD are missing; generated a temporary secret."
        )
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

# serve dashboard
STATIC_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _spa_index_response():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        logger.warning("Frontend build missing at %s", index_file)
        raise HTTPException(status_code=503, detail="Frontend build not found")
    return FileResponse(str(index_file))


@app.get("/", include_in_schema=False)
def home():
    return _spa_index_response()


# ---------------- AUTH HELPERS ----------------
def _pad_base64(value: str) -> str:
    return value + "=" * (-len(value) % 4)


def create_session_token(username: str) -> str:
    payload = {
        "user": username,
        "exp": int(time.time()) + SESSION_DURATION_SECONDS,
    }
    data = json.dumps(payload, separators=(",", ":")).encode()
    encoded = base64.urlsafe_b64encode(data).decode().rstrip("=")
    signature = hmac.new(
        SESSION_SECRET.encode(), encoded.encode(), hashlib.sha256
    ).hexdigest()
    return f"{encoded}.{signature}"


def decode_session_token(token: str | None):
    if not token or "." not in token:
        return None
    encoded, signature = token.split(".", 1)
    expected = hmac.new(
        SESSION_SECRET.encode(), encoded.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return None
    try:
        data = base64.urlsafe_b64decode(_pad_base64(encoded)).decode()
        payload = json.loads(data)
        if payload.get("exp", 0) < int(time.time()):
            return None
        return payload
    except Exception:
        return None


@app.middleware("http")
async def require_session(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)

    path = request.url.path
    if path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES):
        return await call_next(request)

    token = request.cookies.get(SESSION_COOKIE_NAME)
    session = decode_session_token(token)
    if not session:
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)

    request.state.user = session.get("user")
    response = await call_next(request)
    return response


# ---------------- JSON PARSER ----------------
class LoginRequest(BaseModel):
    username: str
    password: str


class UpdateReplyPayload(BaseModel):
    reply: str | None = None


class SendReplyPayload(BaseModel):
    confirm: bool = False


def extract_ticket_from_body(body_text):
    """
    Extracts ticket info from JSON inside email body
    """
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

    except Exception as e:
        logger.error("JSON PARSE ERROR: %s", e)
        return None


# ---------------- AI REPLY ----------------
def generate_reply(ticket):
    try:
        if model is None:
            return DEFAULT_REPLY
        prompt = f"""
You are a professional SaaS customer support agent.
Write a helpful, short and polite email reply.
Customer name: {ticket['name']}
Subject: {ticket['subject']}
Message: {ticket['message']}
Reply only with the email text.
Company name is "HOLA AI"
"""
        response = model.generate_content(prompt)
        reply_text = (response.text or "").strip()

        if not reply_text and getattr(response, "candidates", None):
            parts = []
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
            raise RuntimeError("Gemini returned an empty reply")

        preview = reply_text.replace("\n", " ")[:120]
        logger.info("AI reply generated for '%s': %s", ticket["subject"], preview)
        return reply_text
    except Exception as e:
        logger.error("AI ERROR: %s", e)
        return DEFAULT_REPLY


# ---------------- GMAIL AUTH ----------------
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
    except Exception as exc:
        raise RuntimeError("Failed to load Gmail OAuth token") from exc
    return build("gmail", "v1", credentials=creds)


# ---------------- SEND EMAIL ----------------
def send_email(to_email, subject, body):
    try:
        service = gmail_service()
        message = MIMEText(body)
        message["to"] = to_email.strip()
        message["subject"] = f"Re: {subject}"
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return True
    except Exception as e:
        logger.error("EMAIL ERROR: %s", e)
        return False


# ---------------- READ EMAILS ----------------
def fetch_emails(db: Session):
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
            db.query(Ticket)
            .filter(Ticket.gmail_message_id == gmail_message_id)
            .first()
        )
        if existing:
            continue

        try:
            msg_data = service.users().messages().get(
                userId="me", id=gmail_message_id, format="raw"
            ).execute()
        except Exception as exc:
            logger.error("GMAIL MESSAGE ERROR: %s", exc)
            continue

        raw_msg = base64.urlsafe_b64decode(msg_data["raw"])
        email_msg = message_from_bytes(raw_msg)

        raw_subject = email_msg.get("subject", "(No Subject)")
        decoded_parts = decode_header(raw_subject)
        subject = "".join(
            part.decode(enc or "utf-8") if isinstance(part, bytes) else part
            for part, enc in decoded_parts
        )

        body = ""
        for part in email_msg.walk():
            if part.get_content_type() == "text/plain":
                body = part.get_payload(decode=True).decode(errors="ignore")
                break
            if part.get_content_type() == "text/html":
                html = part.get_payload(decode=True).decode(errors="ignore")
                body = BeautifulSoup(html, "html.parser").get_text("\n")
                break

        parsed = extract_ticket_from_body(body)
        if not parsed:
            logger.info("Skipped email %s because no ticket JSON was found", gmail_message_id)
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


# ---------------- ROUTES ----------------
@app.post("/login")
def login(payload: LoginRequest):
    if not ADMIN_PASSWORD:
        raise HTTPException(
            status_code=500,
            detail="ADMIN_PASSWORD is not configured. Set the environment variable before logging in.",
        )
    if payload.username != ADMIN_USERNAME or payload.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_session_token(payload.username)
    response = JSONResponse({"message": "ok"})
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=SESSION_DURATION_SECONDS,
        expires=SESSION_DURATION_SECONDS,
        samesite=COOKIE_SAMESITE,
        secure=COOKIE_SECURE,
    )
    return response


@app.post("/logout")
def logout():
    response = JSONResponse({"message": "logged out"})
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        samesite=COOKIE_SAMESITE,
        secure=COOKIE_SECURE,
    )
    return response


@app.get("/session")
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


def serialize_ticket(ticket: Ticket) -> dict:
    return TicketSchema.from_orm(ticket).dict(by_alias=True)


@app.get("/tickets")
def get_tickets(db: Session = Depends(get_db)):
    tickets = db.query(Ticket).order_by(Ticket.created_at.desc()).all()
    serialized = [serialize_ticket(t) for t in tickets]
    pending = [t for t in serialized if t["status"] != "resolved"]
    resolved = [t for t in serialized if t["status"] == "resolved"]
    return {"inbox": pending, "sent": resolved}


@app.post("/sync-emails")
def sync_emails(db: Session = Depends(get_db)):
    new_tickets = fetch_emails(db)
    return {"new_tickets": [serialize_ticket(t) for t in new_tickets]}


@app.put("/update-reply/{ticket_id}")
def update_reply(
    ticket_id: int,
    payload: UpdateReplyPayload,
    db: Session = Depends(get_db),
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    reply_text = (payload.reply or "").strip()
    ticket.ai_reply = reply_text
    ticket.status = "edited" if reply_text else "pending"
    db.commit()
    db.refresh(ticket)
    return serialize_ticket(ticket)


@app.post("/send-reply/{ticket_id}")
def send_reply(
    ticket_id: int,
    payload: SendReplyPayload = Body(...),
    db: Session = Depends(get_db),
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        return {"error": "not found"}

    if not payload.confirm:
        raise HTTPException(status_code=400, detail="Send action not confirmed")

    if ticket.status != "edited":
        raise HTTPException(
            status_code=400,
            detail="Review and save the reply before sending",
        )

    if not send_email(ticket.email, ticket.subject, ticket.ai_reply or ""):
        return {"error": "failed"}

    ticket.status = "resolved"
    db.commit()
    return {"message": "sent"}


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    if "." in Path(full_path).name:
        raise HTTPException(status_code=404, detail="Not Found")
    return _spa_index_response()
