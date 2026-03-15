import asyncio
import hashlib
import io
import json as _json
import logging
import secrets
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app import books as books_module
from app.auth import consume_magic_link, require_auth, require_admin, request_magic_link, get_or_create_user, send_magic_email
from app.config import BASE_DIR, AUDIOBOOKS_PATH, COVERS_DIR, ADMIN_EMAIL, BASE_URL, SECURE_COOKIES, CLIENT_LOG_PATH, CLIENT_LOG_LEVEL
from app.db import get_db, init_db
from app.streaming import stream_audio

app = FastAPI(docs_url=None, redoc_url=None)
static_dir = BASE_DIR / "static"

CLIENT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
client_logger = logging.getLogger("client")
client_logger.setLevel(logging.DEBUG)
_ch = RotatingFileHandler(CLIENT_LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=5)
_ch.setFormatter(logging.Formatter("%(message)s"))
client_logger.addHandler(_ch)
client_logger.propagate = False


@app.on_event("startup")
def startup():
    init_db()
    if not AUDIOBOOKS_PATH.exists() or not AUDIOBOOKS_PATH.is_dir():
        logging.getLogger(__name__).warning(
            "Audiobooks directory not found or not a directory: %s", AUDIOBOOKS_PATH
        )
    # Bootstrap: ensure ADMIN_EMAIL is in allowed_emails and has a user row
    if ADMIN_EMAIL:
        now = int(time.time())
        with get_db() as db:
            db.execute(
                "INSERT OR IGNORE INTO allowed_emails (email, is_admin, added_at) VALUES (?, 1, ?)",
                (ADMIN_EMAIL, now),
            )
        get_or_create_user(ADMIN_EMAIL, is_admin=True)


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.get("/login")
def login_page():
    return FileResponse(static_dir / "login.html")


@app.post("/auth/request")
async def auth_request(request: Request):
    body = await request.json()
    email = str(body.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid email")
    try:
        request_magic_link(email)
    except HTTPException:
        raise
    except Exception as e:
        logging.getLogger(__name__).error("auth/request error for %s: %s", email, e)
    # Always return 200 — don't reveal whether email is registered
    return {"ok": True}


@app.get("/auth/magic/{token}")
def magic_link_page(token: str):
    """Show a confirmation page — don't consume the token yet.
    This prevents email scanners from consuming the link on prefetch."""
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Sign in — Bookthing</title>
  <link rel="stylesheet" href="/style.css">
  <link rel="icon" href="/icon-192.webp" type="image/webp">
</head>
<body>
  <div id="app">
    <div class="site-header">
      <img src="/logo2.webp" alt="Bookthing" class="site-logo">
    </div>
    <div class="login-wrap">
      <div class="login-card">
        <h2 class="login-title">Sign in to Bookthing</h2>
        <p class="login-hint">Click the button below to complete your sign-in.</p>
        <form method="post" action="/auth/magic/{token}">
          <button type="submit" class="btn btn-accent">Sign in</button>
        </form>
      </div>
    </div>
  </div>
</body>
</html>"""
    return HTMLResponse(html)


@app.post("/auth/magic/{token}")
def magic_link(token: str):
    session_id = consume_magic_link(token)
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key="session",
        value=session_id,
        max_age=30 * 86400,
        httponly=True,
        samesite="lax",
        secure=SECURE_COOKIES,
    )
    return response


@app.post("/auth/logout")
def logout(request: Request):
    session_id = request.cookies.get("session")
    if session_id:
        with get_db() as db:
            db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("session")
    return response


# ---------------------------------------------------------------------------
# Book API
# ---------------------------------------------------------------------------

@app.get("/api/books")
def list_books(
    search: str = None,
    author: str = None,
    series: str = None,
    tags: str = None,
    _session=Depends(require_auth),
):
    return books_module.get_book_list(search=search, author=author, series=series, tags=tags)


@app.get("/api/books/{book_id}")
def book_detail(book_id: str, _session=Depends(require_auth)):
    book = books_module.get_book_detail(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return book


@app.get("/api/authors")
def authors(_session=Depends(require_auth)):
    return books_module.get_authors()


@app.get("/api/series")
def series(_session=Depends(require_auth)):
    return books_module.get_series_list()


@app.get("/api/tags")
def tags(_session=Depends(require_auth)):
    return books_module.get_tags_list()


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------

@app.get("/api/stream/{book_id}/{file_index}")
async def stream(book_id: str, file_index: int, request: Request, _session=Depends(require_auth)):
    files = books_module.get_book_files(book_id)
    if not files or file_index >= len(files):
        raise HTTPException(status_code=404, detail="Track not found")
    file_path = files[file_index]
    range_header = request.headers.get("range")
    return await stream_audio(file_path, range_header)


# ---------------------------------------------------------------------------
# Cover image
# ---------------------------------------------------------------------------

_COVER_CACHE = Path("/tmp/bookthing_covers")
_COVER_MAX_PX = 600
_COVER_QUALITY = 85


def _cached_webp(cover_path: str) -> Path:
    """Return a resized WebP version of the cover, generating it if needed."""
    from PIL import Image  # imported lazily so startup isn't slowed if Pillow missing

    _COVER_CACHE.mkdir(exist_ok=True)
    src = Path(cover_path)
    mtime = src.stat().st_mtime
    key = hashlib.md5(f"{cover_path}:{mtime}".encode()).hexdigest()
    cached = _COVER_CACHE / f"{key}.webp"
    if not cached.exists():
        with Image.open(src) as img:
            img = img.convert("RGB")
            img.thumbnail((_COVER_MAX_PX, _COVER_MAX_PX), Image.LANCZOS)
            img.save(cached, "WEBP", quality=_COVER_QUALITY)
    return cached


@app.get("/api/cover/{book_id}")
def cover(book_id: str, _session=Depends(require_auth)):
    cover_path = books_module.get_book_cover_path(book_id)
    if not cover_path:
        raise HTTPException(status_code=404, detail="No cover image")
    try:
        cached = _cached_webp(cover_path)
        return FileResponse(
            str(cached),
            media_type="image/webp",
            headers={"Cache-Control": "public, max-age=86400"},
        )
    except Exception:
        # Fall back to the original file if Pillow fails for any reason
        return FileResponse(
            cover_path,
            headers={"Cache-Control": "public, max-age=86400"},
        )


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

@app.get("/api/download/{book_id}")
async def download(book_id: str, _session=Depends(require_auth)):
    book = books_module.get_book_detail(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    files = books_module.get_book_files(book_id)
    if not files:
        raise HTTPException(status_code=404, detail="No files")

    title = book.get("title") or book_id
    author = book.get("author") or ""

    if len(files) == 1:
        file_path = files[0]
        filename = f"{author} - {title}{file_path.suffix}".strip(" -")
        encoded_filename = urllib.parse.quote(filename, safe="")
        response = await stream_audio(file_path, None)
        response.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{encoded_filename}"
        return response

    zip_name = f"{author} - {title}.zip".strip(" -")
    encoded_name = urllib.parse.quote(zip_name, safe="")

    def zip_generator():
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_STORED) as zf:
                for f in files:
                    zf.write(f, arcname=f.name)
            with open(tmp_path, "rb") as f:
                while chunk := f.read(65536):
                    yield chunk
        finally:
            tmp_path.unlink(missing_ok=True)

    return StreamingResponse(
        zip_generator(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
    )


# ---------------------------------------------------------------------------
# Position save/restore
# ---------------------------------------------------------------------------

@app.get("/api/position/{book_id}")
def get_position(book_id: str, session=Depends(require_auth)):
    user_id = session.get("user_id")
    if not user_id:
        return {"file_index": 0, "time_seconds": 0}
    with get_db() as db:
        row = db.execute(
            "SELECT file_index, time_seconds FROM positions WHERE user_id = ? AND book_id = ?",
            (user_id, book_id),
        ).fetchone()
    if not row:
        return {"file_index": 0, "time_seconds": 0}
    return {"file_index": row["file_index"], "time_seconds": row["time_seconds"]}


@app.post("/api/position/{book_id}")
async def save_position(book_id: str, request: Request, session=Depends(require_auth)):
    user_id = session.get("user_id")
    if not user_id:
        return {"ok": False, "error": "no user"}
    body = await request.json()
    file_index = int(body.get("file_index", 0))
    time_seconds = float(body.get("time_seconds", 0))
    now = int(time.time())
    with get_db() as db:
        db.execute(
            "INSERT OR REPLACE INTO positions (user_id, book_id, file_index, time_seconds, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, book_id, file_index, time_seconds, now),
        )
    return {"ok": True}


@app.get("/api/positions")
def get_all_positions(session=Depends(require_auth)):
    user_id = session.get("user_id")
    if not user_id:
        return {}
    with get_db() as db:
        rows = db.execute(
            "SELECT book_id, file_index, time_seconds FROM positions WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    return {r["book_id"]: {"file_index": r["file_index"], "time_seconds": r["time_seconds"]} for r in rows}


# ---------------------------------------------------------------------------
# Admin — library scan
# ---------------------------------------------------------------------------

@app.post("/api/admin/scan")
async def admin_scan(_session=Depends(require_admin)):
    script = BASE_DIR / "scripts" / "scan.py"
    proc = await asyncio.create_subprocess_exec(
        sys.executable, str(script),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await proc.communicate()
    output = stdout.decode(errors="replace")
    return {"ok": proc.returncode == 0, "output": output}


# ---------------------------------------------------------------------------
# Admin activity log
# ---------------------------------------------------------------------------

@app.get("/api/admin/activity")
def admin_activity(_session=Depends(require_admin)):
    with get_db() as db:
        rows = db.execute(
            """SELECT u.email, p.book_id, p.file_index, p.time_seconds, p.updated_at
               FROM positions p
               JOIN users u ON p.user_id = u.user_id
               ORDER BY p.updated_at DESC
               LIMIT 200""",
        ).fetchall()
    data = books_module.load_metadata()
    book_map = {b["book_id"]: b.get("title") or b.get("path", b["book_id"])
                for b in data.get("books", {}).values()}
    return [
        {
            "email": r["email"],
            "book_id": r["book_id"],
            "book_title": book_map.get(r["book_id"], r["book_id"]),
            "file_index": r["file_index"],
            "time_seconds": r["time_seconds"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Admin — allowed emails
# ---------------------------------------------------------------------------

@app.get("/api/admin/allowed-emails")
def list_allowed_emails(_session=Depends(require_admin)):
    with get_db() as db:
        rows = db.execute(
            "SELECT email, is_admin, added_at FROM allowed_emails ORDER BY added_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/admin/allowed-emails")
async def add_allowed_email(request: Request, _session=Depends(require_admin)):
    body = await request.json()
    email = str(body.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid email")
    is_admin = bool(body.get("is_admin", False))
    now = int(time.time())
    with get_db() as db:
        db.execute(
            "INSERT OR REPLACE INTO allowed_emails (email, is_admin, added_at) VALUES (?, ?, ?)",
            (email, 1 if is_admin else 0, now),
        )
    return {"ok": True}


@app.post("/api/admin/send-login/{email:path}")
def admin_send_login(email: str, _session=Depends(require_admin)):
    """Send a login link to an allowed email, bypassing the rate limit."""
    email = email.strip().lower()
    with get_db() as db:
        allowed = db.execute(
            "SELECT is_admin FROM allowed_emails WHERE email = ?", (email,)
        ).fetchone()
    if not allowed:
        raise HTTPException(status_code=404, detail="Email not in allowed list")
    user_id = get_or_create_user(email, bool(allowed["is_admin"]))
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    expires_at = now + 3600
    with get_db() as db:
        db.execute(
            "INSERT INTO magic_links (token, label, email, created_at, expires_at, multi_use, is_admin) "
            "VALUES (?, ?, ?, ?, ?, 0, ?)",
            (token, email, email, now, expires_at, 1 if allowed["is_admin"] else 0),
        )
    link_url = f"{BASE_URL}/auth/magic/{token}"
    try:
        send_magic_email(email, link_url)
    except Exception as e:
        logging.getLogger(__name__).error("admin send-login failed for %s: %s", email, e)
        raise HTTPException(status_code=500, detail=f"Failed to send email: {e}")
    return {"ok": True}


@app.delete("/api/admin/allowed-emails/{email:path}")
def remove_allowed_email(email: str, _session=Depends(require_admin)):
    with get_db() as db:
        db.execute("DELETE FROM allowed_emails WHERE email = ?", (email,))
    return {"ok": True}


# ---------------------------------------------------------------------------
# Session info (lets frontend know admin status)
# ---------------------------------------------------------------------------

@app.get("/api/me")
def me(session=Depends(require_auth)):
    return {"is_admin": bool(session.get("is_admin")), "email": session.get("email")}


# ---------------------------------------------------------------------------
# Admin — metadata editing
# ---------------------------------------------------------------------------

@app.get("/api/admin/books")
def admin_books(_session=Depends(require_admin)):
    return books_module.get_all_books_for_admin()


@app.put("/api/admin/books/{book_id}")
async def admin_update_book(book_id: str, request: Request, _session=Depends(require_admin)):
    body = await request.json()
    fields = {}
    if "title" in body:
        fields["title"] = str(body["title"]).strip() or None
    if "author" in body:
        fields["author"] = str(body["author"]).strip() or None
    if "series" in body:
        fields["series"] = str(body["series"]).strip() or None
    if "number_in_series" in body:
        v = body["number_in_series"]
        fields["number_in_series"] = float(v) if v not in (None, "", "null") else None
    if "tags" in body:
        raw = body["tags"]
        if isinstance(raw, list):
            fields["tags"] = [t.strip() for t in raw if t.strip()]
        else:
            fields["tags"] = [t.strip() for t in str(raw).split(",") if t.strip()]
    if "description" in body:
        fields["description"] = str(body["description"]).strip() or ""
    if "hidden" in body:
        fields["hidden"] = bool(body["hidden"])

    ok = books_module.update_book(book_id, fields)
    if not ok:
        raise HTTPException(status_code=404, detail="Book not found")
    return {"ok": True}


@app.post("/api/admin/bulk")
async def admin_bulk_update(request: Request, _session=Depends(require_admin)):
    body = await request.json()
    book_ids = body.get("book_ids", [])
    if not isinstance(book_ids, list) or not book_ids:
        raise HTTPException(status_code=400, detail="book_ids list required")
    raw = body.get("fields", {})
    tags_mode = body.get("tags_mode", "replace")
    fields = {}
    if raw.get("author"):
        fields["author"] = str(raw["author"]).strip()
    if raw.get("series"):
        fields["series"] = str(raw["series"]).strip()
    if "number_in_series" in raw:
        v = raw["number_in_series"]
        if v not in (None, "", "null"):
            fields["number_in_series"] = float(v)
    if raw.get("tags"):
        t = raw["tags"]
        fields["tags"] = [x.strip() for x in (t if isinstance(t, list) else str(t).split(",")) if x.strip()]
    count = books_module.bulk_update_books(book_ids, fields, tags_mode)
    return {"ok": True, "updated": count}


@app.delete("/api/admin/books/{book_id}")
def admin_delete_book(book_id: str, _session=Depends(require_admin)):
    ok = books_module.delete_book(book_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Book not found")
    return {"ok": True}


@app.get("/api/admin/books/{book_id}/fetch-description")
def fetch_book_description(book_id: str, _session=Depends(require_admin)):
    book = books_module.get_book_detail(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    title = (book.get("title") or "").strip()
    author = (book.get("author") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Book has no title to search with")

    q = f'intitle:"{title}"'
    if author:
        q += f' inauthor:"{author}"'
    url = (
        "https://www.googleapis.com/books/v1/volumes?q="
        + urllib.parse.quote(q)
        + "&maxResults=5&printType=books"
    )

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "bookthing/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read().decode())
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Google Books API error: {e}")

    candidates = []
    for item in data.get("items", []):
        vi = item.get("volumeInfo", {})
        desc = vi.get("description", "").strip()
        if not desc:
            continue
        candidates.append({
            "title": vi.get("title", ""),
            "authors": vi.get("authors", []),
            "description": desc,
        })
    return {"candidates": candidates}


ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

@app.delete("/api/admin/books/{book_id}/cover")
def admin_delete_cover(book_id: str, _session=Depends(require_admin)):
    ok = books_module.clear_book_cover(book_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Book not found")
    return {"ok": True}


@app.post("/api/admin/books/{book_id}/cover")
async def admin_upload_cover(book_id: str, file: UploadFile = File(...), _session=Depends(require_admin)):
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, or WebP images allowed")
    ext = Path(file.filename).suffix.lower() if file.filename else ".jpg"
    if ext not in ALLOWED_IMAGE_EXTS:
        ext = ".jpg"

    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{book_id}{ext}"
    dest = COVERS_DIR / filename

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10 MB limit
        raise HTTPException(status_code=413, detail="Image too large (max 10 MB)")

    dest.write_bytes(content)
    books_module.set_book_cover(book_id, filename)
    return {"ok": True, "filename": filename}


# ---------------------------------------------------------------------------
# Client-side logging
# ---------------------------------------------------------------------------

@app.post("/api/log")
async def client_log(request: Request, user=Depends(require_auth)):
    body = await request.json()
    level = str(body.get("level", "info")).lower()
    message = str(body.get("message", ""))[:2000]
    data = body.get("data")

    with get_db() as db:
        row = db.execute("SELECT debug_logging FROM users WHERE email = ?", (user["email"],)).fetchone()
    user_debug = bool(row and row["debug_logging"])

    effective_level = logging.DEBUG if user_debug else getattr(logging, CLIENT_LOG_LEVEL, logging.WARNING)
    msg_level = getattr(logging, level.upper(), logging.INFO)
    if msg_level < effective_level:
        return {"ok": True}

    entry = {
        "ts": time.time(),
        "level": level,
        "user": user["email"],
        "ua": request.headers.get("user-agent", ""),
        "msg": message,
        "data": data,
    }
    client_logger.log(msg_level, _json.dumps(entry))
    return {"ok": True}


# ---------------------------------------------------------------------------
# Admin — users
# ---------------------------------------------------------------------------

@app.get("/api/admin/users")
def list_users(_=Depends(require_admin)):
    with get_db() as db:
        rows = db.execute(
            "SELECT email, is_admin, debug_logging, created_at FROM users ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


@app.patch("/api/admin/users/{email:path}/debug-logging")
async def set_user_debug_logging(email: str, request: Request, _=Depends(require_admin)):
    body = await request.json()
    enabled = bool(body.get("enabled", False))
    with get_db() as db:
        db.execute("UPDATE users SET debug_logging = ? WHERE email = ?", (int(enabled), email))
    return {"ok": True, "email": email, "debug_logging": enabled}


# ---------------------------------------------------------------------------
# Static files — must be last
# ---------------------------------------------------------------------------

# SPA fallback: reload on /book/<id> or /admin returns index.html
@app.get("/book/{book_id}")
async def spa_book(book_id: str):
    return FileResponse(static_dir / "index.html")

@app.get("/admin")
async def spa_admin():
    return FileResponse(static_dir / "index.html")

app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
