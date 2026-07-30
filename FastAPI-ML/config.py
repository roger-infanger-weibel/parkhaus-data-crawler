"""Zentrale Konfiguration. Liest die gemeinsame .env im Repo-Root."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent

load_dotenv(REPO_ROOT / ".env")
load_dotenv(BASE_DIR / ".env", override=True)

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_USER = os.environ.get("DB_USER", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_CHARSET = os.environ.get("DB_CHARSET", "utf8mb4")

# Gleiche Logik wie flask/web_server.py; DB_DATABASE (Scanner) dient als Test-Fallback.
DB_DATABASE_PROD = os.environ.get("DB_DATABASE_PROD", "ph_fetch_prod")
DB_DATABASE_TEST = os.environ.get(
    "DB_DATABASE_TEST", os.environ.get("DB_DATABASE", "ph_fetch_test")
)

APP_PORT = int(os.environ.get("AI_APP_PORT", "8080"))
DEFAULT_ENV = os.environ.get("AI_DEFAULT_ENV", "prod").lower()
MODELS_DIR = Path(os.environ.get("AI_MODELS_DIR") or (BASE_DIR / "models_store"))
SCHEDULER_ENABLED = os.environ.get("AI_SCHEDULER_ENABLED", "1") not in ("0", "false", "no")

HORIZONS = (1, 2, 4, 8)  # Prognosehorizonte in Stunden


def db_name(env: str | None = None) -> str:
    """Datenbankname fuer 'prod' oder 'test' (Default: DEFAULT_ENV)."""
    env = (env or DEFAULT_ENV).lower()
    return DB_DATABASE_PROD if env == "prod" else DB_DATABASE_TEST
