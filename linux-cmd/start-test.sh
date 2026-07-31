#!/bin/bash
# Startet den Scanner der TEST-Umgebung neu (schreibt nach ph_fetch_test).

echo "[Test] alten Prozess beenden ..."
if pkill -f scheduler-test.py; then
    echo "[Test]   beendet"
else
    echo "[Test]   lief nicht"
fi
sleep 1

anzahl=$(ls -1 latest-github/scanner/ 2>/dev/null | wc -l)
cp -rf latest-github/scanner/* scanner-test
echo "[Test] $anzahl Dateien aus latest-github/scanner kopiert"

cd scanner-test/ || exit 1
cp scheduler.py scheduler-test.py
nohup python3 -u scheduler-test.py > scheduler-test.log 2>&1 &
pid=$!
sleep 2
if kill -0 "$pid" 2>/dev/null; then
    echo "[Test] gestartet (PID $pid), Log: scanner-test/scheduler-test.log"
else
    echo "[Test] FEHLGESCHLAGEN - letzte Zeilen aus scheduler-test.log:"
    tail -5 scheduler-test.log | sed 's/^/[Test]   /'
fi
