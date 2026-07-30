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

CONNECT_TIMEOUT = 20
# Ohne read_timeout wartet pymysql unbegrenzt, wenn der Server die Verbindung
# abbricht (z.B. net_write_timeout=60, wenn der Client ein grosses Ergebnis
# nicht schnell genug abholt) - der Prozess haengt dann fuer immer.
READ_TIMEOUT = 300


def get_conn(env: Optional[str] = None,
             cursorclass=None) -> pymysql.connections.Connection:
    return pymysql.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.db_name(env),
        charset=config.DB_CHARSET,
        cursorclass=cursorclass or pymysql.cursors.DictCursor,
        autocommit=False,
        connect_timeout=CONNECT_TIMEOUT,
        read_timeout=READ_TIMEOUT,
        write_timeout=READ_TIMEOUT,
    )


def query_stream(sql: str, params=None, env: Optional[str] = None,
                 batch_size: int = 20000):
    """Grosse SELECTs streamen: liefert Batches von Tupeln.

    Server-side Cursor (SSCursor) statt alles zu puffern - deutlich weniger
    Speicher als eine Liste aus einer Million Dicts, und die Zeilen werden
    fortlaufend abgeholt, sodass der Server die Verbindung nicht wegen
    net_write_timeout abbricht.
    """
    conn = get_conn(env, cursorclass=pymysql.cursors.SSCursor)
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params if params else None)
            while True:
                batch = cursor.fetchmany(batch_size)
                if not batch:
                    return
                yield batch
    finally:
        conn.close()


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
