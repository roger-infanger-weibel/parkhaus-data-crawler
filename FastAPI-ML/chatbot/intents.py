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


def classify(folded: str, entities: dict) -> str:
    for intent, pattern in INTENTS:
        if re.search(pattern, folded):
            # Zeitangabe macht aus einer Bestandsfrage eine Prognosefrage
            if intent == "current" and entities.get("time") \
                    and entities["time"]["at"] is not None and entities["time"]["explicit"]:
                return "forecast"
            return intent
    # Kein Schluesselwort: Zeit + Stadt deutet auf Prognose/Empfehlung
    if entities.get("time") and entities.get("city"):
        return "best_parking"
    if entities.get("parkhaus"):
        return "current"
    return "fallback"
