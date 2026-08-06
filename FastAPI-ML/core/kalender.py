"""Schweizer Feiertage, Brueckentage und Schulferien als Prognose-Merkmale.

Warum das noetig ist: fuer das Modell ist der 1. August ein ganz normaler
Wochentag - tatsaechlich verhaelt sich die Belegung wie an einem Sonntag.
Dasselbe gilt fuer Schulferien, die den Pendlerverkehr ueber Wochen daempfen.
Ohne diese Merkmale lernt das Modell die Abweichung nie, weil im Trainings-
fenster von 120 Tagen nur eine Handvoll solcher Tage vorkommt.

Alles rein lokal berechnet - keine externe Abfrage, keine Zusatzbibliothek.

Genauigkeit der Daten
---------------------
Die Feiertagsliste unten ist bewusst kompakt und deckt die kantonal
anerkannten Tage der fuenf erfassten Staedte ab. Sie laesst sich an einer
Stelle korrigieren (_FIX / _BEWEGLICH).

Die Schulferien stammen aus core/data/schulferien.json, sofern dort ein
Eintrag fuer (Kanton, Jahr) existiert. Fehlt er, greift eine bewusst grobe
Naeherung (siehe _naeherung) - fuer die Sommer- und Weihnachtsferien, die
schweizweit aehnlich liegen, reicht das; fuer Sport- und Herbstferien ist es
nur ein Anhaltspunkt. Wer es genau will, traegt die kantonalen Termine in die
JSON-Datei ein; das Format steht dort im Kopf.
"""
import json
import logging
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd

import db

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent / "data"
FERIEN_DATEI = DATA_DIR / "schulferien.json"

# Stadt-ID (wie in pls_fetch_current.city) -> Kanton
STADT_KANTON = {
    "basel": "BS",
    "bern": "BE",
    "luzern": "LU",
    "stgallen": "SG",
    "zurich": "ZH",
}

# Feste Feiertage: (Monat, Tag) -> (Name, Kantone; None = alle)
_FIX = {
    (1, 1): ("Neujahr", None),
    (1, 2): ("Berchtoldstag", {"ZH", "BE"}),
    (5, 1): ("Tag der Arbeit", {"ZH", "BS"}),
    (8, 1): ("Bundesfeier", None),
    (8, 15): ("Mariae Himmelfahrt", {"LU"}),
    (11, 1): ("Allerheiligen", {"LU", "SG"}),
    (12, 8): ("Mariae Empfaengnis", {"LU"}),
    (12, 25): ("Weihnachten", None),
    (12, 26): ("Stephanstag", {"ZH", "BE", "LU", "SG"}),
}

# Bewegliche Feiertage: (Abstand zu Ostersonntag in Tagen, Name, Kantone)
_BEWEGLICH = [
    (-2, "Karfreitag", None),
    (1, "Ostermontag", None),
    (39, "Auffahrt", None),
    (50, "Pfingstmontag", None),
    (60, "Fronleichnam", {"LU"}),
]


def ostersonntag(jahr: int) -> date:
    """Ostersonntag nach der anonymen gregorianischen Osterformel."""
    a = jahr % 19
    b, c = divmod(jahr, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    monat, tag = divmod(h + ell - 7 * m + 114, 31)
    return date(jahr, monat, tag + 1)


def _feiertage_aus_db(kanton: str, jahr: int, env: Optional[str] = None) -> Optional[dict]:
    """Feiertage aus ai_feiertage lesen. None falls Tabelle leer/fehlt."""
    try:
        rows = db.query(
            "SELECT datum, name FROM ai_feiertage "
            "WHERE kanton = %s AND YEAR(datum) = %s",
            (kanton, jahr), env=env,
        )
    except Exception:
        return None
    if not rows:
        return None
    return {r["datum"]: r["name"] for r in rows}


def _feiertage_berechnet(kanton: str, jahr: int) -> dict:
    """{datum: name} aller Feiertage eines Kantons (Fallback-Berechnung)."""
    treffer = {}
    for (monat, tag), (name, kantone) in _FIX.items():
        if kantone is None or kanton in kantone:
            treffer[date(jahr, monat, tag)] = name
    ostern = ostersonntag(jahr)
    for versatz, name, kantone in _BEWEGLICH:
        if kantone is None or kanton in kantone:
            treffer[ostern + timedelta(days=versatz)] = name
    return treffer


@lru_cache(maxsize=256)
def feiertage(kanton: str, jahr: int) -> dict:
    """{datum: name} aller Feiertage eines Kantons. Nicht veraendern (gecacht)."""
    aus_db = _feiertage_aus_db(kanton, jahr)
    if aus_db is not None:
        return aus_db
    return _feiertage_berechnet(kanton, jahr)


def ist_feiertag(kanton: str, tag: date) -> bool:
    return tag in feiertage(kanton, tag.year)


def ist_brueckentag(kanton: str, tag: date) -> bool:
    """Arbeitstag, der zwischen einem Feiertag und dem Wochenende klemmt.

    Also der Freitag nach einem Donnerstag-Feiertag (Auffahrt!) und der Montag
    vor einem Dienstag-Feiertag. Solche Tage sind verkehrlich halbe Feiertage.
    """
    if tag.weekday() > 4 or ist_feiertag(kanton, tag):
        return False
    if tag.weekday() == 4:  # Freitag
        return ist_feiertag(kanton, tag - timedelta(days=1))
    if tag.weekday() == 0:  # Montag
        return ist_feiertag(kanton, tag + timedelta(days=1))
    return False


# --- Schulferien ------------------------------------------------------------

@lru_cache(maxsize=1)
def _ferien_datei() -> dict:
    if not FERIEN_DATEI.is_file():
        logger.info("Keine Schulferien-Datei (%s) - es gilt die Naeherung",
                    FERIEN_DATEI)
        return {}
    try:
        roh = json.loads(FERIEN_DATEI.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("Schulferien-Datei nicht lesbar - es gilt die Naeherung",
                       exc_info=True)
        return {}
    return {k: v for k, v in roh.items() if not k.startswith("_")}


def _montag_der_woche(jahr: int, kalenderwoche: int) -> date:
    return date.fromisocalendar(jahr, kalenderwoche, 1)


def _naeherung(jahr: int) -> list:
    """Grobe, kantonsunabhaengige Ferienbereiche als Rueckfallebene.

    Bewusst konservativ: die Sommer- und Weihnachtsferien liegen schweizweit
    aehnlich, Sport- und Herbstferien schwanken um ein bis zwei Wochen.
    """
    ostern = ostersonntag(jahr)
    bereiche = [
        # Sportferien: zwei Wochen ab der 6. Kalenderwoche
        (_montag_der_woche(jahr, 6), _montag_der_woche(jahr, 6) + timedelta(days=13)),
        # Fruehlingsferien: zwei Wochen ab dem Montag nach Ostern
        (ostern + timedelta(days=1), ostern + timedelta(days=14)),
        # Sommerferien: ca. Mitte Juli bis Mitte August
        (date(jahr, 7, 8), date(jahr, 8, 16)),
        # Herbstferien: zwei Wochen ab dem Montag nach dem 26. September
        (date(jahr, 9, 26), date(jahr, 10, 10)),
        # Weihnachtsferien
        (date(jahr, 12, 22), date(jahr, 12, 31)),
        (date(jahr, 1, 1), date(jahr, 1, 3)),
    ]
    return bereiche


def _schulferien_aus_db(kanton: str, jahr: int, env: Optional[str] = None) -> Optional[tuple]:
    """Schulferien aus ai_schulferien lesen. None falls Tabelle leer/fehlt."""
    try:
        rows = db.query(
            "SELECT von, bis FROM ai_schulferien "
            "WHERE kanton = %s AND jahr = %s ORDER BY von",
            (kanton, jahr), env=env,
        )
    except Exception:
        return None
    if not rows:
        return None
    return tuple((r["von"], r["bis"]) for r in rows)


@lru_cache(maxsize=256)
def schulferien(kanton: str, jahr: int) -> tuple:
    """((von, bis), ...) der Schulferien - DB, dann JSON, dann Naeherung."""
    aus_db = _schulferien_aus_db(kanton, jahr)
    if aus_db is not None:
        return aus_db
    eintrag = _ferien_datei().get(kanton, {}).get(str(jahr))
    if eintrag:
        bereiche = []
        for von, bis in eintrag:
            try:
                bereiche.append((date.fromisoformat(von), date.fromisoformat(bis)))
            except ValueError:
                logger.warning("Ungueltiger Ferienbereich %s-%s (%s %s)",
                               von, bis, kanton, jahr)
        if bereiche:
            return tuple(bereiche)
    return tuple(_naeherung(jahr))


def ist_schulferien(kanton: str, tag: date) -> bool:
    return any(von <= tag <= bis for von, bis in schulferien(kanton, tag.year))


# --- Feature-Berechnung -----------------------------------------------------

SPALTEN = ["is_holiday", "is_bridge_day", "is_school_holiday"]


def _werte(stadt: str, tag: date) -> tuple:
    kanton = STADT_KANTON.get(stadt)
    if kanton is None:
        # Unbekannte Stadt: keine Annahme treffen. NaN ist ehrlicher als 0,
        # denn beide Modell-Bibliotheken behandeln fehlende Werte nativ.
        return (float("nan"),) * 3
    return (
        int(ist_feiertag(kanton, tag)),
        int(ist_brueckentag(kanton, tag)),
        int(ist_schulferien(kanton, tag)),
    )


def kalender_spalten(stadt: pd.Series, zeitpunkt: pd.Series) -> pd.DataFrame:
    """Feiertags-/Ferienspalten fuer (Stadt, Zeitpunkt), Index wie die Eingabe.

    Es gibt nur wenige verschiedene (Stadt, Datum)-Paare - fuer 120 Tage und
    fuenf Staedte rund 600 - deshalb wird pro Paar einmal gerechnet und dann
    zugeordnet, statt fuer jede der Hunderttausenden Zeilen.
    """
    tage = pd.to_datetime(zeitpunkt).dt.date
    paare = pd.DataFrame({"stadt": stadt.values, "tag": tage.values}).drop_duplicates()
    nachschlag = {
        (p.stadt, p.tag): _werte(p.stadt, p.tag) for p in paare.itertuples()
    }
    werte = [nachschlag[(s, t)] for s, t in zip(stadt.values, tage.values)]
    return pd.DataFrame(werte, columns=SPALTEN, index=stadt.index)


# --- DB-Sync ----------------------------------------------------------------

def sync_kalender_to_db(env: Optional[str] = None, jahre: Optional[list[int]] = None) -> dict:
    """Berechnete Feiertage und Schulferien in die DB schreiben (idempotent).

    Standardmaessig das aktuelle und das naechste Jahr. Ueberschreibt bestehende
    Eintraege nicht (INSERT IGNORE), damit manuelle Korrekturen erhalten bleiben.
    """
    if jahre is None:
        j = date.today().year
        jahre = [j, j + 1]

    n_ft, n_sf = 0, 0
    for kanton in STADT_KANTON.values():
        ft_rows = []
        sf_rows = []
        for jahr in jahre:
            for datum, name in _feiertage_berechnet(kanton, jahr).items():
                ft_rows.append((datum, kanton, name))
            for von, bis in _naeherung(jahr):
                sf_rows.append((kanton, jahr, von, bis, None))
            # JSON-Ferien bevorzugen, falls vorhanden
            eintrag = _ferien_datei().get(kanton, {}).get(str(jahr))
            if eintrag:
                sf_rows = [(kanton, jahr, date.fromisoformat(v), date.fromisoformat(b), None)
                           for v, b in eintrag]

        n_ft += db.executemany(
            "INSERT IGNORE INTO ai_feiertage (datum, kanton, name) VALUES (%s, %s, %s)",
            ft_rows, env=env,
        )
        n_sf += db.executemany(
            "INSERT IGNORE INTO ai_schulferien (kanton, jahr, von, bis, bezeichnung) "
            "VALUES (%s, %s, %s, %s, %s)",
            sf_rows, env=env,
        )

    feiertage.cache_clear()
    schulferien.cache_clear()
    logger.info("Kalender-Sync: %d Feiertage, %d Ferienperioden geschrieben", n_ft, n_sf)
    return {"feiertage": n_ft, "schulferien": n_sf}
