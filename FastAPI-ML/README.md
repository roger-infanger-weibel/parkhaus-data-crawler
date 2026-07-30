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

## Architektur

- **Zwei Modelle:** statistisches Basismodell (Wochentag/Stunden-Durchschnitt
  + Event-/Regen-Zuschlag) als transparente Referenz und vier globale
  LightGBM-Modelle (eines pro Horizont, Ziel = Belegungsquote 0–1).
  Fällt LightGBM bei der Installation aus, wird automatisch
  scikit-learn `HistGradientBoostingRegressor` verwendet.
- **Jobs (APScheduler, in-process):** Prognose :10/:25/:40/:55, Evaluation
  :13/:28/:43/:58, Mapping-Refresh 03:15, Training 03:30. Ein neues Modell
  wird nur aktiviert, wenn es max. 10 % schlechter ist als das aktive.
- **Metrik:** MAE in freien Plätzen (primär) und in Belegungs-Prozentpunkten;
  bewusst kein MAPE (explodiert bei `free ≈ 0`).
- **Neue Tabellen** (`schema.sql`, Präfix `ai_`): `ai_parkhaus_map`,
  `ai_model_runs`, `ai_predictions`, `ai_accuracy_daily`, `ai_chat_log`.
  Bestehende Tabellen werden **nur gelesen**.
- **Identity-Mapping:** `pls_fetch_current`-IDs ≠ `parkhaeuser`-IDs
  (Basel exakt, Luzern/St. Gallen Namens-Containment, Bern Wort-Vergleich);
  zentral gelöst in `core/identity.py` → Tabelle `ai_parkhaus_map`.

## Setup

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

## Deployment (Server)

```bash
git pull
pip install -r FastAPI-ML/requirements.txt
cd FastAPI-ML
python init_db.py --env prod
python -m forecast.train --env prod
nohup uvicorn main:app --host 0.0.0.0 --port 8080 --workers 1 > ../fastapi-ml.log 2>&1 &
```

Siehe auch `linux-cmd/start-fastapi-ml.sh`. Port 8080 in der Firewall öffnen.
In der `.env` des Servers `AI_DEFAULT_ENV=prod` setzen.

## Tests

```bash
cd FastAPI-ML && python -m pytest tests/ -q
```

Manuelle Checkliste: die drei Seiten öffnen, im Chat die Beispielfragen
stellen, `/api/health` prüfen (aktive Modelle, letzte Prognose, Job-Status).

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
- Häuser ohne Stammdaten-Match (z.B. mehrere Berner Parkings) werden
  trotzdem prognostiziert, nur ohne Event-Features.
