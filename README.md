# Parkhaus-Daten-Crawler — Übersicht und Datei-Index

Sammelt alle 15 Minuten die Belegung von 110 Parkhäusern in Luzern, Basel,
Bern, Zürich und St. Gallen, speichert sie in MariaDB und stellt sie über zwei
Weboberflächen dar — eine klassische und eine mit KI-Prognose.

## Wo was läuft

| Server | Dienste | HealthCheck | API-Doc |
|---|---|---|---|
| **87.106.21.252** | KI-Prognose (FastAPI-ML), Port 80 | [Health](http://87.106.21.252:80/api/health) | [Docs](http://87.106.21.252:80/docs) |
| **87.106.222.137** | Scanner prod + test, Flask-Dashboard Port 80 |  - | - |
| `parkhaus.roil.ch` | MariaDB (`ph_fetch_prod`, `ph_fetch_test`) |  — | - |

Die KI-Prognose ist am 04.08.2026 auf einen eigenen, grösseren Server
umgezogen und trainiert ihre Modelle seither selbst.

## Die vier Bestandteile

| Ordner | Was | Läuft als |
|---|---|---|
| [`scanner/`](#scanner--datensammlung) | Holt die Daten von den Stadt-APIs | Dauerprozess, alle 15 Min |
| [`flask/`](#flask--klassisches-dashboard) | Dashboard mit Ist-Daten | Webserver, Port 80 |
| [`FastAPI-ML/`](#fastapi-ml--ki-prognose) | Prognose, Genauigkeits-Monitoring, Chat | Webserver, Port 80 |
| [`linux-cmd/`](#linux-cmd--serverbetrieb) | Start-Skripte und Betriebsanleitung | — |

```
parkhaus-data-crawler/
├── README.md                ← dieses Dokument
├── .gitignore
├── scanner/                 ← Datensammlung
├── flask/                   ← Dashboard (Port 80)
├── FastAPI-ML/              ← KI-Prognose (Port 80)
└── linux-cmd/               ← Betrieb und Autostart
```

---

## scanner/ — Datensammlung

| Datei | Beschreibung | Aufgerufen von |
|---|---|---|
| **scheduler.py** | Dauerprozess: startet die Sammlung alle 15 Min, Wetter/Events um 06:00 und 18:00 | manuell bzw. `start-prod.sh` |
| **collect_data.py** | Orchestrator: ruft alle Stadt-Collector auf, protokolliert in die DB. CLI mit `--simulation` | `scheduler.py` |
| **base.py** | Abstrakte Basisklasse `BaseParkingCollector` mit Retry-Logik und Fallback auf den letzten Snapshot | alle Collector erben davon |
| **luzern.py** | Collector Luzern (PLS-API) | `collect_data.py` |
| **basel.py** | Collector Basel (ParkenDD) | `collect_data.py` |
| **zurich.py** | Collector Zürich (ParkenDD); pflegt zusätzlich `zurich_parking_map.json` | `collect_data.py` |
| **stgallen.py** | Collector St. Gallen (Open Data) | `collect_data.py` |
| **bern.py** | Collector Bern (XML); überschreibt auch `fetch_raw_data()` | `collect_data.py` |
| **db_utils.py** | DB-Zugriff (`mysql.connector`), UPSERT, Mock-Modus für die Simulation | `base.py`, `collect_data.py` |
| **get_event_and_weather_data.py** | Lädt Wetter von Open-Meteo (`pymysql`) | `scheduler.py` |
| **fetch_events.py** | Scraper für echte Veranstaltungsdaten von Venue-Websites (Hallenstadion, Tonhalle, Stadtcasino Basel, Luzerner Theater, OLMA, Musical.ch) | `scheduler.py` (2× täglich) |
| **cities.json** | Stadt-Konfiguration: IDs, API-Adressen, Aktivierung | `collect_data.py` |
| **zurich_parking_map.json** | Zuordnung und Kapazitäten der Zürcher Parkhäuser; wird vom Collector aktualisiert | `zurich.py` |
| **requirements.txt** | Abhängigkeiten | — |
| **version.py**, **__init__.py**, **.gitignore** | Versionsnummer, Package-Marker, Ausnahmen | — |

**Dokumentation:** [README](scanner/README.md) ·
[QUICK_START](scanner/QUICK_START.md) ·
[ARCHITECTURE](scanner/ARCHITECTURE.md) ·
[CODE_EXAMPLES](scanner/CODE_EXAMPLES.md) ·
[CHANGES_SUMMARY](scanner/CHANGES_SUMMARY.md) ·
[SERVER](scanner/SERVER.md) (SFTP-Pfade) ·
[SIMULATION_MODE_GUIDE](scanner/SIMULATION_MODE_GUIDE.md) und
[README_SIMULATION](scanner/README_SIMULATION.md) sowie
[MANIFEST](scanner/MANIFEST.md) — die letzten drei sind historisch
(abgeschlossene Umstellung).

---

## flask/ — klassisches Dashboard

| Datei | Beschreibung |
|---|---|
| **web_server.py** | Flask-Server auf Port 80. Städte, Gruppen und Events kommen aus der Datenbank; Umschaltung prod/test per `?env=` |
| **db_utils.py** | DB-Zugriff (Kopie von `scanner/db_utils.py`) |
| **index.html** | Dashboard: Parkhaus-Übersicht und Diagramme |
| **logs.html** | Log-Ansicht: Crawler-Protokolle und Statistiken |

---

## FastAPI-ML/ — KI-Prognose

Eigenständige Anwendung auf Port 80. Liest die bestehenden Tabellen **nur**
und schreibt ausschliesslich in eigene Tabellen mit dem Präfix `ai_`.

### Gerüst

| Datei | Beschreibung |
|---|---|
| **main.py** | FastAPI-App, startet den Scheduler, bindet Router und Oberfläche ein |
| **config.py** | Konfiguration, `.env`-Suche, Auflösung der Modelldateien |
| **db.py** | DB-Zugriff via `pymysql`, Streaming für grosse Abfragen, Timeouts |
| **schema.sql** / **init_db.py** | Anlage der `ai_*`-Tabellen (einmalig); **migrate_v2.sql** für Quantil-/Kalender-Erweiterung |
| **requirements.txt** / **.env.example** | Abhängigkeiten, dokumentierte Variablen |

### core/ — Grundlagen

| Datei | Beschreibung |
|---|---|
| **identity.py** | Zuordnung der Parkhaus-Kennungen zwischen Messwerten und Stammdaten → `ai_parkhaus_map` |
| **data_access.py** | Alle Lese-Abfragen (Belegung, Wetter, Events, Stammdaten, Bias) |
| **kalender.py** | Schweizer Feiertage, Brückentage und Schulferien als Features; liest aus DB (`ai_feiertage`, `ai_schulferien`) mit Fallback auf Berechnung |
| **timeutil.py** | Europe/Zurich, 15-Minuten-Raster |

### forecast/ — Prognose

| Datei | Beschreibung |
|---|---|
| **features.py** | Rasterung und Merkmalsbildung, gemeinsam für Training und Prognose |
| **baseline.py** | Statistisches Basismodell (Wochentag/Stunde) als Vergleichsmassstab |
| **ml_model.py** | LightGBM-Wrapper (Regression, Quantil α=0.2, Voll-Klassifikator) mit Fallback auf scikit-learn |
| **train.py** | Trainingslauf, Holdout-Bewertung, Aktivierungssperre |
| **predict.py** | Erzeugt Prognosen alle 15 Minuten |
| **evaluate.py** | Vergleicht gereifte Prognosen mit den Ist-Werten |

### api/ — Schnittstelle

| Datei | Beschreibung |
|---|---|
| **routes_meta.py** | `/api/health`, `/api/cities`, `/api/parkings/{stadt}` |
| **routes_forecast.py** | Aktuelle Prognosen, Detailverlauf, Empfehlung |
| **routes_accuracy.py** | Genauigkeit gesamt, pro Stadt, pro Parkhaus, Verlauf |
| **routes_chat.py** | `/api/chat` |
| **services.py** | Gemeinsame Logik für API und Chatbot |

### chatbot/ — Assistent mit semantischer Sprachverarbeitung

| Datei | Beschreibung |
|---|---|
| **engine.py** | Fassade `ChatEngine` mit Session-Kontext und Slot-Filling |
| **semantic.py** | Intent-Klassifikation via Sentence-Transformer (lokales ML-Modell) |
| **entities.py** | Erkennt Stadt, Parkhaus und deutsche Zeitangaben |
| **intents.py** | Semantische + Regex-Klassifikation (Fallback) |
| **handlers.py** | Beantwortet je Absicht aus der Datenbank |
| **responses.py** | Deutsche Antworttexte |

### static/ — Oberfläche

| Datei | Beschreibung |
|---|---|
| **index.html** / **js/forecast.js** | Prognoseseite mit Rückblick- und Prognosespalten |
| **accuracy.html** / **js/accuracy.js** | Genauigkeits-Dashboard |
| **chat.html** / **js/chat.js** | Chat-Assistent |
| **doku.html** | Erklärung für Nutzer und technische Details |
| **js/api.js** | Gemeinsamer Fetch-Wrapper, prod/test-Umschalter, Link-Menü |
| **css/app.css** | Stylesheet |

### scripts/ — Werkzeuge

| Datei | Beschreibung |
|---|---|
| **export_models.py** | Sammelt die aktiven Modelldateien zum Kopieren auf den Server |
| **backfill_predictions.py** | Simuliert vergangene Prognosen, um das Genauigkeits-Dashboard zu füllen |
| **migrate_old_db.py** | Übernahm fehlende Messwerte aus der abgelösten Datenbank `ph_fetch` |
| **generate_sample_data.py** | Synthetische Daten für eine leere lokale Datenbank |

### tests/

`test_identity.py`, `test_features.py`, `test_baseline.py`,
`test_entities.py`, `test_intents.py` — 45 Tests, Aufruf mit
`python -m pytest tests/ -q`.

**Dokumentation:** [README](FastAPI-ML/README.md) ·
[MODELL-REFRESH](FastAPI-ML/MODELL-REFRESH.md) (wöchentliche Routine)

---

## linux-cmd/ — Serverbetrieb

| Datei | Beschreibung |
|---|---|
| **README.md** | **Betriebsanleitung**: Autostart, Zeitzone, Speichergrenzen, Deployment, Fehlersuche |
| **start-all.sh** | Ruft die vier Startskripte nacheinander auf — für den Autostart |
| **start-prod.sh** / **start-test.sh** | Scanner der jeweiligen Umgebung neu starten |
| **start-flask.sh** | Dashboard (Port 80) neu starten |
| **start-fastapi-ml.sh** | KI-Prognose (Port 80) neu starten |
| **copy-github.sh** | Holt den aktuellen Repository-Stand nach `latest-github/` |
| **install-systemd.sh** | Optionale Alternative: richtet die Dienste als systemd-Units ein |
| **systemd/*.service** | Die vier Unit-Dateien |

Auf dem Server liegen die Skripte direkt in `/root`. Autostart über den
crontab-Eintrag `@reboot sleep 60 && /root/start-all.sh`.

---

## Datenfluss

```
scheduler.py  (Dauerprozess)
├── collect_data.py  (alle 15 Min)
│   ├── cities.json
│   ├── base.py + luzern/basel/bern/zurich/stgallen.py ──→ Stadt-APIs
│   └── db_utils.py ──→ pls_fetch_current, log
│
├── get_event_and_weather_data.py  (06:00 + 18:00)
│   └── Open-Meteo API ──→ weather_forecasts
│
└── fetch_events.py  (06:30 + 18:30)
    └── Venue-Websites ──→ local_events, event_parkhaus

web_server.py  (Port 80)
└── db_utils.py ──→ MariaDB (nur lesend) ──→ index.html / logs.html

FastAPI-ML/main.py  (Port 80)
├── forecast/predict.py    :10/:25/:40/:55 ──→ ai_predictions
├── forecast/evaluate.py   :13/:28/:43/:58 ──→ ai_accuracy_daily
├── core/identity.py       03:15           ──→ ai_parkhaus_map
├── forecast/train.py      (auf dem PC)    ──→ ai_model_runs + models_store/
└── static/ ──→ Prognose, Genauigkeit, Chat, Dokumentation
```

## Datenbanken

Zwei Datenbanken mit identischem Schema: **`ph_fetch_prod`** für den Betrieb
und **`ph_fetch_test`** zum Erproben neuer Scanner-Versionen. Die alte
Datenbank `ph_fetch` wurde am 31.07.2026 abgelöst; fehlende Messwerte wurden
vorher übernommen.

Vom Scanner befüllt: `pls_fetch_current` (~1,5 Mio. Zeilen), `weather_forecasts`,
`local_events`, `event_parkhaus`, `cities`, `parkhaeuser`, `log`.
Von der KI-App: `ai_predictions`, `ai_accuracy_daily`, `ai_model_runs`,
`ai_parkhaus_map`, `ai_chat_log`, `ai_feiertage`, `ai_schulferien`.
Beschreibung aller Tabellen unter `/doku.html`.

## Hinweise

- **flask/db_utils.py** ist eine Kopie von **scanner/db_utils.py** — Änderungen
  müssen in beiden Dateien erfolgen
- **Datenbanktreiber:** `scanner/db_utils.py` und `flask/db_utils.py` verwenden
  `mysql.connector`; `get_event_and_weather_data.py` und die gesamte
  FastAPI-ML-App verwenden `pymysql`
- **Nicht im Repository:** `.env` (Zugangsdaten), `data/` (JSON-Snapshots),
  `FastAPI-ML/models_store/*.joblib` (trainierte Modelle, mehrere MB),
  Datenbank-Dumps
- **Modelle** werden auf einem PC trainiert und auf den Server kopiert — der
  Server hat mit 641 MB RAM zu wenig Speicher dafür, siehe
  [MODELL-REFRESH.md](FastAPI-ML/MODELL-REFRESH.md)
