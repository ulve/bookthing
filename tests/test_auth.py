import secrets
import time

import pytest
from fastapi import HTTPException

from app.auth import consume_magic_link, get_or_create_user, validate_session
from app.db import get_db


class TestGetOrCreateUser:
    def test_creates_new_user(self, temp_db):
        user_id = get_or_create_user("new@example.com")
        assert user_id is not None
        with get_db() as db:
            row = db.execute("SELECT email FROM users WHERE user_id = ?", (user_id,)).fetchone()
        assert row["email"] == "new@example.com"

    def test_returns_existing_user(self, temp_db):
        id1 = get_or_create_user("same@example.com")
        id2 = get_or_create_user("same@example.com")
        assert id1 == id2

    def test_creates_admin_user(self, temp_db):
        user_id = get_or_create_user("admin@example.com", is_admin=True)
        with get_db() as db:
            row = db.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,)).fetchone()
        assert row["is_admin"] == 1

    def test_promotes_existing_to_admin(self, temp_db):
        user_id = get_or_create_user("promote@example.com", is_admin=False)
        get_or_create_user("promote@example.com", is_admin=True)
        with get_db() as db:
            row = db.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,)).fetchone()
        assert row["is_admin"] == 1

    def test_does_not_demote_admin(self, temp_db):
        user_id = get_or_create_user("admin2@example.com", is_admin=True)
        get_or_create_user("admin2@example.com", is_admin=False)
        with get_db() as db:
            row = db.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,)).fetchone()
        assert row["is_admin"] == 1


class TestConsumeMagicLink:
    def _insert_link(self, token, email="user@example.com", is_admin=0, used_at=None, expires_offset=3600):
        now = int(time.time())
        expires_at = now + expires_offset
        with get_db() as db:
            db.execute(
                "INSERT INTO magic_links (token, label, email, created_at, expires_at, multi_use, is_admin, used_at) "
                "VALUES (?, ?, ?, ?, ?, 0, ?, ?)",
                (token, email, email, now, expires_at, is_admin, used_at),
            )
            db.execute(
                "INSERT OR IGNORE INTO users (user_id, email, is_admin, created_at) VALUES (?, ?, ?, ?)",
                (secrets.token_urlsafe(16), email, is_admin, now),
            )

    def test_valid_link_creates_session(self, temp_db):
        token = secrets.token_urlsafe(32)
        self._insert_link(token)
        session_id = consume_magic_link(token)
        assert session_id is not None
        with get_db() as db:
            row = db.execute("SELECT session_id FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        assert row is not None

    def test_valid_link_marks_used(self, temp_db):
        token = secrets.token_urlsafe(32)
        self._insert_link(token)
        consume_magic_link(token)
        with get_db() as db:
            row = db.execute("SELECT used_at FROM magic_links WHERE token = ?", (token,)).fetchone()
        assert row["used_at"] is not None

    def test_nonexistent_token_raises_404(self, temp_db):
        with pytest.raises(HTTPException) as exc:
            consume_magic_link("no-such-token")
        assert exc.value.status_code == 404

    def test_expired_link_raises_410(self, temp_db):
        token = secrets.token_urlsafe(32)
        self._insert_link(token, expires_offset=-1)
        with pytest.raises(HTTPException) as exc:
            consume_magic_link(token)
        assert exc.value.status_code == 410

    def test_already_used_link_raises_410(self, temp_db):
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        self._insert_link(token, used_at=now - 60)
        with pytest.raises(HTTPException) as exc:
            consume_magic_link(token)
        assert exc.value.status_code == 410


class TestValidateSession:
    def _create_session(self, email="user@example.com", is_admin=0, expires_offset=86400):
        now = int(time.time())
        user_id = get_or_create_user(email, is_admin=bool(is_admin))
        session_id = secrets.token_urlsafe(32)
        expires_at = now + expires_offset
        with get_db() as db:
            db.execute(
                "INSERT INTO sessions (session_id, user_id, created_at, expires_at, last_seen, is_admin) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, user_id, now, expires_at, now, is_admin),
            )
        return session_id

    def test_valid_session_returns_data(self, temp_db):
        session_id = self._create_session()
        result = validate_session(session_id)
        assert result is not None
        assert result["email"] == "user@example.com"

    def test_valid_session_updates_last_seen(self, temp_db):
        session_id = self._create_session()
        before = int(time.time())
        validate_session(session_id)
        with get_db() as db:
            row = db.execute("SELECT last_seen FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        assert row["last_seen"] >= before

    def test_expired_session_returns_none(self, temp_db):
        session_id = self._create_session(expires_offset=-1)
        result = validate_session(session_id)
        assert result is None

    def test_unknown_session_returns_none(self, temp_db):
        result = validate_session("nonexistent-session-id")
        assert result is None

    def test_admin_session_reflects_is_admin(self, temp_db):
        session_id = self._create_session(email="admin@example.com", is_admin=1)
        result = validate_session(session_id)
        assert result["is_admin"]
