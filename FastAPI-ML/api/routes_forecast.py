from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api import get_env
from api import services

router = APIRouter(prefix="/api/forecast", tags=["forecast"])


@router.get("/current/{city}")
def current(city: str, env: str = Depends(get_env)):
    return services.current_forecasts(env, city)


@router.get("/parkhaus/{city}/{pls_id}")
def parkhaus(city: str, pls_id: str, hours: int = Query(24, ge=1, le=168),
             env: str = Depends(get_env)):
    return services.house_detail(env, city, pls_id, hours)


@router.get("/best/{city}")
def best(city: str, at: Optional[str] = None, min_free: int = Query(0, ge=0),
         env: str = Depends(get_env)):
    at_dt = None
    if at:
        try:
            at_dt = datetime.fromisoformat(at)
        except ValueError:
            raise HTTPException(422, detail="Ungueltiges Datum (ISO-Format erwartet)")
    return services.best_parking(env, city, at_dt, min_free)
