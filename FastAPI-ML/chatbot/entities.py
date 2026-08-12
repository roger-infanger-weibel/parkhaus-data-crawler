"""Entitaeten-Extraktion: Stadt, Parkhaus (fuzzy), deutsche Zeitausdruecke."""
import re
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Optional

from core.identity import normalize_name, normalize_wordset

CITY_KEYWORDS = {
    "luzern": ["luzern"],
    "basel": ["basel"],
    "bern": ["bern"],
    "zurich": ["zuerich", "zurich", "zueri", "zh"],
    "stgallen": ["st. gallen", "st gallen", "stgallen", "sankt gallen", "st.gallen", "sg"],
}

WEEKDAYS = {
    "montag": 0, "dienstag": 1, "mittwoch": 2, "donnerstag": 3,
    "freitag": 4, "samstag": 5, "sonntag": 6,
}

DAYTIME_HOURS = {
    "frueh": 8, "morgens": 8, "vormittag": 10, "mittag": 12,
    "nachmittag": 15, "abend": 19, "abends": 19, "nacht": 22,
}


def fold(text: str) -> str:
    """Kleinbuchstaben + Umlaut-Faltung fuer robustes Matching."""
    return (
        text.lower()
        .replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    )


def extract_city(folded: str) -> Optional[str]:
    for city, keywords in CITY_KEYWORDS.items():
        for kw in keywords:
            if re.search(r"\b" + re.escape(kw) + r"\b", folded):
                return city
    return None


def extract_time(folded: str, now: datetime) -> Optional[dict]:
    """Zielzeitpunkt aus deutschem Text.

    Liefert {'at': datetime, 'explicit': bool} oder None, wenn kein
    Zeitausdruck erkannt wurde. 'explicit' = Uhrzeit war ausdrueckliches
    Element ("um 19 uhr", "in 2 stunden") und nicht nur Tageszeit-Default.
    """
    # relativ: "in 2 stunden", "in 30 minuten"
    m = re.search(r"\bin\s+(\d+(?:[.,]\d+)?)\s*(stunden?|std|h|minuten?|min)\b", folded)
    if m:
        value = float(m.group(1).replace(",", "."))
        minutes = value * 60 if m.group(2).startswith(("stunde", "std", "h")) else value
        return {"at": now + timedelta(minutes=minutes), "explicit": True}

    if re.search(r"\b(jetzt|gerade|aktuell|im moment)\b", folded):
        return {"at": now, "explicit": True}

    MONTH_NAMES = {
        "januar": 1, "februar": 2, "maerz": 3, "april": 4, "mai": 5,
        "juni": 6, "juli": 7, "august": 8, "september": 9, "oktober": 10,
        "november": 11, "dezember": 12,
    }

    # Tag bestimmen
    day = None

    # "14.8.", "14.08.", "14.8.2026", "14. august"
    m_date = re.search(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})?(?:\b|(?=\s|$))", folded)
    if not m_date:
        m_date = re.search(
            r"\b(\d{1,2})\.\s*(" + "|".join(MONTH_NAMES) + r")\b", folded)
        if m_date:
            d, mon = int(m_date.group(1)), MONTH_NAMES[m_date.group(2)]
            yr = now.year
            candidate = now.date().replace(month=mon, day=d)
            if candidate < now.date():
                yr += 1
            try:
                day = now.date().replace(year=yr, month=mon, day=d)
            except ValueError:
                pass
    if m_date and day is None and m_date.lastindex and m_date.group(2).isdigit():
        d, mon = int(m_date.group(1)), int(m_date.group(2))
        yr = int(m_date.group(3)) if m_date.lastindex >= 3 and m_date.group(3) else now.year
        try:
            candidate = now.date().replace(year=yr, month=mon, day=d)
            if candidate < now.date() and not (m_date.lastindex >= 3 and m_date.group(3)):
                yr += 1
            day = now.date().replace(year=yr, month=mon, day=d)
        except ValueError:
            pass

    if day is None and re.search(r"\buebermorgen\b", folded):
        day = now.date() + timedelta(days=2)
    elif day is None and re.search(r"\bmorgen\b", folded) and not re.search(r"\bmorgens\b", folded):
        day = now.date() + timedelta(days=1)
    elif day is None and re.search(r"\bheute\b", folded):
        day = now.date()
    elif day is None:
        for name, wd in WEEKDAYS.items():
            if re.search(r"\b(am\s+)?" + name + r"\b", folded):
                ahead = (wd - now.weekday()) % 7
                if ahead == 0:
                    ahead = 7  # "am Freitag" an einem Freitag = naechster Freitag
                day = now.date() + timedelta(days=ahead)
                break

    # Uhrzeit bestimmen
    hour, minute, explicit = None, 0, False
    m = re.search(r"\bum\s+(\d{1,2})(?:[:.](\d{2}))?\s*(?:uhr)?\b", folded)
    if not m:
        m = re.search(r"\b(\d{1,2})(?:[:.](\d{2}))?\s*uhr\b", folded)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        explicit = True
    else:
        for word, h in DAYTIME_HOURS.items():
            if re.search(r"\b" + word + r"\b", folded):
                hour = h
                break

    if day is None and hour is None:
        return None
    if day is None:
        day = now.date()
        # "um 19 uhr" nach 19 Uhr gemeint als morgen
        if datetime.combine(day, datetime.min.time()).replace(hour=hour, minute=minute) < now:
            day = day + timedelta(days=1)
    if hour is None:
        hour = 12  # nur Tag genannt -> Mittag als Default

    return {
        "at": datetime.combine(day, datetime.min.time()).replace(hour=hour, minute=minute),
        "explicit": explicit,
    }


def extract_parkhaus(folded: str, mapping: list[dict],
                     city: Optional[str] = None) -> Optional[dict]:
    """Fuzzy-Match des Textes gegen die Parkhaus-Namen aus ai_parkhaus_map.

    Verglichen werden nur unterscheidungskraeftige Wortstaemme (ohne
    "Parkhaus", "Parking", Stadtnamen usw.), damit "das Parkhaus Bahnhof"
    nicht faelschlich irgendein beliebiges "Parkhaus X" trifft.
    """
    candidates = [m for m in mapping if city is None or m["city"] == city]
    norm_text = normalize_name(folded)
    text_words = normalize_wordset(folded)

    best, best_score = None, 0.0
    for m in candidates:
        name_words = normalize_wordset(m["pls_name"])
        if not name_words:
            continue
        norm_name = normalize_name(m["pls_name"])
        if len(norm_name) >= 5 and norm_name in norm_text:
            score = 2.0 + len(norm_name) / 100  # ganzer Name im Text
        else:
            matched = 0
            for nw in name_words:
                if nw in text_words:
                    matched += 1
                elif len(nw) >= 5 and any(
                        SequenceMatcher(None, nw, tw).ratio() >= 0.85
                        for tw in text_words if len(tw) >= 4):
                    matched += 1  # Tippfehler-tolerant
            if matched == 0:
                continue
            score = matched / len(name_words) + matched / 10
        if score > best_score:
            best, best_score = m, score
    if best is not None and best_score >= 0.5:
        return {"city": best["city"], "pls_id": best["pls_id"],
                "name": best["pls_name"]}
    return None


def extract_min_free(folded: str) -> Optional[int]:
    m = re.search(r"\bmindestens\s+(\d+)\b", folded)
    return int(m.group(1)) if m else None


def extract(text: str, now: datetime, mapping: list[dict]) -> dict:
    folded = fold(text)
    city = extract_city(folded)
    parkhaus = extract_parkhaus(folded, mapping, city)
    if parkhaus and not city:
        city = parkhaus["city"]
    return {
        "city": city,
        "parkhaus": parkhaus,
        "time": extract_time(folded, now),
        "min_free": extract_min_free(folded),
    }
