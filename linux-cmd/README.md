# Serverbetrieb

Betriebsanleitung: Autostart, Deployment, Fehlersuche.

## Verzeichnisstruktur

Die Skripte und Konfigurationen sind nach Servertyp organisiert:

- **`medium-server/`** → 87.106.21.252 (KI-Prognose, FastAPI-ML, Port 80)
- **`small-server/`** → 87.106.222.137 (Scanner + Flask-Dashboard, Port 80)

Verwende **immer** die Skripte aus dem passenden Verzeichnis für deinen Server.

## Zwei Server

| Server | Typ | Läuft dort | Adresse |
|---|---|---|---|
| **87.106.21.252** | medium | KI-Prognose (FastAPI-ML) | http://87.106.21.252/ |
| **87.106.222.137** | small | Scanner (prod + test) und Flask-Dashboard | http://87.106.222.137/ |

Die KI-Prognose ist seit dem 04.08.2026 auf einen eigenen, grösseren Server
umgezogen — doppelt so viel RAM und CPU. Dort läuft sie auf **Port 80**
(vorher 8080 auf dem alten Server) und kann die Modelle selbst trainieren.

Die Datenbank liegt auf einem dritten Host (`parkhaus.roil.ch`,
94.231.94.132) und wird von beiden Servern genutzt.

## Dienste

### medium-server (87.106.21.252)

| Dienst | Ordner | Was |
|---|---|---|
| `parkhaus-fastapi-ml` | `/root/FastAPI-ML` | KI-Prognose, Genauigkeit, Chat, Port 80 |

### small-server (87.106.222.137)

| Dienst | Ordner | Was |
|---|---|---|
| `parkhaus-scanner-prod` | `/root/scanner-prod` | Belegungsdaten alle 15 Min → `ph_fetch_prod` |
| `parkhaus-scanner-test` | `/root/scanner-test` | dasselbe → `ph_fetch_test` |
| `parkhaus-flask` | `/root/flask` | Bisheriges Dashboard, Port 80 |

Welche Datenbank ein Scanner verwendet, entscheidet die `.env` im jeweiligen
Arbeitsordner — deshalb ist bei den Diensten `WorkingDirectory` gesetzt. Bei
FastAPI-ML steuert `AI_DEFAULT_ENV`, für welche Umgebung die Hintergrundjobs
laufen; der Port lässt sich über `AI_APP_PORT` ändern.

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

**Wichtig:** Je nach Server-Typ das richtige Verzeichnis verwenden.

### medium-server (FastAPI-ML)
```bash
cp linux-cmd/medium-server/start-all.sh /root/ && chmod +x /root/start-all.sh
crontab -e
```

### small-server (Scanner + Flask)
```bash
cp linux-cmd/small-server/start-all.sh /root/ && chmod +x /root/start-all.sh
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

### Port 80 freigeben

Der Autostart allein genügt nicht — der Port muss zusätzlich freigegeben
werden, an **zwei** Stellen:

```bash
firewall-cmd --permanent --add-port=80/tcp && firewall-cmd --reload
```

Und im **IONOS Cloud Panel** unter Netzwerk → Firewall-Richtlinien eine Regel
für TCP 80 anlegen. Fehlt eine der beiden, läuft der Verbindungsversuch in
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

Kontrolle: `curl -sS http://localhost/api/health` zeigt unter `env_files`,
welche Datei geladen wurde, und unter `db_host`, wohin verbunden wird. Steht
dort `KEINE .env gefunden`, läuft die App auf Standardwerten (localhost) —
dann stimmen auch die Datenbanknamen nicht.

Der Scanner sucht unabhängig davon selbst (`load_dotenv()` ab Arbeitsordner
aufwärts) — er braucht seine `.env` in `scanner-prod/` bzw. `scanner-test/`
oder in `/root`.

## Täglicher Betrieb

### medium-server (FastAPI-ML)
```bash
systemctl status parkhaus-fastapi-ml      # Zustand
systemctl restart parkhaus-fastapi-ml     # neustarten
journalctl -u parkhaus-fastapi-ml -f      # Logs mitlesen
```

### small-server (Scanner + Flask)
```bash
systemctl status parkhaus-scanner-prod    # Zustand Scanner Prod
systemctl status parkhaus-scanner-test    # Zustand Scanner Test
systemctl status parkhaus-flask           # Zustand Flask
journalctl -u parkhaus-scanner-prod -f    # Logs Scanner Prod
journalctl -u parkhaus-scanner-test --since "1 hour ago"  # letzte Stunde Test
```

## Deployment einer neuen Version

Je nach Server-Typ das entsprechende Verzeichnis verwenden:

### medium-server (FastAPI-ML)
```bash
cd /root
bash copy-github.sh              # holt den aktuellen Stand nach latest-github/
./start-all.sh                   # kopiert ihn in die Zielordner und startet neu
./start-fastapi-ml.sh            # nur FastAPI-ML neustarten
```

### small-server (Scanner + Flask)
```bash
cd /root
bash copy-github.sh              # holt den aktuellen Stand nach latest-github/
./start-all.sh                   # kopiert ihn in die Zielordner und startet neu
./start-prod.sh                  # nur Scanner Prod neustarten
./start-test.sh                  # nur Scanner Test neustarten
./start-flask.sh                 # nur Flask neustarten
```

Das Kopieren erledigen die Startskripte selbst, jeweils mit `cp -rf` — also
mit Überschreiben. Das ist wichtig: mit `cp -n` (nicht überschreiben) wurden
vorhandene Dateien übersprungen, sodass ein `git pull` folgenlos blieb und
der Server tagelang alten Code ausführte.

`FastAPI-ML/models_store/` bleibt dabei unangetastet: `cp -rf quelle/* ziel`
führt die Ordner zusammen und löscht nichts. Im Repository liegt dort nur
eine leere Platzhalterdatei, die trainierten Modelle auf dem Server bleiben
erhalten. Dasselbe gilt für die `.env`, die nicht im Repository ist.

Bei Verwendung der systemd-Units stattdessen `systemctl restart …`, nicht beides gleichzeitig.

## Training

**Nur auf medium-server (87.106.21.252).** Die Maschine hat genug Arbeitsspeicher dafür.

```bash
cd /root/FastAPI-ML
python3 -m forecast.train --env prod
python3 -m forecast.train --env test     # nur falls Test-Umgebung genutzt
```

Ein Lauf dauert wenige Minuten und meldet je Horizont, wie gut das neue
Modell im Vergleich zum Basismodell ist. Danach greifen die neuen Modelle
automatisch beim nächsten Prognoselauf; nichts muss kopiert werden.

### Wie oft

**Einmal pro Woche genügt.** Um auf die aktuelle Lage zu reagieren, braucht es
kein Training — die frischen Messwerte gehen bei jeder Prognose als Eingabe
ein. Nachtrainiert wird nur wegen langsamer Veränderungen: Jahreszeiten, neue
Parkhäuser, geänderte Kapazitäten, Baustellen, nachgefüllte Datenlücken. Ob es
dringt, zeigt die Seite **Genauigkeit**: steigt die Fehlerkurve über mehrere
Tage, ist ein Lauf fällig.

Automatisch per crontab:

```
0 3 * * 0 cd /root/FastAPI-ML && python3 -m forecast.train --env prod >> /root/train.log 2>&1
```

Alternativ übernimmt das der eingebaute Scheduler nachts um 03:30, sofern
`AI_RETRAIN_ENABLED` nicht auf `0` steht.

### Meldung «NICHT aktiviert»

```
WARNING Lauf 50 (ml h=2) NICHT aktiviert: MAE 4.984 > 4.422 * 1.10
```

Das ist **kein Fehler**, sondern die Absicherung: das neue Modell war für
diesen Horizont mehr als 10 % schlechter als das laufende, also bleibt das
bessere aktiv. Nach einem Datenausfall verdrängt so kein schwaches Modell ein
gutes. Die übrigen Horizonte werden davon nicht berührt.

Verglichen wird auf **demselben Testzeitraum**: das bisherige Modell wird dafür
eigens auf dem aktuellen Holdout bewertet. Der in der Datenbank gespeicherte
Wert taugt nicht zum Vergleich, weil er aus dem Testzeitraum von damals
stammt — sonst könnte ein altes Modell mit einer günstigen Periode alle
Nachfolger dauerhaft blockieren.

Zeigt die Meldung stattdessen «trotz schlechterem MAE aktiviert: Datei des
bisherigen Laufs fehlt», stammte das bisher aktive Modell von einer anderen
Maschine. Dann wird das neue genommen — ein etwas schlechteres Modell, das
lädt, ist besser als ein besseres, das keine Prognosen erzeugt.

### Speicherbedarf

| Vorgang | Spitzenbedarf |
|---|---|
| App betriebsbereit (pandas/numpy/lightgbm + 5 Modelle) | 216 MB |
| Training, 60-Tage-Fenster | 735 MB |
| Training, 120-Tage-Fenster | 1368 MB |

Auf einem kleinen Server reicht das nicht. Der alte Server hatte 641 MB und
keinen Swap; dort blieb die Maschine beim Training dreimal komplett stehen —
ohne Swap wirft der Kernel den Datei-Cache weg, einschliesslich der
ausführbaren Teile laufender Programme, worauf auch `sshd` unbenutzbar wird.
Auf solchen Maschinen gilt:

```
AI_RETRAIN_ENABLED=0     # kein Training auf diesem Server
AI_TRAIN_DAYS=60         # kleineres Fenster, falls doch
```

und die Modelle kommen von einer anderen Maschine — siehe
[../FastAPI-ML/MODELL-REFRESH.md](../FastAPI-ML/MODELL-REFRESH.md).

## Fehlersuche

### Die Anwendung antwortet nicht

Erst unterscheiden, ob überhaupt Pakete ankommen:

```bash
curl -sS -m 5 http://localhost/api/health    # auf dem Server selbst (medium-server)
curl -sS -m 5 http://localhost/               # auf small-server (Flask/Scanner)
```

- **Funktioniert lokal, aber nicht von aussen** → Firewall. Beide Stellen
  prüfen (firewalld *und* IONOS Cloud Panel, siehe oben).
- **Auch lokal keine Antwort** → der Dienst läuft nicht:
  - medium-server: `systemctl status parkhaus-fastapi-ml` und `journalctl -u parkhaus-fastapi-ml -n 50`
  - small-server: `systemctl status parkhaus-flask` oder `systemctl status parkhaus-scanner-prod`

Von aussen unterscheidet der Fehler die Ursache: *Connection refused* heisst,
der Server antwortet, aber nichts lauscht auf dem Port. *Timeout* heisst, die
Pakete werden verworfen — das ist immer die Firewall.

### Läuft die KI-App wirklich? (medium-server)

Ohne SSH lässt sich das an der Datenbank ablesen — der Dienst schreibt alle
15 Minuten Prognosen:

```sql
SELECT MAX(created_at) FROM ph_fetch_prod.ai_predictions;
```

Ist der Wert älter als ~20 Minuten, läuft der Scheduler nicht.

### Läuft der Scanner? (small-server)

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
