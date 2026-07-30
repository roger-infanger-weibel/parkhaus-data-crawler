"""Fehlende Messwerte aus der alten Datenbank ph_fetch uebernehmen.

Hintergrund: ph_fetch_prod/_test wurden aus einem Dump vom 15.07.2026 aufgebaut;
zwischen Dump und Neustart des Scanners (23.07.) fehlen dort Messwerte, die in
der alten DB noch vorhanden sind. Danach kann ph_fetch geloescht werden.

Kopiert wird stundenweise nach zwei Regeln:
  - vor dem Scanner-Neustart (CUTOFF): jede Stunde, in der die Ziel-DB weniger
    Zeilen hat als die Quelle - das ist die eigentliche Luecke;
  - ab dem CUTOFF: nur Stunden, in denen die Ziel-DB gar nichts hat (echter
    Ausfall). Danach liefen beide Scanner parallel mit um Sekunden
    verschobenen Zeitstempeln; ein Zeilen-Vergleich wuerde dort
    Doppelmessungen erzeugen statt Luecken zu fuellen.
INSERT IGNORE schuetzt zusaetzlich vor exakt gleichen Schluesseln.

    python -m scripts.migrate_old_db --dry-run     # nur anzeigen
    python -m scripts.migrate_old_db               # ausfuehren (test + prod)
"""
import argparse
import logging

import pymysql
import pymysql.cursors

import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SOURCE_DB = "ph_fetch"
TABLE = "pls_fetch_current"
COLUMNS = "day, fetch_ts, city, id, name, free, total"

# Ab hier lief der neue Scanner wieder durchgehend; davor liegt die Luecke.
CUTOFF = "2026-07-24 00"


def connect():
    return pymysql.connect(
        host=config.DB_HOST, port=config.DB_PORT, user=config.DB_USER,
        password=config.DB_PASSWORD, charset=config.DB_CHARSET,
        cursorclass=pymysql.cursors.DictCursor, autocommit=False,
    )


def hourly_counts(cur, database: str) -> dict:
    cur.execute(
        f"SELECT DATE_FORMAT(fetch_ts, '%%Y-%%m-%%d %%H') h, COUNT(*) n "
        f"FROM {database}.{TABLE} GROUP BY h",
        (),
    )
    return {r["h"]: r["n"] for r in cur.fetchall()}


def migrate(target_db: str, dry_run: bool) -> dict:
    conn = connect()
    try:
        cur = conn.cursor()
        source = hourly_counts(cur, SOURCE_DB)
        target = hourly_counts(cur, target_db)

        missing = sorted(
            h for h in source
            if (source[h] > target.get(h, 0) if h < CUTOFF else target.get(h, 0) == 0)
        )
        expected = sum(source[h] - target.get(h, 0) for h in missing)
        logger.info("%s: %d Stunden mit fehlenden Daten, ca. %d Zeilen",
                    target_db, len(missing), expected)
        if missing:
            logger.info("  Zeitraum: %s bis %s", missing[0], missing[-1])
        if dry_run or not missing:
            return {"hours": len(missing), "expected": expected, "inserted": 0}

        inserted = 0
        for h in missing:
            cur.execute(
                f"INSERT IGNORE INTO {target_db}.{TABLE} ({COLUMNS}) "
                f"SELECT {COLUMNS} FROM {SOURCE_DB}.{TABLE} "
                f"WHERE fetch_ts >= %s AND fetch_ts < %s + INTERVAL 1 HOUR",
                (f"{h}:00:00", f"{h}:00:00"),
            )
            inserted += cur.rowcount
        conn.commit()
        logger.info("%s: %d Zeilen eingefuegt", target_db, inserted)
        return {"hours": len(missing), "expected": expected, "inserted": inserted}
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    for env in ("test", "prod"):
        print(migrate(config.db_name(env), args.dry_run))
