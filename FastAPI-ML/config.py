"""Zentrale Konfiguration und Laden der .env.

Gesucht wird in dieser Reihenfolge (der erste Treffer gewinnt pro Variable):
  1. AI_ENV_FILE, falls gesetzt - fuer .env-Dateien an beliebigem Ort
  2. FastAPI-ML/.env
  3. .env im Repo-Root (gemeinsam mit scanner/ und flask/)
  4. .env oberhalb des Arbeitsverzeichnisses (wie load_dotenv() im Scanner)

ENV_FILES_LOADED zeigt, was tatsaechlich gefunden wurde - /api/health gibt das
aus, damit eine nicht gefundene .env nicht still zu Standardwerten fuehrt.
"""
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import find_dotenv, load_dotenv

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent

_candidates = []
if os.environ.get("AI_ENV_FILE"):
    _candidates.append(Path(os.environ["AI_ENV_FILE"]).expanduser())
_candidates += [BASE_DIR / ".env", REPO_ROOT / ".env"]
_found_upwards = find_dotenv(usecwd=True)
if _found_upwards:
    _candidates.append(Path(_found_upwards))

ENV_FILES_LOADED = []
for _path in _candidates:
    if _path.is_file() and str(_path) not in ENV_FILES_LOADED:
        load_dotenv(_path)  # kein override: frueherer Treffer behaelt Vorrang
        ENV_FILES_LOADED.append(str(_path))

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

APP_PORT = int(os.environ.get("AI_APP_PORT", "80"))
DEFAULT_ENV = os.environ.get("AI_DEFAULT_ENV", "prod").lower()
MODELS_DIR = Path(os.environ.get("AI_MODELS_DIR") or (BASE_DIR / "models_store"))


def _flag(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).lower() not in ("0", "false", "no")


SCHEDULER_ENABLED = _flag("AI_SCHEDULER_ENABLED")

# Trainingsfenster in Tagen. 120 Tage bedeuten ~900k Zeilen und rund 2 GB
# Spitzenspeicher - auf kleinen Servern muss das kleiner sein, sonst geraet
# die Maschine ins Swappen. AI_RETRAIN_ENABLED=0 schaltet das naechtliche
# Training komplett ab (dann Modelle woanders trainieren und die .joblib-
# Dateien nach models_store/ kopieren).
TRAIN_DAYS = int(os.environ.get("AI_TRAIN_DAYS", "120"))
RETRAIN_ENABLED = _flag("AI_RETRAIN_ENABLED")

HORIZONS = (1, 2, 4, 8)  # Prognosehorizonte in Stunden


def app_version() -> str:
    """Version = Zeitstempel der jüngsten Quelldatei.

    Kommt damit tatsaechlich aus dem laufenden Code und aktualisiert sich bei
    jedem Deployment von selbst - ohne eine Konstante, die zu pflegen jemand
    vergisst.
    """
    neuste = 0.0
    for muster in ("*.py", "*/*.py", "static/*.html", "static/*/*.js", "static/*/*.css"):
        for datei in BASE_DIR.glob(muster):
            try:
                neuste = max(neuste, datei.stat().st_mtime)
            except OSError:
                continue
    if not neuste:
        return "unbekannt"
    return datetime.fromtimestamp(neuste).strftime("%Y-%m-%d %H:%M")


def artifact_file(stored: str) -> Path:
    """Modelldatei aus dem DB-Eintrag aufloesen.

    In ai_model_runs steht nur der Dateiname, damit Modelle, die auf einer
    anderen Maschine trainiert wurden, nach dem Kopieren nach models_store/
    gefunden werden. Aeltere Eintraege mit absolutem Pfad werden akzeptiert,
    solange die Datei dort existiert.
    """
    path = Path(stored)
    if path.is_absolute() and path.exists():
        return path
    return MODELS_DIR / path.name


def db_name(env: Optional[str] = None) -> str:
    """Datenbankname fuer 'prod' oder 'test' (Default: DEFAULT_ENV)."""
    env = (env or DEFAULT_ENV).lower()
    return DB_DATABASE_PROD if env == "prod" else DB_DATABASE_TEST
