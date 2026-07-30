"""Historische Prognosen simulieren, damit das Genauigkeits-Dashboard sofort
Daten zeigt, statt tagelang auf reifende Prognosen zu warten.

    python -m scripts.backfill_predictions --env test --days 7 [--step 60]

Leak-frei fuer das ML-Modell, solange --days <= 14 (Holdout-Fenster des
Trainings): die Features je Slot stammen ausschliesslich aus Daten vor dem
jeweiligen t0; das aktive Modell hat diese Tage nie im Training gesehen.
Danach laeuft der Evaluator, bis alle gereiften Prognosen bewertet sind.
"""
import argparse
import logging
from datetime import timedelta

import pandas as pd

import config
import db
from core import data_access as da
from core.timeutil import floor_to_grid, now_local
from forecast import evaluate, features
from forecast.baseline import BaselineModel
from forecast.ml_model import ForecastModel
from forecast.predict import _active_runs, _load_artifact

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CHUNK = 5000


def run(env: str, days: int, step_minutes: int) -> None:
    now = floor_to_grid(now_local())
    start = now - timedelta(days=days)

    runs = _active_runs(env)
    baseline = (_load_artifact(runs["baseline"]["artifact_path"], BaselineModel.load)
                if runs["baseline"] else None)
    ml_models = {}
    prior = pd.DataFrame()
    for h, run_row in runs["ml"].items():
        model = _load_artifact(run_row["artifact_path"], ForecastModel.load)
        if model is not None:
            ml_models[h] = (run_row["run_id"], model)
            prior = getattr(model, "prior", prior)
    if not ml_models and baseline is None:
        raise RuntimeError("Keine aktiven Modelle - zuerst forecast.train ausfuehren")

    logger.info("Lade Grid %s bis %s ...", start - timedelta(days=8), now)
    grid = features.build_grid(env, start - timedelta(days=8), now)
    grid = features.add_series_features(grid)
    weather = da.weather_range(env=env, start=start, end=now + timedelta(hours=9))
    events = da.events_range(env=env, start=start, end=now + timedelta(hours=9))

    # nur Slots im Backfill-Fenster auf dem gewuenschten Raster
    in_window = grid[(grid["slot"] >= start)
                     & (grid["slot"].dt.minute % 60 < 15)
                     & ((grid["slot"] - start).dt.total_seconds() / 60
                        % step_minutes < 15)]

    insert_rows = []
    for h in config.HORIZONS:
        frame = features.build_horizon_frame(
            in_window, h, weather, events, prior, require_target=False)
        frame = frame.dropna(subset=["occ_now"])
        if frame.empty:
            continue

        preds = {}
        if h in ml_models:
            run_id, model = ml_models[h]
            preds["ml"] = (run_id, model.predict(frame))
        if baseline is not None:
            preds["baseline"] = (runs["baseline"]["run_id"],
                                 baseline.predict_frame(frame))

        for model_type, (run_id, occ_series) in preds.items():
            for idx, row in frame.iterrows():
                occ = occ_series.loc[idx]
                if occ is None or pd.isna(occ):
                    continue
                total = int(row["total"])
                free = max(0, min(int(round((1 - float(occ)) * total)), total))
                insert_rows.append((
                    row["slot"].to_pydatetime(),
                    row["target_slot"].to_pydatetime(), h, model_type, run_id,
                    row["city"], row["pls_id"], free, round(float(occ), 4), total,
                ))
        logger.info("Horizont %dh: %d Zeilen vorbereitet (kumuliert)", h, len(insert_rows))

    sql = """
        INSERT INTO ai_predictions
            (created_at, target_time, horizon_h, model_type, run_id,
             city, pls_id, predicted_free, predicted_occ, total_at_pred)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE predicted_free = VALUES(predicted_free)
    """
    for i in range(0, len(insert_rows), CHUNK):
        db.executemany(sql, insert_rows[i:i + CHUNK], env=env)
        logger.info("Eingefuegt: %d / %d", min(i + CHUNK, len(insert_rows)), len(insert_rows))

    logger.info("Evaluiere gereifte Prognosen ...")
    while True:
        result = evaluate.run(env)
        if result["evaluated"] + result["unmatched"] == 0:
            break
    logger.info("Backfill abgeschlossen")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", choices=["prod", "test"], default=None)
    parser.add_argument("--days", type=int, default=7,
                        help="max. 14 (Holdout) fuer leak-freie ML-Werte")
    parser.add_argument("--step", type=int, default=60, dest="step_minutes",
                        help="Abstand der simulierten Prognosezeitpunkte in Minuten")
    args = parser.parse_args()
    run(args.env or config.DEFAULT_ENV, args.days, args.step_minutes)
