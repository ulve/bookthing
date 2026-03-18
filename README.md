# bookthing

A self-hosted audiobook streaming web app with magic-link authentication. No passwords — users get a login link sent to their email.

![Library view](docs/screenshots/library.png)

The library shows all your books as a grid. Books with reading progress show a progress bar; completed books show a checkmark. Books added within the last 72 hours since your last visit get a NEW badge. The player bar docks at the bottom of every page while audio is playing.

<details>
<summary>More screenshots</summary>

**Filters**

![Filters](docs/screenshots/filters.png)

Filter and sort your library by any combination of:
- Free-text search across title, author and series
- Author and series dropdowns
- Tag chips — click to toggle, multiple selected tags broaden the results (OR)
- Status: All / Listening (in progress) / Unlistened / Completed
- Sort: Newest first (default) / Oldest first / Series / Author / Title

**Book detail**

![Book detail](docs/screenshots/book-detail.png)

Each book page shows the cover, series position, tags, total duration, date added, and your progress. Below that: a description, external links (e.g. Goodreads), the track list, and a listening log showing every session with its date, duration listened, and how far through the book you got.

**Player**

![Player](docs/screenshots/player.png)

The persistent player bar shows the cover thumbnail, title, and current track. Controls: skip back, play/pause, skip forward, a scrubable progress bar with elapsed time, time remaining, and a playback speed selector.

**Admin — Library**

![Admin library](docs/screenshots/admin-library.png)

The Library tab lists all books with inline editing. Edit title, author, series, tags, and description directly in the table. Filter by missing metadata (no cover, no author, no description, no series) or by missing files. Bulk-edit tags or series across multiple books at once. Fetch descriptions from Google Books, upload covers, hide books, or delete stale entries.

**Admin — Users & Access**

![Admin users](docs/screenshots/admin-users.png)

Manage the allowed-email list and send login links directly from the UI. Toggle admin privileges per user.

**Admin — Tools**

![Admin tools](docs/screenshots/admin-tools.png)

Trigger a library scan without shelling into the container, reset book dates, and view the listening activity log.

**Book requests**

![Request modal](docs/screenshots/request-modal.png)

Any logged-in user can request a book via the **Request a book** button in the header. They enter a title or series name and an optional author.

![Admin requests](docs/screenshots/admin-requests.png)

Requests appear in the **Requests** tab on the admin page, with a badge showing how many are pending. Click **Available** to notify the user by email that the book is ready, or **Dismiss** to quietly close the request without sending anything.

**Bookshelves**

![Shelves](docs/screenshots/shelves.png)

Organise books into named personal collections. Create as many shelves as you like — a book can live on multiple shelves at once. The Shelves page shows each collection as a card with a book count; click a card to browse its contents.

![Shelf detail](docs/screenshots/shelf-detail.png)

Each shelf shows its books as a grid. Hover a card to reveal a remove button. On any book detail page, click **+ Shelf** to open a picker that lets you add or remove the book from any of your shelves, or create a new shelf on the spot.

**Login**

![Login](docs/screenshots/login.png)

No passwords. Enter your email and a one-time login link is sent to your inbox. Only addresses on the allowed list can sign in.

**Mobile (iPhone 14)**

| Library | Book detail | Player bar | Shelves |
|---|---|---|---|
| ![Library mobile](docs/screenshots/library-mobile.png) | ![Book detail mobile](docs/screenshots/book-detail-mobile.png) | ![Library with player](docs/screenshots/library-mobile-player.png) | ![Shelves mobile](docs/screenshots/shelves-mobile.png) |

</details>

## Requirements

- Docker and Docker Compose
- A Gmail account with an [App Password](https://myaccount.google.com/apppasswords) for sending login emails
- A domain with HTTPS (or run locally)
- Your audiobooks somewhere on the host machine

---

## First-time setup

```bash
# 1. Copy the example compose file and fill in your values
cp docker-compose.example.yml docker-compose.yml

# 2. Build and start
docker compose up -d --build

# 3. Scan your library
#    Detects books, reads durations, extracts cover art → data/metadata.json
docker compose exec bookthing python scripts/scan.py
```

On first start, the app emails a login link to `ADMIN_EMAIL`. Check your inbox, click the link, and you're in.

---

## docker-compose.yml settings

| Variable | Description |
|---|---|
| `BASE_URL` | Public URL of your instance (used in login email links) |
| `SESSION_DAYS` | How long login sessions last (default: 30) |
| `SECURE_COOKIES` | Set the `Secure` flag on session cookies (default: `true`). Set to `false` if running without HTTPS (e.g. local development). |
| `ADMIN_EMAIL` | Bootstrapped as admin on first start; receives the first login link |
| `GMAIL_SENDER` | Gmail address used to send login emails |
| `GMAIL_APP_PASSWORD` | Gmail App Password (not your account password) |
| `CLIENT_LOG_LEVEL` | Minimum level for browser logs written to disk: `debug`, `info`, `warning`, `error` (default: `warning`). Per-user debug logging can be toggled in the admin UI regardless of this setting. |
| `CLIENT_LOG_PATH` | Path for the browser log file (default: next to `metadata.json`, i.e. `data/client.log`) |

The audiobooks volume (`/audiobooks:ro`) should point to wherever your audio files live on the host. The `./data` volume is where the app stores its database, metadata, and uploaded covers — back this up.

---

## Running tests

```bash
# Install test dependencies (one-time)
pip install -r requirements-dev.txt

# Run all tests
pytest tests/ -v
```

Tests use temporary files and an in-memory SQLite database — no running server or real audiobook files needed.

---

## Day-to-day commands

```bash
docker compose up -d          # start in background
docker compose down           # stop
docker compose restart        # restart without rebuilding
docker compose up -d --build  # rebuild after code changes
docker compose logs -f        # view logs
```

---

## Adding users

From the admin page (`/admin`), go to the **Users** section:

1. Add an email address to the allowed list
2. Click **Send login link** — the app emails them a link directly

Users can only log in if their email is on the allowed list. Removing an email from the list doesn't invalidate existing sessions.

---

## Library scanning

The scanner walks your audiobooks directory, detects books, reads audio durations, extracts embedded cover art, and writes `data/metadata.json`.

```bash
docker compose exec bookthing python scripts/scan.py
```

Run the scanner when you add or remove books.

On first run it reads every file's audio duration (can take a minute or two for large libraries). Subsequent scans only re-read files that changed.

**What the scanner preserves:**
- title, author, series, number in series, tags, description, hidden status — anything edited in the admin UI

**What the scanner updates:**
- File list, audio durations, cover art — only if you haven't manually uploaded a cover

---

## Data & persistence

Everything persistent lives in `./data/` (mounted as a Docker volume):

| Path | Contents |
|---|---|
| `data/metadata.json` | All book metadata (titles, authors, tags, descriptions, etc.) |
| `data/covers/` | Uploaded cover images |
| `data/bookthing.db` | Sessions, magic links, and user list |
| `data/client.log` | Browser-side log (JS errors, navigation, playback events) — rotated at 5 MB, up to 5 files |

This directory lives on the host machine — it survives rebuilds, restarts, and image updates. **Back this up.**

The audiobooks themselves are mounted read-only. The app never writes to them.

---

## Updating

```bash
git pull
docker compose up -d --build
```

Your data is untouched. Database schema changes are applied automatically on startup.

---

## Admin page

Visit `/admin` while logged in as an admin. From there you can:

- Edit title, author, series, number in series, tags, and description for any book
- Fetch book descriptions from Google Books
- Upload cover images
- Bulk-edit tags or series across multiple books at once
- Hide books from the library without deleting them
- Delete stale entries left behind after moving files (shown as "missing")
- Filter by missing metadata: no author, no cover, no description, no series, missing files
- Trigger a library scan without shelling into the container
- Manage allowed emails and send login links
- Review book requests from users — mark as available (sends the user an email) or dismiss

Regular users cannot access `/admin`.

---

## Nginx + HTTPS (recommended)

```nginx
server {
    listen 443 ssl;
    server_name bookthing.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        # Required for audio streaming
        proxy_http_version 1.1;
    }
}
```

Use Certbot for the SSL certificate:

```bash
certbot --nginx -d bookthing.example.com
```
