#!/bin/bash
# Startet den Scanner der prod-Umgebung neu (schreibt nach ph_fetch_prod).

echo "[prod] alten Prozess beenden ..."
if pkill -f scheduler-prod.py; then
    echo "[prod]   beendet"
else
    echo "[prod]   lief nicht"
fi
sleep 1

rsync -av --delete latest-github/scanner/ scanner-prod/

cd scanner-prod/ || exit 1
cp scheduler.py scheduler-prod.py
nohup python3 -u scheduler-prod.py > scheduler-prod.log 2>&1 &
pid=$!
sleep 2
if kill -0 "$pid" 2>/dev/null; then
    echo "[prod] gestartet (PID $pid), Log: scanner-prod/scheduler-prod.log"
else
    echo "[prod] FEHLGESCHLAGEN - letzte Zeilen aus scheduler-prod.log:"
    tail -5 scheduler-prod.log | sed 's/^/[prod]   /'
fi
