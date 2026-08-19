#!/bin/bash
# Startet das Flask-Dashboard (Port 80) neu.

echo "[Flask] alten Prozess beenden ..."
if pkill -f web_server.py; then
    echo "[Flask]   beendet"
else
    echo "[Flask]   lief nicht"
fi
sleep 1

rsync -av --delete latest-github/flask/ flask/

cd flask/ || exit 1
nohup python3 web_server.py >web_server.log 2>&1 &
pid=$!
sleep 2
if kill -0 "$pid" 2>/dev/null; then
    echo "[Flask] gestartet (PID $pid), Log: flask/web_server.log"
else
    echo "[Flask] FEHLGESCHLAGEN - letzte Zeilen aus web_server.log:"
    tail -5 web_server.log | sed 's/^/[Flask]   /'
fi
