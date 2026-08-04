"""FastAPI-App: Prognose, Genauigkeits-Monitoring und Chat-Assistent.

Start (aus dem Ordner FastAPI-ML):
    uvicorn main:app --host 0.0.0.0 --port 80 --workers 1
Wichtig: genau 1 Worker, damit der eingebaute Scheduler nur einmal existiert.
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import config
from api import routes_accuracy, routes_chat, routes_forecast, routes_meta

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if config.SCHEDULER_ENABLED:
        from jobs import scheduler
        scheduler.start()
    else:
        logger.info("Scheduler deaktiviert (AI_SCHEDULER_ENABLED=0)")
    yield
    if config.SCHEDULER_ENABLED:
        from jobs import scheduler
        scheduler.shutdown()


app = FastAPI(title="Parkhaus KI-Prognose", version="1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

app.include_router(routes_meta.router)
app.include_router(routes_forecast.router)
app.include_router(routes_accuracy.router)
app.include_router(routes_chat.router)

app.mount(
    "/", StaticFiles(directory=Path(__file__).parent / "static", html=True),
    name="static",
)
