"""Datenbankzugriff via pymysql (wie scanner/get_event_and_weather_data.py).

Eine Verbindung pro Operation - einfach und robust; die Zugriffsmuster der App
(Batch-Jobs alle 15 Min, wenige UI-Requests) brauchen keinen Pool.
"""
import logging
from typing import Optional

import pymysql
import pymysql.cursors

import config

logger = logging.getLogger(__name__)


def get_conn(env: Optional[str] = None) -> pymysql.connections.Connection:
    return pymysql.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.db_name(env),
        charset=config.DB_CHARSET,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def query(sql: str, params=None, env: Optional[str] = None) -> list[dict]:
    """SELECT ausfuehren, Ergebnis als Liste von Dicts."""
    conn = get_conn(env)
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params if params else None)
            return cursor.fetchall()
    finally:
        conn.close()


def execute(sql: str, params=None, env: Optional[str] = None) -> int:
    """Einzelnes INSERT/UPDATE/DELETE mit Commit. Liefert rowcount."""
    conn = get_conn(env)
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params if params else None)
            rowcount = cursor.rowcount
        conn.commit()
        return rowcount
    finally:
        conn.close()


def executemany(sql: str, seq_params, env: Optional[str] = None) -> int:
    """Batch-INSERT/UPDATE mit Commit. Liefert rowcount."""
    seq_params = list(seq_params)
    if not seq_params:
        return 0
    conn = get_conn(env)
    try:
        with conn.cursor() as cursor:
            cursor.executemany(sql, seq_params)
            rowcount = cursor.rowcount
        conn.commit()
        return rowcount
    finally:
        conn.close()
