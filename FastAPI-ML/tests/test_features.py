"""Feature-Engineering: Raster, Lags, Luecken-Handling, Zielvariable."""
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from forecast import features


def _grid_df(hours=30, total=100):
    """Handgebautes Grid: Belegung steigt linear, 1 Haus."""
    slots = pd.date_range(datetime(2026, 7, 1), periods=hours * 4, freq="15min")
    occ = np.linspace(0.2, 0.8, len(slots))
    return pd.DataFrame({
        "city": "luzern", "pls_id": "SP01", "slot": slots,
        "free": (total * (1 - occ)).round(), "total": total, "occ": occ,
    })


def test_add_series_features_lags():
    grid = features.add_series_features(_grid_df())
    row = grid.iloc[8]  # 2h nach Start
    assert abs(row["occ_1h_ago"] - grid.iloc[4]["occ"]) < 1e-9
    assert abs(row["occ_2h_ago"] - grid.iloc[0]["occ"]) < 1e-9
    assert np.isnan(row["occ_24h_ago"])  # noch keine 24h Historie


def test_horizon_frame_target_shift():
    grid = features.add_series_features(_grid_df())
    frame = features.build_horizon_frame(
        grid, 1, pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    first = frame.iloc[0]
    # Ziel = Belegung 4 Slots spaeter
    expected = grid[grid["slot"] == first["slot"] + timedelta(hours=1)]["occ"].iloc[0]
    assert abs(first["target"] - expected) < 1e-9
    assert first["target_slot"] == first["slot"] + timedelta(hours=1)


def test_grid_gap_stays_nan():
    df = _grid_df()
    # 3h-Luecke: occ muss NaN bleiben (ffill-Limit 1h)
    df = df.drop(df.index[10:22]).reset_index(drop=True)
    raw = pd.DataFrame({
        "city": df["city"], "pls_id": df["pls_id"], "fetch_ts": df["slot"],
        "free": df["free"], "total": df["total"],
    })
    import core.data_access as da
    orig = da.occupancy_history
    da.occupancy_history = lambda **kw: raw
    try:
        grid = features.build_grid("test", df["slot"].min(), df["slot"].max())
    finally:
        da.occupancy_history = orig
    gap_slots = grid[(grid["slot"] > df["slot"].iloc[9] + timedelta(hours=1))
                     & (grid["slot"] < df["slot"].iloc[10])]
    assert gap_slots["occ"].isna().all()


def test_calendar_features_of_target_time():
    grid = features.add_series_features(_grid_df())
    frame = features.build_horizon_frame(
        grid, 8, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
        require_target=False)
    row = frame.iloc[0]
    assert row["hour"] == (row["slot"] + timedelta(hours=8)).hour
