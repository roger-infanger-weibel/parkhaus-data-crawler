"""Statistisches Basismodell - transparente Referenz fuer das ML-Modell.

Prognose = mittlere Belegung des Slots (city, pls_id, weekday, hour, quarter)
ueber die letzten 8 Wochen, mit Fallback-Kette:
  exakter Slot -> Stunde des Hauses -> Stunde der Stadt -> Haus-Mittel.
Additive Zuschlaege (Event-Bonus, Regen), geclippt auf [0, 1].
"""
from dataclasses import dataclass, field

import joblib
import pandas as pd

RAIN_BONUS = 0.03  # Heuristik: bei Regen etwas hoehere Belegung
RAIN_THRESHOLD_MM = 0.5


@dataclass
class BaselineModel:
    slot_mean: dict = field(default_factory=dict)   # (city,pls,wd,h,q) -> occ
    hour_mean: dict = field(default_factory=dict)   # (city,pls,wd,h) -> occ
    city_hour_mean: dict = field(default_factory=dict)  # (city,wd,h) -> occ
    house_mean: dict = field(default_factory=dict)  # (city,pls) -> occ

    def fit(self, grid: pd.DataFrame) -> "BaselineModel":
        """grid: Ausgabe von features.build_grid ueber die letzten ~8 Wochen."""
        g = grid.dropna(subset=["occ"]).copy()
        if g.empty:
            return self
        g["weekday"] = g["slot"].dt.weekday
        g["hour"] = g["slot"].dt.hour
        g["quarter"] = g["slot"].dt.minute // 15

        self.slot_mean = g.groupby(
            ["city", "pls_id", "weekday", "hour", "quarter"])["occ"].mean().to_dict()
        self.hour_mean = g.groupby(
            ["city", "pls_id", "weekday", "hour"])["occ"].mean().to_dict()
        self.city_hour_mean = g.groupby(
            ["city", "weekday", "hour"])["occ"].mean().to_dict()
        self.house_mean = g.groupby(["city", "pls_id"])["occ"].mean().to_dict()
        return self

    def predict_one(self, city: str, pls_id: str, target_slot,
                    event_bonus: float = 0.0, precipitation: float = 0.0) -> float | None:
        wd, h, q = target_slot.weekday(), target_slot.hour, target_slot.minute // 15
        occ = self.slot_mean.get((city, pls_id, wd, h, q))
        if occ is None:
            occ = self.hour_mean.get((city, pls_id, wd, h))
        if occ is None:
            occ = self.city_hour_mean.get((city, wd, h))
        if occ is None:
            occ = self.house_mean.get((city, pls_id))
        if occ is None:
            return None
        if event_bonus:
            occ += event_bonus
        if (precipitation or 0) > RAIN_THRESHOLD_MM:
            occ += RAIN_BONUS
        return float(min(max(occ, 0.0), 1.0))

    def predict_frame(self, frame: pd.DataFrame) -> pd.Series:
        """Vektorisiert ueber einen Feature-Frame (features.build_horizon_frame)."""
        return frame.apply(
            lambda r: self.predict_one(
                r["city"], r["pls_id"], r["target_slot"],
                event_bonus=r.get("event_bonus", 0.0) if r.get("event_active", 0) else 0.0,
                precipitation=r.get("precipitation", 0.0) or 0.0,
            ),
            axis=1,
        )

    def save(self, path) -> None:
        joblib.dump(self, path)

    @staticmethod
    def load(path) -> "BaselineModel":
        return joblib.load(path)
