# Modelle auffrischen — Anleitung für den PC

Wöchentliche Routine, Dauer rund 10 Minuten. Das Training läuft auf dem PC,
weil der Server mit **641 MB RAM und ohne Swap** dafür schlicht zu klein ist —
das Training braucht 735 MB, also mehr, als die Maschine besitzt. Drei
Versuche am 30./31.07.2026 legten sie jedes Mal komplett lahm.

## Wann

**Einmal pro Woche genügt.** Um auf die aktuelle Lage zu reagieren, braucht es
kein Training — die frischen Messwerte gehen bei jeder Prognose als Eingabe
ein. Nachtrainiert wird nur wegen langsamer Veränderungen: Jahreszeiten, neue
Parkhäuser, geänderte Kapazitäten, Baustellen, nachgefüllte Datenlücken.

Ausserplanmässig, wenn auf der Seite **Genauigkeit** die Fehlerkurve über
mehrere Tage steigt.

## Voraussetzungen (einmalig)

- Python 3.9+ mit `pip install -r requirements.txt`
- Eine `.env` mit den Datenbank-Zugangsdaten (liegt im Repo-Root)
- WinSCP oder `scp` für die Übertragung
- Auf dem Server muss `AI_RETRAIN_ENABLED=0` gesetzt sein, sonst trainiert er
  nachts selbst und bringt sich zum Absturz

---

## Schritt 1 — Trainieren

```bash
cd FastAPI-ML
python -m forecast.train --env prod
```

Dauert etwa 5 Minuten und braucht bis zu 1,4 GB Arbeitsspeicher. Die Ausgabe
zeigt pro Horizont, wie gut das neue Modell ist:

```
Horizont 1h: ML MAE 5.64 Plaetze / 2.22 pp - Baseline 34.26 / 12.83
```

Links das neue KI-Modell, rechts das einfache Basismodell zum Vergleich.

**Prüfen:** Ist der ML-Wert bei 1 h und 2 h *schlechter* als beim letzten Mal,
stimmt etwas mit den Daten nicht — dann nicht ausliefern, sondern erst der
Ursache nachgehen (etwa eine Lücke in `pls_fetch_current`).

Falls du auch die Test-Umgebung nutzt, denselben Befehl mit `--env test`.

## Schritt 2 — Dateien einsammeln

```bash
python -m scripts.export_models --env prod
```

Das legt genau die fünf Dateien des aktiven Laufs (~18 MB) nach
`FastAPI-ML/export_models/` und zeigt sie an:

```
prod (ph_fetch_prod):
  Basis  baseline_prod_20260731_0930.joblib   1.7 MB  (trainiert 31.07. 09:30)
  +1h    ml_h1_prod_20260731_0930.joblib      4.0 MB
  +2h    ml_h2_prod_20260731_0930.joblib      4.0 MB
  +4h    ml_h4_prod_20260731_0930.joblib      4.0 MB
  +8h    ml_h8_prod_20260731_0930.joblib      4.0 MB
```

Der Ordner wird bei jedem Lauf geleert — es liegen also nie alte Dateien
darin, die man versehentlich mitkopiert.

### prod und test im selben Ordner

`models_store/` ist ein gemeinsamer Ablageort für beide Umgebungen. Welche
Datei zu welcher gehört, steht **nicht** im Dateinamen als Verzeichnis,
sondern in der jeweiligen Datenbank (`ai_model_runs.artifact_path`). Damit
nichts kollidiert:

- Der Dateiname enthält die Umgebung: `ml_h1_prod_…` bzw. `ml_h1_test_…`
- Beim Aufräumen alter Modelle bleibt jede Datei verschont, auf die noch ein
  aktiver Lauf zeigt — auch der der *anderen* Umgebung

Du kannst prod und test also gefahrlos nacheinander trainieren und alle
Dateien in denselben Zielordner kopieren. Ein Überschreiben gibt es nicht.

Ältere Dateien ohne Umgebung im Namen (vor dem 31.07.2026 erzeugt) bleiben
gültig — sie werden weiterhin über den in der Datenbank gespeicherten Namen
gefunden.

## Schritt 3 — Auf den Server kopieren

Ziel: `/root/FastAPI-ML/models_store/`

Mit WinSCP den Inhalt von `export_models/` dorthin ziehen, oder:

```bash
scp export_models/*.joblib root@87.106.222.137:/root/FastAPI-ML/models_store/
```

**Zügig machen.** Das Training hat den neuen Lauf in der Datenbank sofort als
aktiv markiert. Bis die Dateien auf dem Server sind, findet er kein Modell und
erzeugt keine Prognosen — höchstens ein 15-Minuten-Zyklus fällt aus.

Die alten Dateien müssen nicht gelöscht werden; es zählt nur, was in
`ai_model_runs` als aktiv steht.

## Schritt 4 — Kontrollieren

Auf dem Server:

```bash
curl -sS http://localhost:8080/api/health
```

Zwei Dinge müssen stimmen:

- **`last_prediction`** wird beim nächsten Viertelstunden-Lauf
  (:10/:25/:40/:55) frisch. Bleibt der Wert alt, fehlen die Modelldateien.
- **`active_runs`** zeigt fünf Einträge mit dem Zeitstempel von heute.

Oder im Browser auf `http://87.106.222.137:8080/`: erscheint dort die rote
Warnung «Prognose veraltet», hat etwas nicht geklappt.

Falls das Log Klarheit bringen soll:

```bash
grep "Modelldatei fehlt" /root/FastAPI-ML/fastapi-ml.log
```

Diese Meldung bedeutet: Datenbank und Dateien passen nicht zusammen — Schritt 3
wiederholen.

---

## Kurzfassung

```bash
cd FastAPI-ML
python -m forecast.train --env prod
python -m scripts.export_models --env prod
scp export_models/*.joblib root@87.106.222.137:/root/FastAPI-ML/models_store/
# danach auf dem Server: curl -sS http://localhost:8080/api/health
```

## Häufige Stolpersteine

| Beobachtung | Ursache |
|---|---|
| Prognosen bleiben alt, obwohl trainiert | Dateien nicht kopiert (Schritt 3) |
| `KEINE .env gefunden` in `/api/health` | Server findet die `.env` nicht → `AI_ENV_FILE` setzen oder `ln -sf /root/myenv/.env /root/.env` |
| Server hängt sich nachts auf | `AI_RETRAIN_ENABLED=0` fehlt in der `.env` |
| Training bricht mit Speicherfehler ab | Fenster verkleinern: `--days 60` |
| MAE plötzlich viel schlechter | Datenlücke prüfen: `SELECT MAX(fetch_ts) FROM ph_fetch_prod.pls_fetch_current;` |
