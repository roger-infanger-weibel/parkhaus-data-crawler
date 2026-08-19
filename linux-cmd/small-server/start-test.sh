#!/bin/bash
# Startet den Scanner der test-Umgebung neu (schreibt nach ph_fetch_test).

echo "[test] alten Prozess beenden ..."
if pkill -f scheduler-test.py; then
    echo "[test]   beendet"
else
    echo "[test]   lief nicht"
fi
sleep 1

echo "Synch Code"
rsync -av --delete latest-github/scanner/ scanner-test/

echo "Copy Env File"
cp myenv/.testenv scanner-test/.env

cd scanner-test/ || exit 1
cp scheduler.py scheduler-test.py
nohup python3 -u scheduler-test.py > scheduler-test.log 2>&1 &
pid=$!
sleep 2
if kill -0 "$pid" 2>/dev/null; then
    echo "[test] gestartet (PID $pid), Log: scanner-test/scheduler-test.log"
else
    echo "[test] FEHLGESCHLAGEN - letzte Zeilen aus scheduler-test.log:"
    tail -5 scheduler-test.log | sed 's/^/[test]   /'
fi
