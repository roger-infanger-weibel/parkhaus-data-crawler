"""Intent-Klassifikation inkl. Zeit-Umdeutung current -> forecast."""
from datetime import datetime

from chatbot.entities import extract, fold
from chatbot.intents import classify

NOW = datetime(2026, 7, 30, 11, 0)
MAPPING = [{"city": "luzern", "pls_id": "SP09", "pls_name": "Kesselturm"}]


def _classify(text):
    entities = extract(text, NOW, MAPPING)
    return classify(fold(text), entities), entities


def test_greeting():
    assert _classify("Hallo!")[0] == "greeting"


def test_accuracy():
    assert _classify("Wie genau sind deine Prognosen?")[0] == "accuracy"


def test_weather():
    assert _classify("Regnet es in Basel?")[0] == "weather"


def test_events():
    assert _classify("Welche Events laufen am Freitag in Zürich?")[0] == "events"


def test_best_parking():
    assert _classify("Wo parke ich morgen um 19 Uhr in Luzern?")[0] == "best_parking"


def test_current_becomes_forecast_with_time():
    intent, _ = _classify("Wie viele Plätze sind in 2 Stunden in Basel frei?")
    assert intent == "forecast"


def test_current_stays_current_without_time():
    intent, _ = _classify("Wie viele Plätze sind in Basel frei?")
    assert intent == "current"


def test_fallback():
    assert _classify("blabla xyz")[0] == "fallback"
