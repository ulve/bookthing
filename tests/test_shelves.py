"""Tests for bookshelf API endpoints."""
import secrets
import time

import pytest


def test_create_shelf(auth_client):
    resp = auth_client.post("/api/shelves", json={"name": "My Shelf"})
    assert resp.status_code == 200
    data = resp.json()
    assert "shelf_id" in data
    assert data["name"] == "My Shelf"


def test_list_shelves_includes_created(auth_client):
    auth_client.post("/api/shelves", json={"name": "Fantasy"})
    resp = auth_client.get("/api/shelves")
    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()]
    assert "Fantasy" in names


def test_list_shelves_book_count_zero(auth_client):
    auth_client.post("/api/shelves", json={"name": "Empty Shelf"})
    shelves = auth_client.get("/api/shelves").json()
    shelf = next(s for s in shelves if s["name"] == "Empty Shelf")
    assert shelf["book_count"] == 0


def test_add_book_to_shelf(auth_client):
    shelf_id = auth_client.post("/api/shelves", json={"name": "Reading"}).json()["shelf_id"]
    resp = auth_client.post(f"/api/shelves/{shelf_id}/books", json={"book_id": "book1"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_get_shelf_books_includes_added(auth_client):
    shelf_id = auth_client.post("/api/shelves", json={"name": "Sci-Fi"}).json()["shelf_id"]
    auth_client.post(f"/api/shelves/{shelf_id}/books", json={"book_id": "book1"})
    resp = auth_client.get(f"/api/shelves/{shelf_id}/books")
    assert resp.status_code == 200
    books = resp.json()
    assert any(b["book_id"] == "book1" for b in books)


def test_get_book_shelves_includes_shelf(auth_client):
    shelf_id = auth_client.post("/api/shelves", json={"name": "To Read"}).json()["shelf_id"]
    auth_client.post(f"/api/shelves/{shelf_id}/books", json={"book_id": "book2"})
    resp = auth_client.get("/api/books/book2/shelves")
    assert resp.status_code == 200
    assert shelf_id in resp.json()


def test_remove_book_from_shelf(auth_client):
    shelf_id = auth_client.post("/api/shelves", json={"name": "Temp"}).json()["shelf_id"]
    auth_client.post(f"/api/shelves/{shelf_id}/books", json={"book_id": "book1"})
    resp = auth_client.delete(f"/api/shelves/{shelf_id}/books/book1")
    assert resp.status_code == 200
    books = auth_client.get(f"/api/shelves/{shelf_id}/books").json()
    assert not any(b["book_id"] == "book1" for b in books)


def test_rename_shelf(auth_client):
    shelf_id = auth_client.post("/api/shelves", json={"name": "Old Name"}).json()["shelf_id"]
    resp = auth_client.put(f"/api/shelves/{shelf_id}", json={"name": "New Name"})
    assert resp.status_code == 200
    shelves = auth_client.get("/api/shelves").json()
    names = [s["name"] for s in shelves]
    assert "New Name" in names
    assert "Old Name" not in names


def test_delete_shelf(auth_client):
    shelf_id = auth_client.post("/api/shelves", json={"name": "Delete Me"}).json()["shelf_id"]
    resp = auth_client.delete(f"/api/shelves/{shelf_id}")
    assert resp.status_code == 200
    shelves = auth_client.get("/api/shelves").json()
    assert not any(s["shelf_id"] == shelf_id for s in shelves)


def test_access_other_users_shelf_returns_403(client):
    """Two separate users; one cannot access the other's shelf."""
    from tests.conftest import _insert_user_session
    from app.db import get_db

    # Create user A's shelf
    _insert_user_session(client, "user_a@example.com", is_admin=False)
    shelf_resp = client.post("/api/shelves", json={"name": "Private Shelf"})
    assert shelf_resp.status_code == 200
    shelf_id = shelf_resp.json()["shelf_id"]

    # Switch to user B
    client.cookies.clear()
    _insert_user_session(client, "user_b@example.com", is_admin=False)

    # User B cannot access user A's shelf books
    resp = client.get(f"/api/shelves/{shelf_id}/books")
    assert resp.status_code == 403

    # User B cannot delete user A's shelf
    resp = client.delete(f"/api/shelves/{shelf_id}")
    assert resp.status_code == 403
