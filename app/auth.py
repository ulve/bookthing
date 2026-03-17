import logging
import secrets
import smtplib
import ssl
import time
from email.mime.text import MIMEText
from fastapi import Request, HTTPException
from app.db import get_db
from app.config import SESSION_DAYS, BASE_URL, GMAIL_SENDER, GMAIL_APP_PASSWORD

logger = logging.getLogger(__name__)

# Rate limit: at most one login email per address per 10 minutes
_RATE_LIMIT_SECONDS = 600
_last_sent: dict[str, float] = {}


def get_or_create_user(email: str, is_admin: bool = False) -> str:
    """Return user_id for the given email, creating the user if they don't exist."""
    with get_db() as db:
        row = db.execute("SELECT user_id, is_admin FROM users WHERE email = ?", (email,)).fetchone()
        if row:
            # Promote to admin if needed (e.g. bootstrap)
            if is_admin and not row["is_admin"]:
                db.execute("UPDATE users SET is_admin = 1 WHERE email = ?", (email,))
            return row["user_id"]
        user_id = secrets.token_urlsafe(16)
        now = int(time.time())
        db.execute(
            "INSERT INTO users (user_id, email, is_admin, created_at) VALUES (?, ?, ?, ?)",
            (user_id, email, 1 if is_admin else 0, now),
        )
        return user_id


def request_magic_link(email: str) -> None:
    """Check if email is allowed, generate a single-use 1-hour magic link, and email it."""
    email = email.strip().lower()
    with get_db() as db:
        allowed = db.execute(
            "SELECT is_admin FROM allowed_emails WHERE email = ?", (email,)
        ).fetchone()

    if not allowed:
        # Silently return — don't leak whether email is registered
        return

    # Rate limit: silently drop if a link was sent too recently
    now_f = time.time()
    for k in [k for k, v in _last_sent.items() if now_f - v > _RATE_LIMIT_SECONDS]:
        del _last_sent[k]
    if now_f - _last_sent.get(email, 0) < _RATE_LIMIT_SECONDS:
        logger.info("Rate limit: suppressing login email for %s", email)
        return

    is_admin = bool(allowed["is_admin"])
    get_or_create_user(email, is_admin)

    token = secrets.token_urlsafe(32)
    now = int(time.time())
    expires_at = now + 3600  # link valid for 1 hour

    with get_db() as db:
        db.execute(
            "INSERT INTO magic_links (token, label, email, created_at, expires_at, multi_use, is_admin) "
            "VALUES (?, ?, ?, ?, ?, 0, ?)",
            (token, email, email, now, expires_at, 1 if is_admin else 0),
        )

    link_url = f"{BASE_URL}/auth/magic/{token}"
    send_magic_email(email, link_url)
    # Only set rate limit after successful send
    _last_sent[email] = now_f
    logger.info("Login link sent to %s", email)


def send_magic_email(email: str, link_url: str) -> None:
    """Send a login link via Gmail SMTP (App Password)."""
    if not GMAIL_SENDER or not GMAIL_APP_PASSWORD:
        raise HTTPException(status_code=500, detail="Email sending is not configured")

    msg = MIMEText(
        f"Hi,\n\nClick the link below to sign in to Bookthing:\n\n{link_url}\n\n"
        f"This link expires in 1 hour and can only be used once.\n\n"
        f"If you didn't request this, ignore this email."
    )
    msg["Subject"] = "Your Bookthing login link"
    msg["From"] = GMAIL_SENDER
    msg["To"] = email

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls(context=context)
            server.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_SENDER, email, msg.as_string())
    except Exception as e:
        logger.error("Failed to send login email to %s: %s", email, e)
        raise


def consume_magic_link(token: str) -> str:
    """Validate magic link and create a session. Returns session_id."""
    now = int(time.time())
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM magic_links WHERE token = ?", (token,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Link not found")
        if row["expires_at"] < now:
            raise HTTPException(status_code=410, detail="Link has expired")
        if not row["multi_use"] and row["used_at"] is not None:
            raise HTTPException(status_code=410, detail="Link already used")

        if not row["multi_use"]:
            db.execute("UPDATE magic_links SET used_at = ? WHERE token = ?", (now, token))

        # Resolve user for this link
        email = row["email"]
        user_id = get_or_create_user(email, bool(row["is_admin"])) if email else None

        session_id = secrets.token_urlsafe(32)
        expires_at = now + SESSION_DAYS * 86400
        db.execute(
            "INSERT INTO sessions (session_id, magic_token, user_id, created_at, expires_at, last_seen, is_admin) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, token, user_id, now, expires_at, now, row["is_admin"]),
        )
    return session_id


def validate_session(session_id: str) -> dict | None:
    now = int(time.time())
    with get_db() as db:
        row = db.execute(
            """SELECT s.session_id, s.expires_at, s.last_seen, s.is_admin AS session_is_admin,
                      u.user_id, u.email, u.is_admin AS user_is_admin
               FROM sessions s
               LEFT JOIN users u ON s.user_id = u.user_id
               WHERE s.session_id = ? AND s.expires_at > ?""",
            (session_id, now),
        ).fetchone()
        if not row:
            return None
        db.execute(
            "UPDATE sessions SET last_seen = ? WHERE session_id = ?", (now, session_id)
        )
    d = dict(row)
    # Prefer user-level is_admin; fall back to session-level for legacy sessions
    d["is_admin"] = d.get("user_is_admin") or d.get("session_is_admin", 0)
    return d


def require_auth(request: Request):
    session_id = request.cookies.get("session")
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    session = validate_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Session expired")
    return session


def require_admin(request: Request):
    session = require_auth(request)
    if not session.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return session
