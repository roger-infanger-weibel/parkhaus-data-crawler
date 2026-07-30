"""Identity-Mapping mit echten Namenspaaren aus der Datenbank."""
from core.identity import match_parkhaus, normalize_name, normalize_wordset

BASEL = [{"id": "baselparkhausaeschen", "name": "Basel Parkhaus Aeschen"}]
LUZERN = [
    {"id": "luzernparkhauskantonalbank", "name": "Luzern Parkhaus Kantonalbank"},
    {"id": "luzernparkhausaltstadt", "name": "Luzern Parkhaus Altstadt"},
]
BERN = [
    {"id": "bernparkhausbahnhof", "name": "Bern Parkhaus Bahnhof"},
    {"id": "bernparkhauscasino", "name": "Bern Parkhaus Casino"},
    {"id": "bernparkhausmetro", "name": "Bern Parkhaus Metro"},
]
STGALLEN = [{"id": "stgallenparkhausbahnhof", "name": "St. Gallen Parkhaus Bahnhof"}]


def test_normalize_name_folds_umlauts():
    assert normalize_name("Gütsch") == normalize_name("Guetsch")
    assert normalize_name("Bad. Bahnhof") == "badbahnhof"


def test_wordset_strips_generic_parts():
    assert normalize_wordset("Casinoparking") == frozenset({"casino"})
    assert normalize_wordset("Bern Parkhaus Bahnhof") == frozenset({"bahnhof"})


def test_basel_exact_id():
    ph_id, method = match_parkhaus("baselparkhausaeschen", "Aeschen", BASEL)
    assert (ph_id, method) == ("baselparkhausaeschen", "id")


def test_luzern_containment():
    ph_id, method = match_parkhaus("SP03", "Kantonalbank", LUZERN)
    assert (ph_id, method) == ("luzernparkhauskantonalbank", "contain")


def test_bern_reversed_word_order():
    ph_id, method = match_parkhaus("p01", "Bahnhof Parking", BERN)
    assert (ph_id, method) == ("bernparkhausbahnhof", "wordset")


def test_bern_casinoparking_single_word():
    ph_id, method = match_parkhaus("p06", "Casinoparking", BERN)
    assert (ph_id, method) == ("bernparkhauscasino", "wordset")


def test_stgallen_cityparking():
    ph_id, method = match_parkhaus("24", "Cityparking Bahnhof", STGALLEN)
    assert ph_id == "stgallenparkhausbahnhof"


def test_unmatched_returns_none():
    ph_id, method = match_parkhaus("p10", "Kursaal Parking", BERN)
    assert (ph_id, method) == (None, "none")
