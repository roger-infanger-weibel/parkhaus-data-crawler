#!/bin/bash
# Startet den Scanner der test-Umgebung neu (schreibt nach ph_fetch_test).

echo "[test] alten Prozess beenden ..."
if pkill -f web_server.py; then
    echo "[test]   beendet"
else
    echo "[test]   lief nicht"
fi
sleep 1

echo "Synch Codefiles"
rsync -av --delete latest-github/flask/ flask/

echo "Copy Env File"^S
cp myenv/.flaskenv flask/.env

cd flask/

nohup python3 web_server.py >web_server.log 2>&1 &
pid=$!
sleep 2
if kill -0 "$pid" 2>/dev/null; then
    echo "[Flask] gestartet (PID $pid), Log: web_server.log"
else
    echo "[Flask] FEHLGESCHLAGEN - letzte Zeilen aus web_server.log:"
    tail -5 web_server.log 
fi


