"""Evaluations-Job: matcht gereifte Prognosen gegen Ist-Werte.

Laeuft alle 15 Minuten (:13/:28/:43/:58). Ist-Wert = naechstgelegener
Messwert innerhalb von +/-20 Minuten um target_time. Ohne Treffer wird die
Zeile als 'nicht auswertbar' markiert (evaluated_at gesetzt, actual_free NULL)
und fliesst nicht in die Metriken ein. Danach werden die Tagesaggregate
(ai_accuracy_daily) fuer die betroffenen Tage neu berechnet.
"""
import argparse
import logging
from bisect import bisect_left
from datetime import timedelta
from typing import Optional

import config
import db
from core.timeutil import now_local

logger = logging.getLogger(__name__)

TOLERANCE = timedelta(minutes=20)
BATCH_LIMIT = 20000


def _nearest(actuals: list[tuple], target) -> Optional[tuple]:
    """Naechster (fetch_ts, free, total)-Eintrag innerhalb der Toleranz."""
    if not actuals:
        return None
    times = [a[0] for a in actuals]
    i = bisect_left(times, target)
    best = None
    for j in (i - 1, i):
        if 0 <= j < len(actuals):
            diff = abs((actuals[j][0] - target).total_seconds())
            if best is None or diff < best[0]:
                best = (diff, actuals[j])
    if best and best[0] <= TOLERANCE.total_seconds():
        return best[1]
    return None


def _rebuild_daily(env, days: set) -> None:
    """Tagesaggregate fuer die betroffenen Tage neu berechnen."""
    for day in sorted(days):
        for scope_cols, scope_vals in (
            ("city, pls_id", None),          # pro Haus
            ("city, ''", None),              # pro Stadt
            ("'', ''", None),                # global
        ):
            db.execute(
                f"""
                REPLACE INTO ai_accuracy_daily
                    (day, city, pls_id, model_type, horizon_h, n,
                     mae_free, mae_occ, rmse_free, bias_free)
                SELECT DATE(target_time), {scope_cols}, model_type, horizon_h,
                       COUNT(*),
                       AVG(abs_err_free),
                       AVG(abs_err_occ) * 100,
                       SQRT(AVG(POW(predicted_free - actual_free, 2))),
                       AVG(predicted_free - actual_free)
                FROM ai_predictions
                WHERE actual_free IS NOT NULL AND DATE(target_time) = %s
                GROUP BY DATE(target_time), {scope_cols}, model_type, horizon_h
                """,
                (day,),
                env=env,
            )


def run(env: Optional[str] = None) -> dict:
    env = env or config.DEFAULT_ENV
    now = now_local()
    pending = db.query(
        """
        SELECT id, city, pls_id, target_time, predicted_free, predicted_occ,
               total_at_pred
        FROM ai_predictions
        WHERE evaluated_at IS NULL AND target_time <= %s
        ORDER BY target_time
        LIMIT %s
        """,
        (now - timedelta(minutes=5), BATCH_LIMIT),
        env=env,
    )
    if not pending:
        return {"evaluated": 0, "unmatched": 0}

    # Ist-Werte pro Stadt in einem Rutsch laden
    lo = min(p["target_time"] for p in pending) - TOLERANCE
    hi = max(p["target_time"] for p in pending) + TOLERANCE
    cities = sorted({p["city"] for p in pending})
    actuals: dict[tuple, list] = {}
    for city in cities:
        rows = db.query(
            """
            SELECT id AS pls_id, fetch_ts, free, total
            FROM pls_fetch_current
            WHERE city = %s AND fetch_ts BETWEEN %s AND %s
            ORDER BY fetch_ts
            """,
            (city, lo, hi),
            env=env,
        )
        for r in rows:
            actuals.setdefault((city, r["pls_id"]), []).append(
                (r["fetch_ts"], r["free"], r["total"]))

    updates, unmatched, days = [], [], set()
    for p in pending:
        hit = _nearest(actuals.get((p["city"], p["pls_id"]), []), p["target_time"])
        if hit is None:
            unmatched.append((now, p["id"]))
            continue
        fetch_ts, actual_free, actual_total = hit
        total = actual_total if actual_total else p["total_at_pred"]
        actual_occ = None
        abs_err_occ = None
        if total:
            actual_occ = min(max((total - actual_free) / total, 0.0), 1.0)
            abs_err_occ = round(abs(float(p["predicted_occ"]) - actual_occ), 4)
        updates.append((
            actual_free, fetch_ts,
            abs(p["predicted_free"] - actual_free), abs_err_occ, now, p["id"],
        ))
        days.add(p["target_time"].date())

    db.executemany(
        """
        UPDATE ai_predictions
        SET actual_free = %s, actual_ts = %s, abs_err_free = %s,
            abs_err_occ = %s, evaluated_at = %s
        WHERE id = %s
        """,
        updates, env=env,
    )
    db.executemany(
        "UPDATE ai_predictions SET evaluated_at = %s WHERE id = %s",
        unmatched, env=env,
    )
    _rebuild_daily(env, days)
    logger.info("Evaluiert: %d, nicht auswertbar: %d, Tage: %s",
                len(updates), len(unmatched), sorted(days))
    return {"evaluated": len(updates), "unmatched": len(unmatched)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", choices=["prod", "test"], default=None)
    args = parser.parse_args()
    print(run(args.env))
