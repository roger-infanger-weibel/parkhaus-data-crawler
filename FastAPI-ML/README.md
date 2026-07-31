# FastAPI-ML – KI-gestützte Parkhaus-Prognose

Moderne FastAPI-Anwendung neben der bestehenden Flask-App: intelligente
Belegungsprognosen (1h/2h/4h/8h) mit Wetter-, Event- und historischen Daten,
laufendes Genauigkeits-Monitoring und ein deutschsprachiger Chat-Assistent.

## Funktionsumfang

| Seite | Inhalt |
|---|---|
| **Prognose** (`/`) | Aktuelle Belegung + Prognosen +1/2/4/8 h pro Parkhaus, Detail-Chart mit Ist-Verlauf, Wetter und Events |
| **Genauigkeit** (`/accuracy.html`) | MAE pro Horizont/Stadt/Parkhaus, KI vs. Basismodell, Skill-Score, Verlauf, Trainingsläufe |
| **Chat** (`/chat.html`) | Regelbasierter Assistent: Verfügbarkeit, Prognosen, Empfehlungen, Wetter, Events, Genauigkeit |
| **Dokumentation** (`/doku.html`) | Erklärung für Nutzer (Datenquellen, wo ML eingesetzt wird) plus technischer Teil mit Tabellenübersicht |

## Architektur

- **Zwei Modelle:** statistisches Basismodell (Wochentag/Stunden-Durchschnitt
  + Event-/Regen-Zuschlag) als transparente Referenz und vier globale
  LightGBM-Modelle (eines pro Horizont, Ziel = Belegungsquote 0–1).
  Fällt LightGBM bei der Installation aus, wird automatisch
  scikit-learn `HistGradientBoostingRegressor` verwendet.
- **Jobs (APScheduler, in-process, Zeitzone Europe/Zurich):** Prognose
  :10/:25/:40/:55, Evaluation :13/:28/:43/:58, Mapping-Refresh 03:15,
  Training 03:30. Ein neues Modell wird nur aktiviert, wenn es max. 10 %
  schlechter ist als das aktive. Das Training lässt sich per
  `AI_RETRAIN_ENABLED=0` abschalten – auf kleinen Servern nötig, siehe unten.
- **Metrik:** MAE in freien Plätzen (primär) und in Belegungs-Prozentpunkten;
  bewusst kein MAPE (explodiert bei `free ≈ 0`).
- **Neue Tabellen** (`schema.sql`, Präfix `ai_`): `ai_parkhaus_map`,
  `ai_model_runs`, `ai_predictions`, `ai_accuracy_daily`, `ai_chat_log`.
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
uvicorn main:app --host 0.0.0.0 --port 8080 --workers 1
```

Wichtig: **genau 1 Worker**, sonst läuft der Scheduler mehrfach.
Konfiguration über die gemeinsame `.env` im Repo-Root (siehe `.env.example`);
`AI_DEFAULT_ENV` steuert, gegen welche DB die Scheduler-Jobs laufen.
DB-Rechte: zur Laufzeit nur `SELECT, INSERT, UPDATE, DELETE`;
`CREATE, ALTER, INDEX` braucht einzig das einmalige `init_db.py`
(fuer ph_fetch_test und ph_fetch_prod bereits am 2026-07-30 ausgefuehrt).

## Training: nicht auf dem Zielserver

Das Training hält das gesamte Zeitfenster im Arbeitsspeicher — gemessen
**735 MB** bei 60 Tagen, **1368 MB** bei 120 Tagen. Der Produktivserver
(87.106.222.137) hat **641 MB und keinen Swap**; das Training braucht also
mehr, als die Maschine besitzt. Kein Limit ändert daran etwas.

Ohne Swap wirft der Kernel bei Speichermangel den Datei-Cache weg,
einschliesslich der ausführbaren Teile laufender Programme — auch `sshd`
wird dann unbenutzbar. Genau so blieb die Maschine am 30./31.07.2026
dreimal komplett stehen.

Zum Vergleich: die App selbst braucht betriebsbereit rund 216 MB
(pandas/numpy/lightgbm plus die fünf Modelle).

**Deshalb dort abschalten:**

```
AI_RETRAIN_ENABLED=0
```

**Stattdessen auf einer Arbeitsstation trainieren** (wöchentlich genügt) und
nur die Modelldateien übertragen:

```bash
python -m forecast.train --env prod
python -m scripts.export_models --env prod       # sammelt die aktiven Dateien
```

`export_models` legt genau die fünf Dateien des aktiven Laufs (~18 MB) nach
`export_models/` und nennt den Kopierbefehl. Ziel ist
`/root/FastAPI-ML/models_store/`. Das genügt, weil in `ai_model_runs` nur der
Dateiname steht — die Datenbank kennt den aktiven Lauf bereits, sobald das
Training gegen sie gelaufen ist. Zügig kopieren: bis die Dateien da sind,
findet der Server kein Modell und erzeugt einen Zyklus lang keine Prognosen.

**Schritt-für-Schritt-Anleitung dafür: [MODELL-REFRESH.md](MODELL-REFRESH.md).**
Serverbetrieb und Fehlersuche: [../linux-cmd/README.md](../linux-cmd/README.md).

## Deployment (Server)

```bash
git pull
pip install -r FastAPI-ML/requirements.txt
cd FastAPI-ML
python init_db.py --env prod        # nur beim allerersten Mal
./start-fastapi-ml.sh               # bzw. /root/start-all.sh
```

Vorausgesetzt: Port 8080 in der Firewall **und** im IONOS Cloud Panel
freigegeben, in der `.env` `AI_DEFAULT_ENV=prod` und `AI_RETRAIN_ENABLED=0`.

Autostart nach einem Neustart läuft über den crontab-Eintrag
`@reboot sleep 60 && /root/start-all.sh`. Alternativ gibt es systemd-Units
(`bash linux-cmd/install-systemd.sh`), die zusätzlich Speicherlimits und
Neustart nach Absturz mitbringen.

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

## Chatbot-Erweiterung (LLM)

`chatbot/engine.py` definiert die Fassade `ChatEngine`. Die Handler liefern
bereits strukturierte Daten – ein späterer `LLMEngine` (z.B. Claude API)
kann sie unverändert als Tools nutzen; nur Klassifikation und
Antwortformulierung würden ersetzt.

## Hinweise

- Backfill (`scripts/backfill_predictions.py`) ist für max. `--days 14`
  leak-frei (Holdout-Fenster des Trainings).
- `scripts/generate_sample_data.py` erzeugt synthetische Daten – nur für
  leere lokale Datenbanken (eingebauter Schutz).
- Häuser ohne Stammdaten-Match (15 von 110, v.a. Bern und St. Gallen) werden
  trotzdem prognostiziert, nur ohne Event-Features.
- Die Events in `local_events` sind **erzeugt, nicht real**: wiederkehrende
  Termine für Stadttheater/KKL Luzern und Theater 11 Zürich, Fr–So. Für
  Basel, Bern und St. Gallen existieren keine Events.
- Ist der Prognosestand älter als 30 Minuten, warnt die Prognoseseite. Die
  Spalten +1 h bis +8 h zählen ab dem Prognosestand, nicht ab der Uhrzeit
  des Betrachters.
