"""Einmalig: Löscht die generierten Dummy-Events (lu-*-hist-*, zh-*-hist-*) aus beiden DBs."""
import os, sys
from pathlib import Path
from dotenv import load_dotenv
import pymysql

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

for db_name in ["ph_fetch_prod", "ph_fetch_test"]:
    print(f"\n=== {db_name} ===")
    try:
        conn = pymysql.connect(host=DB_HOST, port=DB_PORT, user=DB_USER,
                               password=DB_PASSWORD, database=db_name, autocommit=True)
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM local_events WHERE id LIKE '%%-hist-%%'")
        fake = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM event_parkhaus WHERE event_id LIKE '%%-hist-%%'")
        fake_map = cur.fetchone()[0]

        print(f"  Fake-Events: {fake}, Fake-Mappings: {fake_map}")

        if fake_map:
            cur.execute("DELETE FROM event_parkhaus WHERE event_id LIKE '%%-hist-%%'")
        if fake:
            cur.execute("DELETE FROM local_events WHERE id LIKE '%%-hist-%%'")

        cur.execute("SELECT COUNT(*) FROM local_events")
        remaining = cur.fetchone()[0]
        print(f"  Gelöscht. Verbleibende echte Events: {remaining}")

        cur.close()
        conn.close()
    except Exception as e:
        print(f"  Fehler: {e}")
