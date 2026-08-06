"""Prognose-Job: alle 15 Minuten (:10/:25/:40/:55) oder per CLI.

Erzeugt fuer jedes aktive Parkhaus x Horizont x Modell (baseline, ml) eine
Prognose und schreibt sie idempotent (UNIQUE-Key) nach ai_predictions.
"""
import argparse
import logging
from datetime import timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

import config
import db
from core import data_access as da
from core.timeutil import floor_to_grid, now_local
from forecast import features
from forecast.baseline import BaselineModel
from forecast.ml_model import ForecastModel, QuantileModel, FullClassifier

logger = logging.getLogger(__name__)

HISTORY_DAYS = 8  # fuer 7d-Lag + 24h-Rolling
_artifact_cache: dict[str, object] = {}


def _load_artifact(stored: str, loader):
    model = _artifact_cache.get(stored)
    if model is None:
        path = config.artifact_file(stored)
        if not path.is_file():
            logger.error("Modelldatei fehlt: %s - Modell wird uebersprungen", path)
            return None
        model = loader(path)
        _artifact_cache[stored] = model
    return model


def _active_runs(env) -> dict:
    """{'ml': {h: run}, 'ml_q20': {h: run}, 'ml_full': {h: run}, 'baseline': run|None}"""
    rows = db.query("SELECT * FROM ai_model_runs WHERE is_active = 1", env=env)
    ml = {r["horizon_h"]: r for r in rows if r["model_type"] == "ml"}
    ml_q20 = {r["horizon_h"]: r for r in rows if r["model_type"] == "ml_q20"}
    ml_full = {r["horizon_h"]: r for r in rows if r["model_type"] == "ml_full"}
    baseline = next((r for r in rows if r["model_type"] == "baseline"), None)
    return {"ml": ml, "ml_q20": ml_q20, "ml_full": ml_full, "baseline": baseline}


def run(env: Optional[str] = None) -> dict:
    env = env or config.DEFAULT_ENV
    t0 = floor_to_grid(now_local())

    snapshots = da.latest_snapshots(env=env)
    if not snapshots:
        logger.warning("Keine frischen Messwerte - keine Prognosen")
        return {"predictions": 0}
    fresh = {(s["city"], s["pls_id"]): s for s in snapshots}

    grid = features.build_grid(env, t0 - timedelta(days=HISTORY_DAYS), t0 + timedelta(minutes=15))
    grid = features.add_series_features(grid)

    # Der Scanner schreibt nicht exakt auf dem Raster, und bei einer Stoerung
    # koennen die letzten Slots ganz fehlen: immer den juengsten Slot nehmen,
    # der tatsaechlich Messwerte hat. Wie alt der sein darf, begrenzt bereits
    # latest_snapshots (max_age_hours).
    with_data = grid[grid["occ"].notna() & (grid["slot"] <= t0)]
    if with_data.empty:
        logger.warning("Keine Rasterpunkte mit Messwerten - keine Prognosen")
        return {"predictions": 0}
    latest_slot = with_data["slot"].max()
    if latest_slot != t0:
        logger.info("Slot %s ohne Daten - verwende %s", t0, latest_slot)
        t0 = latest_slot.to_pydatetime()
    base_rows = with_data[with_data["slot"] == latest_slot]
    base_rows = base_rows[base_rows.apply(
        lambda r: (r["city"], r["pls_id"]) in fresh, axis=1)]
    if base_rows.empty:
        logger.warning("Kein Rasterpunkt fuer t0=%s - keine Prognosen", t0)
        return {"predictions": 0}

    weather = da.weather_range(env=env, start=t0, end=t0 + timedelta(hours=9))
    events = da.events_range(env=env, start=t0 - timedelta(hours=6), end=t0 + timedelta(hours=12))

    bias = da.bias_lookup(env=env)

    runs = _active_runs(env)
    baseline = None
    if runs["baseline"]:
        baseline = _load_artifact(runs["baseline"]["artifact_path"], BaselineModel.load)
    ml_models = {}
    q20_models = {}
    full_models = {}
    prior = pd.DataFrame()
    for h, run_row in runs["ml"].items():
        model = _load_artifact(run_row["artifact_path"], ForecastModel.load)
        if model is not None:
            ml_models[h] = (run_row["run_id"], model)
            prior = getattr(model, "prior", prior)
    for h, run_row in runs["ml_q20"].items():
        model = _load_artifact(run_row["artifact_path"], QuantileModel.load)
        if model is not None:
            q20_models[h] = model
    for h, run_row in runs["ml_full"].items():
        model = _load_artifact(run_row["artifact_path"], FullClassifier.load)
        if model is not None:
            full_models[h] = model
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

        preds: dict[str, tuple[Optional[int], pd.Series]] = {}
        if h in ml_models:
            run_id, model = ml_models[h]
            preds["ml"] = (run_id, model.predict(frame))
        if baseline is not None:
            b_run = runs["baseline"]["run_id"]
            preds["baseline"] = (b_run, baseline.predict_frame(frame))

        q20_series = q20_models[h].predict(frame) if h in q20_models else None
        full_series = full_models[h].predict_proba(frame) if h in full_models else None

        for model_type, (run_id, occ_series) in preds.items():
            for idx, row in frame.iterrows():
                occ = occ_series.loc[idx]
                if occ is None or pd.isna(occ):
                    continue
                total = int(row["total"])
                free = int(round((1 - float(occ)) * total))
                b = bias.get((row["city"], row["pls_id"], h), 0)
                if b and model_type == "ml":
                    free = free - round(b)
                free = max(0, min(free, total))

                free_q20 = None
                full_prob = None
                if model_type == "ml":
                    if q20_series is not None:
                        occ_q = float(q20_series.loc[idx])
                        free_q20 = max(0, min(total, int(round((1 - occ_q) * total))))
                    if full_series is not None:
                        full_prob = round(float(full_series.loc[idx]), 4)

                insert_rows.append((
                    t0, target, h, model_type, run_id, row["city"], row["pls_id"],
                    free, round(float(occ), 4), total, free_q20, full_prob,
                ))

    n = db.executemany(
        """
        INSERT INTO ai_predictions
            (created_at, target_time, horizon_h, model_type, run_id,
             city, pls_id, predicted_free, predicted_occ, total_at_pred,
             predicted_free_q20, predicted_full_prob)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            predicted_free = VALUES(predicted_free),
            predicted_occ = VALUES(predicted_occ),
            total_at_pred = VALUES(total_at_pred),
            predicted_free_q20 = VALUES(predicted_free_q20),
            predicted_full_prob = VALUES(predicted_full_prob),
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
