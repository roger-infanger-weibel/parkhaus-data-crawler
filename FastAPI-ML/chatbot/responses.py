"""Deutsche Antwort-Texte und Formatierungshelfer."""
from datetime import datetime

CITY_NAMES = {
    "luzern": "Luzern", "basel": "Basel", "bern": "Bern",
    "zurich": "Zürich", "stgallen": "St. Gallen",
}

HELP_TEXT = (
    "Ich bin der Parkhaus-Assistent für Luzern, Basel, Bern, Zürich und St. Gallen. "
    "Du kannst mich zum Beispiel fragen:\n"
    "• «Wo parke ich morgen um 19 Uhr in Luzern?»\n"
    "• «Wie viele Plätze sind jetzt in Basel frei?»\n"
    "• «Wie voll wird das Parkhaus Bahnhof in 2 Stunden?»\n"
    "• «Wie ist das Wetter in Bern?»\n"
    "• «Welche Events laufen am Freitag in Zürich?»\n"
    "• «Wie genau sind deine Prognosen?»"
)

GREETINGS = [
    "Hallo! " + HELP_TEXT,
]

ASK_CITY = (
    "Für welche Stadt möchtest du das wissen? "
    "(Luzern, Basel, Bern, Zürich oder St. Gallen)"
)

FALLBACK = (
    "Das habe ich leider nicht verstanden. " + HELP_TEXT
)


def city_name(city: str) -> str:
    return CITY_NAMES.get(city, city)


def fmt_time(dt: datetime, now: datetime) -> str:
    """'heute 19:00', 'morgen 08:30', 'Freitag, 01.08. 19:00'."""
    clock = dt.strftime("%H:%M")
    delta_days = (dt.date() - now.date()).days
    if delta_days == 0:
        return f"heute {clock}"
    if delta_days == 1:
        return f"morgen {clock}"
    weekdays = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
                "Freitag", "Samstag", "Sonntag"]
    return f"{weekdays[dt.weekday()]}, {dt.strftime('%d.%m.')} {clock}"
