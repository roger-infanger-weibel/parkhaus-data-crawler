"""ML-Modell-Wrapper: LightGBM, mit Fallback auf sklearn HistGradientBoosting.

Ein globales Modell pro Horizont, trainiert ueber alle Staedte/Haeuser
gemeinsam (city/pls_key als Kategorien). Beide Bibliotheken behandeln NaN
nativ - keine Imputation noetig.
"""
import logging

import joblib
import pandas as pd

from forecast.features import CATEGORICAL_COLUMNS, FEATURE_COLUMNS

logger = logging.getLogger(__name__)

try:
    from lightgbm import LGBMRegressor
    HAS_LIGHTGBM = True
except ImportError:  # pragma: no cover - Server ohne LightGBM-Wheel
    HAS_LIGHTGBM = False


class ForecastModel:
    """fit/predict/save/load - identisch fuer LightGBM und sklearn-Fallback."""

    def __init__(self, horizon_h: int):
        self.horizon_h = horizon_h
        self.categories: dict[str, list] = {}
        if HAS_LIGHTGBM:
            self.library = "lightgbm"
            self.model = LGBMRegressor(
                objective="regression_l1",
                n_estimators=600,
                learning_rate=0.05,
                num_leaves=63,
                min_child_samples=50,
                verbose=-1,
            )
        else:
            from sklearn.ensemble import HistGradientBoostingRegressor
            self.library = "sklearn"
            self.model = HistGradientBoostingRegressor(
                loss="absolute_error",
                max_iter=400,
                learning_rate=0.06,
                categorical_features="from_dtype",
            )

    def _prepare(self, frame: pd.DataFrame, fit: bool) -> pd.DataFrame:
        x = frame[FEATURE_COLUMNS].copy()
        for col in CATEGORICAL_COLUMNS:
            if fit:
                x[col] = x[col].astype("category")
                self.categories[col] = list(x[col].cat.categories)
            else:
                # Unbekannte Kategorien (neue Haeuser) werden NaN
                x[col] = pd.Categorical(x[col], categories=self.categories[col])
        return x

    def fit(self, frame: pd.DataFrame) -> "ForecastModel":
        x = self._prepare(frame, fit=True)
        self.model.fit(x, frame["target"].astype(float))
        return self

    def predict(self, frame: pd.DataFrame) -> pd.Series:
        x = self._prepare(frame, fit=False)
        pred = self.model.predict(x)
        return pd.Series(pred, index=frame.index).clip(0.0, 1.0)

    def save(self, path) -> None:
        joblib.dump(self, path)

    @staticmethod
    def load(path) -> "ForecastModel":
        return joblib.load(path)


class QuantileModel(ForecastModel):
    """Pessimistisches 20%-Quantil: 'mit 80% Wahrscheinlichkeit mindestens X frei'."""

    def __init__(self, horizon_h: int, alpha: float = 0.2):
        self.horizon_h = horizon_h
        self.alpha = alpha
        self.categories: dict[str, list] = {}
        if HAS_LIGHTGBM:
            self.library = "lightgbm"
            self.model = LGBMRegressor(
                objective="quantile",
                alpha=alpha,
                n_estimators=600,
                learning_rate=0.05,
                num_leaves=63,
                min_child_samples=50,
                verbose=-1,
            )
        else:
            from sklearn.ensemble import HistGradientBoostingRegressor
            self.library = "sklearn"
            self.model = HistGradientBoostingRegressor(
                loss="quantile",
                quantile=alpha,
                max_iter=400,
                learning_rate=0.06,
                categorical_features="from_dtype",
            )


class FullClassifier:
    """Binaer-Klassifikator: P(free < threshold)."""

    THRESHOLD = 5

    def __init__(self, horizon_h: int):
        self.horizon_h = horizon_h
        self.categories: dict[str, list] = {}
        if HAS_LIGHTGBM:
            from lightgbm import LGBMClassifier
            self.library = "lightgbm"
            self.model = LGBMClassifier(
                objective="binary",
                n_estimators=400,
                learning_rate=0.05,
                num_leaves=63,
                min_child_samples=50,
                verbose=-1,
            )
        else:
            from sklearn.ensemble import HistGradientBoostingClassifier
            self.library = "sklearn"
            self.model = HistGradientBoostingClassifier(
                max_iter=300,
                learning_rate=0.06,
                categorical_features="from_dtype",
            )

    def _prepare(self, frame: pd.DataFrame, fit: bool) -> pd.DataFrame:
        x = frame[FEATURE_COLUMNS].copy()
        for col in CATEGORICAL_COLUMNS:
            if fit:
                x[col] = x[col].astype("category")
                self.categories[col] = list(x[col].cat.categories)
            else:
                x[col] = pd.Categorical(x[col], categories=self.categories[col])
        return x

    def fit(self, frame: pd.DataFrame) -> "FullClassifier":
        x = self._prepare(frame, fit=True)
        total = frame["total"].astype(float)
        free_abs = (1 - frame["target"].astype(float)) * total
        y = (free_abs < self.THRESHOLD).astype(int)
        self.model.fit(x, y)
        return self

    def predict_proba(self, frame: pd.DataFrame) -> pd.Series:
        x = self._prepare(frame, fit=False)
        proba = self.model.predict_proba(x)[:, 1]
        return pd.Series(proba, index=frame.index).clip(0.0, 1.0)

    def save(self, path) -> None:
        joblib.dump(self, path)

    @staticmethod
    def load(path) -> "FullClassifier":
        return joblib.load(path)
