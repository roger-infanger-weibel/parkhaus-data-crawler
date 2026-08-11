"""Semantische Intent-Klassifikation mit Sentence-Transformers.

Lädt ein kleines multilinguales Modell (~120 MB RAM) und vergleicht den
User-Input per Cosinus-Ähnlichkeit mit vordefinierten Beispielsätzen pro
Intent. Versteht damit auch Umschreibungen, Tippfehler und natürliche
Formulierungen — deutlich robuster als reine Regex-Patterns.

Fallback: ist sentence-transformers nicht installiert, liefert classify()
None und der Aufrufer nutzt die Regex-Logik.
"""
import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
MIN_CONFIDENCE = 0.45

EXAMPLES: dict[str, list[str]] = {
    "greeting": [
        "hallo", "hi", "guten tag", "grüezi", "hoi", "guten morgen",
        "guten abend", "salut", "servus", "hey",
    ],
    "help": [
        "hilfe", "was kannst du", "wie funktioniert das",
        "was kann ich fragen", "anleitung", "befehle",
        "welche funktionen hast du", "erkläre mir was du kannst",
    ],
    "accuracy": [
        "wie genau sind deine prognosen",
        "wie zuverlässig ist die vorhersage",
        "wie gross ist der fehler",
        "wie gut sind die vorhersagen",
        "treffsicherheit der prognose",
        "stimmen deine vorhersagen",
        "qualität der prognosen",
        "wie verlässlich bist du",
        "kannst du das auch wirklich vorhersagen",
        "wie oft liegst du daneben",
    ],
    "weather": [
        "wie ist das wetter", "wetter in luzern",
        "regnet es morgen", "wird es regnen",
        "temperatur am freitag", "sonnig oder bewölkt",
        "brauche ich einen regenschirm",
        "wie warm wird es", "schneit es",
    ],
    "events": [
        "welche events gibt es", "veranstaltungen am freitag",
        "was läuft am wochenende", "konzerte in zürich",
        "gibt es veranstaltungen heute",
        "was ist los in basel", "events am samstag",
        "spielt die tonhalle heute abend",
        "irgendwelche events in der nähe",
        "was findet statt",
    ],
    "best_parking": [
        "wo parke ich am besten", "welches parkhaus empfiehlst du",
        "wo finde ich einen platz", "bestes parkhaus in bern",
        "wo soll ich parkieren", "empfehlung für ein parkhaus",
        "wo hat es noch platz", "lohnt sich das parkhaus bahnhof",
        "wohin soll ich fahren zum parkieren",
        "welches parkhaus ist am freiesten",
        "gib mir einen parkplatz tipp",
        "wo finde ich abends um 20 uhr einen parkplatz in zürich",
    ],
    "forecast": [
        "wie voll wird es morgen",
        "prognose für das parkhaus steinen",
        "wird es heute abend noch frei",
        "vorhersage für morgen um 19 uhr",
        "wie viele plätze werden frei sein",
        "wird das parkhaus voll sein",
        "hat es morgen mittag noch platz im bahnhof parking",
        "wie sieht es morgen nachmittag im kesselturm aus",
        "wird es am samstag voll in zürich",
    ],
    "current": [
        "wie viele plätze sind frei",
        "aktueller stand",
        "verfügbare plätze in luzern",
        "gibt es noch freie parkplätze",
        "ist das parkhaus voll",
        "wie voll ist es jetzt",
        "status parkhaus bahnhof",
        "kann ich jetzt noch parkieren",
        "sind noch plätze frei",
        "hat es platz im parkhaus city",
        "belegung parkhaus steinen",
    ],
}

_model = None
_embeddings: Optional[np.ndarray] = None
_labels: Optional[list[str]] = None


def _load():
    global _model, _embeddings, _labels
    if _model is not None:
        return True
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        logger.info("sentence-transformers nicht installiert — Regex-Fallback aktiv")
        return False

    logger.info("Lade Sentence-Transformer '%s' ...", MODEL_NAME)
    _model = SentenceTransformer(MODEL_NAME)

    all_sentences = []
    _labels = []
    for intent, examples in EXAMPLES.items():
        for ex in examples:
            all_sentences.append(ex)
            _labels.append(intent)

    _embeddings = _model.encode(all_sentences, normalize_embeddings=True,
                                show_progress_bar=False)
    logger.info("Semantic classifier bereit: %d Beispielsätze, %d Intents",
                len(all_sentences), len(EXAMPLES))
    return True


def classify(text: str) -> Optional[tuple[str, float]]:
    """Intent + Konfidenz, oder None wenn Modell nicht verfügbar.

    Liefert (intent, score) wobei score ∈ [0, 1].
    Bei score < MIN_CONFIDENCE wird None zurückgegeben (→ Regex-Fallback).
    """
    if not _load():
        return None

    query = _model.encode([text], normalize_embeddings=True, show_progress_bar=False)
    scores = (query @ _embeddings.T).flatten()
    best_idx = int(np.argmax(scores))
    best_score = float(scores[best_idx])

    if best_score < MIN_CONFIDENCE:
        return None

    return _labels[best_idx], best_score
