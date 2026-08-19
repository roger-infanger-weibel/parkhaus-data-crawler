#!/bin/bash
# Startet alle vier Dienste nacheinander.
#
# Autostart nach Reboot einrichten (einmalig):
#   crontab -e
#   @reboot sleep 60 && /root/start-all.sh >> /root/start-all.log 2>&1
#
# Der Wrapper laesst sich auch jederzeit von Hand aufrufen - die einzelnen
# Startskripte beenden vorher jeweils den alten Prozess (pkill), es entstehen
# also keine Doppelstarts.

timedatectl set-timezone Europe/Zurich && date

cd "$(dirname "$0")" || exit 1

echo "=== Start $(date '+%Y-%m-%d %H:%M:%S') ==="
for script in start-fastapi-ml.sh; do
    if [ -x "$script" ] || [ -f "$script" ]; then
        echo "--- $script"
        bash "$script"
    else
        echo "--- $script fehlt, uebersprungen"
    fi
done
echo "=== Fertig $(date '+%Y-%m-%d %H:%M:%S') ==="
