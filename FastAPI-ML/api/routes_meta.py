from datetime import datetime

from fastapi import APIRouter, Depends

import config
import db
from api import get_env
from core import data_access as da

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health")
def health(env: str = Depends(get_env)):
    status: dict = {
        "status": "ok", "env": env, "db": config.db_name(env),
        "db_host": config.DB_HOST,
        "version": config.app_version(),
        "env_files": config.ENV_FILES_LOADED or "KEINE .env gefunden - Standardwerte aktiv",
    }
    try:
        runs = db.query(
            "SELECT model_type, horizon_h, trained_at, cv_mae_occ FROM ai_model_runs "
            "WHERE is_active = 1", env=env)
        status["active_runs"] = [
            {**r, "trained_at": r["trained_at"].isoformat()} for r in runs
        ]
        last = db.query("SELECT MAX(created_at) AS ts FROM ai_predictions", env=env)
        status["last_prediction"] = (
            last[0]["ts"].isoformat() if last and last[0]["ts"] else None
        )
    except Exception as exc:  # DB nicht erreichbar
        status["status"] = "degraded"
        status["error"] = str(exc)

    try:
        from jobs.scheduler import job_states
        status["scheduler"] = job_states()
    except Exception:
        status["scheduler"] = None
    return status


@router.get("/environments")
def environments():
    return {"prod": config.DB_DATABASE_PROD, "test": config.DB_DATABASE_TEST}


@router.get("/version")
def version():
    """Version und Fusszeilen-Angaben für die Oberfläche."""
    return {
        "version": config.app_version(),
        "titel": "Swiss Parking Monitor",
        "kontakt": "roger@roil.ch",
    }


@router.get("/cities")
def cities(env: str = Depends(get_env)):
    rows = da.get_cities(env=env)
    for r in rows:
        for k in ("latitude", "longitude"):
            if r.get(k) is not None:
                r[k] = float(r[k])
    return rows


@router.get("/parkings/{city}")
def parkings(city: str, env: str = Depends(get_env)):
    mapping = {m["pls_id"]: m for m in da.get_mapping(env=env, city=city)}
    result = []
    for s in sorted(da.latest_snapshots(env=env, city=city),
                    key=lambda s: s["name"]):
        m = mapping.get(s["pls_id"], {})
        occ = None
        if s["total"]:
            occ = round((s["total"] - s["free"]) / s["total"], 3)
        result.append({
            "pls_id": s["pls_id"],
            "name": s["name"],
            "group": m.get("parking_group"),
            "free": s["free"],
            "total": s["total"],
            "occ": occ,
            "fetch_ts": s["fetch_ts"].isoformat(),
        })
    return result
