"""Alle Lese-Zugriffe auf die bestehenden Tabellen (read-only)."""
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

import db
from core.timeutil import now_local


def get_cities(env: Optional[str] = None) -> list[dict]:
    return db.query(
        "SELECT id, name, latitude, longitude FROM cities ORDER BY name", env=env
    )


def get_mapping(env: Optional[str] = None, city: Optional[str] = None) -> list[dict]:
    """ai_parkhaus_map inkl. Gruppenname aus parkhaeuser."""
    sql = """
        SELECT m.city, m.pls_id, m.pls_name, m.parkhaus_id, m.match_method,
               p.parking_group
        FROM ai_parkhaus_map m
        LEFT JOIN parkhaeuser p ON p.id = m.parkhaus_id
    """
    params: tuple = ()
    if city:
        sql += " WHERE m.city = %s"
        params = (city,)
    return db.query(sql + " ORDER BY m.city, m.pls_name", params, env=env)


def latest_snapshots(env: Optional[str] = None, city: Optional[str] = None,
                     max_age_hours: int = 2) -> list[dict]:
    """Neuster Messwert pro (city, pls_id), nicht aelter als max_age_hours."""
    cutoff = now_local() - timedelta(hours=max_age_hours)
    sql = """
        SELECT p.city, p.id AS pls_id, p.name, p.free, p.total, p.fetch_ts
        FROM pls_fetch_current p
        JOIN (
            SELECT city, id, MAX(fetch_ts) AS max_ts
            FROM pls_fetch_current
            WHERE fetch_ts >= %s
            GROUP BY city, id
        ) m ON m.city = p.city AND m.id = p.id AND m.max_ts = p.fetch_ts
    """
    params: list = [cutoff]
    if city:
        sql += " WHERE p.city = %s"
        params.append(city)
    return db.query(sql, tuple(params), env=env)


def occupancy_history(env: Optional[str] = None, start: Optional[datetime] = None,
                      end: Optional[datetime] = None,
                      city: Optional[str] = None,
                      pls_id: Optional[str] = None) -> pd.DataFrame:
    """Belegungs-Rohdaten als DataFrame [city, pls_id, fetch_ts, free, total]."""
    sql = """
        SELECT city, id AS pls_id, fetch_ts, free, total
        FROM pls_fetch_current
        WHERE 1=1
    """
    params: list = []
    if start:
        sql += " AND fetch_ts >= %s"
        params.append(start)
    if end:
        sql += " AND fetch_ts < %s"
        params.append(end)
    if city:
        sql += " AND city = %s"
        params.append(city)
    if pls_id:
        sql += " AND id = %s"
        params.append(pls_id)
    rows = db.query(sql + " ORDER BY fetch_ts", tuple(params), env=env)
    df = pd.DataFrame(rows, columns=["city", "pls_id", "fetch_ts", "free", "total"])
    if not df.empty:
        df["fetch_ts"] = pd.to_datetime(df["fetch_ts"])
    return df


def weather_range(env: Optional[str] = None, start: Optional[datetime] = None,
                  end: Optional[datetime] = None,
                  city: Optional[str] = None) -> pd.DataFrame:
    """Stundenwetter als DataFrame [city, ts, temperature, precipitation]."""
    sql = """
        SELECT city_id AS city, timestamp AS ts, temperature, precipitation
        FROM weather_forecasts
        WHERE 1=1
    """
    params: list = []
    if start:
        sql += " AND timestamp >= %s"
        params.append(start)
    if end:
        sql += " AND timestamp < %s"
        params.append(end)
    if city:
        sql += " AND city_id = %s"
        params.append(city)
    rows = db.query(sql + " ORDER BY timestamp", tuple(params), env=env)
    df = pd.DataFrame(rows, columns=["city", "ts", "temperature", "precipitation"])
    if not df.empty:
        df["ts"] = pd.to_datetime(df["ts"])
        df["temperature"] = df["temperature"].astype(float)
        df["precipitation"] = df["precipitation"].astype(float)
    return df


def events_range(env: Optional[str] = None, start: Optional[datetime] = None,
                 end: Optional[datetime] = None,
                 city: Optional[str] = None) -> pd.DataFrame:
    """Events inkl. betroffener pls_ids (via ai_parkhaus_map).

    DataFrame [event_id, city, start_time, end_time, bonus, pls_id, title, venue, category]
    - pls_id NULL, wenn das Event keinem gemappten Haus zugeordnet ist.
    """
    sql = """
        SELECT e.id AS event_id, e.city, e.title, e.venue, e.category,
               e.start_time, e.end_time, e.peak_occupancy_bonus AS bonus,
               m.pls_id
        FROM local_events e
        LEFT JOIN event_parkhaus ep ON ep.event_id = e.id
        LEFT JOIN ai_parkhaus_map m
               ON m.parkhaus_id = ep.parkhaus_id AND m.city = e.city
        WHERE 1=1
    """
    params: list = []
    if start:
        sql += " AND e.end_time >= %s"
        params.append(start)
    if end:
        sql += " AND e.start_time < %s"
        params.append(end)
    if city:
        sql += " AND e.city = %s"
        params.append(city)
    rows = db.query(sql + " ORDER BY e.start_time", tuple(params), env=env)
    df = pd.DataFrame(rows, columns=[
        "event_id", "city", "title", "venue", "category",
        "start_time", "end_time", "bonus", "pls_id",
    ])
    if not df.empty:
        df["start_time"] = pd.to_datetime(df["start_time"])
        df["end_time"] = pd.to_datetime(df["end_time"])
        df["bonus"] = df["bonus"].astype(float)
    return df
