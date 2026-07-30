"""Kanonisches Parkhaus-Identity-Mapping.

Ist-Daten (pls_fetch_current) und Stammdaten/Events (parkhaeuser) verwenden
nicht dieselben IDs:
  - basel/zurich: pls.id == parkhaeuser.id                      -> 'id'
  - luzern/stgallen: pls.id = Kuerzel ("SP03"), Name enthalten  -> 'contain'
  - bern: umgekehrte Wortreihenfolge ("Bahnhof Parking" vs.
    "Bern Parkhaus Bahnhof"), generische Woerter unterschiedlich -> 'wordset'

Kanonischer Schluessel der AI-App ist (city, pls_id); dieses Modul pflegt die
Tabelle ai_parkhaus_map, ueber die alle anderen Module joinen.
"""
import argparse
import logging

import db
from core.timeutil import now_local

logger = logging.getLogger(__name__)

# Woerter ohne Unterscheidungskraft fuer den Wort-Vergleich
GENERIC_WORDS = {
    "parkhaus", "parking", "parkplatz", "parkgarage", "garage", "haus",
    "basel", "bern", "luzern", "zuerich", "zurich", "st", "gallen", "stgallen",
    "sankt", "ag", "p",
}


def normalize_name(name: str) -> str:
    """Kleinbuchstaben, Umlaute falten, alles Nicht-Alphanumerische entfernen.

    Gleiche Logik wie flask/web_server.py, plus Umlaut-Faltung, damit
    "Guetsch" und "Gütsch" zusammenfinden.
    """
    folded = (
        name.lower()
        .replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    )
    return "".join(ch for ch in folded if ch.isalnum())


def normalize_wordset(name: str) -> frozenset[str]:
    """Menge der unterscheidungskraeftigen Wortstaemme eines Namens."""
    folded = (
        name.lower()
        .replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    )
    words = "".join(ch if ch.isalnum() else " " for ch in folded).split()
    result = set()
    for w in words:
        # Generische Bestandteile auch innerhalb zusammengeschriebener Woerter
        # entfernen ("casinoparking" -> "casino", "cityparking" -> "city")
        for generic in ("parkhaus", "parkgarage", "parkplatz", "parking"):
            w = w.replace(generic, "")
        if w and w not in GENERIC_WORDS:
            result.add(w)
    return frozenset(result)


def match_parkhaus(pls_id: str, pls_name: str, parkhaeuser: list[dict]) -> tuple[str | None, str]:
    """Bestes parkhaeuser-Match fuer einen pls-Eintrag: (parkhaus_id, methode)."""
    # a) exakte ID (basel, zurich)
    for ph in parkhaeuser:
        if ph["id"] == pls_id:
            return ph["id"], "id"

    # b) normalisierter Name im Zielnamen enthalten, laengster Treffer gewinnt
    #    (luzern, stgallen; portiert aus flask/web_server.py get_groups)
    norm_pls = normalize_name(pls_name)
    best_id, best_len = None, 0
    if norm_pls:
        for ph in parkhaeuser:
            target = normalize_name(ph["name"]) + normalize_name(ph["id"])
            if norm_pls in target and len(norm_pls) > best_len:
                best_id, best_len = ph["id"], len(norm_pls)
    if best_id:
        return best_id, "contain"

    # c) Wort-Vergleich ohne generische Woerter (bern)
    pls_words = normalize_wordset(pls_name)
    if pls_words:
        candidates = []
        for ph in parkhaeuser:
            # Nur der lesbare Name - in der ID kleben Stadt/Parkhaus-Praefixe
            # am Wortstamm ("stgallenparkhausbahnhof") und verhindern Matches.
            ph_words = normalize_wordset(ph["name"])
            if pls_words <= ph_words or ph_words <= pls_words:
                overlap = len(pls_words & ph_words)
                if overlap:
                    candidates.append((overlap, -len(ph_words ^ pls_words), ph["id"]))
        if candidates:
            candidates.sort(reverse=True)
            return candidates[0][2], "wordset"

    return None, "none"


def build_mapping(env: str | None = None) -> dict[str, int]:
    """ai_parkhaus_map neu aufbauen. Liefert Zaehler pro Match-Methode."""
    pls_rows = db.query(
        """
        SELECT p.city, p.id, p.name
        FROM pls_fetch_current p
        JOIN (
            SELECT city, id, MAX(fetch_ts) AS max_ts
            FROM pls_fetch_current GROUP BY city, id
        ) m ON m.city = p.city AND m.id = p.id AND m.max_ts = p.fetch_ts
        GROUP BY p.city, p.id, p.name
        """,
        env=env,
    )
    parkhaeuser = db.query(
        "SELECT id, name, city_id FROM parkhaeuser WHERE is_active = 1", env=env
    )
    by_city: dict[str, list[dict]] = {}
    for ph in parkhaeuser:
        by_city.setdefault(ph["city_id"], []).append(ph)

    now = now_local().replace(microsecond=0)
    counts: dict[str, int] = {}
    rows = []
    for pls in pls_rows:
        candidates = by_city.get(pls["city"], [])
        parkhaus_id, method = match_parkhaus(pls["id"], pls["name"], candidates)
        counts[method] = counts.get(method, 0) + 1
        rows.append((pls["city"], pls["id"], pls["name"], parkhaus_id, method, now))

    db.executemany(
        """
        INSERT INTO ai_parkhaus_map (city, pls_id, pls_name, parkhaus_id, match_method, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            pls_name = VALUES(pls_name),
            parkhaus_id = VALUES(parkhaus_id),
            match_method = VALUES(match_method),
            updated_at = VALUES(updated_at)
        """,
        rows,
        env=env,
    )
    logger.info("Mapping aktualisiert: %s", counts)
    return counts


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="ai_parkhaus_map neu aufbauen")
    parser.add_argument("--env", choices=["prod", "test"], default=None)
    args = parser.parse_args()
    print(build_mapping(args.env))
