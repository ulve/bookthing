import json
import threading
from pathlib import Path
from app.config import METADATA_PATH, AUDIOBOOKS_PATH, COVERS_DIR

_metadata_lock = threading.RLock()

# Uploaded cover files are stored as data/covers/{book_id}.{ext}
# and referenced in metadata.json as "__covers/{book_id}.{ext}"
COVER_PREFIX = "__covers/"


def load_metadata() -> dict:
    with _metadata_lock:
        if not METADATA_PATH.exists():
            return {"books": {}}
        with open(METADATA_PATH) as f:
            return json.load(f)


def save_metadata(data: dict):
    METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(METADATA_PATH, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def update_book(book_id: str, fields: dict):
    """Update user-editable metadata fields for one book."""
    with _metadata_lock:
        data = load_metadata()
        book = data.get("books", {}).get(book_id)
        if not book:
            return False
        allowed = {"title", "author", "series", "number_in_series", "tags", "description", "hidden", "links"}
        for k, v in fields.items():
            if k in allowed:
                book[k] = v
        save_metadata(data)
    return True


def bulk_update_books(book_ids: list[str], fields: dict, tags_mode: str = "replace") -> int:
    """Apply fields to a list of books. tags_mode='add' merges instead of replacing."""
    with _metadata_lock:
        data = load_metadata()
        allowed = {"author", "series", "number_in_series", "tags"}
        count = 0
        for book_id in book_ids:
            book = data.get("books", {}).get(book_id)
            if book:
                for k, v in fields.items():
                    if k in allowed:
                        if k == "tags" and tags_mode == "add":
                            existing = set(book.get("tags") or [])
                            existing.update(v)
                            book[k] = sorted(existing)
                        else:
                            book[k] = v
                count += 1
        if count:
            save_metadata(data)
    return count


def rename_tag(old_tag: str, new_tag: str | None) -> int:
    """Remove or rename a tag across all books. If new_tag is None/empty, removes old_tag."""
    with _metadata_lock:
        data = load_metadata()
        count = 0
        for book in data.get("books", {}).values():
            tags = book.get("tags") or []
            if old_tag not in tags:
                continue
            if new_tag:
                seen: set[str] = set()
                result: list[str] = []
                for t in tags:
                    merged = new_tag if t == old_tag else t
                    if merged not in seen:
                        seen.add(merged)
                        result.append(merged)
                book["tags"] = result
            else:
                book["tags"] = [t for t in tags if t != old_tag]
            count += 1
        if count:
            save_metadata(data)
    return count


def delete_book(book_id: str) -> bool:
    """Permanently remove a book entry from metadata.json."""
    with _metadata_lock:
        data = load_metadata()
        if book_id not in data.get("books", {}):
            return False
        del data["books"][book_id]
        save_metadata(data)
    return True


def set_book_cover(book_id: str, cover_path_rel: str):
    """Point a book's cover to an uploaded file (relative to covers dir)."""
    with _metadata_lock:
        data = load_metadata()
        book = data.get("books", {}).get(book_id)
        if not book:
            return False
        book["cover"] = COVER_PREFIX + cover_path_rel
        save_metadata(data)
    return True


def clear_book_cover(book_id: str) -> bool:
    """Remove a book's cover, deleting the uploaded file if there is one."""
    with _metadata_lock:
        data = load_metadata()
        book = data.get("books", {}).get(book_id)
        if not book:
            return False
        cover = book.get("cover")
        if cover and cover.startswith(COVER_PREFIX):
            file_path = COVERS_DIR / cover[len(COVER_PREFIX):]
            file_path.unlink(missing_ok=True)
        book.pop("cover", None)
        save_metadata(data)
    return True


def get_book_list(search: str = None, author: str = None, series: str = None, tags: str = None) -> list:
    data = load_metadata()
    books = list(data.get("books", {}).values())

    # Filter out missing and hidden books
    books = [b for b in books if not b.get("missing") and not b.get("hidden")]

    if search:
        s = search.lower()
        books = [
            b for b in books
            if s in (b.get("title") or "").lower()
            or s in (b.get("author") or "").lower()
            or s in (b.get("series") or "").lower()
        ]
    if author:
        books = [b for b in books if author.lower() in
                 [a.strip().lower() for a in (b.get("author") or "").split(",")]]
    if series:
        books = [b for b in books if (b.get("series") or "").lower() == series.lower()]
    if tags:
        tag_list = [t.strip().lower() for t in tags.split(",")]
        books = [
            b for b in books
            if any(t in [x.lower() for x in (b.get("tags") or [])] for t in tag_list)
        ]

    # When filtering by series, sort by number in series; otherwise by author, series+number, title
    if series:
        def sort_key(b):
            return (
                b.get("number_in_series") or 0,
                b.get("title") or "",
            )
    else:
        def sort_key(b):
            return (
                b.get("author") or "",
                b.get("series") or "",
                b.get("number_in_series") or 0,
                b.get("title") or "",
            )

    books.sort(key=sort_key)
    return [_book_summary(b) for b in books]


def get_all_books_for_admin() -> list:
    """All books (including missing) with full metadata for admin editing."""
    data = load_metadata()
    books = sorted(
        data.get("books", {}).values(),
        key=lambda b: (b.get("author") or "", b.get("title") or ""),
    )
    return [_book_admin(b) for b in books]


def get_book_detail(book_id: str) -> dict:
    data = load_metadata()
    book = data.get("books", {}).get(book_id)
    if not book:
        return None
    return _book_detail(book)


def get_authors() -> list:
    data = load_metadata()
    authors = set()
    for b in data.get("books", {}).values():
        if not b.get("missing") and not b.get("hidden") and b.get("author"):
            for a in b["author"].split(","):
                a = a.strip()
                if a:
                    authors.add(a)
    return sorted(authors)


def get_series_list() -> list:
    data = load_metadata()
    series = set()
    for b in data.get("books", {}).values():
        if not b.get("missing") and not b.get("hidden") and b.get("series"):
            series.add(b["series"])
    return sorted(series)


def get_tags_list() -> list:
    data = load_metadata()
    tags = set()
    for b in data.get("books", {}).values():
        if not b.get("missing") and not b.get("hidden"):
            for t in b.get("tags") or []:
                tags.add(t)
    return sorted(tags)


def get_book_files(book_id: str) -> list[Path]:
    data = load_metadata()
    book = data.get("books", {}).get(book_id)
    if not book:
        return []
    return [AUDIOBOOKS_PATH / f for f in book.get("files", [])]


def get_book_cover_path(book_id: str) -> Path | None:
    data = load_metadata()
    book = data.get("books", {}).get(book_id)
    if not book or not book.get("cover"):
        return None
    cover = book["cover"]
    if cover.startswith(COVER_PREFIX):
        # Uploaded cover stored in data/covers/
        p = COVERS_DIR / cover[len(COVER_PREFIX):]
    else:
        # Scanner-detected cover in audiobooks dir
        p = AUDIOBOOKS_PATH / cover
    return p if p.exists() else None


def _book_summary(b: dict) -> dict:
    return {
        "book_id": b["book_id"],
        "title": b.get("title"),
        "author": b.get("author"),
        "series": b.get("series"),
        "number_in_series": b.get("number_in_series"),
        "tags": b.get("tags") or [],
        "has_cover": bool(_cover_exists(b)),
        "file_count": len(b.get("files") or []),
        "file_durations": b.get("file_durations") or [],
    }


def _book_detail(b: dict) -> dict:
    files = b.get("files") or []
    durations = b.get("file_durations") or []
    total_seconds = sum(durations) if durations else 0
    return {
        "book_id": b["book_id"],
        "title": b.get("title"),
        "author": b.get("author"),
        "series": b.get("series"),
        "number_in_series": b.get("number_in_series"),
        "tags": b.get("tags") or [],
        "description": b.get("description") or "",
        "links": b.get("links") or [],
        "has_cover": bool(_cover_exists(b)),
        "file_count": len(files),
        "total_seconds": round(total_seconds),
        "file_durations": durations,
        "chapters": b.get("chapters") or [],
        "files": [
            {"index": i, "name": Path(f).name}
            for i, f in enumerate(files)
        ],
    }


def _book_admin(b: dict) -> dict:
    return {
        "book_id": b["book_id"],
        "path": b.get("path"),
        "title": b.get("title"),
        "author": b.get("author"),
        "series": b.get("series"),
        "number_in_series": b.get("number_in_series"),
        "tags": b.get("tags") or [],
        "description": b.get("description") or "",
        "links": b.get("links") or [],
        "has_cover": bool(_cover_exists(b)),
        "missing": bool(b.get("missing")),
        "hidden": bool(b.get("hidden")),
        "file_count": len(b.get("files") or []),
    }


def _cover_exists(b: dict) -> bool:
    cover = b.get("cover")
    if not cover:
        return False
    if cover.startswith(COVER_PREFIX):
        return (COVERS_DIR / cover[len(COVER_PREFIX):]).exists()
    return (AUDIOBOOKS_PATH / cover).exists()
