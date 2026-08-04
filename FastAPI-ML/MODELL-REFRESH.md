# Modelle auffrischen

Wöchentliche Routine. Seit dem Serverumzug am 04.08.2026 läuft das Training
**direkt auf dem Server** (87.106.21.252) — die Maschine hat genug
Arbeitsspeicher. Nichts muss mehr kopiert werden.

## Wann

**Einmal pro Woche genügt.** Um auf die aktuelle Lage zu reagieren, braucht es
kein Training — die frischen Messwerte gehen bei jeder Prognose als Eingabe
ein. Nachtrainiert wird nur wegen langsamer Veränderungen: Jahreszeiten, neue
Parkhäuser, geänderte Kapazitäten, Baustellen, nachgefüllte Datenlücken.

Ausserplanmässig, wenn auf der Seite **Genauigkeit** die Fehlerkurve über
mehrere Tage steigt.

---

## Der Ablauf

```bash
cd /root/FastAPI-ML
python3 -m forecast.train --env prod
python3 -m forecast.train --env test     # nur falls Test-Umgebung genutzt
```

Ein Lauf dauert wenige Minuten. Danach greifen die neuen Modelle automatisch
beim nächsten Viertelstunden-Lauf.

Automatisch per crontab, sonntags um 03:00:

```
0 3 * * 0 cd /root/FastAPI-ML && python3 -m forecast.train --env prod >> /root/train.log 2>&1
```

Alternativ erledigt das der eingebaute Scheduler nachts um 03:30, sofern
`AI_RETRAIN_ENABLED` nicht auf `0` steht.

## Die Ausgabe lesen

```
Horizont 1h: ML MAE 5.69 Plaetze / 2.31 pp - Baseline 33.35 / 12.64
```

Links das neue KI-Modell, rechts das einfache Basismodell zum Vergleich.
Steigt der ML-Wert bei 1 h und 2 h gegenüber dem letzten Lauf deutlich an,
stimmt etwas mit den Daten nicht — dann der Ursache nachgehen, etwa einer
Lücke:

```sql
SELECT MAX(fetch_ts) FROM ph_fetch_prod.pls_fetch_current;
```

### «NICHT aktiviert» ist kein Fehler

```
WARNING Lauf 50 (ml h=2) NICHT aktiviert: MAE 4.984 > 4.422 * 1.10
```

Das neue Modell war für diesen Horizont mehr als 10 % schlechter als das
laufende, also bleibt das bessere aktiv. Genau dafür ist die Regel da: nach
einem Datenausfall verdrängt kein schwaches Modell ein gutes. Die übrigen
Horizonte sind davon nicht berührt.

Beide Modelle werden dafür auf **demselben Testzeitraum** bewertet — das
bisherige wird eigens noch einmal durchgerechnet. Im Log steht der Vergleich:

```
Horizont 2h: bisheriges Modell auf demselben Holdout: 5.89 pp (neu: 5.89 pp)
```

Steht dort stattdessen «trotz schlechterem MAE aktiviert: Datei des bisherigen
Laufs fehlt», stammte das bisher aktive Modell von einer anderen Maschine.
Dann wird das neue genommen — ein etwas schlechteres Modell, das lädt, ist
besser als ein besseres, das keine Prognosen erzeugt.

## Kontrollieren

```bash
curl -sS http://localhost/api/health
```

- **`active_runs`** zeigt fünf Einträge; die Zeitstempel sollten vom heutigen
  Lauf sein (ausser bei einem «NICHT aktiviert»-Horizont)
- **`last_prediction`** wird beim nächsten Viertelstunden-Lauf frisch

Oder im Browser auf `http://87.106.21.252/`: erscheint dort die rote Warnung
«Prognose veraltet», hat etwas nicht geklappt. Das Log sagt dann, was:

```bash
grep -E "Modelldatei fehlt|NICHT aktiviert" /root/FastAPI-ML/fastapi-ml.log
```

---

## Alternative: auf einem anderen Rechner trainieren

Nötig nur, wenn der Server zu wenig Arbeitsspeicher hat (Training braucht
735 MB bei 60 Tagen, 1368 MB bei 120 Tagen). Dann auf dem Server
`AI_RETRAIN_ENABLED=0` setzen und:

```bash
cd FastAPI-ML
python -m forecast.train --env prod
python -m scripts.export_models --env prod
scp export_models/*.joblib root@87.106.21.252:/root/FastAPI-ML/models_store/
```

`export_models` sammelt genau die fünf Dateien des aktiven Laufs (~18 MB) in
`export_models/` — der Ordner wird bei jedem Lauf geleert, es liegen also nie
alte Dateien darin, die man versehentlich mitkopiert.

**Zügig kopieren:** das Training markiert den neuen Lauf sofort als aktiv, und
bis die Dateien eintreffen, findet der Server kein Modell und erzeugt einen
Zyklus lang keine Prognosen.

### prod und test im selben Ordner

`models_store/` ist ein gemeinsamer Ablageort für beide Umgebungen. Welche
Datei zu welcher gehört, steht in der jeweiligen Datenbank
(`ai_model_runs.artifact_path`). Damit nichts kollidiert:

- Der Dateiname enthält die Umgebung: `ml_h1_prod_…` bzw. `ml_h1_test_…`
- Beim Aufräumen bleibt jede Datei verschont, auf die noch ein aktiver Lauf
  zeigt — auch der der *anderen* Umgebung

Ältere Dateien ohne Umgebung im Namen (vor dem 31.07.2026) bleiben gültig.

## Häufige Stolpersteine

| Beobachtung | Ursache |
|---|---|
| Prognosen bleiben alt, obwohl trainiert | Modelldateien nicht am Ort der App — Log auf «Modelldatei fehlt» prüfen |
| `KEINE .env gefunden` in `/api/health` | `AI_ENV_FILE` setzen oder `.env` nach `/root/FastAPI-ML/` legen |
| Ein Horizont bleibt alt | «NICHT aktiviert» — Absicht, siehe oben |
| Training bricht mit Speicherfehler ab | Fenster verkleinern: `--days 60` |
| Server hängt beim Training | Zu wenig RAM — `AI_RETRAIN_ENABLED=0` und woanders trainieren |
