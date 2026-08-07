from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

import db
from api import get_env
from core.timeutil import now_local

router = APIRouter(prefix="/api/accuracy", tags=["accuracy"])


def _weighted(rows: list[dict]) -> list[dict]:
    """ai_accuracy_daily-Zeilen n-gewichtet zu einer Kennzahl pro Gruppe."""
    groups: dict = {}
    for r in rows:
        key = (r["scope"], r["model_type"], r["horizon_h"])
        g = groups.setdefault(key, {"n": 0, "mae_free": 0.0, "mae_occ": 0.0,
                                    "bias_free": 0.0})
        n = int(r["n"])
        g["n"] += n
        g["mae_free"] += float(r["mae_free"]) * n
        g["mae_occ"] += float(r["mae_occ"]) * n
        g["bias_free"] += float(r["bias_free"] or 0) * n
    result = []
    for (scope, model_type, horizon), g in sorted(groups.items()):
        n = g["n"]
        result.append({
            "scope": scope, "model_type": model_type, "horizon_h": horizon,
            "n": n,
            "mae_free": round(g["mae_free"] / n, 2),
            "mae_occ_pp": round(g["mae_occ"] / n, 2),
            "bias_free": round(g["bias_free"] / n, 2),
        })
    return result


def _add_skill(entries: list[dict]) -> None:
    """Skill-Score 1 - MAE_ml / MAE_baseline pro (scope, horizon) anfuegen."""
    baseline = {(e["scope"], e["horizon_h"]): e["mae_free"]
                for e in entries if e["model_type"] == "baseline"}
    for e in entries:
        e["skill"] = None
        if e["model_type"] == "ml":
            b = baseline.get((e["scope"], e["horizon_h"]))
            if b:
                e["skill"] = round(1 - e["mae_free"] / b, 3)


@router.get("/summary")
def summary(days: int = Query(14, ge=1, le=120), env: str = Depends(get_env)):
    since = (now_local() - timedelta(days=days)).date()
    rows = db.query(
        """
        SELECT CASE WHEN city = '' THEN 'global' ELSE city END AS scope,
               model_type, horizon_h, n, mae_free, mae_occ, bias_free
        FROM ai_accuracy_daily
        WHERE pls_id = '' AND day >= %s
        """,
        (since,), env=env,
    )
    entries = _weighted(rows)
    _add_skill(entries)
    return {"days": days, "entries": entries}


@router.get("/parkhaus/{city}")
def per_parkhaus(city: str, days: int = Query(14, ge=1, le=120),
                 horizon: Optional[int] = Query(None),
                 env: str = Depends(get_env)):
    since = (now_local() - timedelta(days=days)).date()
    sql = """
        SELECT pls_id AS scope, model_type, horizon_h, n, mae_free, mae_occ,
               bias_free
        FROM ai_accuracy_daily
        WHERE city = %s AND pls_id <> '' AND day >= %s
    """
    params: list = [city, since]
    if horizon:
        sql += " AND horizon_h = %s"
        params.append(horizon)
    entries = _weighted(db.query(sql, tuple(params), env=env))
    _add_skill(entries)

    names = {r["pls_id"]: r["pls_name"] for r in db.query(
        "SELECT pls_id, pls_name FROM ai_parkhaus_map WHERE city = %s",
        (city,), env=env)}
    for e in entries:
        e["name"] = names.get(e["scope"], e["scope"])
    return {"city": city, "days": days, "entries": entries}


@router.get("/timeseries")
def timeseries(scope: str = Query("global"), days: int = Query(60, ge=1, le=365),
               horizon: int = Query(1), env: str = Depends(get_env)):
    since = (now_local() - timedelta(days=days)).date()
    if scope == "global":
        cond, params = "city = '' AND pls_id = ''", []
    elif scope.startswith("city:"):
        cond, params = "city = %s AND pls_id = ''", [scope[5:]]
    elif scope.startswith("ph:"):
        parts = scope.split(":", 2)
        if len(parts) != 3:
            raise HTTPException(422, detail="scope: ph:<city>:<pls_id>")
        cond, params = "city = %s AND pls_id = %s", [parts[1], parts[2]]
    else:
        raise HTTPException(422, detail="scope: global | city:<c> | ph:<c>:<id>")

    rows = db.query(
        f"""
        SELECT day, model_type, n, mae_free, mae_occ
        FROM ai_accuracy_daily
        WHERE {cond} AND horizon_h = %s AND day >= %s
        ORDER BY day
        """,
        tuple(params + [horizon, since]), env=env,
    )
    series: dict = {}
    for r in rows:
        series.setdefault(r["model_type"], []).append({
            "day": r["day"].isoformat(), "n": int(r["n"]),
            "mae_free": float(r["mae_free"]), "mae_occ_pp": float(r["mae_occ"]),
        })
    return {"scope": scope, "horizon_h": horizon, "series": series}


@router.get("/runs")
def runs(env: str = Depends(get_env)):
    rows = db.query(
        """
        SELECT run_id, model_type, horizon_h, trained_at, train_rows,
               cv_mae_free, cv_mae_occ, cv_r2, is_active
        FROM ai_model_runs ORDER BY trained_at DESC, horizon_h LIMIT 60
        """,
        env=env,
    )
    for r in rows:
        r["trained_at"] = r["trained_at"].isoformat()
        for k in ("cv_mae_free", "cv_mae_occ", "cv_r2"):
            if r.get(k) is not None:
                r[k] = float(r[k])
    return rows
