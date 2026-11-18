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
def timeseries(scope: str = Query("global"), days: int = Query(90, ge=1, le=365),
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


def _ampel(free, total):
    """Gleiche Logik wie ampelKlasse() in forecast.js."""
    if not total or total == 0:
        return "gelb"
    ratio = free / total
    if ratio > 0.1 and free > 15:
        return "gruen"
    if ratio > 0.05 and free > 15:
        return "gelb"
    return "rot"


@router.get("/ampel")
def ampel_accuracy(days: int = Query(30, ge=1, le=120), env: str = Depends(get_env)):
    """Ampel-Trefferquote: wie oft stimmt gruen/gelb/rot?"""
    since = now_local() - timedelta(days=days)
    rows = db.query(
        """
        SELECT city, horizon_h, predicted_free, actual_free, total_at_pred
        FROM ai_predictions
        WHERE actual_free IS NOT NULL
          AND total_at_pred IS NOT NULL AND total_at_pred > 0
          AND model_type = 'ml'
          AND target_time >= %s
        """,
        (since,), env=env,
    )
    if not rows:
        return {"days": days, "total": 0, "by_horizon": [], "by_city": [], "confusion": []}

    from collections import defaultdict
    by_hz: dict = defaultdict(lambda: {"n": 0, "correct": 0})
    by_city: dict = defaultdict(lambda: {"n": 0, "correct": 0})
    confusion: dict = defaultdict(int)

    for r in rows:
        pred_a = _ampel(r["predicted_free"], r["total_at_pred"])
        act_a = _ampel(r["actual_free"], r["total_at_pred"])
        match = pred_a == act_a

        hz = r["horizon_h"]
        by_hz[hz]["n"] += 1
        if match:
            by_hz[hz]["correct"] += 1

        if hz == 1:
            city = r["city"]
            by_city[city]["n"] += 1
            if match:
                by_city[city]["correct"] += 1

        confusion[(pred_a, act_a)] += 1

    horizon_list = []
    for hz in sorted(by_hz):
        g = by_hz[hz]
        horizon_list.append({"horizon_h": hz, "n": g["n"],
                             "correct": g["correct"],
                             "pct": round(g["correct"] / g["n"] * 100, 1)})

    city_list = []
    for city in sorted(by_city):
        g = by_city[city]
        city_list.append({"city": city, "n": g["n"],
                          "correct": g["correct"],
                          "pct": round(g["correct"] / g["n"] * 100, 1)})

    conf_list = []
    total_n = len(rows)
    for (pred, act), n in sorted(confusion.items(), key=lambda x: -x[1]):
        conf_list.append({"predicted": pred, "actual": act, "n": n,
                          "pct": round(n / total_n * 100, 1)})

    dangerous = confusion.get(("gruen", "rot"), 0)

    return {
        "days": days,
        "total": total_n,
        "by_horizon": horizon_list,
        "by_city": city_list,
        "confusion": conf_list,
        "dangerous_pct": round(dangerous / total_n * 100, 2) if total_n else 0,
    }


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


@router.get("/activations")
def activations(days: int = Query(90, ge=1, le=365), env: str = Depends(get_env)):
    """Aktivierungsdaten der ML-Modelle fuer Timeline-Markierungen."""
    since = (now_local() - timedelta(days=days)).date()
    rows = db.query(
        """
        SELECT trained_at, horizon_h,
               ROUND(cv_mae_occ, 1) AS mae_occ,
               ROUND(cv_r2, 3) AS r2,
               params_json
        FROM ai_model_runs
        WHERE model_type = 'ml' AND trained_at >= %s
        ORDER BY trained_at
        """,
        (since,), env=env,
    )
    result = []
    for r in rows:
        params = {}
        if r.get("params_json"):
            try:
                import json
                params = json.loads(r["params_json"]) if isinstance(r["params_json"], str) else r["params_json"]
            except Exception:
                pass
        label_parts = []
        if r.get("mae_occ") is not None:
            label_parts.append(f"MAE {float(r['mae_occ']):.1f}pp")
        if r.get("r2") is not None:
            label_parts.append(f"R² {float(r['r2']):.3f}")
        cv_folds = params.get("cv_folds")
        if cv_folds:
            label_parts.append(f"{cv_folds}-Fold CV")
        result.append({
            "date": r["trained_at"].strftime("%Y-%m-%d"),
            "horizon_h": r["horizon_h"],
            "label": " · ".join(label_parts) if label_parts else "Neues Modell",
        })
    return result
