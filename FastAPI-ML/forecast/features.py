"""Feature-Engineering - identischer Code-Pfad fuer Training und Prognose.

Ziel der Modelle ist die Belegungsquote occ = (total - free) / total in [0, 1];
sie macht ein globales Modell ueber Haeuser sehr unterschiedlicher Groesse
moeglich. Rueckrechnung in freie Plaetze ueber das letzte bekannte total.
"""
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from core import data_access as da

SLOTS_PER_HOUR = 4
LAGS = {  # Spaltenname -> Verschiebung in 15-Min-Slots (bezogen auf t0)
    "occ_1h_ago": 4,
    "occ_2h_ago": 8,
    "occ_24h_ago": 96,
    "occ_7d_ago": 672,
}

# Spalten, die das ML-Modell als Eingabe sieht
FEATURE_COLUMNS = [
    "hour", "quarter", "weekday", "is_weekend", "month",
    "sin_hour", "cos_hour", "sin_weekday", "cos_weekday",
    "occ_now", "occ_1h_ago", "occ_2h_ago", "occ_24h_ago", "occ_7d_ago",
    "delta_occ_1h", "occ_mean_3h", "occ_mean_24h", "occ_std_24h",
    "prior_occ",
    "temperature", "precipitation", "is_raining",
    "event_active", "event_soon", "event_bonus",
    "log_total",
    "city", "pls_key",
]
CATEGORICAL_COLUMNS = ["city", "pls_key"]


def build_grid(env: Optional[str], start: datetime, end: datetime,
               city: Optional[str] = None, pls_id: Optional[str] = None) -> pd.DataFrame:
    """Belegung auf striktem 15-Min-Raster pro (city, pls_id).

    Luecken bis 1 h werden forward-gefuellt, laengere bleiben NaN.
    Spalten: city, pls_id, slot, free, total, occ (occ NaN in Luecken).
    """
    raw = da.occupancy_history(env=env, start=start, end=end, city=city, pls_id=pls_id)
    if raw.empty:
        return pd.DataFrame(columns=["city", "pls_id", "slot", "free", "total", "occ"])

    raw["slot"] = raw["fetch_ts"].dt.floor("15min")
    raw = (
        raw.sort_values("fetch_ts")
        .groupby(["city", "pls_id", "slot"], as_index=False)
        .last()
    )

    frames = []
    for (c, p), g in raw.groupby(["city", "pls_id"]):
        idx = pd.date_range(g["slot"].min(), g["slot"].max(), freq="15min")
        g = g.set_index("slot").reindex(idx)
        g[["free", "total"]] = g[["free", "total"]].ffill(limit=SLOTS_PER_HOUR)
        g["city"] = c
        g["pls_id"] = p
        frames.append(g.reset_index(names="slot")[["city", "pls_id", "slot", "free", "total"]])

    grid = pd.concat(frames, ignore_index=True)
    total = grid["total"].astype(float)
    free = grid["free"].astype(float)
    grid["occ"] = np.where(total > 0, ((total - free) / total).clip(0, 1), np.nan)
    return grid


def compute_prior(grid: pd.DataFrame) -> pd.DataFrame:
    """Saisonaler Prior: mittlere Belegung pro (city, pls_id, weekday, hour)."""
    g = grid.dropna(subset=["occ"]).copy()
    if g.empty:
        return pd.DataFrame(columns=["city", "pls_id", "weekday", "hour", "prior_occ"])
    g["weekday"] = g["slot"].dt.weekday
    g["hour"] = g["slot"].dt.hour
    return (
        g.groupby(["city", "pls_id", "weekday", "hour"], as_index=False)["occ"]
        .mean()
        .rename(columns={"occ": "prior_occ"})
    )


def _event_slot_table(events: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Events zu Slot-Tabellen expandieren: (aktiv, bald-beginnend)."""
    active_rows, soon_rows = [], []
    ev = events.dropna(subset=["pls_id"])
    for _, e in ev.iterrows():
        bonus = float(e["bonus"] or 0)
        for slot in pd.date_range(e["start_time"].floor("15min"),
                                  e["end_time"].ceil("15min"), freq="15min"):
            active_rows.append((e["city"], e["pls_id"], slot, bonus))
        for slot in pd.date_range((e["start_time"] - timedelta(hours=3)).ceil("15min"),
                                  e["start_time"].floor("15min"), freq="15min",
                                  inclusive="left"):
            soon_rows.append((e["city"], e["pls_id"], slot, bonus))

    cols = ["city", "pls_id", "target_slot", "event_bonus"]
    active = (
        pd.DataFrame(active_rows, columns=cols)
        .groupby(cols[:3], as_index=False).max()
        if active_rows else pd.DataFrame(columns=cols)
    )
    soon = (
        pd.DataFrame(soon_rows, columns=["city", "pls_id", "target_slot", "soon_bonus"])
        .groupby(["city", "pls_id", "target_slot"], as_index=False).max()
        if soon_rows else pd.DataFrame(columns=["city", "pls_id", "target_slot", "soon_bonus"])
    )
    return active, soon


def add_series_features(grid: pd.DataFrame) -> pd.DataFrame:
    """Lag- und Rolling-Features (bezogen auf t0 = slot) pro Haus anfuegen."""
    grid = grid.sort_values(["city", "pls_id", "slot"]).copy()
    g = grid.groupby(["city", "pls_id"])["occ"]
    grid["occ_now"] = grid["occ"]
    for col, shift in LAGS.items():
        grid[col] = g.shift(shift)
    grid["delta_occ_1h"] = grid["occ_now"] - grid["occ_1h_ago"]
    grid["occ_mean_3h"] = g.transform(lambda s: s.rolling(12, min_periods=4).mean())
    grid["occ_mean_24h"] = g.transform(lambda s: s.rolling(96, min_periods=24).mean())
    grid["occ_std_24h"] = g.transform(lambda s: s.rolling(96, min_periods=24).std())
    return grid


def build_horizon_frame(grid: pd.DataFrame, horizon_h: int,
                        weather: pd.DataFrame, events: pd.DataFrame,
                        prior: pd.DataFrame,
                        require_target: bool = True) -> pd.DataFrame:
    """Feature-Frame fuer einen Horizont.

    grid muss bereits add_series_features durchlaufen haben. Eine Zeile pro
    (city, pls_id, slot=t0); 'target' = Belegung bei t0+h (NaN bei Prognose).
    """
    df = grid.copy()
    shift = horizon_h * SLOTS_PER_HOUR
    df["target"] = df.groupby(["city", "pls_id"])["occ"].shift(-shift)
    df["target_slot"] = df["slot"] + timedelta(hours=horizon_h)

    if require_target:
        df = df.dropna(subset=["target", "occ_now"])
    else:
        df = df.dropna(subset=["occ_now"])

    # Kalender des Zielzeitpunkts
    ts = df["target_slot"]
    df["hour"] = ts.dt.hour
    df["quarter"] = ts.dt.minute // 15
    df["weekday"] = ts.dt.weekday
    df["is_weekend"] = (df["weekday"] >= 5).astype(int)
    df["month"] = ts.dt.month
    df["sin_hour"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["cos_hour"] = np.cos(2 * np.pi * df["hour"] / 24)
    df["sin_weekday"] = np.sin(2 * np.pi * df["weekday"] / 7)
    df["cos_weekday"] = np.cos(2 * np.pi * df["weekday"] / 7)

    # Wetter zur Zielstunde
    if not weather.empty:
        w = weather.rename(columns={"ts": "target_hour"})
        df["target_hour"] = ts.dt.floor("h")
        df = df.merge(w, on=["city", "target_hour"], how="left")
        df = df.drop(columns=["target_hour"])
    else:
        df["temperature"] = np.nan
        df["precipitation"] = np.nan
    df["is_raining"] = (df["precipitation"].fillna(0) > 0.5).astype(int)

    # Events zum Zielzeitpunkt
    active, soon = _event_slot_table(events) if not events.empty else (
        pd.DataFrame(columns=["city", "pls_id", "target_slot", "event_bonus"]),
        pd.DataFrame(columns=["city", "pls_id", "target_slot", "soon_bonus"]),
    )
    df = df.merge(active, on=["city", "pls_id", "target_slot"], how="left")
    df = df.merge(soon, on=["city", "pls_id", "target_slot"], how="left")
    df["event_active"] = df["event_bonus"].notna().astype(int)
    df["event_soon"] = df["soon_bonus"].notna().astype(int)
    active_bonus = pd.to_numeric(df["event_bonus"], errors="coerce")
    soon_bonus = pd.to_numeric(df["soon_bonus"], errors="coerce")
    df["event_bonus"] = active_bonus.fillna(soon_bonus).fillna(0.0)
    df = df.drop(columns=["soon_bonus"])

    # Saisonaler Prior (weekday/hour des Zielzeitpunkts)
    if not prior.empty:
        df = df.merge(prior, on=["city", "pls_id", "weekday", "hour"], how="left")
    else:
        df["prior_occ"] = np.nan

    df["log_total"] = np.log1p(df["total"].astype(float))
    df["pls_key"] = df["city"] + "::" + df["pls_id"]
    return df
