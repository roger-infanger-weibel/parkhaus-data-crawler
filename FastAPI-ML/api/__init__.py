"""API-Router. Gemeinsame Abhaengigkeit: ?env=prod|test wie in der Flask-App."""
from fastapi import Query
from typing import Optional

import config


def get_env(env: Optional[str] = Query(default=None)) -> str:
    env = (env or config.DEFAULT_ENV).lower()
    return "prod" if env == "prod" else "test"
