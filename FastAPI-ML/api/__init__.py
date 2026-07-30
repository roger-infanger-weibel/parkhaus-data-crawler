"""API-Router. Gemeinsame Abhaengigkeit: ?env=prod|test wie in der Flask-App."""
from fastapi import Query

import config


def get_env(env: str | None = Query(default=None)) -> str:
    env = (env or config.DEFAULT_ENV).lower()
    return "prod" if env == "prod" else "test"
