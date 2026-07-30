# Serverbetrieb (87.106.222.137)

Betriebsanleitung für die vier Dienste: Autostart, Deployment, Fehlersuche.

## Übersicht

| Dienst | Ordner | Was | Port |
|---|---|---|---|
| `parkhaus-scanner-prod` | `/root/scanner-prod` | Sammelt Belegungsdaten alle 15 Min → `ph_fetch_prod` | — |
| `parkhaus-scanner-test` | `/root/scanner-test` | dasselbe → `ph_fetch_test` | — |
| `parkhaus-flask` | `/root/flask` | Bisheriges Dashboard | 80 |
| `parkhaus-fastapi-ml` | `/root/FastAPI-ML` | KI-Prognose, Genauigkeit, Chat | 8080 |

Welche Datenbank ein Scanner verwendet, entscheidet die `.env` im jeweiligen
Arbeitsordner — deshalb ist bei den Diensten `WorkingDirectory` gesetzt.

## Zeitzone des Servers

Empfohlen: `Europe/Zurich`.

```bash
timedatectl set-timezone Europe/Zurich
systemctl restart parkhaus-scanner-prod parkhaus-scanner-test parkhaus-flask parkhaus-fastapi-ml
```

Das ist reine Lesbarkeit, keine Datenkorrektur: Logs und `journalctl` zeigen
dann dieselbe Zeit wie die Messwerte in der Datenbank. Läuft der Server auf
UTC, steht im Trainingslog z.B. `10:13`, während der zugehörige Messwert
`12:13` trägt — das kostet bei jeder Fehlersuche unnötig Zeit.

An den Daten ändert sich nichts:

- Der Scanner setzt seine Zeitstempel explizit über `datetime.now(SWISS_TZ)`.
- FastAPI-ML rechnet durchgehend über `core.timeutil.now_local()` und legt
  die Scheduler-Jobs fest auf Europe/Zurich.
- Die Datenbank läuft auf einem eigenen Host (94.231.94.132, bereits CEST)
  und ist von der Umstellung gar nicht betroffen.

## Einmalige Einrichtung: Autostart

```bash
cd /root && bash linux-cmd/install-systemd.sh
```

Das Skript beendet laufende `nohup`-Prozesse, installiert die Units nach
`/etc/systemd/system/`, ermittelt den Python-Pfad automatisch und aktiviert
alle Dienste. Ordner, die nicht existieren, werden übersprungen.

Damit starten die Dienste nach jedem Reboot automatisch, werden nach einem
Absturz neu gestartet und schreiben ins Journal statt in Logdateien.

### Port 8080 freigeben

Der Autostart allein genügt nicht — Port 8080 muss zusätzlich freigegeben
werden, an **zwei** Stellen:

```bash
firewall-cmd --permanent --add-port=8080/tcp && firewall-cmd --reload
```

Und im **IONOS Cloud Panel** unter Netzwerk → Firewall-Richtlinien eine Regel
für TCP 8080 anlegen. Fehlt eine der beiden, läuft der Verbindungsversuch in
einen Timeout (siehe Fehlersuche unten).

## Wo liegt die .env?

FastAPI-ML sucht in dieser Reihenfolge: `AI_ENV_FILE` (falls gesetzt),
`FastAPI-ML/.env`, `.env` im Repo-Root, dann aufwärts vom Arbeitsverzeichnis.

Liegt die Datei woanders — etwa in `/root/myenv/.env` — den Pfad in der Unit
eintragen:

```bash
systemctl edit --full parkhaus-fastapi-ml
# unter [Service] einfuegen:
#   Environment=AI_ENV_FILE=/root/myenv/.env
systemctl restart parkhaus-fastapi-ml
```

Kontrolle: `curl -sS http://localhost:8080/api/health` zeigt unter `env_files`,
welche Datei geladen wurde, und unter `db_host`, wohin verbunden wird. Steht
dort `KEINE .env gefunden`, läuft die App auf Standardwerten (localhost) —
dann stimmen auch die Datenbanknamen nicht.

Der Scanner sucht unabhängig davon selbst (`load_dotenv()` ab Arbeitsordner
aufwärts) — er braucht seine `.env` in `scanner-prod/` bzw. `scanner-test/`
oder in `/root`.

## Täglicher Betrieb

```bash
systemctl status parkhaus-fastapi-ml      # Zustand
systemctl restart parkhaus-fastapi-ml     # neustarten
systemctl stop parkhaus-scanner-test      # anhalten
journalctl -u parkhaus-fastapi-ml -f      # Logs mitlesen
journalctl -u parkhaus-scanner-prod --since "1 hour ago"
```

## Deployment einer neuen Version

```bash
cd /root
bash linux-cmd/copy-github.sh
cp -u latest-github/scanner/* scanner-prod/
cp -u latest-github/scanner/* scanner-test/
cp latest-github/flask/* flask/
cp -r latest-github/FastAPI-ML/* FastAPI-ML/
systemctl restart parkhaus-scanner-prod parkhaus-scanner-test parkhaus-flask parkhaus-fastapi-ml
```

Wichtig: `FastAPI-ML/models_store/` beim Kopieren **nicht** überschreiben —
dort liegen die trainierten Modelle, die nicht im Git sind.

Die alten Skripte `start-prod.sh`, `start-test.sh`, `start-flask.sh` und
`start-fastapi-ml.sh` funktionieren weiterhin für manuelle Starts. Nicht
gleichzeitig mit den systemd-Diensten verwenden, sonst laufen Prozesse doppelt.

## Speicher: das Training kann den Server lahmlegen

Das Modelltraining hält das gesamte Zeitfenster im Arbeitsspeicher:

| Fenster | Spitzenspeicher |
|---|---|
| 60 Tage | 735 MB |
| 120 Tage | 1368 MB |

Reicht der RAM nicht, geht die Maschine ins Swappen und reagiert auf nichts
mehr — auch der Scanner schreibt dann nicht mehr. Die systemd-Unit begrenzt
FastAPI-ML deshalb auf `MemoryMax=1200M`: im Ernstfall stirbt nur dieser
Dienst, der Rest läuft weiter.

Steuerung über `/root/.env`:

```
AI_TRAIN_DAYS=60         # kleineres Fenster (Standard 120)
AI_RETRAIN_ENABLED=0     # gar kein Training auf diesem Server
```

Bei `AI_RETRAIN_ENABLED=0` wird auf einer anderen Maschine trainiert und nur
die Modelldateien kopiert (`scp FastAPI-ML/models_store/*.joblib
root@SERVER:/root/FastAPI-ML/models_store/`). Das genügt, weil in der
Datenbank nur der Dateiname des Modells steht.

## Fehlersuche

### Port 8080 antwortet nicht

Erst unterscheiden, ob überhaupt Pakete ankommen:

```bash
curl -sS -m 5 http://localhost:8080/api/health    # auf dem Server selbst
```

- **Funktioniert lokal, aber nicht von aussen** → Firewall. Beide Stellen
  prüfen (firewalld *und* IONOS Cloud Panel, siehe oben).
- **Auch lokal keine Antwort** → der Dienst läuft nicht:
  `systemctl status parkhaus-fastapi-ml` und `journalctl -u parkhaus-fastapi-ml -n 50`.

Von aussen unterscheidet der Fehler die Ursache: *Connection refused* heisst,
der Server antwortet, aber nichts lauscht auf dem Port. *Timeout* heisst, die
Pakete werden verworfen — das ist immer die Firewall.

### Läuft die KI-App wirklich?

Ohne SSH lässt sich das an der Datenbank ablesen — der Dienst schreibt alle
15 Minuten Prognosen:

```sql
SELECT MAX(created_at) FROM ph_fetch_prod.ai_predictions;
```

Ist der Wert älter als ~20 Minuten, läuft der Scheduler nicht.

### Läuft der Scanner?

```sql
SELECT MAX(fetch_ts) FROM ph_fetch_prod.pls_fetch_current;
```

Älter als ~20 Minuten heisst: Scanner steht oder der Server hat ein Problem.

### Ein Prozess hängt und reagiert nicht auf Ctrl+C

```bash
systemctl restart parkhaus-fastapi-ml     # als Dienst
pkill -f "forecast.train"                 # manuell gestarteter Prozess
```

Reagiert der ganze Server nicht mehr (auch SSH nicht), hilft nur der harte
Neustart über das IONOS Cloud Panel. Nach dem Reboot starten die Dienste dank
systemd von selbst.
