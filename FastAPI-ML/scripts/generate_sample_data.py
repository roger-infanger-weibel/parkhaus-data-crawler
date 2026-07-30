"""Synthetische Belegungs- und Wetterdaten fuer die lokale Entwicklung.

Nur fuer eine LEERE lokale Datenbank gedacht (z.B. frisch angelegtes
ph_fetch_test ohne Scanner). Bricht ab, wenn pls_fetch_current bereits Daten
enthaelt - damit echte Testdaten nie mit synthetischen vermischt werden.

    python -m scripts.generate_sample_data --env test --days 60 --until-now
"""
import argparse
import logging
import math
import random
from datetime import datetime, timedelta

import config
import db
from core.timeutil import floor_to_grid, now_local

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SAMPLE_HOUSES = {
    "luzern": [("SP01", "Altstadt", 456), ("SP03", "Kantonalbank", 260),
               ("SP04", "Stadt Theater", 130)],
    "basel": [("baselparkhausaeschen", "Aeschen", 95),
              ("baselparkhauselisabethen", "Elisabethen", 840)],
    "bern": [("p01", "Bahnhof Parking", 545), ("p02", "Metro Parking", 310)],
    "zurich": [("zuerichparkhausurania", "Urania", 607)],
    "stgallen": [("P21", "Neumarkt", 230)],
}


def occupancy(ts: datetime, base_ratio: float) -> float:
    """Plausible Tageskurve: Rushhour-Peaks, Wochenend-Daempfung, Rauschen."""
    hour = ts.hour + ts.minute / 60
    day_curve = (
        0.55 * math.exp(-((hour - 11) ** 2) / 18)
        + 0.45 * math.exp(-((hour - 15.5) ** 2) / 14)
    )
    weekend = 0.75 if ts.weekday() >= 5 else 1.0
    noise = random.gauss(0, 0.03)
    return min(max(base_ratio * 0.3 + day_curve * weekend + noise, 0.02), 0.98)


def run(env: str, days: int, until_now: bool) -> None:
    existing = db.query("SELECT COUNT(*) AS n FROM pls_fetch_current", env=env)
    if existing[0]["n"] > 0:
        raise SystemExit(
            f"pls_fetch_current in '{config.db_name(env)}' enthaelt bereits "
            f"{existing[0]['n']} Zeilen - Generator ist nur fuer leere "
            f"Datenbanken gedacht (Schutz vor Vermischung mit echten Daten)."
        )

    end = floor_to_grid(now_local()) if until_now else floor_to_grid(
        now_local()).replace(hour=0, minute=0)
    start = end - timedelta(days=days)

    rows, weather_rows = [], []
    for city, houses in SAMPLE_HOUSES.items():
        random.seed(hash(city) % 10000)
        for pls_id, name, total in houses:
            base = random.uniform(0.1, 0.3)
            ts = start
            while ts <= end:
                occ = occupancy(ts, base)
                free = int(round(total * (1 - occ)))
                rows.append((ts.date(), ts, city, pls_id, name, free, total))
                ts += timedelta(minutes=15)
        ts = start.replace(minute=0)
        while ts <= end + timedelta(days=7):
            temp = 12 + 10 * math.sin((ts.timetuple().tm_yday - 100) / 58) \
                + 6 * math.exp(-((ts.hour - 14) ** 2) / 30) + random.gauss(0, 1)
            rain = max(0.0, random.gauss(-1.5, 2.0))
            weather_rows.append((city, ts, round(temp, 1), round(rain, 1)))
            ts += timedelta(hours=1)

    for i in range(0, len(rows), 5000):
        db.executemany(
            """INSERT INTO pls_fetch_current (day, fetch_ts, city, id, name, free, total)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE free = VALUES(free)""",
            rows[i:i + 5000], env=env,
        )
    for i in range(0, len(weather_rows), 5000):
        db.executemany(
            """INSERT INTO weather_forecasts (city_id, timestamp, temperature, precipitation)
               VALUES (%s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE temperature = VALUES(temperature)""",
            weather_rows[i:i + 5000], env=env,
        )
    logger.info("%d Belegungs- und %d Wetterzeilen erzeugt (%s bis %s)",
                len(rows), len(weather_rows), start, end)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", choices=["prod", "test"], default=None)
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--until-now", action="store_true")
    args = parser.parse_args()
    run(args.env or config.DEFAULT_ENV, args.days, args.until_now)
