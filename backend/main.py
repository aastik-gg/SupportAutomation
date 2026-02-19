from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.routers import router
from backend.services.auth import (
    PUBLIC_PATHS,
    PUBLIC_PREFIXES,
    SESSION_COOKIE_NAME,
    decode_session_token,
)

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger.setLevel(logging.INFO)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

DEFAULT_FRONTEND_ORIGINS = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://support-automation-phi.vercel.app",
    "https://supportautomation-zd3v.onrender.com",
}

ENV_FRONTEND_ORIGINS = {
    origin.strip()
    for origin in (os.getenv("FRONTEND_ORIGINS") or "").split(",")
    if origin.strip()
}

FRONTEND_ORIGINS = sorted(DEFAULT_FRONTEND_ORIGINS | ENV_FRONTEND_ORIGINS)

print("DATABASE_URL:", os.getenv("DATABASE_URL"))

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

def _maybe_attach_cors_headers(response, request: Request):
    origin = request.headers.get("origin")
    if not origin:
        return
    if origin in FRONTEND_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Credentials"] = "true"


@app.middleware("http")
async def require_session(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)

    path = request.url.path
    try:
        cookie_keys = list(request.cookies.keys())
    except Exception:
        cookie_keys = []
    logger.info("require_session: path=%s cookies=%s", path, cookie_keys)

    if path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES):
        logger.info("require_session: public path, skipping auth")
        return await call_next(request)

    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        preview = (token[:8] + "...") if isinstance(token, str) else "(present)"
        logger.info("require_session: token preview=%s", preview)

    session = decode_session_token(token)
    if not session:
        logger.info("require_session: unauthorized - no valid session")
        response = JSONResponse({"detail": "Unauthorized"}, status_code=401)
        _maybe_attach_cors_headers(response, request)
        return response

    request.state.user = session.get("user")
    response = await call_next(request)
    return response


def _spa_index_response():
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return JSONResponse({"detail": "SPA not built"}, status_code=404)


app.include_router(router)
