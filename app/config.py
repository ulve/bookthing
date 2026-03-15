import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

AUDIOBOOKS_PATH = Path(os.environ.get("AUDIOBOOKS_PATH", "/home/ulve/media/audiobooks"))
METADATA_PATH = Path(os.environ.get("METADATA_PATH", BASE_DIR / "data" / "metadata.json"))
DB_PATH = Path(os.environ.get("DB_PATH", BASE_DIR / "bookthing.db"))
COVERS_DIR = METADATA_PATH.parent / "covers"
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
SESSION_DAYS = int(os.environ.get("SESSION_DAYS", "30"))

# Email (Gmail SMTP with App Password)
GMAIL_SENDER = os.environ.get("GMAIL_SENDER", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")

# First-run bootstrap: this email is auto-added as admin on startup
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "").strip().lower()
