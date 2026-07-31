# Cross-Reference: Datei-Übersicht und Abhängigkeiten

## Projektstruktur

```
parkhaus-data-crawler/
├── README.md                   ← dieses Dokument
├── scanner/                    ← Datensammlung (Crawler)
│   ├── collect_data.py
│   ├── scheduler.py
│   ├── base.py
│   ├── db_utils.py
│   ├── luzern.py / basel.py / bern.py / zurich.py / stgallen.py
│   ├── get_event_and_weather_data.py
│   ├── cities.json / groups.json / events.json
│   ├── requirements.txt
│   ├── version.py / __init__.py
│   └── *.md (Dokumentation)
├── FastAPI-ML/                 ← KI-Prognose-App (FastAPI, siehe FastAPI-ML/README.md)
├── flask/                      ← Web-Server (Dashboard)
│   ├── web_server.py
│   ├── db_utils.py
│   ├── index.html / logs.html
└── linux-cmd/                  ← Linux Start-Skripte
    └── copy-github.sh          ← Refresh Local Github Folder
    └── start-flask.sh          ← Startup Flask Server
    ├── start-prod.sh           ← Startup Prod Crawler
    └── start-test.sh           ← Startup Test Crawler
```

---

## scanner/ — Crawler-Dateien

| Datei | Beschreibung | Aufgerufen von | Verwendet |
|-------|-------------|----------------|-----------|
| **collect_data.py** | Hauptskript: sammelt Parkdaten aller 5 Städte | `scheduler.py` (alle 15 Min) oder manuell via CLI | `base.py`, `db_utils.py`, `cities.json`, alle City-Collector |
| **scheduler.py** | Zeitsteuerung: startet Crawler und Wetter/Events nach Zeitplan | Manuell (`python scheduler.py`) | `collect_data.py` (15 Min), `get_event_and_weather_data.py` (06:00 + 18:00) |
| **base.py** | Abstrakte Basisklasse `BaseParkingCollector` mit Retry-Logik | Alle City-Collector erben davon | `db_utils.py` (get_connection, insert_measurement) |
| **db_utils.py** | DB-Layer: Verbindung, UPSERT, Mock-Mode (Simulation) | `base.py`, `collect_data.py` | `db_config.json` (optional) |
| **luzern.py** | Collector für Luzern (PLS Luzern API) | `collect_data.py` | `base.py` |
| **basel.py** | Collector für Basel (ParkenDD API) | `collect_data.py` | `base.py` |
| **bern.py** | Collector für Bern (Parking Bern XML) | `collect_data.py` | `base.py` |
| **zurich.py** | Collector für Zürich (ParkenDD API) | `collect_data.py` | `base.py` |
| **stgallen.py** | Collector für St. Gallen (Open Data Portal) | `collect_data.py` | `base.py` |
| **get_event_and_weather_data.py** | Wetter (Open-Meteo) und Events in DB importieren | `scheduler.py` (06:00 + 18:00) | `pymysql`, `.env` (DB-Credentials) |
| **cities.json** | Stadt-Konfiguration (IDs, APIs, Koordinaten) | `collect_data.py` (load_config) | — |
| **groups.json** | Parkhaus-Gruppierungen pro Stadt | **Verwaist** – wird von keinem Skript mehr gelesen (Gruppen kommen aus der DB-Tabelle `parkhaeuser`) | — |
| **events.json** | Event-Definitionen | **Verwaist** – Events liegen in der DB-Tabelle `local_events` | — |
| **requirements.txt** | Python-Abhängigkeiten | `pip install -r` | — |
| **version.py** | Versionsnummer | — | — |
| **__init__.py** | Package-Marker | Python-Import-System | — |

---

## flask/ — Web-Server-Dateien

| Datei | Beschreibung | Aufgerufen von | Verwendet |
|-------|-------------|----------------|-----------|
| **web_server.py** | Flask-Server: API-Endpoints + statische Dateien. Städte, Gruppen und Events kommen aus der Datenbank, nicht aus JSON-Dateien. Umschaltung prod/test per `?env=` | Manuell (`python web_server.py`) | `db_utils.py`, `index.html`, `logs.html` |
| **db_utils.py** | DB-Layer (Kopie von scanner/db_utils.py) | `web_server.py` | `db_config.json` (optional) |
| **index.html** | Dashboard: Parkhaus-Übersicht und Diagramme | `web_server.py` (Route `/`) | API-Endpoints von `web_server.py` |
| **logs.html** | Log-Ansicht: Crawler-Logs und Statistiken | `web_server.py` (Route `/logs`) | API-Endpoints von `web_server.py` |

---

## Abhängigkeitsgraph

```
scheduler.py
├── collect_data.py  (alle 15 Min)
│   ├── cities.json
│   ├── db_utils.py ──→ MariaDB
│   ├── base.py
│   │   └── db_utils.py
│   ├── luzern.py ──→ PLS Luzern API
│   ├── basel.py ──→ ParkenDD API
│   ├── bern.py ──→ Parking Bern XML
│   ├── zurich.py ──→ ParkenDD API
│   └── stgallen.py ──→ Open Data SG API
│
└── get_event_and_weather_data.py  (06:00 + 18:00)
    ├── .env (DB-Credentials)
    ├── Open-Meteo API ──→ weather_forecasts (DB)
    └── Hardcoded Events ──→ local_events + event_parkhaus (DB)

web_server.py  (separater Prozess, Port 80)
├── db_utils.py ──→ MariaDB (lesend)
├── index.html (Dashboard)
└── logs.html (Log-Viewer)

FastAPI-ML/main.py  (separater Prozess, Port 8080)
├── db.py ──→ MariaDB (liest pls_fetch_current, weather_forecasts,
│              local_events, cities, parkhaeuser; schreibt nur ai_*-Tabellen)
├── forecast/  ──→ Prognosen alle 15 Min, Auswertung, Training
├── chatbot/   ──→ regelbasierter Assistent
└── static/    ──→ Prognose, Genauigkeit, Chat, Dokumentation
```

---

## Dokumentation (scanner/)

| Datei | Inhalt |
|-------|--------|
| **README.md** | Hauptdokumentation: Features, Quick Start, Projektstruktur |
| **QUICK_START.md** | Kurzanleitung: Installation und erster Start |
| **README_SIMULATION.md** | Übersicht Simulation-Mode |
| **SIMULATION_MODE_GUIDE.md** | Detaillierte Simulation-Dokumentation |
| **CODE_EXAMPLES.md** | Code-Beispiele und Vergleiche |
| **CHANGES_SUMMARY.md** | Zusammenfassung aller technischen Änderungen |
| **ARCHITECTURE.md** | Systemdesign und Datenfluss |
| **MANIFEST.md** | Datei-Inventar und Implementierungsguide |
| **SERVER.md** | SFTP-Pfade der beiden Scanner-Instanzen auf dem Server |

## Weitere Dokumentation

| Datei | Inhalt |
|-------|--------|
| [FastAPI-ML/README.md](FastAPI-ML/README.md) | KI-Prognose-App: Architektur, Modelle, Setup, Deployment |
| [linux-cmd/README.md](linux-cmd/README.md) | Serverbetrieb: Autostart, Zeitzone, Training, Fehlersuche |

---

## linux-cmd/ — Linux Start-Skripte

| Datei | Beschreibung |
|-------|-------------|
| **start-prod.sh** | Stoppt laufenden Prod-Scheduler, kopiert `scheduler.py` → `scheduler-prod.py` und startet ihn im Hintergrund (nohup) |
| **start-test.sh** | Dasselbe für die Test-Umgebung |
| **start-flask.sh** | Startet das Flask-Dashboard (Port 80) neu |
| **start-fastapi-ml.sh** | Startet die KI-Prognose-App (Port 8080) neu |
| **start-all.sh** | Ruft alle vier obigen Skripte nacheinander auf – für den Autostart per crontab |
| **copy-github.sh** | Holt den aktuellen Repository-Stand nach `latest-github/` |
| **install-systemd.sh** | Optionale Alternative zum crontab: richtet die vier Dienste als systemd-Units ein |
| **systemd/** | Die zugehörigen Unit-Dateien |
| **README.md** | **Betriebsanleitung des Servers**: Autostart, Deployment, Zeitzone, Speichergrenzen, Fehlersuche |

Verwendung auf dem Linux-Server (`root@87.106.222.137`), alle Skripte liegen
dort direkt in `/root`:

```bash
./start-all.sh          # alle vier Dienste
./start-test.sh         # einzeln
```

Autostart nach einem Neustart über den crontab-Eintrag
`@reboot sleep 60 && /root/start-all.sh >> /root/start-all.log 2>&1`.
Einzelheiten in [linux-cmd/README.md](linux-cmd/README.md).

---

## FastAPI-ML/ — KI-Prognose-App

Eigenständige FastAPI-Anwendung auf Port 8080: Prognosen für 1/2/4/8 Stunden,
laufendes Genauigkeits-Monitoring und ein Chat-Assistent. Sie liest die
bestehenden Tabellen nur und schreibt ausschliesslich in eigene Tabellen mit
dem Präfix `ai_`. Aufbau, Modelle, Betrieb und Deployment sind in
[FastAPI-ML/README.md](FastAPI-ML/README.md) beschrieben, die
Benutzer-Dokumentation liegt zusätzlich als Seite unter `/doku.html`.

---

## Hinweise

- **flask/db_utils.py** ist eine Kopie von **scanner/db_utils.py** — Änderungen müssen in beiden Dateien gemacht werden
- **Datenbanktreiber:** `scanner/db_utils.py` und `flask/db_utils.py` verwenden `mysql.connector`; `get_event_and_weather_data.py` und die gesamte FastAPI-ML-App verwenden `pymysql`
- **Zwei Datenbanken:** `ph_fetch_prod` und `ph_fetch_test` mit identischem Schema, damit neue Scanner-Versionen gefahrlos erprobt werden können. Die alte Datenbank `ph_fetch` wurde am 31.07.2026 abgelöst (fehlende Messwerte wurden vorher übernommen)
