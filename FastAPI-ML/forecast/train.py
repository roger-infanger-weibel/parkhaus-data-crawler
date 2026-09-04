"""Trainings-Pipeline: taeglich 03:30 per Scheduler oder manuell per CLI.

    python -m forecast.train --env test [--days 120]

Trainiert 4 globale ML-Modelle (1h/2h/4h/8h) plus das Basismodell, bewertet
auf einem zeitbasierten Holdout (letzte 14 Tage) und registriert die Laeufe
in ai_model_runs. Ein neuer ML-Lauf wird nur aktiviert, wenn er nicht mehr
als 10 % schlechter ist als der aktuell aktive (Schutz vor Datenausfaellen).
"""
import argparse
import gc
import json
import logging
from pathlib import Path
from datetime import timedelta
from typing import Optional

import numpy as np

import config
import db
from core import data_access as da
from core.identity import build_mapping
from core.timeutil import now_local
from forecast import features
from forecast.baseline import BaselineModel
from forecast.ml_model import ForecastModel, QuantileModel, FullClassifier, ResidualModel, ResidualStore

logger = logging.getLogger(__name__)

TRAIN_DAYS = config.TRAIN_DAYS
HOLDOUT_DAYS = 14
CV_FOLDS = 4
CV_FOLD_DAYS = 14
BASELINE_WEEKS = 8
ACTIVATION_TOLERANCE = 1.10  # neuer Lauf darf max. 10% schlechter sein
KEEP_ARTIFACTS = 7


def _mae_metrics(pred_occ, frame) -> tuple[float, float]:
    """(MAE in freien Plaetzen, MAE in Belegungs-Prozentpunkten)."""
    err_occ = np.abs(np.asarray(pred_occ, dtype=float) - frame["target"].to_numpy(dtype=float))
    mask = ~np.isnan(err_occ)
    err_occ = err_occ[mask]
    totals = frame["total"].to_numpy(dtype=float)[mask]
    if len(err_occ) == 0:
        return float("nan"), float("nan")
    return float(np.mean(err_occ * totals)), float(np.mean(err_occ) * 100)


def _r2(pred_occ, frame) -> float:
    """R² (Bestimmtheitsmass) auf der Belegungsquote."""
    y = frame["target"].to_numpy(dtype=float)
    p = np.asarray(pred_occ, dtype=float)
    mask = ~(np.isnan(y) | np.isnan(p))
    y, p = y[mask], p[mask]
    if len(y) < 2:
        return float("nan")
    ss_res = np.sum((y - p) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    return float(1 - ss_res / ss_tot) if ss_tot > 0 else float("nan")


def _insert_run(env, model_type, horizon_h, now, n_rows, train_from, train_to,
                mae_free, mae_occ, params, artifact_path, r2=None) -> int:
    conn = db.get_conn(env)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO ai_model_runs
                    (model_type, horizon_h, trained_at, train_rows, train_from,
                     train_to, cv_mae_free, cv_mae_occ, cv_r2,
                     params_json, artifact_path)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (model_type, horizon_h, now, n_rows, train_from, train_to,
                 None if mae_free is None or np.isnan(mae_free) else round(mae_free, 3),
                 None if mae_occ is None or np.isnan(mae_occ) else round(mae_occ, 3),
                 None if r2 is None or np.isnan(r2) else round(r2, 4),
                 # nur der Dateiname - so funktionieren Modelle auch, wenn sie
                 # auf einer anderen Maschine trainiert und kopiert wurden
                 json.dumps(params), Path(artifact_path).name),
            )
            run_id = cursor.lastrowid
        conn.commit()
        return run_id
    finally:
        conn.close()


def _vergleichswert(env, horizon_h, hold_f) -> Optional[float]:
    """MAE des aktiven Modells auf DEMSELBEN Holdout wie der neue Lauf.

    Der in ai_model_runs gespeicherte cv_mae_occ taugt nicht zum Vergleich:
    er wurde auf dem Holdout von damals gemessen. Ist die juengere Periode
    schwerer vorherzusagen, faellt jedes neue Modell durch - und ein altes
    Modell mit einem guenstigen Testzeitraum blockiert alle Nachfolger
    dauerhaft. Deshalb wird das aktive Modell hier auf den aktuellen Holdout
    losgelassen und erst dann verglichen.

    None bedeutet: kein aktives Modell oder dessen Datei fehlt - dann gibt es
    nichts zu verteidigen und der neue Lauf wird aktiviert.
    """
    rows = db.query(
        "SELECT artifact_path FROM ai_model_runs "
        "WHERE model_type = 'ml' AND horizon_h = %s AND is_active = 1",
        (horizon_h,), env=env,
    )
    if not rows:
        return None
    datei = config.artifact_file(rows[0]["artifact_path"] or "")
    if not datei.is_file():
        logger.info("h=%s: Datei des aktiven Modells fehlt (%s) - neuer Lauf "
                    "wird aktiviert", horizon_h, datei)
        return None
    try:
        _, mae_occ = _mae_metrics(ForecastModel.load(datei).predict(hold_f), hold_f)
    except Exception:
        logger.warning("h=%s: aktives Modell nicht auswertbar - neuer Lauf "
                       "wird aktiviert", horizon_h, exc_info=True)
        return None
    return None if np.isnan(mae_occ) else mae_occ


def _activate(env, run_id, model_type, horizon_h, new_mae_occ,
              alt_mae_occ: Optional[float] = None) -> bool:
    """Lauf aktivieren, ausser er ist deutlich schlechter als der aktive."""
    horizon_cond = "horizon_h = %s" if horizon_h is not None else "horizon_h IS NULL"
    params = [model_type] + ([horizon_h] if horizon_h is not None else [])
    if (alt_mae_occ is not None and not np.isnan(new_mae_occ)
            and new_mae_occ > alt_mae_occ * ACTIVATION_TOLERANCE):
        logger.warning(
            "Lauf %s (%s h=%s) NICHT aktiviert: MAE %.3f > %.3f * %.2f "
            "(beide auf demselben Holdout gemessen)",
            run_id, model_type, horizon_h, new_mae_occ, alt_mae_occ,
            ACTIVATION_TOLERANCE,
        )
        return False
    db.execute(
        f"UPDATE ai_model_runs SET is_active = 0 "
        f"WHERE model_type = %s AND {horizon_cond} AND is_active = 1",
        tuple(params), env=env,
    )
    db.execute("UPDATE ai_model_runs SET is_active = 1 WHERE run_id = %s",
               (run_id,), env=env)
    return True


def _active_artifact_names() -> Optional[set]:
    """Dateinamen aller aktiven Laeufe - aus BEIDEN Umgebungen.

    models_store/ ist ein gemeinsamer Ablageort; welche Datei zu prod und
    welche zu test gehoert, steht nur in der jeweiligen Datenbank. Beim
    Aufraeumen darf deshalb keine Datei verschwinden, auf die die andere
    Umgebung noch zeigt. Ist eine der Datenbanken nicht lesbar, wird gar
    nicht aufgeraeumt (None).
    """
    namen = set()
    for env in ("prod", "test"):
        try:
            rows = db.query(
                "SELECT artifact_path FROM ai_model_runs WHERE is_active = 1", env=env)
        except Exception:
            logger.warning("Aktive Laeufe von '%s' nicht lesbar - Aufraeumen "
                           "wird uebersprungen", env)
            return None
        namen.update(Path(r["artifact_path"]).name for r in rows if r["artifact_path"])
    return namen


def _cleanup_artifacts(env: str) -> None:
    """Alte Artefakte dieser Umgebung entfernen, aktive immer behalten."""
    geschuetzt = _active_artifact_names()
    if geschuetzt is None:
        return
    prefixe = ([f"ml_h{h}_{env}_" for h in config.HORIZONS]
                + [f"ml_q20_h{h}_{env}_" for h in config.HORIZONS]
                + [f"ml_full_h{h}_{env}_" for h in config.HORIZONS]
                + [f"residual_h{h}_{env}_" for h in config.HORIZONS]
                + [f"baseline_{env}_"])
    for prefix in prefixe:
        files = sorted(config.MODELS_DIR.glob(prefix + "*.joblib"), reverse=True)
        for old in files[KEEP_ARTIFACTS:]:
            if old.name not in geschuetzt:
                old.unlink(missing_ok=True)


def run(env: Optional[str] = None, days: int = TRAIN_DAYS) -> dict:
    env = env or config.DEFAULT_ENV
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    now = now_local().replace(second=0, microsecond=0)
    stamp = now.strftime("%Y%m%d_%H%M")
    start = now - timedelta(days=days)
    holdout_start = now - timedelta(days=HOLDOUT_DAYS)

    build_mapping(env)

    logger.info("Lade Belegungsdaten seit %s ...", start)
    grid = features.build_grid(env, start, now)
    if grid.empty:
        raise RuntimeError("Keine Belegungsdaten im Trainingsfenster")
    logger.info("Raster gebaut: %d Zeilen - berechne Lag-Features ...", len(grid))
    grid = features.add_series_features(grid)

    logger.info("Lade Wetter und Events ...")
    weather = da.weather_range(env=env, start=start, end=now + timedelta(hours=9))
    events = da.events_range(env=env, start=start, end=now + timedelta(hours=9))
    # Prior nur aus dem Trainingsteil (kein Leakage ins Holdout)
    prior = features.compute_prior(grid[grid["slot"] < holdout_start])

    # Basismodell: letzte 8 Wochen des Trainingsteils
    logger.info("Trainiere Basismodell ...")
    baseline = BaselineModel().fit(
        grid[(grid["slot"] < holdout_start)
             & (grid["slot"] >= holdout_start - timedelta(weeks=BASELINE_WEEKS))]
    )

    results: dict = {}
    baseline_metrics: dict = {}
    for h in config.HORIZONS:
        logger.info("Horizont %dh: baue Feature-Frame ...", h)
        frame = features.build_horizon_frame(grid, h, weather, events, prior)
        train_f = frame[frame["slot"] < holdout_start]
        hold_f = frame[frame["slot"] >= holdout_start]
        if train_f.empty or hold_f.empty:
            logger.warning("Horizont %dh: zu wenig Daten, uebersprungen", h)
            continue

        # Rolling Cross-Validation auf dem Trainingsteil
        cv_maes_free, cv_maes_occ, cv_r2s = [], [], []
        train_slots = sorted(train_f["slot"].unique())
        for fold in range(CV_FOLDS):
            fold_end = train_slots[-1] - timedelta(days=fold * CV_FOLD_DAYS)
            fold_start = fold_end - timedelta(days=CV_FOLD_DAYS)
            if fold_start < train_slots[0]:
                break
            cv_train = train_f[train_f["slot"] < fold_start]
            cv_val = train_f[(train_f["slot"] >= fold_start) & (train_f["slot"] < fold_end)]
            if cv_train.empty or cv_val.empty:
                continue
            cv_model = ForecastModel(h).fit(cv_train)
            cv_pred = cv_model.predict(cv_val)
            mf, mo = _mae_metrics(cv_pred, cv_val)
            rv = _r2(cv_pred, cv_val)
            if not np.isnan(mo):
                cv_maes_free.append(mf)
                cv_maes_occ.append(mo)
                cv_r2s.append(rv)
            del cv_model
        cv_mae_free_avg = float(np.mean(cv_maes_free)) if cv_maes_free else float("nan")
        cv_mae_occ_avg = float(np.mean(cv_maes_occ)) if cv_maes_occ else float("nan")
        cv_r2_avg = float(np.mean(cv_r2s)) if cv_r2s else float("nan")
        logger.info("Horizont %dh: Rolling-CV (%d Folds) MAE %.2f pp, R² %.4f",
                    h, len(cv_maes_occ), cv_mae_occ_avg, cv_r2_avg)

        # Finales Modell auf allen Trainingsdaten
        logger.info("Horizont %dh: trainiere auf %d Zeilen ...", h, len(train_f))
        model = ForecastModel(h).fit(train_f)
        model.prior = prior
        pred_occ = model.predict(hold_f)
        mae_free, mae_occ = _mae_metrics(pred_occ, hold_f)
        r2_val = _r2(pred_occ, hold_f)

        b_free, b_occ = _mae_metrics(
            baseline.predict_frame(hold_f).to_numpy(dtype=float), hold_f)
        baseline_metrics[h] = {"mae_free": b_free, "mae_occ": b_occ}

        # Das bisherige Modell auf demselben Holdout bewerten - nur so ist der
        # Vergleich fair (siehe _vergleichswert)
        alt_mae_occ = _vergleichswert(env, h, hold_f)
        if alt_mae_occ is not None:
            logger.info("Horizont %dh: bisheriges Modell auf demselben Holdout: "
                        "%.2f pp (neu: %.2f pp)", h, alt_mae_occ, mae_occ)

        # Feature Importance (Top 15 fuer params_json)
        fi = getattr(model, "feature_importance", {})
        fi_top = dict(sorted(fi.items(), key=lambda x: x[1], reverse=True)[:15])
        if fi_top:
            logger.info("Horizont %dh Feature Importance (Top 5): %s", h,
                        ", ".join(f"{k}={v:.0f}" for k, v in list(fi_top.items())[:5]))

        artifact = config.MODELS_DIR / f"ml_h{h}_{env}_{stamp}.joblib"
        model.save(artifact)
        run_id = _insert_run(
            env, "ml", h, now, len(train_f), train_f["slot"].min().to_pydatetime(),
            train_f["slot"].max().to_pydatetime(), mae_free, mae_occ,
            {"library": model.library, "features": features.FEATURE_COLUMNS,
             "holdout_days": HOLDOUT_DAYS,
             "cv_folds": len(cv_maes_occ),
             "cv_mae_occ_avg": round(cv_mae_occ_avg, 2) if not np.isnan(cv_mae_occ_avg) else None,
             "cv_r2_avg": round(cv_r2_avg, 4) if not np.isnan(cv_r2_avg) else None,
             "feature_importance": fi_top},
            artifact, r2=r2_val,
        )
        activated = _activate(env, run_id, "ml", h, mae_occ, alt_mae_occ)
        results[h] = {
            "run_id": run_id, "activated": activated,
            "ml_mae_free": round(mae_free, 2), "ml_mae_occ_pp": round(mae_occ, 2),
            "ml_r2": round(r2_val, 4) if not np.isnan(r2_val) else None,
            "cv_folds": len(cv_maes_occ),
            "cv_mae_occ_pp": round(cv_mae_occ_avg, 2) if not np.isnan(cv_mae_occ_avg) else None,
            "cv_r2": round(cv_r2_avg, 4) if not np.isnan(cv_r2_avg) else None,
            "vorheriges_modell_occ_pp": (round(alt_mae_occ, 2)
                                         if alt_mae_occ is not None else None),
            "baseline_mae_free": round(b_free, 2), "baseline_mae_occ_pp": round(b_occ, 2),
            "rows_train": len(train_f), "rows_holdout": len(hold_f),
        }
        logger.info("Horizont %dh: ML MAE %.2f Plaetze / %.2f pp  R²=%.4f - "
                    "Baseline %.2f / %.2f",
                    h, mae_free, mae_occ, r2_val, b_free, b_occ)

        # Quantil-Modell (pessimistisches 20%-Quantil)
        logger.info("Horizont %dh: trainiere Quantil-Modell ...", h)
        q_model = QuantileModel(h).fit(train_f)
        q_artifact = config.MODELS_DIR / f"ml_q20_h{h}_{env}_{stamp}.joblib"
        q_model.save(q_artifact)
        q_mae_free, q_mae_occ = _mae_metrics(q_model.predict(hold_f), hold_f)
        q_run = _insert_run(
            env, "ml_q20", h, now, len(train_f), train_f["slot"].min().to_pydatetime(),
            train_f["slot"].max().to_pydatetime(), q_mae_free, q_mae_occ,
            {"library": q_model.library, "alpha": 0.2}, q_artifact,
        )
        _activate(env, q_run, "ml_q20", h, float("nan"))

        # Voll-Klassifikator
        logger.info("Horizont %dh: trainiere Voll-Klassifikator ...", h)
        clf = FullClassifier(h).fit(train_f)
        c_artifact = config.MODELS_DIR / f"ml_full_h{h}_{env}_{stamp}.joblib"
        clf.save(c_artifact)
        c_run = _insert_run(
            env, "ml_full", h, now, len(train_f), train_f["slot"].min().to_pydatetime(),
            train_f["slot"].max().to_pydatetime(), None, None,
            {"library": clf.library, "threshold": FullClassifier.THRESHOLD}, c_artifact,
        )
        _activate(env, c_run, "ml_full", h, float("nan"))

        # Residual-Modelle pro Parkhaus
        logger.info("Horizont %dh: trainiere Residual-Modelle ...", h)
        global_pred_train = model.predict(train_f)
        residuals_train = global_pred_train - train_f["target"].astype(float)
        train_f["pls_key"] = train_f["city"] + "::" + train_f["pls_id"]
        res_models = {}
        for pls_key, grp in train_f.groupby("pls_key"):
            if len(grp) < ResidualModel.MIN_ROWS:
                continue
            try:
                rm = ResidualModel().fit(grp, residuals_train.loc[grp.index])
                res_models[pls_key] = rm
            except Exception:
                logger.warning("Residual-Modell fuer %s fehlgeschlagen", pls_key,
                               exc_info=True)
        res_store = ResidualStore(res_models)
        res_artifact = config.MODELS_DIR / f"residual_h{h}_{env}_{stamp}.joblib"
        res_store.save(res_artifact)
        res_run = _insert_run(
            env, "ml_residual", h, now, len(train_f),
            train_f["slot"].min().to_pydatetime(),
            train_f["slot"].max().to_pydatetime(), None, None,
            {"n_parkhaus": len(res_models),
             "min_rows": ResidualModel.MIN_ROWS},
            res_artifact,
        )
        _activate(env, res_run, "ml_residual", h, float("nan"))
        logger.info("Horizont %dh: %d Residual-Modelle trainiert", h, len(res_models))

        # Speicher freigeben, bevor der naechste Horizont-Frame entsteht
        del frame, train_f, hold_f, model, q_model, clf, res_store
        gc.collect()

    # Basismodell als eigener Lauf (horizon NULL), immer aktiv
    b_artifact = config.MODELS_DIR / f"baseline_{env}_{stamp}.joblib"
    baseline.save(b_artifact)
    avg_free = float(np.mean([m["mae_free"] for m in baseline_metrics.values()]))
    avg_occ = float(np.mean([m["mae_occ"] for m in baseline_metrics.values()]))
    b_run = _insert_run(
        env, "baseline", None, now, len(grid), start, now, avg_free, avg_occ,
        {"weeks": BASELINE_WEEKS, "per_horizon": baseline_metrics}, b_artifact,
    )
    _activate(env, b_run, "baseline", None, float("nan"))
    results["baseline_run_id"] = b_run

    _cleanup_artifacts(env)
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", choices=["prod", "test"], default=None)
    parser.add_argument("--days", type=int, default=TRAIN_DAYS)
    args = parser.parse_args()
    out = run(args.env, args.days)
    print(json.dumps(out, indent=2, default=str))
