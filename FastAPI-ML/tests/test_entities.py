"""Deutsche Zeitausdruecke und Entitaeten-Extraktion (tabellengetrieben)."""
from datetime import datetime

import pytest

from chatbot.entities import extract_city, extract_parkhaus, extract_time, fold

NOW = datetime(2026, 7, 30, 11, 0)  # Donnerstag

TIME_CASES = [
    ("morgen um 19 uhr", datetime(2026, 7, 31, 19, 0)),
    ("in 2 stunden", datetime(2026, 7, 30, 13, 0)),
    ("in 30 minuten", datetime(2026, 7, 30, 11, 30)),
    ("heute mittag", datetime(2026, 7, 30, 12, 0)),
    ("heute abend", datetime(2026, 7, 30, 19, 0)),
    ("am freitag abend", datetime(2026, 7, 31, 19, 0)),
    ("am donnerstag", datetime(2026, 8, 6, 12, 0)),  # heute Do -> naechster Do
    ("um 9 uhr", datetime(2026, 7, 30, 12, 0)),      # nur Stunden-Check unten
    ("uebermorgen frueh", datetime(2026, 8, 1, 8, 0)),
    ("morgen um 8:30", datetime(2026, 7, 31, 8, 30)),
]


@pytest.mark.parametrize("text,expected", TIME_CASES)
def test_extract_time(text, expected):
    result = extract_time(fold(text), NOW)
    assert result is not None, text
    if text == "um 9 uhr":
        # 9 Uhr ist heute schon vorbei -> morgen 9 Uhr
        assert result["at"] == datetime(2026, 7, 31, 9, 0)
    else:
        assert result["at"] == expected, text


def test_no_time_returns_none():
    assert extract_time(fold("Wie viele Plätze sind frei?"), NOW) is None


@pytest.mark.parametrize("text,city", [
    ("parkplatz in luzern", "luzern"),
    ("Wetter in St. Gallen", "stgallen"),
    ("Zürich HB", "zurich"),
    ("was läuft in basel", "basel"),
    ("hallo", None),
])
def test_extract_city(text, city):
    assert extract_city(fold(text)) == city


MAPPING = [
    {"city": "luzern", "pls_id": "SP03", "pls_name": "Kantonalbank"},
    {"city": "luzern", "pls_id": "NP01", "pls_name": "Bahnhofparking P3"},
    {"city": "luzern", "pls_id": "SP09", "pls_name": "Kesselturm"},
    {"city": "luzern", "pls_id": "SP11", "pls_name": "Flora"},
]


def test_parkhaus_exact_word():
    hit = extract_parkhaus(fold("Wie voll ist das Parkhaus Kesselturm?"), MAPPING)
    assert hit and hit["pls_id"] == "SP09"


def test_parkhaus_generic_word_alone_matches_nothing():
    assert extract_parkhaus(fold("Wo ist ein Parkhaus?"), MAPPING) is None


def test_parkhaus_partial_name():
    hit = extract_parkhaus(fold("das parkhaus bahnhof in luzern"), MAPPING, "luzern")
    assert hit and hit["pls_id"] == "NP01"


def test_parkhaus_typo_tolerance():
    hit = extract_parkhaus(fold("wie voll ist das kesseltrum"), MAPPING)
    assert hit and hit["pls_id"] == "SP09"
