#!/usr/bin/env python3
"""Generate screenshots for README documentation."""

import json
import os
import secrets
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = REPO_ROOT / "docs" / "screenshots"

FEATURED_ID = "58a1ef4144ac"  # Dune by Frank Herbert

SAMPLE_BOOKS = {
    "58a1ef4144ac": {
        "book_id": "58a1ef4144ac",
        "title": "Dune",
        "author": "Frank Herbert",
        "series": "Dune Chronicles",
        "number_in_series": 1,
        "tags": ["sci-fi", "classic", "epic"],
        "description": (
            "Set in the distant future amidst a feudal interstellar society in which various "
            "noble houses control planetary fiefs, Dune tells the story of young Paul Atreides, "
            "whose family accepts the stewardship of the planet Arrakis.\n\n"
            "As the only producer of the most valuable substance in the universe — the spice "
            "melange — Arrakis is a prize worth killing for. When House Atreides is betrayed, "
            "the destruction of Paul's family will set the boy on a journey toward a destiny "
            "greater than he could ever have imagined."
        ),
        "links": [{"label": "Goodreads", "url": "https://www.goodreads.com/book/show/44767458-dune"}],
        "files": [
            "dune/part1_the_prophet.mp3",
            "dune/part2_the_holy_war.mp3",
            "dune/part3_the_prophet_undone.mp3",
        ],
        "file_durations": [12600.0, 14400.0, 11800.0],
    },
    "d141618a91e3": {
        "book_id": "d141618a91e3",
        "title": "Dune Messiah",
        "author": "Frank Herbert",
        "series": "Dune Chronicles",
        "number_in_series": 2,
        "tags": ["sci-fi", "classic"],
        "files": ["dune-messiah/full.mp3"],
        "file_durations": [28800.0],
    },
    "bbbdaad90be1": {
        "book_id": "bbbdaad90be1",
        "title": "Children of Dune",
        "author": "Frank Herbert",
        "series": "Dune Chronicles",
        "number_in_series": 3,
        "tags": ["sci-fi", "classic"],
        "files": ["children-of-dune/full.mp3"],
        "file_durations": [36000.0],
    },
    "6af96c9ee785": {
        "book_id": "6af96c9ee785",
        "title": "The Way of Kings",
        "author": "Brandon Sanderson",
        "series": "The Stormlight Archive",
        "number_in_series": 1,
        "tags": ["fantasy", "epic"],
        "files": ["way-of-kings/part1.mp3", "way-of-kings/part2.mp3"],
        "file_durations": [54000.0, 54000.0],
    },
    "32a3ce7b7f2c": {
        "book_id": "32a3ce7b7f2c",
        "title": "Words of Radiance",
        "author": "Brandon Sanderson",
        "series": "The Stormlight Archive",
        "number_in_series": 2,
        "tags": ["fantasy", "epic"],
        "files": ["words-of-radiance/full.mp3"],
        "file_durations": [72000.0],
    },
    "3c3984234200": {
        "book_id": "3c3984234200",
        "title": "Leviathan Wakes",
        "author": "James S. A. Corey",
        "series": "The Expanse",
        "number_in_series": 1,
        "tags": ["sci-fi", "space-opera"],
        "files": ["leviathan-wakes/full.mp3"],
        "file_durations": [57600.0],
    },
    "36f086af7c71": {
        "book_id": "36f086af7c71",
        "title": "Project Hail Mary",
        "author": "Andy Weir",
        "tags": ["sci-fi", "adventure"],
        "files": ["project-hail-mary/full.mp3"],
        "file_durations": [43200.0],
    },
    "871514dd415b": {
        "book_id": "871514dd415b",
        "title": "Hyperion",
        "author": "Dan Simmons",
        "series": "Hyperion Cantos",
        "number_in_series": 1,
        "tags": ["sci-fi", "classic"],
        "files": ["hyperion/full.mp3"],
        "file_durations": [50400.0],
    },
    "fec10baa2223": {
        "book_id": "fec10baa2223",
        "title": "Guards! Guards!",
        "author": "Terry Pratchett",
        "series": "Discworld",
        "number_in_series": 8,
        "tags": ["fantasy", "humor"],
        "files": ["guards-guards/full.mp3"],
        "file_durations": [28800.0],
    },
    "9e931f447093": {
        "book_id": "9e931f447093",
        "title": "The Blade Itself",
        "author": "Joe Abercrombie",
        "series": "The First Law",
        "number_in_series": 1,
        "tags": ["fantasy", "grimdark"],
        "files": ["blade-itself/full.mp3"],
        "file_durations": [36000.0],
    },
}


def find_free_port():
    import socket
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def wait_for_server(url, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def seed_db(db_path: Path, user_id: str, session_id: str):
    conn = sqlite3.connect(str(db_path))
    now = int(time.time())
    expires_at = now + 86400 * 365

    conn.execute(
        "INSERT INTO allowed_emails (email, is_admin, added_at) VALUES (?, 1, ?)",
        ("admin@example.com", now),
    )
    conn.execute(
        "INSERT INTO users (user_id, email, is_admin, created_at) VALUES (?, ?, 1, ?)",
        (user_id, "admin@example.com", now),
    )
    conn.execute(
        "INSERT INTO sessions (session_id, magic_token, user_id, created_at, expires_at, last_seen, is_admin) "
        "VALUES (?, NULL, ?, ?, ?, ?, 1)",
        (session_id, user_id, now, expires_at, now),
    )

    # Seed listening heartbeats for the featured book (Dune) to populate the log
    base_time = now - 3 * 86400  # 3 days ago
    # Session 1: 2 days ago, file 0, listened for ~40 min
    session_base = base_time + 86400
    for i in range(0, 2400, 30):  # every 30s over 2400s (~40min)
        conn.execute(
            "INSERT INTO listening_heartbeats (user_id, book_id, at, pos_seconds, file_index) VALUES (?, ?, ?, ?, 0)",
            (user_id, FEATURED_ID, session_base + i, float(i)),
        )
    # Session 2: today, file 1, listened for ~25 min
    session_base2 = now - 3600
    for i in range(0, 1500, 30):
        conn.execute(
            "INSERT INTO listening_heartbeats (user_id, book_id, at, pos_seconds, file_index) VALUES (?, ?, ?, ?, 1)",
            (user_id, FEATURED_ID, session_base2 + i, float(i)),
        )

    # Set a position for the featured book (partway through file 1)
    conn.execute(
        "INSERT INTO positions (user_id, book_id, file_index, time_seconds, updated_at) VALUES (?, ?, 1, 720.0, ?)",
        (user_id, FEATURED_ID, now),
    )

    conn.commit()
    conn.close()


def main():
    from playwright.sync_api import sync_playwright

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    port = find_free_port()
    base_url = f"http://127.0.0.1:{port}"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        db_path = tmp / "bookthing.db"
        metadata_path = tmp / "metadata.json"
        audiobooks_path = tmp / "audiobooks"
        audiobooks_path.mkdir()

        # Write metadata
        metadata_path.write_text(json.dumps({"books": SAMPLE_BOOKS}))

        # Start server
        env = os.environ.copy()
        env.update({
            "DB_PATH": str(db_path),
            "METADATA_PATH": str(metadata_path),
            "AUDIOBOOKS_PATH": str(audiobooks_path),
            "SECURE_COOKIES": "false",
            "ADMIN_EMAIL": "",
            "BASE_URL": base_url,
        })

        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port), "--host", "127.0.0.1"],
            env=env,
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            # Init DB (server will do it on startup, wait for it)
            print(f"Waiting for server at {base_url} ...")
            if not wait_for_server(f"{base_url}/login"):
                stderr = proc.stderr.read().decode() if proc.stderr else ""
                print(f"Server failed to start.\nstderr: {stderr}")
                sys.exit(1)
            print("Server ready.")

            # Seed DB after server has initialized it
            user_id = secrets.token_urlsafe(16)
            session_id = secrets.token_urlsafe(32)
            seed_db(db_path, user_id, session_id)

            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                context = browser.new_context(
                    viewport={"width": 1280, "height": 800},
                )
                context.add_cookies([{
                    "name": "session",
                    "value": session_id,
                    "domain": "127.0.0.1",
                    "path": "/",
                }])

                page = context.new_page()

                # --- library.png ---
                print("Capturing library.png ...")
                page.goto(f"{base_url}/")
                page.wait_for_selector(".book-card", timeout=10000)
                page.screenshot(path=str(OUTPUT_DIR / "library.png"), full_page=True)
                print(f"  Saved {OUTPUT_DIR / 'library.png'}")

                # --- filters.png ---
                print("Capturing filters.png ...")
                # Open the filter sidebar if it's not visible
                toggle = page.locator("#filter-toggle-btn")
                sidebar = page.locator("#filter-sidebar")
                if not sidebar.is_visible():
                    toggle.click()
                    page.wait_for_selector("#filter-sidebar", state="visible", timeout=5000)
                sidebar.screenshot(path=str(OUTPUT_DIR / "filters.png"))
                print(f"  Saved {OUTPUT_DIR / 'filters.png'}")

                # --- book-detail.png ---
                print("Capturing book-detail.png ...")
                page.goto(f"{base_url}/book/{FEATURED_ID}")
                page.wait_for_load_state("networkidle", timeout=10000)
                page.screenshot(path=str(OUTPUT_DIR / "book-detail.png"), full_page=True)
                print(f"  Saved {OUTPUT_DIR / 'book-detail.png'}")

                # --- player.png ---
                print("Capturing player.png ...")
                # Click the Play button to trigger the player bar
                play_btn = page.locator("#play-btn")
                play_btn.click()
                try:
                    page.wait_for_selector("#player-bar:not(.hidden)", timeout=8000)
                except Exception:
                    print("  Warning: player bar did not appear; screenshotting anyway")
                page.screenshot(path=str(OUTPUT_DIR / "player.png"), full_page=True)
                print(f"  Saved {OUTPUT_DIR / 'player.png'}")

                browser.close()

        finally:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    print(f"\nDone. Screenshots saved to {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
