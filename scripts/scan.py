#!/usr/bin/env python3
"""
Scan the audiobooks directory and update data/metadata.json.
Existing metadata (title, author, series, tags, etc.) is preserved.
Only 'files', 'pattern', and 'cover' are updated from disk.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

# Allow running from any directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import AUDIOBOOKS_PATH, METADATA_PATH, COVERS_DIR

AUDIO_EXTENSIONS = {".mp3", ".m4b", ".m4a", ".mp4", ".ogg", ".flac", ".aac"}
COVER_NAMES = {"cover.jpg", "cover.png", "folder.jpg", "folder.png", "cover.jpeg"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
UPLOADED_COVER_PREFIX = "__covers/"  # must match books.py

# Folder names that suggest disc/part splitting of one book
DISC_RE = re.compile(
    r"(disc|disk|cd|part|side)\s*\d+|\(\d+\s+of\s+\d+\)|\bcd\d+\b",
    re.IGNORECASE,
)


def is_audio(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS


def audio_files_in(path: Path) -> list[Path]:
    return sorted([f for f in path.iterdir() if is_audio(f)])


def subdirs_of(path: Path) -> list[Path]:
    return sorted([d for d in path.iterdir() if d.is_dir()])


def all_subdirs_have_audio(path: Path) -> bool:
    dirs = subdirs_of(path)
    if not dirs:
        return False
    return all(len(audio_files_in(d)) > 0 for d in dirs)


def subdirs_look_like_discs(path: Path) -> bool:
    """True if ALL subdirectory names match disc/part naming patterns."""
    dirs = subdirs_of(path)
    if not dirs:
        return False
    return all(bool(DISC_RE.search(d.name)) for d in dirs)


def is_disc_pattern(path: Path) -> bool:
    return all_subdirs_have_audio(path) and subdirs_look_like_discs(path)


def extract_embedded_cover(files: list[Path], book_id: str) -> str | None:
    """Extract cover art embedded in audio file tags. Returns __covers/... string or None."""
    try:
        from mutagen.id3 import ID3, APIC, ID3NoHeaderError
        from mutagen.mp4 import MP4, MP4Cover
        from mutagen.flac import FLAC
    except ImportError:
        return None

    for f in files[:3]:  # try the first few files
        ext = f.suffix.lower()
        data = None
        img_ext = ".jpg"
        try:
            if ext == ".mp3":
                try:
                    tags = ID3(f)
                except ID3NoHeaderError:
                    continue
                for tag in tags.values():
                    if isinstance(tag, APIC):
                        data = tag.data
                        img_ext = ".png" if "png" in tag.mime else ".jpg"
                        break
            elif ext in (".m4b", ".m4a", ".mp4"):
                audio = MP4(f)
                if audio.tags and "covr" in audio.tags:
                    cover = audio.tags["covr"][0]
                    data = bytes(cover)
                    img_ext = ".png" if cover.imageformat == MP4Cover.FORMAT_PNG else ".jpg"
            elif ext == ".flac":
                audio = FLAC(f)
                if audio.pictures:
                    pic = audio.pictures[0]
                    data = pic.data
                    img_ext = ".png" if "png" in pic.mime else ".jpg"
        except Exception:
            continue

        if data:
            filename = f"{book_id}_emb{img_ext}"
            dest = COVERS_DIR / filename
            COVERS_DIR.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            return UPLOADED_COVER_PREFIX + filename

    return None


def find_cover(paths: list[Path]) -> Path | None:
    """Find a cover image in any of the given directories."""
    for p in paths:
        if not p.is_dir():
            continue
        # Check preferred names first
        for name in COVER_NAMES:
            candidate = p / name
            if candidate.exists():
                return candidate
        # Fall back to any image file
        for f in sorted(p.iterdir()):
            if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS:
                return f
    return None


def collect_disc_files(book_root: Path) -> list[Path]:
    """Collect audio files from all disc sub-folders in sorted order."""
    files = []
    for disc in subdirs_of(book_root):
        files.extend(audio_files_in(disc))
    return files


def make_book_id(rel_path: str) -> str:
    return hashlib.sha1(rel_path.encode()).hexdigest()[:12]


def guess_title(folder_name: str) -> str:
    name = folder_name.replace("_", " ")  # underscores → spaces
    # Strip leading numbers/dashes: "01. Horus Rising" → "Horus Rising"
    name = re.sub(r"^[\d\s._-]+", "", name)
    # Strip trailing year: "Artemis (2017)" → "Artemis"
    name = re.sub(r"\s*\(\d{4}\)\s*$", "", name)
    name = name.strip()
    return name or folder_name


def guess_author_title(folder_name: str) -> tuple[str | None, str]:
    """Try to split 'Author - Title' pattern."""
    name = guess_title(folder_name)
    if " - " in name:
        parts = name.split(" - ", 1)
        # Heuristic: first part is author if ≤ 4 words
        if len(parts[0].split()) <= 4:
            return parts[0].strip(), parts[1].strip()
    return None, name


class BookCandidate:
    def __init__(self, path: Path, files: list[Path], pattern: str):
        self.path = path
        self.files = files
        self.pattern = pattern


def walk_for_books(path: Path, books: list, root: Path, depth: int = 0):
    try:
        entries = list(path.iterdir())
    except PermissionError:
        return

    audio_here = sorted([f for f in entries if is_audio(f)])
    dirs_here = sorted([d for d in entries if d.is_dir()])

    if depth == 0:
        # At the root: loose audio files each become their own book
        for f in audio_here:
            books.append(BookCandidate(path, [f], "single"))
        for d in dirs_here:
            walk_for_books(d, books, root, depth + 1)
        return

    if audio_here and not dirs_here:
        # Leaf folder: all audio files = one book
        books.append(BookCandidate(path, audio_here, "flat"))
        return

    if audio_here and dirs_here:
        if is_disc_pattern(path):
            # Mixed disc pattern (audio at root level + disc subdirs)
            all_files = audio_here + collect_disc_files(path)
            all_files = sorted(all_files, key=lambda f: (f.parent.name, f.name))
            books.append(BookCandidate(path, all_files, "disc"))
        else:
            # Loose audio files at this level = their own flat book
            books.append(BookCandidate(path, audio_here, "flat"))
            for d in dirs_here:
                walk_for_books(d, books, root, depth + 1)
        return

    if not audio_here and dirs_here:
        if is_disc_pattern(path):
            # Pure disc pattern
            all_files = collect_disc_files(path)
            books.append(BookCandidate(path, all_files, "disc"))
        else:
            for d in dirs_here:
                walk_for_books(d, books, root, depth + 1)
        return

    # Empty folder — skip


def scan_library(root: Path) -> list[BookCandidate]:
    books: list[BookCandidate] = []
    walk_for_books(root, books, root, depth=0)
    return books


def candidate_to_entry(candidate: BookCandidate, root: Path) -> dict:
    if candidate.pattern == "single":
        # Use the file itself as the stable path identifier
        rel_path = str(candidate.files[0].relative_to(root))
    else:
        rel_path = str(candidate.path.relative_to(root))
    book_id = make_book_id(rel_path)

    # Determine cover search paths
    cover_dirs = [candidate.path]
    if candidate.pattern == "disc":
        cover_dirs += subdirs_of(candidate.path)
    cover = find_cover(cover_dirs)
    cover_rel = str(cover.relative_to(root)) if cover else None

    files_rel = [str(f.relative_to(root)) for f in candidate.files]

    # Guess metadata from folder name
    folder_name = candidate.path.name
    if candidate.pattern == "single":
        # Use filename stem
        folder_name = candidate.files[0].stem
    author_guess, title_guess = guess_author_title(folder_name)

    # Fall back to embedded cover art if no image file found
    if not cover_rel:
        cover_rel = extract_embedded_cover(candidate.files, book_id)

    return {
        "book_id": book_id,
        "path": rel_path,
        "title": title_guess,
        "author": author_guess,
        "series": None,
        "number_in_series": None,
        "tags": [],
        "pattern": candidate.pattern,
        "cover": cover_rel,
        "files": files_rel,
    }


USER_EDITABLE_FIELDS = {"title", "author", "series", "number_in_series", "tags", "description", "hidden"}


def read_durations(files_rel: list[str], root: Path) -> list[float]:
    """Read audio duration for each file via mutagen. Returns 0.0 on failure."""
    from mutagen import File as MutagenFile
    durations = []
    for f_rel in files_rel:
        path = root / f_rel
        try:
            audio = MutagenFile(path, easy=False)
            durations.append(round(audio.info.length, 2) if audio and audio.info else 0.0)
        except Exception:
            durations.append(0.0)
    return durations


def merge(existing: dict, new_entry: dict) -> dict:
    """Update scanner-derived fields, preserve user-edited fields."""
    merged = dict(new_entry)
    for field in USER_EDITABLE_FIELDS:
        if existing.get(field) is not None:
            merged[field] = existing[field]
        elif existing.get(field) == [] and field == "tags":
            merged[field] = []
    # Preserve user-uploaded covers (they start with UPLOADED_COVER_PREFIX but
    # don't end in _emb, which is our own embedded-extraction marker).
    existing_cover = existing.get("cover") or ""
    if existing_cover.startswith(UPLOADED_COVER_PREFIX) and "_emb." not in existing_cover:
        merged["cover"] = existing_cover
    merged.pop("missing", None)
    return merged


def main():
    print(f"Scanning {AUDIOBOOKS_PATH} ...")
    candidates = scan_library(AUDIOBOOKS_PATH)
    print(f"Found {len(candidates)} book candidates")

    # Load existing metadata
    if METADATA_PATH.exists():
        with open(METADATA_PATH) as f:
            existing_data = json.load(f)
    else:
        existing_data = {"books": {}}

    existing_books = existing_data.get("books", {})
    new_books = {}

    for candidate in candidates:
        entry = candidate_to_entry(candidate, AUDIOBOOKS_PATH)
        book_id = entry["book_id"]
        existing = existing_books.get(book_id, {})

        if book_id in existing_books:
            new_books[book_id] = merge(existing, entry)
        else:
            new_books[book_id] = entry
            print(f"  + New: {entry['path']}")

        # Read durations only when the file list has changed or is missing
        merged = new_books[book_id]
        if merged.get("files") != existing.get("files") or "file_durations" not in existing:
            merged["file_durations"] = read_durations(merged["files"], AUDIOBOOKS_PATH)
            if book_id in existing_books:
                print(f"  ↺ Re-read durations: {entry['path']}")
        else:
            merged["file_durations"] = existing["file_durations"]

    # Mark missing books
    for book_id, book in existing_books.items():
        if book_id not in new_books:
            book["missing"] = True
            new_books[book_id] = book
            print(f"  ! Missing: {book['path']}")

    # Sort by path for readable diffs
    sorted_books = dict(sorted(new_books.items(), key=lambda x: x[1].get("path", "")))

    METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(METADATA_PATH, "w") as f:
        json.dump({"books": sorted_books}, f, indent=2, ensure_ascii=False)

    total = len([b for b in sorted_books.values() if not b.get("missing")])
    print(f"\nDone. {total} books written to {METADATA_PATH}")


def rescan_book(book_id: str) -> tuple[bool, str]:
    """Rescan a single book by book_id. Returns (success, message)."""
    if not METADATA_PATH.exists():
        return False, "No metadata found"

    with open(METADATA_PATH) as f:
        existing_data = json.load(f)

    existing_books = existing_data.get("books", {})
    if book_id not in existing_books:
        return False, f"Book {book_id!r} not found in metadata"

    existing = existing_books[book_id]
    book_path_str = existing.get("path", "")

    # Single-file book: path is the audio file itself
    if Path(book_path_str).suffix.lower() in AUDIO_EXTENSIONS:
        audio_path = AUDIOBOOKS_PATH / book_path_str
        candidates = [BookCandidate(audio_path.parent, [audio_path], "single")] if is_audio(audio_path) else []
    else:
        book_dir = AUDIOBOOKS_PATH / book_path_str
        candidates: list[BookCandidate] = []
        if book_dir.is_dir():
            walk_for_books(book_dir, candidates, AUDIOBOOKS_PATH, depth=1)

    if not candidates:
        existing_books[book_id]["missing"] = True
        sorted_books = dict(sorted(existing_books.items(), key=lambda x: x[1].get("path", "")))
        METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(METADATA_PATH, "w") as f:
            json.dump({"books": sorted_books}, f, indent=2, ensure_ascii=False)
        return False, f"No audio files found at: {book_path_str}"

    # Find the candidate that matches this book_id (path-derived)
    matched = None
    for c in candidates:
        entry = candidate_to_entry(c, AUDIOBOOKS_PATH)
        if entry["book_id"] == book_id:
            matched = entry
            break
    if matched is None:
        matched = candidate_to_entry(candidates[0], AUDIOBOOKS_PATH)

    merged = merge(existing, matched)
    if merged.get("files") != existing.get("files") or "file_durations" not in existing:
        merged["file_durations"] = read_durations(merged["files"], AUDIOBOOKS_PATH)
    else:
        merged["file_durations"] = existing["file_durations"]

    # Replace old entry (book_id won't change for same path)
    existing_books.pop(book_id, None)
    existing_books[merged["book_id"]] = merged

    sorted_books = dict(sorted(existing_books.items(), key=lambda x: x[1].get("path", "")))
    METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(METADATA_PATH, "w") as f:
        json.dump({"books": sorted_books}, f, indent=2, ensure_ascii=False)

    n = len(merged["files"])
    return True, f"Rescanned: {matched['path']} ({n} file{'s' if n != 1 else ''})"


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--book-id", help="Rescan a single book by ID instead of the full library")
    args = parser.parse_args()

    if args.book_id:
        ok, msg = rescan_book(args.book_id)
        print(msg)
        sys.exit(0 if ok else 1)
    else:
        main()
