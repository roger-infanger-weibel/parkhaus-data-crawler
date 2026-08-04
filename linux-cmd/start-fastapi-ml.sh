#!/bin/bash
# Startet die KI-Prognose-App neu.
# --workers 1 ist Pflicht, sonst laeuft der eingebaute Scheduler mehrfach.

PORT="${AI_APP_PORT:-80}"

echo "[ML] alten Prozess beenden ..."
if pkill -f uvicorn; then
    echo "[ML]   beendet"
else
    echo "[ML]   lief nicht"
fi
sleep 1

anzahl=$(ls -1 latest-github/FastAPI-ML/ 2>/dev/null | wc -l)
cp -rf latest-github/FastAPI-ML/* FastAPI-ML
echo "[ML] $anzahl Eintraege aus latest-github/FastAPI-ML kopiert"

cd FastAPI-ML || exit 1

# Modelle liegen nicht im Repository - ohne sie entstehen keine Prognosen
modelle=$(ls -1 models_store/*.joblib 2>/dev/null | wc -l)
if [ "$modelle" -gt 0 ]; then
    echo "[ML] $modelle Modelldateien in models_store/"
else
    echo "[ML] WARNUNG: keine Modelldateien in models_store/ -"
    echo "[ML]          es werden keine Prognosen entstehen."
    echo "[ML]          Siehe FastAPI-ML/MODELL-REFRESH.md"
fi

nohup python3 -m uvicorn main:app --host 0.0.0.0 --port ${PORT} --workers 1 > fastapi-ml.log 2>&1 &
pid=$!
sleep 3
if kill -0 "$pid" 2>/dev/null; then
    echo "[ML] gestartet (PID $pid), Log: FastAPI-ML/fastapi-ml.log"
    if command -v curl >/dev/null && curl -sS -m 5 http://localhost:${PORT}/api/health >/dev/null 2>&1; then
        echo "[ML] antwortet auf http://localhost:${PORT}"
    else
        echo "[ML] startet noch - in ein paar Sekunden pruefen:"
        echo "[ML]   curl -sS http://localhost:${PORT}/api/health"
    fi
else
    echo "[ML] FEHLGESCHLAGEN - letzte Zeilen aus fastapi-ml.log:"
    tail -10 fastapi-ml.log | sed 's/^/[ML]   /'
fi
