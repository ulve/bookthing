import secrets
import time

import pytest

from app.db import get_db


class TestAuthRequest:
    def test_valid_email_returns_ok(self, client):
        resp = client.post("/auth/request", json={"email": "anyone@example.com"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_invalid_email_returns_400(self, client):
        resp = client.post("/auth/request", json={"email": "notanemail"})
        assert resp.status_code == 400

    def test_missing_email_returns_400(self, client):
        resp = client.post("/auth/request", json={})
        assert resp.status_code == 400


class TestAuthRequired:
    def test_books_without_session_returns_401(self, client):
        resp = client.get("/api/books")
        assert resp.status_code == 401

    def test_book_detail_without_session_returns_401(self, client):
        resp = client.get("/api/books/book1")
        assert resp.status_code == 401

    def test_me_without_session_returns_401(self, client):
        resp = client.get("/api/me")
        assert resp.status_code == 401


class TestBooksApi:
    def test_list_books(self, auth_client):
        resp = auth_client.get("/api/books")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        ids = [b["book_id"] for b in data]
        assert "book1" in ids
        assert "book2" in ids

    def test_hidden_excluded_from_list(self, auth_client):
        resp = auth_client.get("/api/books")
        ids = [b["book_id"] for b in resp.json()]
        assert "hidden_book" not in ids

    def test_search_filter(self, auth_client):
        resp = auth_client.get("/api/books?search=test+book")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["book_id"] == "book1"

    def test_book_detail(self, auth_client):
        resp = auth_client.get("/api/books/book1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["book_id"] == "book1"
        assert data["title"] == "Test Book"

    def test_unknown_book_returns_404(self, auth_client):
        resp = auth_client.get("/api/books/nonexistent")
        assert resp.status_code == 404

    def test_authors(self, auth_client):
        resp = auth_client.get("/api/authors")
        assert resp.status_code == 200
        assert "Test Author" in resp.json()

    def test_series(self, auth_client):
        resp = auth_client.get("/api/series")
        assert resp.status_code == 200
        assert "Test Series" in resp.json()

    def test_tags(self, auth_client):
        resp = auth_client.get("/api/tags")
        assert resp.status_code == 200
        assert "fantasy" in resp.json()


class TestMeEndpoint:
    def test_returns_user_info(self, auth_client):
        resp = auth_client.get("/api/me")
        assert resp.status_code == 200
        data = resp.json()
        assert "is_admin" in data
        assert "email" in data
        assert data["is_admin"] is False

    def test_admin_flag(self, admin_client):
        resp = admin_client.get("/api/me")
        assert resp.status_code == 200
        assert resp.json()["is_admin"] is True


class TestPositionApi:
    def test_get_position_default(self, auth_client):
        resp = auth_client.get("/api/position/book1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["file_index"] == 0
        assert data["time_seconds"] == 0

    def test_save_and_get_position(self, auth_client):
        auth_client.post("/api/position/book1", json={"file_index": 1, "time_seconds": 42.5})
        resp = auth_client.get("/api/position/book1")
        data = resp.json()
        assert data["file_index"] == 1
        assert data["time_seconds"] == pytest.approx(42.5)

    def test_save_position_returns_ok(self, auth_client):
        resp = auth_client.post("/api/position/book1", json={"file_index": 0, "time_seconds": 10.0})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_get_all_positions(self, auth_client):
        auth_client.post("/api/position/book1", json={"file_index": 0, "time_seconds": 5.0})
        resp = auth_client.get("/api/positions")
        assert resp.status_code == 200
        data = resp.json()
        assert "book1" in data


class TestMagicLinkFlow:
    def test_magic_link_page_returns_html(self, client):
        resp = client.get("/auth/magic/sometoken")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_invalid_magic_link_post_redirects_to_error_page(self, client):
        resp = client.post("/auth/magic/badtoken", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/auth/magic/badtoken"

    def test_valid_magic_link_redirects(self, client):
        now = int(time.time())
        token = secrets.token_urlsafe(32)
        email = "link@example.com"
        with get_db() as db:
            db.execute(
                "INSERT INTO users (user_id, email, is_admin, created_at) VALUES (?, ?, 0, ?)",
                (secrets.token_urlsafe(16), email, now),
            )
            db.execute(
                "INSERT INTO magic_links (token, label, email, created_at, expires_at, multi_use, is_admin) "
                "VALUES (?, ?, ?, ?, ?, 0, 0)",
                (token, email, email, now, now + 3600),
            )
        resp = client.post(f"/auth/magic/{token}", follow_redirects=False)
        assert resp.status_code == 302
        assert "session" in resp.cookies
