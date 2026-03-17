"""Tests for walk_for_books in scripts/scan.py."""
import sys
from pathlib import Path

import pytest

# Make scripts/ importable without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from scan import walk_for_books, BookCandidate


def _make_audio(path: Path, name: str) -> Path:
    f = path / name
    f.write_bytes(b"")
    return f


@pytest.fixture()
def lib(tmp_path):
    """Return a fresh temporary library root."""
    return tmp_path


# ---------------------------------------------------------------------------
# Parametrized cases
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("audio_names,expected_pattern,expected_count", [
    # Flat leaf: single folder with audio files → one flat book
    (["chapter1.mp3", "chapter2.mp3"], "flat", 1),
    # Single file leaf
    (["book.m4b"], "flat", 1),
])
def test_flat_leaf_folder(lib, audio_names, expected_pattern, expected_count):
    """A folder containing only audio files is discovered as one flat book."""
    book_dir = lib / "My Book"
    book_dir.mkdir()
    for name in audio_names:
        _make_audio(book_dir, name)

    books: list[BookCandidate] = []
    walk_for_books(lib, books, lib)

    assert len(books) == expected_count
    assert books[0].pattern == expected_pattern
    assert books[0].path == book_dir
    assert len(books[0].files) == len(audio_names)


def test_disc_pattern_folder(lib):
    """A folder whose subdirs all match disc naming and contain audio → one disc book."""
    book_dir = lib / "My Book"
    disc1 = book_dir / "Disc 1"
    disc2 = book_dir / "Disc 2"
    disc1.mkdir(parents=True)
    disc2.mkdir(parents=True)
    _make_audio(disc1, "track1.mp3")
    _make_audio(disc1, "track2.mp3")
    _make_audio(disc2, "track3.mp3")

    books: list[BookCandidate] = []
    walk_for_books(lib, books, lib)

    assert len(books) == 1
    assert books[0].pattern == "disc"
    assert books[0].path == book_dir
    assert len(books[0].files) == 3


def test_mixed_folder_no_disc_pattern(lib):
    """A folder with audio files AND subdirs (non-disc) yields a flat book plus recursed books."""
    book_dir = lib / "Series"
    book_dir.mkdir()
    _make_audio(book_dir, "intro.mp3")

    sub = book_dir / "Volume 1"
    sub.mkdir()
    _make_audio(sub, "chapter1.mp3")
    _make_audio(sub, "chapter2.mp3")

    books: list[BookCandidate] = []
    walk_for_books(lib, books, lib)

    patterns = {b.pattern for b in books}
    paths = {b.path for b in books}

    assert len(books) == 2
    assert "flat" in patterns
    assert book_dir in paths
    assert sub in paths


def test_root_loose_audio_files(lib):
    """Audio files directly in the root become individual single-file books."""
    _make_audio(lib, "a.mp3")
    _make_audio(lib, "b.mp3")

    books: list[BookCandidate] = []
    walk_for_books(lib, books, lib)

    assert len(books) == 2
    assert all(b.pattern == "single" for b in books)


def test_empty_folder_skipped(lib):
    """An empty subfolder produces no books."""
    empty = lib / "Empty"
    empty.mkdir()

    books: list[BookCandidate] = []
    walk_for_books(lib, books, lib)

    assert books == []


def test_permission_error_skipped(lib, monkeypatch):
    """A directory that raises PermissionError is silently skipped."""
    book_dir = lib / "Locked"
    book_dir.mkdir()
    _make_audio(book_dir, "track.mp3")

    original_iterdir = Path.iterdir

    def patched_iterdir(self):
        if self == book_dir:
            raise PermissionError("no access")
        return original_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", patched_iterdir)

    books: list[BookCandidate] = []
    walk_for_books(lib, books, lib)

    assert books == []
