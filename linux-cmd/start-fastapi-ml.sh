#!/bin/bash
# Startet die FastAPI-ML App (Port 8080) neben der bestehenden Flask-App.
# Wichtig: --workers 1, damit der eingebaute Scheduler nur einmal laeuft.
cd "$(dirname "$0")/../FastAPI-ML" || exit 1
nohup python3 -m uvicorn main:app --host 0.0.0.0 --port 8080 --workers 1 \
  > ../fastapi-ml.log 2>&1 &
echo "FastAPI-ML gestartet (PID $!), Log: fastapi-ml.log"
