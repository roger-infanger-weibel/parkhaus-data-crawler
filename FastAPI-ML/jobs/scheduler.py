"""APScheduler-Jobs, gestartet im FastAPI-Lifespan (uvicorn --workers 1).

Zeitplan (der Scanner schreibt alle 15 Min, sein Offset kann driften -
predict hat deshalb einen Fallback auf den letzten Slot mit Daten):
  predict   :10/:25/:40/:55   Prognosen erzeugen
  evaluate  :13/:28/:43/:58   gereifte Prognosen gegen Ist-Werte matchen
  mapping   03:15             ai_parkhaus_map aktualisieren
  retrain   03:30             Modelle neu trainieren
"""
import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import config
from core.timeutil import SWISS_TZ, now_local

logger = logging.getLogger(__name__)

_scheduler: Optional[AsyncIOScheduler] = None
_last_runs: dict[str, dict] = {}


def _wrap(name: str, fn):
    """Jobs duerfen die App nie zum Absturz bringen."""
    def runner():
        # now_local statt datetime.now: auf einem UTC-Server waere die in
        # /api/health gezeigte Laufzeit sonst 2 Stunden neben allen anderen
        # Zeitangaben der App.
        started = now_local()
        try:
            result = fn()
            _last_runs[name] = {"at": started.isoformat(), "ok": True,
                                "result": str(result)[:200]}
        except Exception as exc:
            logger.exception("Job '%s' fehlgeschlagen", name)
            _last_runs[name] = {"at": started.isoformat(), "ok": False,
                                "error": str(exc)[:500]}
    return runner


def start() -> AsyncIOScheduler:
    global _scheduler
    from core.identity import build_mapping
    from forecast import evaluate, predict, train

    env = config.DEFAULT_ENV
    sched = AsyncIOScheduler(
        timezone=SWISS_TZ,
        job_defaults={"misfire_grace_time": 300, "coalesce": True, "max_instances": 1},
    )
    # Zeitzone explizit: der Server laeuft auf UTC, die Daten und now_local()
    # aber auf Europe/Zurich - ohne das liefe das naechtliche Training um
    # 05:30 statt 03:30 Ortszeit.
    sched.add_job(_wrap("predict", lambda: predict.run(env)),
                  CronTrigger(minute="10,25,40,55", timezone=SWISS_TZ), id="predict")
    sched.add_job(_wrap("evaluate", lambda: evaluate.run(env)),
                  CronTrigger(minute="13,28,43,58", timezone=SWISS_TZ), id="evaluate")
    sched.add_job(_wrap("mapping", lambda: build_mapping(env)),
                  CronTrigger(hour=3, minute=15, timezone=SWISS_TZ), id="mapping")
    if config.RETRAIN_ENABLED:
        sched.add_job(_wrap("retrain", lambda: train.run(env, config.TRAIN_DAYS)),
                      CronTrigger(hour=3, minute=30, timezone=SWISS_TZ), id="retrain")
    else:
        logger.info("Naechtliches Training deaktiviert (AI_RETRAIN_ENABLED=0)")
    sched.start()
    _scheduler = sched
    logger.info("Scheduler gestartet (env=%s)", env)
    return sched


def shutdown() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def job_states() -> dict:
    states = {}
    if _scheduler:
        for job in _scheduler.get_jobs():
            states[job.id] = {
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "last": _last_runs.get(job.id),
            }
    return states
