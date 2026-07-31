"""Intent-Klassifikation: geordnete Regeln, erster Treffer gewinnt."""
import re

INTENTS = [
    ("greeting", r"\b(hallo|hi|hoi|gruezi|gruessech|guten\s+(tag|morgen|abend)|salue|salut)\b"),
    ("help", r"\b(hilfe|was kannst du|wie funktionier|anleitung|befehle)\b"),
    ("accuracy", r"\b(genau|zuverlaess|fehler|qualitaet|abweich|treffsicher|verlaesslich)\w*"),
    ("weather", r"\b(wetter|regen|regnet|temperatur|sonnig|schnee)\w*"),
    ("events", r"\b(event|veranstaltung|konzert|theater|festival|was (laeuft|los))\w*"),
    ("best_parking", r"\b(wo\s+(park|find|stell)|empfehl|bestes parkhaus|am besten park|welches parkhaus)\w*"),
    ("forecast", r"\b(prognose|vorhersage|voraussage|wie (voll|frei) wird|wird .{0,30}(frei|voll))\w*"),
    ("current", r"\b(frei|verfuegbar|plaetze|platz|belegt|offen|aktuell|status)\w*"),
]

# Intents, die zwingend eine Stadt (oder ein Parkhaus) brauchen
NEEDS_CITY = {"current", "forecast", "best_parking", "weather", "events"}


JETZT_TOLERANZ_MIN = 20


def _liegt_in_zukunft(entities: dict, now) -> bool:
    """Ist eine Zeitangabe da, die spuerbar in der Zukunft liegt?"""
    zeit = entities.get("time")
    if not zeit or zeit.get("at") is None or not zeit.get("explicit"):
        return False
    if now is None:
        return True
    return (zeit["at"] - now).total_seconds() > JETZT_TOLERANZ_MIN * 60


def classify(folded: str, entities: dict, now=None) -> str:
    for intent, pattern in INTENTS:
        if re.search(pattern, folded):
            # Eine Zeitangabe macht aus der Bestandsfrage eine Prognosefrage -
            # aber nur, wenn sie wirklich in der Zukunft liegt. "jetzt" und
            # "gerade" sind zwar ausdrueckliche Zeitangaben, gemeint ist aber
            # der Ist-Wert; eine Prognose fuer den aktuellen Moment waere
            # schlechter als die Messung selbst.
            if intent == "current" and _liegt_in_zukunft(entities, now):
                return "forecast"
            return intent
    # Kein Schluesselwort: Zeit + Stadt deutet auf Prognose/Empfehlung
    if _liegt_in_zukunft(entities, now) and entities.get("city"):
        return "best_parking"
    if entities.get("parkhaus"):
        return "current"
    return "fallback"
