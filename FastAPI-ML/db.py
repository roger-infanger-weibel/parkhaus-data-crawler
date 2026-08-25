"""Datenbankzugriff via pymysql mit Connection Pool.

Bis Aug 2026 oeffnete jede Query eine eigene Verbindung. Bei 5-6 Queries pro
Seitenaufruf (current_forecasts) kostete das ~500ms nur fuer TCP-Handshakes.
Jetzt haelt ein Pool pro (env, cursorclass) offene Verbindungen vor.
"""
import logging
import threading
from collections import defaultdict
from queue import Empty, Queue
from typing import Optional

import pymysql
import pymysql.cursors

import config

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT = 20
READ_TIMEOUT = 300

POOL_SIZE = 4
POOL_MAX_IDLE = 60

_pools: dict[tuple, Queue] = defaultdict(lambda: Queue(maxsize=POOL_SIZE))
_lock = threading.Lock()


def _pool_key(env: Optional[str], cursorclass) -> tuple:
    return (config.db_name(env), cursorclass or pymysql.cursors.DictCursor)


def _new_conn(env: Optional[str] = None,
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


def get_conn(env: Optional[str] = None,
             cursorclass=None) -> pymysql.connections.Connection:
    key = _pool_key(env, cursorclass)
    pool = _pools[key]
    try:
        conn = pool.get_nowait()
        try:
            conn.ping(reconnect=False)
            return conn
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
    except Empty:
        pass
    return _new_conn(env, cursorclass)


def _return_conn(conn: pymysql.connections.Connection,
                 env: Optional[str] = None, cursorclass=None):
    key = _pool_key(env, cursorclass)
    pool = _pools[key]
    try:
        pool.put_nowait(conn)
    except Exception:
        try:
            conn.close()
        except Exception:
            pass


def query_stream(sql: str, params=None, env: Optional[str] = None,
                 batch_size: int = 20000):
    """Grosse SELECTs streamen: liefert Batches von Tupeln.

    SSCursor-Verbindungen gehen nicht zurueck in den Pool, weil der Cursor-
    State an die Verbindung gebunden ist.
    """
    conn = _new_conn(env, cursorclass=pymysql.cursors.SSCursor)
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
            result = cursor.fetchall()
        _return_conn(conn, env)
        return result
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        raise


def execute(sql: str, params=None, env: Optional[str] = None) -> int:
    """Einzelnes INSERT/UPDATE/DELETE mit Commit. Liefert rowcount."""
    conn = get_conn(env)
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params if params else None)
            rowcount = cursor.rowcount
        conn.commit()
        _return_conn(conn, env)
        return rowcount
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        raise


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
        _return_conn(conn, env)
        return rowcount
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        raise
