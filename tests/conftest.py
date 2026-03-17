import json
import secrets
import time

import pytest
from fastapi.testclient import TestClient


SAMPLE_METADATA = {
    "books": {
        "book1": {
            "book_id": "book1",
            "title": "Test Book",
            "author": "Test Author",
            "series": "Test Series",
            "number_in_series": 1,
            "tags": ["fantasy", "adventure"],
            "files": ["book1/chapter1.mp3"],
            "file_durations": [3600.0],
        },
        "book2": {
            "book_id": "book2",
            "title": "Another Book",
            "author": "Another Author",
            "series": None,
            "tags": ["sci-fi"],
            "files": ["book2/file.m4b"],
            "file_durations": [7200.0],
        },
        "hidden_book": {
            "book_id": "hidden_book",
            "title": "Hidden Book",
            "author": "Test Author",
            "hidden": True,
            "tags": [],
            "files": [],
        },
        "missing_book": {
            "book_id": "missing_book",
            "title": "Missing Book",
            "author": "Gone Author",
            "missing": True,
            "tags": [],
            "files": [],
        },
    }
}


@pytest.fixture
def temp_metadata(tmp_path, monkeypatch):
    meta_file = tmp_path / "metadata.json"
    meta_file.write_text(json.dumps(SAMPLE_METADATA))
    monkeypatch.setattr("app.books.METADATA_PATH", meta_file)
    monkeypatch.setattr("app.books.AUDIOBOOKS_PATH", tmp_path / "audiobooks")
    monkeypatch.setattr("app.books.COVERS_DIR", tmp_path / "covers")
    return meta_file


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("app.db.DB_PATH", db_path)
    from app.db import init_db
    init_db()
    return db_path


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    meta_file = tmp_path / "metadata.json"
    meta_file.write_text(json.dumps(SAMPLE_METADATA))

    monkeypatch.setattr("app.db.DB_PATH", db_path)
    monkeypatch.setattr("app.books.METADATA_PATH", meta_file)
    monkeypatch.setattr("app.books.AUDIOBOOKS_PATH", tmp_path / "audiobooks")
    monkeypatch.setattr("app.books.COVERS_DIR", tmp_path / "covers")
    monkeypatch.setattr("app.main.ADMIN_EMAIL", "")

    from app.main import app
    with TestClient(app) as c:
        yield c


def _insert_user_session(client, email: str, is_admin: bool) -> None:
    """Insert an allowed_email + user + session row and set the session cookie on client."""
    from app.db import get_db
    from app.auth import get_or_create_user

    now = int(time.time())
    admin_flag = 1 if is_admin else 0

    with get_db() as db:
        db.execute(
            "INSERT INTO allowed_emails (email, is_admin, added_at) VALUES (?, ?, ?)",
            (email, admin_flag, now),
        )
    user_id = get_or_create_user(email, is_admin=is_admin)

    session_id = secrets.token_urlsafe(32)
    expires_at = now + 86400
    with get_db() as db:
        db.execute(
            "INSERT INTO sessions (session_id, user_id, created_at, expires_at, last_seen, is_admin) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, user_id, now, expires_at, now, admin_flag),
        )

    client.cookies.set("session", session_id)


@pytest.fixture
def auth_client(client):
    """TestClient with a valid user session cookie set."""
    _insert_user_session(client, "user@example.com", is_admin=False)
    return client


@pytest.fixture
def admin_client(client):
    """TestClient with a valid admin session cookie set."""
    _insert_user_session(client, "admin@example.com", is_admin=True)
    return client
