#!/bin/bash
# Startet den Scanner der PROD-Umgebung neu (schreibt nach ph_fetch_prod).

echo "[Prod] alten Prozess beenden ..."
if pkill -f scheduler-prod.py; then
    echo "[Prod]   beendet"
else
    echo "[Prod]   lief nicht"
fi
sleep 1

anzahl=$(ls -1 latest-github/scanner/ 2>/dev/null | wc -l)
cp -rf latest-github/scanner/* scanner-prod
echo "[Prod] $anzahl Dateien aus latest-github/scanner kopiert"

cd scanner-prod || exit 1
cp scheduler.py scheduler-prod.py
nohup python3 -u scheduler-prod.py > scheduler-prod.log 2>&1 &
pid=$!
sleep 2
if kill -0 "$pid" 2>/dev/null; then
    echo "[Prod] gestartet (PID $pid), Log: scanner-prod/scheduler-prod.log"
else
    echo "[Prod] FEHLGESCHLAGEN - letzte Zeilen aus scheduler-prod.log:"
    tail -5 scheduler-prod.log | sed 's/^/[Prod]   /'
fi
