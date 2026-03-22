#!/usr/bin/env python3
"""
Scan the audiobooks directory and update data/metadata.json.
Existing metadata (title, author, series, tags, etc.) is preserved.
Only 'files', 'pattern', and 'cover' are updated from disk.
"""
import hashlib
import json
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Allow running from any directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import AUDIOBOOKS_PATH, METADATA_PATH, COVERS_DIR, MERGED_DIR

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
        # Unreadable directory — skip silently
        return

    audio_here = sorted([f for f in entries if is_audio(f)])
    dirs_here = sorted([d for d in entries if d.is_dir() and d.name != "_merged"])

    if depth == 0:
        # Root level: loose audio files each become their own single-file book
        for f in audio_here:
            books.append(BookCandidate(path, [f], "single"))
        for d in dirs_here:
            walk_for_books(d, books, root, depth + 1)
        return

    if not audio_here and not dirs_here:
        # Empty folder — nothing to discover
        return

    if is_disc_pattern(path):
        # Disc/part sub-folder pattern: collect all audio across disc dirs as one book
        all_files = audio_here + collect_disc_files(path)
        all_files = sorted(all_files, key=lambda f: (f.parent.name, f.name))
        books.append(BookCandidate(path, all_files, "disc"))
        return

    if audio_here:
        # Audio at this level: treat these files as their own flat book
        books.append(BookCandidate(path, audio_here, "flat"))

    # Recurse into any subdirectories not claimed by a disc pattern
    for d in dirs_here:
        walk_for_books(d, books, root, depth + 1)


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


USER_EDITABLE_FIELDS = {"title", "author", "series", "number_in_series", "tags", "description", "hidden", "links"}


def _read_mp4_chapters(path: Path) -> list[dict]:
    """Read embedded chapter markers from an M4B/MP4 file."""
    try:
        from mutagen.mp4 import MP4
        audio = MP4(path)
        chaps = getattr(audio, "chapters", None)
        if not chaps:
            return []
        return [
            {"title": (ch.title or f"Chapter {i + 1}").strip(), "start": round(ch.start, 2)}
            for i, ch in enumerate(chaps)
        ]
    except Exception:
        return []


def _track_title(path: Path) -> str:
    """Get a human-readable title for a track from its tags or filename."""
    try:
        from mutagen import File as MutagenFile
        audio = MutagenFile(path, easy=True)
        if audio:
            title = audio.get("title")
            if title:
                return str(title[0]).strip()
    except Exception:
        pass
    stem = path.stem
    stem = re.sub(r"^[\d\s._\-]+", "", stem)
    return stem or path.stem


def read_chapters(files_rel: list[str], file_durations: list[float], root: Path) -> list[dict]:
    """
    Extract chapter list for the book.
    Returns list of {title, start} where start is absolute seconds from book start.
    For a single M4B with embedded chapters, uses those. Otherwise one entry per file.
    """
    # Single M4B/M4A: try embedded chapter markers first
    if len(files_rel) == 1:
        path = root / files_rel[0]
        if path.suffix.lower() in (".m4b", ".m4a", ".mp4"):
            embedded = _read_mp4_chapters(path)
            if len(embedded) > 1:
                return embedded

    # Multi-file or single file with no embedded chapters: one chapter per file
    chapters = []
    abs_start = 0.0
    for i, f_rel in enumerate(files_rel):
        path = root / f_rel
        title = _track_title(path)
        chapters.append({"title": title, "start": round(abs_start, 2)})
        abs_start += file_durations[i] if i < len(file_durations) else 0.0
    return chapters


def read_durations(files_rel: list[str], root: Path) -> list[float]:
    """Read audio duration for each file via mutagen. Returns 0.0 on failure."""
    try:
        from mutagen import File as MutagenFile
    except ImportError:
        return [0.0] * len(files_rel)
    durations = []
    for f_rel in files_rel:
        path = root / f_rel
        try:
            audio = MutagenFile(path, easy=False)
            if audio is None:
                # mutagen.File is case-sensitive on extension; try explicit types
                ext = path.suffix.lower()
                if ext == ".mp3":
                    from mutagen.mp3 import MP3
                    audio = MP3(path)
                elif ext in (".m4b", ".m4a", ".mp4"):
                    from mutagen.mp4 import MP4
                    audio = MP4(path)
                elif ext == ".flac":
                    from mutagen.flac import FLAC
                    audio = FLAC(path)
            durations.append(round(audio.info.length, 2) if audio is not None and audio.info else 0.0)
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
    if "date_added" in existing:
        merged["date_added"] = existing["date_added"]
    return merged


def merge_multipart(files_rel: list[str], book_id: str, chapters: list[dict], root: Path) -> str | None:
    """Merge multiple audio files into a single file using ffmpeg.

    Returns a path relative to METADATA_PATH.parent (e.g. "merged/{book_id}.mp3")
    on success, or None on failure / if ffmpeg is not available.
    Only runs when len(files_rel) > 1.
    """
    if len(files_rel) <= 1:
        return None

    if not shutil.which("ffmpeg"):
        return None

    # Determine output extension
    exts = {Path(f).suffix.lower() for f in files_rel}
    out_ext = ".mp3" if exts == {".mp3"} else ".m4b"

    MERGED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = MERGED_DIR / f"{book_id}{out_ext}"
    out_rel = f"_merged/{book_id}{out_ext}"

    # Skip if merged file exists and is newer than all source files
    if out_path.exists():
        out_mtime = out_path.stat().st_mtime
        src_mtimes = []
        for f_rel in files_rel:
            src = root / f_rel
            if src.exists():
                src_mtimes.append(src.stat().st_mtime)
        if src_mtimes and out_mtime > max(src_mtimes):
            return out_rel

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Write ffmpeg concat file list
        filelist = tmp / "filelist.txt"
        lines = []
        for f_rel in files_rel:
            abs_path = (root / f_rel).resolve()
            lines.append(f"file '{abs_path}'")
        filelist.write_text("\n".join(lines) + "\n")

        if out_ext in (".m4b", ".mp4", ".m4a"):
            # Write ffmetadata file for chapters
            meta_lines = [";FFMETADATA1"]
            for i, ch in enumerate(chapters):
                start_ms = int(ch["start"] * 1000)
                if i + 1 < len(chapters):
                    end_ms = int(chapters[i + 1]["start"] * 1000)
                else:
                    # For last chapter, estimate end from total duration of all source files
                    try:
                        from mutagen import File as MutagenFile
                        total = 0.0
                        for f_rel in files_rel:
                            af = MutagenFile(root / f_rel, easy=False)
                            if af and af.info:
                                total += af.info.length
                        end_ms = int(total * 1000)
                    except Exception:
                        end_ms = start_ms + 1
                meta_lines.append("[CHAPTER]")
                meta_lines.append("TIMEBASE=1/1000")
                meta_lines.append(f"START={start_ms}")
                meta_lines.append(f"END={end_ms}")
                meta_lines.append(f"title={ch['title']}")
            ffmeta = tmp / "ffmetadata.txt"
            ffmeta.write_text("\n".join(meta_lines) + "\n")

            import subprocess
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-f", "concat", "-safe", "0",
                    "-i", str(filelist),
                    "-i", str(ffmeta),
                    "-map", "0:a",
                    "-map_metadata", "1",
                    "-c", "copy",
                    str(out_path),
                    "-y",
                ],
                capture_output=True,
                text=True,
            )
        else:
            # MP3: simple concat
            import subprocess
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-f", "concat", "-safe", "0",
                    "-i", str(filelist),
                    "-c", "copy",
                    str(out_path),
                    "-y",
                ],
                capture_output=True,
                text=True,
            )

        if result.returncode != 0:
            print(f"  ffmpeg error for {book_id}:\n{result.stderr[-2000:]}")
            return None

    return out_rel


def main(folder: str | None = None):
    scan_root = AUDIOBOOKS_PATH
    if folder:
        scan_root = AUDIOBOOKS_PATH / folder
        if not scan_root.exists():
            print(f"Folder not found: {scan_root}")
            sys.exit(1)
        print(f"Scanning {scan_root} ...")
    else:
        print(f"Scanning {AUDIOBOOKS_PATH} ...")

    if folder:
        # Folder-scoped scan: treat the target folder as depth-1 (a book folder),
        # not depth-0 (the library root). Otherwise audio files directly in the
        # folder each become separate single-file books instead of one flat book.
        candidates: list[BookCandidate] = []
        walk_for_books(scan_root, candidates, AUDIOBOOKS_PATH, depth=1)
    else:
        candidates = scan_library(scan_root)
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
            entry["date_added"] = datetime.now(timezone.utc).isoformat()
            entry["tags"] = ["_unfetched"]
            new_books[book_id] = entry
            print(f"  + New: {entry['path']}")

        # Read durations and chapters only when the file list has changed or is missing
        merged = new_books[book_id]
        files_changed = merged.get("files") != existing.get("files") or "file_durations" not in existing
        if files_changed:
            merged["file_durations"] = read_durations(merged["files"], AUDIOBOOKS_PATH)
            merged["chapters"] = read_chapters(merged["files"], merged["file_durations"], AUDIOBOOKS_PATH)
            if book_id in existing_books:
                print(f"  ↺ Re-read durations: {entry['path']}")
        else:
            merged["file_durations"] = existing["file_durations"]
            if "chapters" not in existing:
                merged["chapters"] = read_chapters(merged["files"], merged["file_durations"], AUDIOBOOKS_PATH)
            else:
                merged["chapters"] = existing["chapters"]

        # Merge multipart books into a single file
        if len(merged["files"]) > 1:
            if files_changed or existing.get("merged_file") is None:
                mf = merge_multipart(merged["files"], book_id, merged["chapters"], AUDIOBOOKS_PATH)
                merged["merged_file"] = mf
            else:
                merged["merged_file"] = existing.get("merged_file")
        else:
            merged["merged_file"] = None

    # Handle books from existing metadata
    folder_prefix = (folder.rstrip("/") + "/") if folder else None
    for book_id, book in existing_books.items():
        if book_id in new_books:
            continue
        book_path = book.get("path", "")
        if folder:
            # In folder-scan mode: only mark books inside the scanned folder as missing
            in_scanned = book_path == folder or book_path.startswith(folder_prefix)
            if in_scanned:
                book["missing"] = True
                new_books[book_id] = book
                print(f"  ! Missing: {book_path}")
            else:
                new_books[book_id] = book  # preserve unchanged
        else:
            book["missing"] = True
            new_books[book_id] = book
            print(f"  ! Missing: {book_path}")

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
    files_changed = merged.get("files") != existing.get("files") or "file_durations" not in existing
    if files_changed:
        merged["file_durations"] = read_durations(merged["files"], AUDIOBOOKS_PATH)
        merged["chapters"] = read_chapters(merged["files"], merged["file_durations"], AUDIOBOOKS_PATH)
    else:
        merged["file_durations"] = existing["file_durations"]
        if "chapters" not in existing:
            merged["chapters"] = read_chapters(merged["files"], merged["file_durations"], AUDIOBOOKS_PATH)
        else:
            merged["chapters"] = existing["chapters"]

    # Merge multipart books into a single file
    if len(merged["files"]) > 1:
        if files_changed or existing.get("merged_file") is None:
            mf = merge_multipart(merged["files"], book_id, merged["chapters"], AUDIOBOOKS_PATH)
            merged["merged_file"] = mf
        else:
            merged["merged_file"] = existing.get("merged_file")
    else:
        merged["merged_file"] = None

    # Replace old entry (book_id won't change for same path)
    existing_books.pop(book_id, None)
    existing_books[merged["book_id"]] = merged

    sorted_books = dict(sorted(existing_books.items(), key=lambda x: x[1].get("path", "")))
    METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(METADATA_PATH, "w") as f:
        json.dump({"books": sorted_books}, f, indent=2, ensure_ascii=False)

    n = len(merged["files"])
    return True, f"Rescanned: {matched['path']} ({n} file{'s' if n != 1 else ''})"


def merge_only():
    """Merge multipart books that don't yet have a merged_file, without rescanning."""
    if not METADATA_PATH.exists():
        print("No metadata found")
        sys.exit(1)

    with open(METADATA_PATH) as f:
        existing_data = json.load(f)

    books = existing_data.get("books", {})
    candidates = [
        (bid, b)
        for bid, b in books.items()
        if not b.get("missing") and len(b.get("files", [])) > 1 and not b.get("merged_file")
    ]

    print(f"Found {len(candidates)} multipart book(s) without a merged file")
    changed = False
    for bid, book in candidates:
        print(f"  Merging: {book.get('path', bid)} ...")
        mf = merge_multipart(book["files"], bid, book.get("chapters", []), AUDIOBOOKS_PATH)
        if mf:
            book["merged_file"] = mf
            print(f"    -> {mf}")
            changed = True
        else:
            print(f"    -> failed or skipped")

    if changed:
        sorted_books = dict(sorted(books.items(), key=lambda x: x[1].get("path", "")))
        METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(METADATA_PATH, "w") as f:
            json.dump({"books": sorted_books}, f, indent=2, ensure_ascii=False)
        print("Metadata updated.")
    else:
        print("No changes.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--book-id", help="Rescan a single book by ID instead of the full library")
    parser.add_argument("--folder", help="Scan only this subfolder (relative to AUDIOBOOKS_PATH)")
    parser.add_argument("--merge-only", action="store_true", help="Merge multipart books without a full rescan")
    args = parser.parse_args()

    if args.merge_only:
        merge_only()
    elif args.book_id:
        ok, msg = rescan_book(args.book_id)
        print(msg)
        sys.exit(0 if ok else 1)
    else:
        main(folder=args.folder)
