"""ChatEngine-Fassade. RuleBasedEngine = aktuelle Implementierung ohne LLM."""
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import db
from core import data_access as da
from core.timeutil import now_local
from chatbot import entities as E
from chatbot import intents as I
from chatbot import responses as R
from chatbot.handlers import HANDLERS

logger = logging.getLogger(__name__)

SESSION_TTL = 15 * 60  # Slot-Filling-Kontext 15 Minuten behalten
MAPPING_TTL = 10 * 60


@dataclass
class ChatResponse:
    reply: str
    intent: str
    entities: dict
    payload: Optional[dict] = None


@dataclass
class _Session:
    pending_intent: Optional[str] = None
    entities: dict = field(default_factory=dict)
    updated: float = field(default_factory=time.time)


class ChatEngine:
    def answer(self, text: str, session_id: str, env: str) -> ChatResponse:
        raise NotImplementedError


class RuleBasedEngine(ChatEngine):
    def __init__(self):
        self._sessions: dict[str, _Session] = {}
        self._mapping_cache: dict[str, tuple[float, list[dict]]] = {}

    def _mapping(self, env: str) -> list[dict]:
        ts_rows = self._mapping_cache.get(env)
        if ts_rows and time.time() - ts_rows[0] < MAPPING_TTL:
            return ts_rows[1]
        rows = da.get_mapping(env=env)
        self._mapping_cache[env] = (time.time(), rows)
        return rows

    def _session(self, session_id: str) -> _Session:
        s = self._sessions.get(session_id)
        if s is None or time.time() - s.updated > SESSION_TTL:
            s = _Session()
            self._sessions[session_id] = s
        s.updated = time.time()
        return s

    def answer(self, text: str, session_id: str, env: str) -> ChatResponse:
        now = now_local()
        folded = E.fold(text)
        entities = E.extract(text, now, self._mapping(env))
        session = self._session(session_id)

        intent = I.classify(folded, entities, now, raw_text=text)

        # Slot-Filling: vorher fehlte die Stadt, jetzt kam nur "Luzern" o.ae.
        if session.pending_intent and entities.get("city") and intent in ("fallback", "current"):
            only_city = len(folded.split()) <= 3
            if only_city:
                intent = session.pending_intent
                merged = dict(session.entities)
                merged.update({k: v for k, v in entities.items() if v is not None})
                entities = merged
        session.pending_intent = None

        # Stadt noetig, aber keine erkannt -> nachfragen und Intent merken
        if intent in I.NEEDS_CITY and not entities.get("city"):
            session.pending_intent = intent
            session.entities = entities
            reply = R.ASK_CITY
            self._log(env, session_id, text, intent, entities, reply)
            return ChatResponse(reply, intent, self._entities_out(entities), None)

        handler = HANDLERS.get(intent, HANDLERS["fallback"])
        try:
            reply, payload = handler(env, entities, now)
        except Exception:
            logger.exception("Chat-Handler '%s' fehlgeschlagen", intent)
            reply, payload = (
                "Entschuldigung, da ist etwas schiefgelaufen. Versuche es bitte nochmals.",
                None,
            )
        self._log(env, session_id, text, intent, entities, reply)
        return ChatResponse(reply, intent, self._entities_out(entities), payload)

    @staticmethod
    def _entities_out(entities: dict) -> dict:
        out = dict(entities)
        if out.get("time"):
            out["time"] = {"at": out["time"]["at"].isoformat(),
                           "explicit": out["time"]["explicit"]}
        return out

    def _log(self, env, session_id, text, intent, entities, reply) -> None:
        try:
            db.execute(
                """
                INSERT INTO ai_chat_log (ts, session_id, user_text, intent,
                                         entities_json, bot_text)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (now_local(), session_id[:64], text[:2000], intent,
                 json.dumps(self._entities_out(entities), default=str)[:2000],
                 reply[:4000]),
                env=env,
            )
        except Exception:
            logger.warning("Chat-Log konnte nicht geschrieben werden", exc_info=True)


engine = RuleBasedEngine()
