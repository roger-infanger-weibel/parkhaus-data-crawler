# FastAPI-ML – KI-gestützte Parkhaus-Prognose

Moderne FastAPI-Anwendung neben der bestehenden Flask-App: intelligente
Belegungsprognosen (1h/2h/4h/8h) mit Wetter-, Event- und historischen Daten,
laufendes Genauigkeits-Monitoring und ein deutschsprachiger Chat-Assistent.

## Funktionsumfang

| Seite | Inhalt |
|---|---|
| **Prognose** (`/`) | Aktuelle Belegung + Prognosen +1/2/4/8 h pro Parkhaus, Detail-Chart mit Ist-Verlauf, Wetter und Events |
| **Genauigkeit** (`/accuracy.html`) | MAE pro Horizont/Stadt/Parkhaus, KI vs. Basismodell, Skill-Score, Verlauf, Trainingsläufe |
| **Chat** (`/chat.html`) | Assistent mit semantischer Sprachverarbeitung (lokales ML-Modell): Verfügbarkeit, Prognosen, Empfehlungen, Wetter, Events, Genauigkeit |
| **Dokumentation** (`/doku.html`) | Erklärung für Nutzer (Datenquellen, wo ML eingesetzt wird) plus technischer Teil mit Tabellenübersicht |

## Architektur

- **Mehrere Modelle pro Horizont:** statistisches Basismodell
  (Wochentag/Stunden-Durchschnitt + Event-/Regen-Zuschlag) als Referenz,
  vier globale LightGBM-Regressionen (Ziel = Belegungsquote 0–1),
  vier Quantil-Modelle (α=0.2, pessimistisches 20%-Quantil: „mit 80 %
  Wahrscheinlichkeit mindestens X Plätze frei") und vier Voll-Klassifikatoren
  (P(free < 5): Wahrscheinlichkeit, dass das Parkhaus voll ist).
  Fällt LightGBM bei der Installation aus, wird automatisch
  scikit-learn verwendet.
- **Jobs (APScheduler, in-process, Zeitzone Europe/Zurich):** Prognose
  :10/:25/:40/:55, Evaluation :13/:28/:43/:58, Mapping-Refresh 03:15,
  Training 03:30. Ein neues Modell wird nur aktiviert, wenn es max. 10 %
  schlechter ist als das aktive. Das Training lässt sich per
  `AI_RETRAIN_ENABLED=0` abschalten – auf kleinen Servern nötig, siehe unten.
- **Metrik:** MAE in freien Plätzen (primär) und in Belegungs-Prozentpunkten;
  bewusst kein MAPE (explodiert bei `free ≈ 0`).
- **Bias-Korrektur:** Die Prognose wird pro Parkhaus und Horizont um den
  mittleren Bias der letzten 14 Tage korrigiert (aus `ai_accuracy_daily`,
  min. 50 Auswertungen). Gleicht systematische Abweichungen des globalen
  Modells bei einzelnen Häusern aus.
- **Kalender-Features:** Feiertage (kantonal), Brückentage und Schulferien
  fliessen als Merkmale ins Modell ein. Die Daten liegen in den Tabellen
  `ai_feiertage` und `ai_schulferien` (Sync per `kalender.sync_kalender_to_db`).
- **Neue Tabellen** (`schema.sql`, Präfix `ai_`): `ai_parkhaus_map`,
  `ai_model_runs`, `ai_predictions`, `ai_accuracy_daily`, `ai_chat_log`,
  `ai_feiertage`, `ai_schulferien`.
  Bestehende Tabellen werden **nur gelesen**.
- **Identity-Mapping:** `pls_fetch_current`-IDs ≠ `parkhaeuser`-IDs
  (Basel exakt, Luzern/St. Gallen Namens-Containment, Bern Wort-Vergleich);
  zentral gelöst in `core/identity.py` → Tabelle `ai_parkhaus_map`.

## Setup

Voraussetzung: **Python 3.9 oder neuer** (der Server läuft auf 3.9,
deshalb verzichtet der Code bewusst auf `X | None`-Syntax aus 3.10).

```bash
cd FastAPI-ML
pip install -r requirements.txt
python init_db.py --env test          # ai_*-Tabellen anlegen
python -m core.identity --env test    # Parkhaus-Mapping aufbauen
python -m forecast.train --env test   # Erst-Training (~5 Min)
python -m scripts.backfill_predictions --env test --days 7   # optional: Dashboard sofort füllen
uvicorn main:app --host 0.0.0.0 --port 80 --workers 1
```

Wichtig: **genau 1 Worker**, sonst läuft der Scheduler mehrfach.
Konfiguration über die gemeinsame `.env` im Repo-Root (siehe `.env.example`);
`AI_DEFAULT_ENV` steuert, gegen welche DB die Scheduler-Jobs laufen.
DB-Rechte: zur Laufzeit nur `SELECT, INSERT, UPDATE, DELETE`;
`CREATE, ALTER, INDEX` braucht einzig das einmalige `init_db.py`
(fuer ph_fetch_test und ph_fetch_prod bereits am 2026-07-30 ausgefuehrt).

## Training

Läuft auf dem Server (87.106.21.252), wöchentlich genügt:

```bash
cd /root/FastAPI-ML
python3 -m forecast.train --env prod
```

Die neuen Modelle greifen automatisch beim nächsten Prognoselauf. Details,
Zeitplan und die Deutung der Ausgabe: [MODELL-REFRESH.md](MODELL-REFRESH.md).

**Speicherbedarf:** 735 MB bei einem 60-Tage-Fenster, 1368 MB bei 120 Tagen;
die App selbst braucht betriebsbereit rund 216 MB. Auf einer Maschine mit
weniger als etwa 2 GB reicht das nicht — dort `AI_RETRAIN_ENABLED=0` setzen,
auf einem anderen Rechner trainieren und die Modelldateien übertragen
(`python -m scripts.export_models --env prod`). Das genügt, weil in
`ai_model_runs` nur der Dateiname steht.

Was passiert, wenn zu wenig Speicher da ist, zeigte der alte Server mit
641 MB und ohne Swap: der Kernel wirft dann den Datei-Cache weg,
einschliesslich der ausführbaren Teile laufender Programme, worauf auch
`sshd` unbenutzbar wird — die Maschine steht komplett.

## Deployment (Server)

```bash
git pull
pip install -r FastAPI-ML/requirements.txt
cd FastAPI-ML
python init_db.py --env prod        # nur beim allerersten Mal
./start-fastapi-ml.sh               # bzw. /root/start-all.sh
```

Vorausgesetzt: Port 80 in der Firewall **und** im IONOS Cloud Panel
freigegeben, in der `.env` `AI_DEFAULT_ENV=prod`. Der Port lässt sich über
`AI_APP_PORT` ändern.

Autostart nach einem Neustart läuft über den crontab-Eintrag
`@reboot sleep 60 && /root/start-all.sh`. Alternativ gibt es systemd-Units
(`bash linux-cmd/install-systemd.sh`), die zusätzlich Speicherlimits und
Neustart nach Absturz mitbringen.

### Umgebungswahl in der Oberfläche

**Prod ist der Normalfall** und der Umschalter ist ausgeblendet — sonst landen
Besucher versehentlich auf Testdaten.

| Aufruf | Wirkung |
|---|---|
| `http://87.106.21.252/?admin` | Umschalter erscheint, Freischaltung bleibt gemerkt |
| `http://87.106.21.252/?admin=0` | Umschalter wieder verstecken und auf prod zurück |

Läuft die Oberfläche auf Test, steht das zusätzlich rot in der Fusszeile.
Gemerkt wird die Freischaltung im `localStorage` des Browsers, gilt also pro
Gerät und Browser — es ist eine Bequemlichkeit, kein Zugriffsschutz.

### Wo die .env gesucht wird

`AI_ENV_FILE` (falls gesetzt) → `FastAPI-ML/.env` → `.env` im Repo-Root →
aufwärts vom Arbeitsverzeichnis. Liegt sie woanders, den Pfad über
`AI_ENV_FILE` setzen. `/api/health` zeigt unter `env_files` und `db_host`,
was tatsächlich geladen wurde — steht dort `KEINE .env gefunden`, läuft die
App auf Standardwerten.

## Tests

```bash
cd FastAPI-ML && python -m pytest tests/ -q
```

Manuelle Checkliste: die vier Seiten öffnen, im Chat die Beispielfragen
stellen, `/api/health` prüfen (aktive Modelle, letzte Prognose, Job-Status,
geladene `.env`).

## Chatbot — semantische Intent-Erkennung

`chatbot/semantic.py` nutzt ein lokales Sentence-Transformer-Modell
(`paraphrase-multilingual-MiniLM-L12-v2`, ~120 MB) für die Intent-Klassifikation
via Cosine-Similarity. Der Regex-Fallback in `intents.py` greift nur, wenn das
Modell nicht verfügbar ist oder der Score unter 0.45 liegt. Es werden keine
Daten an externe KI-Dienste gesendet.

## Hinweise

- Backfill (`scripts/backfill_predictions.py`) ist für max. `--days 14`
  leak-frei (Holdout-Fenster des Trainings).
- `scripts/generate_sample_data.py` erzeugt synthetische Daten – nur für
  leere lokale Datenbanken (eingebauter Schutz).
- Häuser ohne Stammdaten-Match (15 von 110, v.a. Bern und St. Gallen) werden
  trotzdem prognostiziert, nur ohne Event-Features.
- Events werden automatisch 2× täglich von `scanner/fetch_events.py` gescrapt
  (Hallenstadion, Tonhalle, Stadtcasino Basel, Luzerner Theater, Musical.ch,
  OLMA). Die Venue→Parkhaus-Zuordnung ist manuell gepflegt.
- Ist der Prognosestand älter als 30 Minuten, warnt die Prognoseseite. Die
  Spalten +1 h bis +8 h zählen ab dem Prognosestand, nicht ab der Uhrzeit
  des Betrachters.
