"""Gemini-API-Fallback fuer den Chatbot (kostenloses Kontingent).

Nutzt Gemini Flash fuer intelligente Antworten auf Fragen, die der
regelbasierte Chatbot nicht versteht. Trackt Nutzung pro Tag in der DB.
"""
import logging
import os
from datetime import date

import db

logger = logging.getLogger(__name__)

MODEL = "gemini-3.6-flash"
DAILY_REQUEST_LIMIT = int(os.getenv("AI_CHAT_DAILY_LIMIT", "1500"))
MAX_TOKENS = 500

_model = None
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
- Erwähne nie, dass du ein KI-Modell von Google bist. \
Du bist der "Parkhaus-Assistent".
"""


def _init():
    global _model, _initialized
    if _initialized:
        return _model is not None
    _initialized = True
    try:
        from google import genai
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            logger.warning("GEMINI_API_KEY nicht gesetzt — LLM-Fallback deaktiviert")
            return False
        client = genai.Client(api_key=api_key)
        _model = client
        logger.info("Gemini-API-Client initialisiert (Modell: %s)", MODEL)
        return True
    except Exception:
        logger.warning("Gemini-API nicht verfügbar", exc_info=True)
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


def _get_daily_requests(env: str) -> int:
    _ensure_table(env)
    rows = db.query(
        "SELECT requests FROM ai_chat_llm_usage WHERE day = %s",
        (date.today(),), env=env,
    )
    return int(rows[0]["requests"]) if rows else 0


def _record_usage(env: str, input_tokens: int, output_tokens: int):
    _ensure_table(env)
    db.execute("""
        INSERT INTO ai_chat_llm_usage (day, input_tokens, output_tokens, requests, cost_usd)
        VALUES (%s, %s, %s, 1, 0)
        ON DUPLICATE KEY UPDATE
            input_tokens = input_tokens + VALUES(input_tokens),
            output_tokens = output_tokens + VALUES(output_tokens),
            requests = requests + 1
    """, (date.today(), input_tokens, output_tokens), env=env)
    logger.info("LLM-Usage: +%d/%d tokens, Request #%d heute",
                input_tokens, output_tokens, _get_daily_requests(env))


def ask(user_text: str, env: str, context: str = "") -> str | None:
    if not _init():
        return None

    daily_reqs = _get_daily_requests(env)
    if daily_reqs >= DAILY_REQUEST_LIMIT:
        logger.warning("Tageslimit erreicht: %d >= %d Requests", daily_reqs, DAILY_REQUEST_LIMIT)
        return ("Ich habe mein tägliches Kontingent für ausführliche Antworten "
                "aufgebraucht. Bitte versuch es morgen wieder, oder stell mir "
                "eine konkrete Frage zu Parkplätzen, Wetter oder Events — "
                "diese kann ich immer beantworten!")

    system = SYSTEM_PROMPT
    if context:
        system += f"\n\nAktueller Kontext:\n{context}"

    try:
        from google.genai import types
        response = _model.models.generate_content(
            model=MODEL,
            contents=user_text,
            config=types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=MAX_TOKENS,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=True,
                ),
            ),
        )
        reply = response.text
        usage = response.usage_metadata
        in_tok = usage.prompt_token_count or 0
        out_tok = usage.candidates_token_count or 0
        _record_usage(env, in_tok, out_tok)
        return reply
    except Exception:
        logger.exception("Gemini-API-Aufruf fehlgeschlagen")
        return None
