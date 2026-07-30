"""Basismodell: Fallback-Kette, Zuschlaege, Clipping."""
from datetime import datetime

import pandas as pd

from forecast.baseline import BaselineModel


def _fit_model():
    slots = pd.date_range(datetime(2026, 7, 6), periods=7 * 96, freq="15min")  # 1 Woche
    df = pd.DataFrame({
        "city": "luzern", "pls_id": "SP01", "slot": slots,
        "free": 50, "total": 100,
        "occ": [0.9 if s.hour == 12 else 0.3 for s in slots],
    })
    return BaselineModel().fit(df)


def test_exact_slot_mean():
    m = _fit_model()
    # Montag 12:00 -> 0.9
    assert abs(m.predict_one("luzern", "SP01", datetime(2026, 7, 13, 12, 0)) - 0.9) < 1e-9


def test_city_fallback_for_unknown_house():
    m = _fit_model()
    occ = m.predict_one("luzern", "UNBEKANNT", datetime(2026, 7, 13, 12, 0))
    assert occ is not None and abs(occ - 0.9) < 1e-9  # Stadt-Mittel derselben Stunde


def test_unknown_city_returns_none():
    m = _fit_model()
    assert m.predict_one("basel", "X", datetime(2026, 7, 13, 12, 0)) is None


def test_event_and_rain_bonus_clipped():
    m = _fit_model()
    occ = m.predict_one("luzern", "SP01", datetime(2026, 7, 13, 12, 0),
                        event_bonus=0.4, precipitation=2.0)
    assert occ == 1.0  # 0.9 + 0.4 + 0.03 -> geclippt
