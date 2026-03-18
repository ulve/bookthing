import hashlib
import sqlite3
import time

from app import books as books_module


def get_shelves(db: sqlite3.Connection, user_id: str) -> list[dict]:
    rows = db.execute(
        """
        SELECT s.shelf_id, s.name,
               COUNT(b.book_id) AS book_count
          FROM bookshelves s
          LEFT JOIN bookshelf_books b ON b.shelf_id = s.shelf_id
         WHERE s.user_id = ?
         GROUP BY s.shelf_id
         ORDER BY s.name COLLATE NOCASE
        """,
        (user_id,),
    ).fetchall()
    return [{"shelf_id": r["shelf_id"], "name": r["name"], "book_count": r["book_count"]} for r in rows]


def create_shelf(db: sqlite3.Connection, user_id: str, name: str) -> dict:
    now = int(time.time())
    shelf_id = hashlib.sha1(f"{user_id}:{name}:{now}".encode()).hexdigest()[:12]
    db.execute(
        "INSERT INTO bookshelves (shelf_id, user_id, name, created_at) VALUES (?, ?, ?, ?)",
        (shelf_id, user_id, name, now),
    )
    return {"shelf_id": shelf_id, "name": name}


def rename_shelf(db: sqlite3.Connection, user_id: str, shelf_id: str, name: str) -> dict:
    row = db.execute(
        "SELECT shelf_id FROM bookshelves WHERE shelf_id = ? AND user_id = ?",
        (shelf_id, user_id),
    ).fetchone()
    if not row:
        return None
    db.execute(
        "UPDATE bookshelves SET name = ? WHERE shelf_id = ?",
        (name, shelf_id),
    )
    return {"shelf_id": shelf_id, "name": name}


def delete_shelf(db: sqlite3.Connection, user_id: str, shelf_id: str) -> bool:
    row = db.execute(
        "SELECT shelf_id FROM bookshelves WHERE shelf_id = ? AND user_id = ?",
        (shelf_id, user_id),
    ).fetchone()
    if not row:
        return False
    db.execute("DELETE FROM bookshelves WHERE shelf_id = ?", (shelf_id,))
    return True


def get_shelf_books(db: sqlite3.Connection, user_id: str, shelf_id: str) -> list[dict] | None:
    row = db.execute(
        "SELECT shelf_id FROM bookshelves WHERE shelf_id = ? AND user_id = ?",
        (shelf_id, user_id),
    ).fetchone()
    if not row:
        return None
    book_rows = db.execute(
        "SELECT book_id FROM bookshelf_books WHERE shelf_id = ? ORDER BY added_at",
        (shelf_id,),
    ).fetchall()
    data = books_module.load_metadata()
    books_map = data.get("books", {})
    results = []
    for br in book_rows:
        book = books_map.get(br["book_id"])
        if book:
            results.append(books_module._book_detail(book))
    return results


def add_book_to_shelf(db: sqlite3.Connection, user_id: str, shelf_id: str, book_id: str) -> bool:
    row = db.execute(
        "SELECT shelf_id FROM bookshelves WHERE shelf_id = ? AND user_id = ?",
        (shelf_id, user_id),
    ).fetchone()
    if not row:
        return False
    now = int(time.time())
    db.execute(
        "INSERT OR IGNORE INTO bookshelf_books (shelf_id, book_id, added_at) VALUES (?, ?, ?)",
        (shelf_id, book_id, now),
    )
    return True


def remove_book_from_shelf(db: sqlite3.Connection, user_id: str, shelf_id: str, book_id: str) -> bool:
    row = db.execute(
        "SELECT shelf_id FROM bookshelves WHERE shelf_id = ? AND user_id = ?",
        (shelf_id, user_id),
    ).fetchone()
    if not row:
        return False
    db.execute(
        "DELETE FROM bookshelf_books WHERE shelf_id = ? AND book_id = ?",
        (shelf_id, book_id),
    )
    return True


def get_book_shelf_ids(db: sqlite3.Connection, user_id: str, book_id: str) -> list[str]:
    rows = db.execute(
        """
        SELECT bb.shelf_id
          FROM bookshelf_books bb
          JOIN bookshelves s ON s.shelf_id = bb.shelf_id
         WHERE s.user_id = ? AND bb.book_id = ?
        """,
        (user_id, book_id),
    ).fetchall()
    return [r["shelf_id"] for r in rows]
