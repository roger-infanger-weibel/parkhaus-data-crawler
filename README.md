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
├── flask/                      ← Web-Server (Dashboard)
│   ├── web_server.py
│   ├── db_utils.py
│   ├── index.html / logs.html
│   └── cities.json / groups.json / events.json
└── linux-cmd/                  ← Linux Start-Skripte
    ├── start-prod.sh
    └── start-test.sh
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
| **groups.json** | Parkhaus-Gruppierungen pro Stadt | Nur von `flask/web_server.py` verwendet | — |
| **events.json** | Event-Definitionen für Dashboard | Nur von `flask/web_server.py` verwendet | — |
| **requirements.txt** | Python-Abhängigkeiten | `pip install -r` | — |
| **version.py** | Versionsnummer | — | — |
| **__init__.py** | Package-Marker | Python-Import-System | — |

---

## flask/ — Web-Server-Dateien

| Datei | Beschreibung | Aufgerufen von | Verwendet |
|-------|-------------|----------------|-----------|
| **web_server.py** | Flask-Server: API-Endpoints + statische Dateien | Manuell (`python web_server.py`) | `db_utils.py`, `cities.json`, `groups.json`, `events.json`, `index.html`, `logs.html` |
| **db_utils.py** | DB-Layer (Kopie von scanner/db_utils.py) | `web_server.py` | `db_config.json` (optional) |
| **index.html** | Dashboard: Parkhaus-Übersicht und Diagramme | `web_server.py` (Route `/`) | Lädt `cities.json`, `groups.json`, `events.json` via HTTP |
| **logs.html** | Log-Ansicht: Crawler-Logs und Statistiken | `web_server.py` (Route `/logs`) | API-Endpoints von `web_server.py` |
| **cities.json** | Stadt-Konfiguration (Kopie) | `web_server.py` (Route `/cities.json`) | — |
| **groups.json** | Parkhaus-Gruppierungen (Kopie) | `web_server.py` (Route `/groups.json`) | — |
| **events.json** | Event-Definitionen (Kopie) | `web_server.py` (Route `/events.json`) | — |

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

web_server.py  (separater Prozess)
├── db_utils.py ──→ MariaDB (lesend)
├── cities.json / groups.json / events.json
├── index.html (Dashboard)
└── logs.html (Log-Viewer)
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

---

## linux-cmd/ — Linux Start-Skripte

| Datei | Beschreibung |
|-------|-------------|
| **start-prod.sh** | Stoppt laufenden Prod-Scheduler, kopiert `scheduler.py` → `scheduler-prod.py` und startet ihn im Hintergrund (nohup) |
| **start-test.sh** | Stoppt laufenden Test-Scheduler, kopiert `scheduler.py` → `scheduler-test.py` und startet ihn im Hintergrund (nohup) |

Verwendung auf dem Linux-Server (`root@87.106.222.137`):
```bash
# Test-Umgebung starten
bash start-test.sh

# Produktions-Umgebung starten
bash start-prod.sh
```

---

## Hinweise

- **flask/db_utils.py** ist eine Kopie von **scanner/db_utils.py** — Änderungen müssen in beiden Dateien gemacht werden
- **get_event_and_weather_data.py** verwendet `pymysql`, alle anderen DB-Zugriffe verwenden `mysql.connector`
