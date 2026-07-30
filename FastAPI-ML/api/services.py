"""Gemeinsame Service-Funktionen fuer API-Router und Chatbot."""
from datetime import datetime, timedelta
from pathlib import Path

import db
from core import data_access as da
from core.timeutil import now_local
from forecast.baseline import BaselineModel

_baseline_cache: dict[str, BaselineModel] = {}


def load_active_baseline(env: str) -> BaselineModel | None:
    rows = db.query(
        "SELECT artifact_path FROM ai_model_runs "
        "WHERE model_type = 'baseline' AND is_active = 1",
        env=env,
    )
    if not rows:
        return None
    path = rows[0]["artifact_path"]
    model = _baseline_cache.get(path)
    if model is None and Path(path).exists():
        model = BaselineModel.load(path)
        _baseline_cache[path] = model
    return model


def latest_prediction_slot(env: str, city: str | None = None) -> datetime | None:
    sql = "SELECT MAX(created_at) AS slot FROM ai_predictions"
    params: tuple = ()
    if city:
        sql += " WHERE city = %s"
        params = (city,)
    rows = db.query(sql, params, env=env)
    return rows[0]["slot"] if rows else None


def current_forecasts(env: str, city: str) -> dict:
    """Neuste Prognosen aller Haeuser einer Stadt, gruppiert pro Haus."""
    slot = latest_prediction_slot(env, city)
    mapping = {m["pls_id"]: m for m in da.get_mapping(env=env, city=city)}
    snapshots = {s["pls_id"]: s for s in da.latest_snapshots(env=env, city=city)}

    houses: dict[str, dict] = {}
    if slot:
        rows = db.query(
            """
            SELECT pls_id, horizon_h, model_type, predicted_free, predicted_occ,
                   target_time
            FROM ai_predictions
            WHERE city = %s AND created_at = %s
            """,
            (city, slot), env=env,
        )
        for r in rows:
            h = houses.setdefault(r["pls_id"], {"horizons": {}})
            hz = h["horizons"].setdefault(r["horizon_h"], {})
            hz[r["model_type"]] = {
                "free": r["predicted_free"],
                "occ": float(r["predicted_occ"]),
                "target_time": r["target_time"].isoformat(),
            }

    result = []
    for pls_id, snap in sorted(snapshots.items(), key=lambda kv: kv[1]["name"]):
        m = mapping.get(pls_id, {})
        entry = {
            "pls_id": pls_id,
            "name": snap["name"],
            "group": m.get("parking_group"),
            "free_now": snap["free"],
            "total": snap["total"],
            "fetch_ts": snap["fetch_ts"].isoformat(),
            "horizons": houses.get(pls_id, {}).get("horizons", {}),
        }
        result.append(entry)
    return {"city": city, "slot": slot.isoformat() if slot else None, "houses": result}


def house_detail(env: str, city: str, pls_id: str, hours: int = 24) -> dict:
    """Ist-Verlauf + Prognosepunkte fuer die Detailansicht (Chart)."""
    now = now_local()
    start = now - timedelta(hours=hours)
    hist = da.occupancy_history(env=env, start=start, city=city, pls_id=pls_id)
    actual = [
        {"ts": r.fetch_ts.isoformat(), "free": int(r.free), "total": int(r.total)}
        for r in hist.itertuples()
    ]

    # Pro (model, horizon, target_time) nur die neuste Prognose
    rows = db.query(
        """
        SELECT p.model_type, p.horizon_h, p.target_time, p.predicted_free
        FROM ai_predictions p
        JOIN (
            SELECT model_type, horizon_h, target_time, MAX(created_at) AS max_created
            FROM ai_predictions
            WHERE city = %s AND pls_id = %s AND target_time >= %s
            GROUP BY model_type, horizon_h, target_time
        ) m ON m.model_type = p.model_type AND m.horizon_h = p.horizon_h
           AND m.target_time = p.target_time AND m.max_created = p.created_at
        WHERE p.city = %s AND p.pls_id = %s
        ORDER BY p.target_time
        """,
        (city, pls_id, start, city, pls_id), env=env,
    )
    forecasts: dict = {}
    for r in rows:
        series = forecasts.setdefault(r["model_type"], {}).setdefault(r["horizon_h"], [])
        series.append({"ts": r["target_time"].isoformat(), "free": r["predicted_free"]})

    weather = da.weather_range(env=env, start=start, end=now + timedelta(hours=9), city=city)
    events = da.events_range(env=env, start=start, end=now + timedelta(hours=12), city=city)
    ev_list = []
    if not events.empty:
        for eid, g in events.groupby("event_id"):
            first = g.iloc[0]
            ev_list.append({
                "title": first["title"], "venue": first["venue"],
                "start": first["start_time"].isoformat(),
                "end": first["end_time"].isoformat(),
                "affects_this": bool((g["pls_id"] == pls_id).any()),
            })

    return {
        "city": city, "pls_id": pls_id, "actual": actual, "forecasts": forecasts,
        "weather": [
            {"ts": r.ts.isoformat(), "temperature": r.temperature,
             "precipitation": r.precipitation}
            for r in weather.itertuples()
        ],
        "events": ev_list,
    }


def best_parking(env: str, city: str, at: datetime | None = None,
                 min_free: int = 0, limit: int = 5) -> dict:
    """Parkhaus-Empfehlung fuer einen Zeitpunkt.

    Innerhalb des 8h-Fensters aus ai_predictions (neuste Prognose je Haus);
    weiter in der Zukunft ueber das Basismodell mit expliziter Einschraenkung.
    """
    now = now_local()
    at = at or now
    horizon_hours = (at - now).total_seconds() / 3600

    if horizon_hours <= 8.5:
        rows = db.query(
            """
            SELECT p.pls_id, p.predicted_free, p.predicted_occ, p.target_time,
                   p.total_at_pred, p.model_type
            FROM ai_predictions p
            JOIN (
                SELECT pls_id, model_type, MAX(created_at) AS max_created
                FROM ai_predictions
                WHERE city = %s AND target_time BETWEEN %s AND %s
                GROUP BY pls_id, model_type
            ) m ON m.pls_id = p.pls_id AND m.model_type = p.model_type
               AND m.max_created = p.created_at
            WHERE p.city = %s AND p.target_time BETWEEN %s AND %s
            """,
            (city, at - timedelta(minutes=45), at + timedelta(minutes=45),
             city, at - timedelta(minutes=45), at + timedelta(minutes=45)),
            env=env,
        )
        # ML bevorzugen, Baseline als Fallback pro Haus
        per_house: dict[str, dict] = {}
        for r in rows:
            cur = per_house.get(r["pls_id"])
            if cur is None or (cur["model_type"] == "baseline" and r["model_type"] == "ml"):
                per_house[r["pls_id"]] = r
        method = "prediction"
    else:
        baseline = load_active_baseline(env)
        per_house = {}
        if baseline:
            slot = at.replace(minute=at.minute - at.minute % 15, second=0, microsecond=0)
            for s in da.latest_snapshots(env=env, city=city, max_age_hours=24):
                occ = baseline.predict_one(city, s["pls_id"], slot)
                if occ is None:
                    continue
                total = int(s["total"])
                per_house[s["pls_id"]] = {
                    "pls_id": s["pls_id"],
                    "predicted_free": max(0, min(int(round((1 - occ) * total)), total)),
                    "predicted_occ": occ, "target_time": slot,
                    "total_at_pred": total, "model_type": "baseline",
                }
        method = "baseline_seasonal"

    snapshots = {s["pls_id"]: s for s in da.latest_snapshots(env=env, city=city, max_age_hours=24)}
    mae = {
        r["pls_id"]: float(r["mae"])
        for r in db.query(
            """
            SELECT pls_id, AVG(mae_free) AS mae
            FROM ai_accuracy_daily
            WHERE city = %s AND pls_id <> '' AND day >= %s
            GROUP BY pls_id
            """,
            (city, (now - timedelta(days=7)).date()), env=env,
        )
    }

    ranked = []
    for pls_id, r in per_house.items():
        snap = snapshots.get(pls_id)
        if snap is None:
            continue
        free = int(r["predicted_free"])
        if free < min_free:
            continue
        ranked.append({
            "pls_id": pls_id,
            "name": snap["name"],
            "predicted_free": free,
            "predicted_occ": round(float(r["predicted_occ"]), 3),
            "total": int(r["total_at_pred"] or snap["total"]),
            "target_time": r["target_time"].isoformat()
                if hasattr(r["target_time"], "isoformat") else str(r["target_time"]),
            "model_type": r["model_type"],
            "recent_mae_free": round(mae[pls_id], 1) if pls_id in mae else None,
        })
    ranked.sort(key=lambda x: x["predicted_free"], reverse=True)
    return {"city": city, "at": at.isoformat(), "method": method,
            "recommendations": ranked[:limit]}
