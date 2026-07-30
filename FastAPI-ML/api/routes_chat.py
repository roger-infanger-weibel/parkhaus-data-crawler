from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api import get_env
from chatbot.engine import engine

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    session_id: str = Field(min_length=1, max_length=64)


@router.post("/chat")
def chat(req: ChatRequest, env: str = Depends(get_env)):
    resp = engine.answer(req.message, req.session_id, env)
    return {
        "reply": resp.reply,
        "intent": resp.intent,
        "entities": resp.entities,
        "payload": resp.payload,
    }
