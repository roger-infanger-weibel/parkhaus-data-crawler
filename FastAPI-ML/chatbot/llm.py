"""Claude-API-Fallback fuer den Chatbot mit taeglichem Kostenlimit.

Nutzt Claude Haiku fuer kosteneffiziente Antworten auf Fragen, die der
regelbasierte Chatbot nicht versteht. Trackt Kosten pro Tag in der DB.
"""
import logging
import os
from datetime import date

import db

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
# Haiku pricing (USD per million tokens)
COST_INPUT_PER_M = 0.80
COST_OUTPUT_PER_M = 4.00
DAILY_LIMIT_USD = float(os.getenv("AI_CHAT_DAILY_LIMIT", "1.00"))
MAX_TOKENS = 300

_client = None
_initialized = False

SYSTEM_PROMPT = """\
Du bist der Parkhaus-Assistent für Schweizer Städte (Luzern, Basel, Bern, \
Zürich, St. Gallen). Du hilfst Benutzern mit Fragen rund ums Parkieren.

Regeln:
- Antworte immer auf Deutsch (Schweizer Hochdeutsch).
- Halte Antworten kurz (2-4 Sätze).
- Du hast Zugang zu Echtzeit-Parkhausdaten, Prognosen, Wetter und Events \
— aber nur über die strukturierten Befehle. Wenn der Benutzer nach \
konkreten Parkplatz-Daten fragt, empfehle ihm die passende Frage \
(z.B. "Frag mich: Wie viele Plätze sind in Luzern frei?").
- Beantworte allgemeine Fragen freundlich und hilfsbereit.
- Wenn du etwas nicht weisst, sag es ehrlich.
- Erwähne nie, dass du ein KI-Modell von Anthropic/Claude bist. \
Du bist der "Parkhaus-Assistent".
"""


def _init():
    global _client, _initialized
    if _initialized:
        return _client is not None
    _initialized = True
    try:
        import anthropic
        _client = anthropic.Anthropic()
        logger.info("Claude-API-Client initialisiert (Modell: %s)", MODEL)
        return True
    except Exception:
        logger.warning("Claude-API nicht verfügbar — kein ANTHROPIC_API_KEY?",
                       exc_info=True)
        return False


def _ensure_table(env: str):
    db.execute("""
        CREATE TABLE IF NOT EXISTS ai_chat_llm_usage (
            day DATE NOT NULL,
            input_tokens INT NOT NULL DEFAULT 0,
            output_tokens INT NOT NULL DEFAULT 0,
            requests INT NOT NULL DEFAULT 0,
            cost_usd DOUBLE NOT NULL DEFAULT 0,
            PRIMARY KEY (day)
        )
    """, env=env)


def _get_daily_cost(env: str) -> float:
    _ensure_table(env)
    rows = db.query(
        "SELECT cost_usd FROM ai_chat_llm_usage WHERE day = %s",
        (date.today(),), env=env,
    )
    return float(rows[0]["cost_usd"]) if rows else 0.0


def _record_usage(env: str, input_tokens: int, output_tokens: int):
    cost = (input_tokens * COST_INPUT_PER_M + output_tokens * COST_OUTPUT_PER_M) / 1_000_000
    _ensure_table(env)
    db.execute("""
        INSERT INTO ai_chat_llm_usage (day, input_tokens, output_tokens, requests, cost_usd)
        VALUES (%s, %s, %s, 1, %s)
        ON DUPLICATE KEY UPDATE
            input_tokens = input_tokens + VALUES(input_tokens),
            output_tokens = output_tokens + VALUES(output_tokens),
            requests = requests + 1,
            cost_usd = cost_usd + VALUES(cost_usd)
    """, (date.today(), input_tokens, output_tokens, cost), env=env)
    logger.info("LLM-Usage: +%d/%d tokens, +$%.4f (Tagessumme wird ~$%.4f)",
                input_tokens, output_tokens, cost, _get_daily_cost(env) + cost)


def ask(user_text: str, env: str, context: str = "") -> str | None:
    """Stellt eine Frage an Claude Haiku. Gibt None zurück bei Fehler/Limit."""
    if not _init():
        return None

    daily_cost = _get_daily_cost(env)
    if daily_cost >= DAILY_LIMIT_USD:
        logger.warning("Tageslimit erreicht: $%.2f >= $%.2f", daily_cost, DAILY_LIMIT_USD)
        return ("Ich habe mein tägliches Kontingent für ausführliche Antworten "
                "aufgebraucht. Bitte versuch es morgen wieder, oder stell mir "
                "eine konkrete Frage zu Parkplätzen, Wetter oder Events — "
                "diese kann ich immer beantworten!")

    system = SYSTEM_PROMPT
    if context:
        system += f"\n\nAktueller Kontext:\n{context}"

    try:
        response = _client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user_text}],
        )
        reply = response.content[0].text
        _record_usage(env, response.usage.input_tokens, response.usage.output_tokens)
        return reply
    except Exception:
        logger.exception("Claude-API-Aufruf fehlgeschlagen")
        return None
