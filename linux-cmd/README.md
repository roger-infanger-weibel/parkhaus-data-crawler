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

## Autostart – einfache Variante (crontab)

Alle vier Startskripte nach dem Booten ausführen, mehr nicht:

```bash
cp linux-cmd/start-all.sh /root/ && chmod +x /root/start-all.sh
crontab -e
```

Diese eine Zeile eintragen:

```
@reboot sleep 60 && /root/start-all.sh >> /root/start-all.log 2>&1
```

Das `sleep 60` gibt dem Netzwerk Zeit, sonst scheitert der erste
Datenbankzugriff. Testen ohne Reboot: `/root/start-all.sh` — die Skripte
beenden jeweils den alten Prozess, es entstehen keine Doppelstarts.

Prüfen, was der Autostart gemacht hat: `cat /root/start-all.log`.

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

## Training: nicht auf diesem Server

**Der Server ist zu klein zum Trainieren — die Rechnung geht nicht auf:**

| | |
|---|---|
| RAM gesamt (`free -h`) | **641 MB** |
| davon im Betrieb frei | ~180 MB |
| Swap | **0** |
| Training, 60-Tage-Fenster | **735 MB** |
| Grundbedarf der App (pandas/numpy/lightgbm + 5 Modelle) | 216 MB |

Das Training braucht mehr, als die Maschine besitzt. Kein Limit und keine
Einstellung ändern daran etwas.

Warum die Maschine dabei komplett stehen blieb — und nicht einfach der
Trainingsprozess starb: es gibt **keinen Swap**. Bei Speichermangel wirft der
Kernel stattdessen den Datei-Cache weg, und darin liegen auch die
ausführbaren Teile der laufenden Programme. Die müssen dann bei jedem Aufruf
neu von der Platte gelesen werden, auch die von `sshd` — deshalb kam keine
Anmeldung mehr zustande. `MemorySwapMax=0` war folglich wirkungslos, es gab
nie einen Swap zum Abschalten.

Wer das Training auf dem Server haben will, muss den Arbeitsspeicher
aufstocken; ab etwa 2 GB wird es realistisch.

Deshalb gilt:

```bash
echo "AI_RETRAIN_ENABLED=0" >> /root/myenv/.env
```

Und **keinen** cron-Eintrag fürs Training auf dem Server anlegen.

### Stattdessen: auf dem PC trainieren, Dateien kopieren

Einmal pro Woche genügt. Auf dem PC:

```bash
cd FastAPI-ML
python -m forecast.train --env prod
python -m forecast.train --env test          # nur falls Test-Umgebung genutzt
python -m scripts.export_models --env prod --env test
```

`export_models` legt genau die Dateien, die der Server braucht, in
`FastAPI-ML/export_models/` (rund 18 MB je Umgebung) und nennt den passenden
Kopierbefehl. Die Dateien dann per WinSCP oder `scp` nach
`/root/FastAPI-ML/models_store/` übertragen.

Ausführliche Anleitung mit Kontrollschritten und Stolpersteinen:
[../FastAPI-ML/MODELL-REFRESH.md](../FastAPI-ML/MODELL-REFRESH.md)

Zügig kopieren: das Training markiert den neuen Lauf sofort als aktiv, und bis
die Dateien eintreffen, findet der Server kein Modell und erzeugt für einen
Zyklus keine Prognosen. Danach prüfen:

```bash
curl -sS http://localhost:8080/api/health     # last_prediction muss frisch sein
```

### Warum wöchentlich reicht

Um auf die aktuelle Lage zu reagieren, braucht es kein Training — die frischen
Messwerte gehen bei jeder Prognose als Eingabe ein. Nachtrainiert wird nur
wegen langsamer Veränderungen: Jahreszeiten, neue Parkhäuser, geänderte
Kapazitäten, Baustellen, nachgefüllte Datenlücken. Ob es dringt, zeigt die
Seite **Genauigkeit**: steigt die Fehlerkurve über mehrere Tage, ist ein Lauf
fällig.

### Erst nach einem RAM-Upgrade auf dem Server

Ab etwa 2 GB wird es realistisch. Dann vorher die übrigen Dienste anhalten,
damit der Speicher frei ist:

```bash
pkill -f "uvicorn main:app"; pkill -f scheduler-test.py
cd /root/FastAPI-ML
systemd-run --scope -p MemoryMax=1G --collect \
  python3 -m forecast.train --env prod --days 60
/root/start-all.sh
```

Voraussetzung ist ausserdem der aktuelle Codestand: seit dem Streaming-Fix
werden die Messwerte stadtweise geladen (~123 MB statt mehrerer GB beim
reinen Laden). **Vorher `git pull`.**

## Speicherbedarf im Überblick

| Vorgang | Spitzenbedarf |
|---|---|
| App betriebsbereit (pandas/numpy/lightgbm + 5 Modelle) | 216 MB |
| Training, 60-Tage-Fenster | 735 MB |
| Training, 120-Tage-Fenster | 1368 MB |

Zum Vergleich: der Server hat **641 MB** insgesamt. Die App passt hinein, das
Training nicht.

Steuerung über die `.env`:

```
AI_RETRAIN_ENABLED=0     # kein Training auf diesem Server  -> Pflicht
AI_TRAIN_DAYS=60         # nur relevant, falls doch trainiert wird
```

Die Modelle kommen stattdessen vom PC — siehe
[../FastAPI-ML/MODELL-REFRESH.md](../FastAPI-ML/MODELL-REFRESH.md).

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
