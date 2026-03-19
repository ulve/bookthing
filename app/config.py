import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

AUDIOBOOKS_PATH = Path(os.environ.get("AUDIOBOOKS_PATH", "/home/ulve/media/audiobooks"))
METADATA_PATH = Path(os.environ.get("METADATA_PATH", BASE_DIR / "data" / "metadata.json"))
DB_PATH = Path(os.environ.get("DB_PATH", BASE_DIR / "bookthing.db"))
COVERS_DIR = METADATA_PATH.parent / "covers"
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
SESSION_DAYS = int(os.environ.get("SESSION_DAYS", "30"))
SECURE_COOKIES = os.environ.get("SECURE_COOKIES", "true").strip().lower() not in ("0", "false", "no")

# Email (Gmail SMTP with App Password)
GMAIL_SENDER = os.environ.get("GMAIL_SENDER", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")

CLIENT_LOG_PATH = Path(os.environ.get("CLIENT_LOG_PATH", METADATA_PATH.parent / "client.log"))
CLIENT_LOG_LEVEL = os.environ.get("CLIENT_LOG_LEVEL", "warning").upper()
VERSION_POLL_MS = int(os.environ.get("VERSION_POLL_SECS", str(5 * 60))) * 1000

# First-run bootstrap: this email is auto-added as admin on startup
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "").strip().lower()
