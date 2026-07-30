"""Legt die ai_* Tabellen an: python init_db.py --env prod|test"""
import argparse
import logging
from pathlib import Path

import config
import db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def init_db(env: str) -> None:
    schema = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
    # Kommentare entfernen (auch inline), damit Semikolons in Kommentaren
    # das Statement-Splitting nicht zerreissen. Die Schema-Datei verwendet
    # kein '--' innerhalb von SQL-Literalen.
    sql = "\n".join(line.split("--", 1)[0] for line in schema.splitlines())
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    conn = db.get_conn(env)
    try:
        cursor = conn.cursor()
        for stmt in statements:
            cursor.execute(stmt)
        conn.commit()
        cursor.close()
    finally:
        conn.close()
    logger.info("Schema angewendet auf '%s' (%d Statements)", config.db_name(env), len(statements))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ai_* Tabellen anlegen")
    parser.add_argument("--env", choices=["prod", "test"], default=config.DEFAULT_ENV)
    args = parser.parse_args()
    init_db(args.env)
