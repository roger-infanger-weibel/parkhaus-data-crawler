"""Prognose-Job: alle 15 Minuten (:10/:25/:40/:55) oder per CLI.

Erzeugt fuer jedes aktive Parkhaus x Horizont x Modell (baseline, ml) eine
Prognose und schreibt sie idempotent (UNIQUE-Key) nach ai_predictions.
"""
import argparse
import logging
from datetime import timedelta
from pathlib import Path

import pandas as pd

import config
import db
from core import data_access as da
from core.timeutil import floor_to_grid, now_local
from forecast import features
from forecast.baseline import BaselineModel
from forecast.ml_model import ForecastModel

logger = logging.getLogger(__name__)

HISTORY_DAYS = 8  # fuer 7d-Lag + 24h-Rolling
_artifact_cache: dict[str, object] = {}


def _load_artifact(path: str, loader):
    model = _artifact_cache.get(path)
    if model is None and Path(path).exists():
        model = loader(path)
        _artifact_cache[path] = model
    return model


def _active_runs(env) -> dict:
    """{'ml': {horizon: run_row}, 'baseline': run_row|None}"""
    rows = db.query("SELECT * FROM ai_model_runs WHERE is_active = 1", env=env)
    ml = {r["horizon_h"]: r for r in rows if r["model_type"] == "ml"}
    baseline = next((r for r in rows if r["model_type"] == "baseline"), None)
    return {"ml": ml, "baseline": baseline}


def run(env: str | None = None) -> dict:
    env = env or config.DEFAULT_ENV
    t0 = floor_to_grid(now_local())

    snapshots = da.latest_snapshots(env=env)
    if not snapshots:
        logger.warning("Keine frischen Messwerte - keine Prognosen")
        return {"predictions": 0}
    fresh = {(s["city"], s["pls_id"]): s for s in snapshots}

    grid = features.build_grid(env, t0 - timedelta(days=HISTORY_DAYS), t0 + timedelta(minutes=15))
    grid = features.add_series_features(grid)

    # Der Scanner schreibt nicht exakt auf dem Raster (Offset kann driften):
    # falls der aktuelle Slot noch leer ist, den letzten Slot mit Daten nehmen.
    base_rows = grid[grid["slot"] == t0]
    if base_rows.empty or base_rows["occ"].isna().all():
        t0 = t0 - timedelta(minutes=15)
        base_rows = grid[grid["slot"] == t0]
    base_rows = base_rows[base_rows["occ"].notna()]
    base_rows = base_rows[base_rows.apply(
        lambda r: (r["city"], r["pls_id"]) in fresh, axis=1)]
    if base_rows.empty:
        logger.warning("Kein Rasterpunkt fuer t0=%s - keine Prognosen", t0)
        return {"predictions": 0}

    weather = da.weather_range(env=env, start=t0, end=t0 + timedelta(hours=9))
    events = da.events_range(env=env, start=t0 - timedelta(hours=6), end=t0 + timedelta(hours=12))

    runs = _active_runs(env)
    baseline = None
    if runs["baseline"]:
        baseline = _load_artifact(runs["baseline"]["artifact_path"], BaselineModel.load)
    ml_models = {}
    prior = pd.DataFrame()
    for h, run_row in runs["ml"].items():
        model = _load_artifact(run_row["artifact_path"], ForecastModel.load)
        if model is not None:
            ml_models[h] = (run_row["run_id"], model)
            prior = getattr(model, "prior", prior)
    if not ml_models:
        logger.warning("Kein aktives ML-Modell - nur Baseline-Prognosen")
    if baseline is None:
        logger.warning("Kein aktives Basismodell - nur ML-Prognosen")

    insert_rows = []
    for h in config.HORIZONS:
        # Lags/Rollings stehen schon auf base_rows (add_series_features auf dem
        # vollen Grid); build_horizon_frame ergaenzt nur Kalender/Wetter/Events.
        frame = features.build_horizon_frame(
            base_rows, h, weather, events, prior, require_target=False,
        )
        if frame.empty:
            continue
        target = t0 + timedelta(hours=h)

        preds: dict[str, tuple[int | None, pd.Series]] = {}
        if h in ml_models:
            run_id, model = ml_models[h]
            preds["ml"] = (run_id, model.predict(frame))
        if baseline is not None:
            b_run = runs["baseline"]["run_id"]
            preds["baseline"] = (b_run, baseline.predict_frame(frame))

        for model_type, (run_id, occ_series) in preds.items():
            for idx, row in frame.iterrows():
                occ = occ_series.loc[idx]
                if occ is None or pd.isna(occ):
                    continue
                total = int(row["total"])
                free = int(round((1 - float(occ)) * total))
                free = max(0, min(free, total))
                insert_rows.append((
                    t0, target, h, model_type, run_id, row["city"], row["pls_id"],
                    free, round(float(occ), 4), total,
                ))

    n = db.executemany(
        """
        INSERT INTO ai_predictions
            (created_at, target_time, horizon_h, model_type, run_id,
             city, pls_id, predicted_free, predicted_occ, total_at_pred)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            predicted_free = VALUES(predicted_free),
            predicted_occ = VALUES(predicted_occ),
            total_at_pred = VALUES(total_at_pred),
            run_id = VALUES(run_id)
        """,
        insert_rows,
        env=env,
    )
    logger.info("t0=%s: %d Prognose-Zeilen geschrieben", t0, len(insert_rows))
    return {"t0": t0, "predictions": len(insert_rows), "affected": n}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", choices=["prod", "test"], default=None)
    args = parser.parse_args()
    print(run(args.env))
