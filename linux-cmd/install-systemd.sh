#!/bin/bash
# Richtet die Dienste als systemd-Units ein: Autostart nach Reboot,
# Neustart nach Absturz, Speicherlimits, Logs via journalctl.
#
# Einmalig ausfuehren:  bash linux-cmd/install-systemd.sh
#
# Ersetzt die nohup-Startskripte (start-prod.sh, start-test.sh, start-flask.sh,
# start-fastapi-ml.sh) fuer den Dauerbetrieb. Nach einem Deployment nicht mehr
# die Skripte aufrufen, sondern:  systemctl restart parkhaus-scanner-prod
set -e

UNIT_DIR="$(cd "$(dirname "$0")" && pwd)/systemd"
SERVICES=(parkhaus-scanner-prod parkhaus-scanner-test parkhaus-flask parkhaus-fastapi-ml)

# systemd kennt kein PATH-Lookup: ExecStart braucht den absoluten Pfad.
PYTHON=$(command -v python3)
if [ -z "$PYTHON" ]; then
    echo "python3 nicht gefunden" >&2
    exit 1
fi
echo "Verwende Python: $PYTHON"

# Laufende nohup-Prozesse beenden, damit sich Alt und Neu nicht in die Quere kommen
echo "Beende bestehende nohup-Prozesse ..."
pkill -f scheduler-prod.py || true
pkill -f scheduler-test.py || true
pkill -f web_server.py || true
pkill -f "uvicorn main:app" || true

for svc in "${SERVICES[@]}"; do
    unit="$UNIT_DIR/$svc.service"
    workdir=$(sed -n 's/^WorkingDirectory=//p' "$unit")
    if [ ! -d "$workdir" ]; then
        echo "  UEBERSPRUNGEN: $svc (Ordner $workdir fehlt)"
        continue
    fi
    sed "s|^ExecStart=/usr/bin/python3|ExecStart=$PYTHON|" "$unit" \
        > "/etc/systemd/system/$svc.service"
    echo "  installiert: $svc"
done

systemctl daemon-reload

for svc in "${SERVICES[@]}"; do
    if [ -f "/etc/systemd/system/$svc.service" ]; then
        systemctl enable --now "$svc"
    fi
done

echo
echo "Status:"
for svc in "${SERVICES[@]}"; do
    if [ -f "/etc/systemd/system/$svc.service" ]; then
        printf '  %-28s %s (Autostart: %s)\n' "$svc" \
            "$(systemctl is-active "$svc")" "$(systemctl is-enabled "$svc")"
    fi
done
echo
echo "Logs ansehen:      journalctl -u parkhaus-fastapi-ml -f"
echo "Dienst neustarten: systemctl restart parkhaus-fastapi-ml"
