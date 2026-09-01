"""Ein Handler pro Intent. Liefert (Antworttext, strukturiertes Payload).

Die Handler rufen dieselben Service-Funktionen wie die REST-API (direkt,
nicht via HTTP) und liefern strukturierte Daten - ein spaeterer LLM-Engine
kann sie unveraendert als Tools verwenden.
"""
from datetime import datetime, timedelta

import db
from api import services
from core import data_access as da
from chatbot import responses as R
from chatbot import llm

MAX_LIST = 5


def greeting(env, entities, now):
    return R.GREETINGS[0], None


def help_(env, entities, now):
    return R.HELP_TEXT, None


def _enrich(snap, mapping):
    m = mapping.get(snap["pls_id"], {})
    extras = []
    if m.get("price_category"):
        extras.append(f"Preis: {m['price_category']}")
    if m.get("url"):
        extras.append(f"Info: {m['url']}")
    if m.get("latitude") and m.get("longitude"):
        lat, lon = float(m["latitude"]), float(m["longitude"])
        extras.append(f"Route: https://www.google.com/maps/dir/?api=1&destination={lat},{lon}")
    return extras, m


def current(env, entities, now):
    city = entities.get("city")
    parkhaus = entities.get("parkhaus")
    snaps = da.latest_snapshots(env=env, city=city)
    mapping = {m["pls_id"]: m for m in da.get_mapping(env=env, city=city)}
    if parkhaus:
        snap = next((s for s in snaps if s["pls_id"] == parkhaus["pls_id"]), None)
        if snap is None:
            return (f"Für das Parkhaus {parkhaus['name']} habe ich gerade "
                    f"keine aktuellen Daten."), None
        occ_pct = round(100 * (snap["total"] - snap["free"]) / snap["total"]) if snap["total"] else None
        extras, m = _enrich(snap, mapping)
        text = (f"Im {snap['name']} ({R.city_name(snap['city'])}) sind aktuell "
                f"{snap['free']} von {snap['total']} Plätzen frei"
                + (f" (Belegung {occ_pct} %)" if occ_pct is not None else "") + ".")
        if extras:
            text += "\n" + " · ".join(extras)
        return text, {"type": "current", "houses": [_snap_payload(snap, mapping)]}

    if not snaps:
        return f"Für {R.city_name(city)} habe ich gerade keine aktuellen Daten.", None
    snaps = sorted(snaps, key=lambda s: s["free"], reverse=True)
    total_free = sum(s["free"] for s in snaps)
    text = (f"In {R.city_name(city)} sind aktuell {total_free} Plätze frei "
            f"({len(snaps)} Parkhäuser). Am meisten Platz gibt es hier:\n")
    text += "\n".join(
        f"• {s['name']}: {s['free']} von {s['total']} frei"
        + (f" ({mapping.get(s['pls_id'], {}).get('price_category', '')})" if mapping.get(s['pls_id'], {}).get('price_category') else "")
        for s in snaps[:MAX_LIST]
    )
    return text, {"type": "current", "houses": [_snap_payload(s, mapping) for s in snaps[:MAX_LIST]]}


def forecast(env, entities, now):
    parkhaus = entities.get("parkhaus")
    t = entities.get("time")
    at = t["at"] if t else now + timedelta(hours=1)
    if parkhaus is None:
        return best_parking(env, entities, now)

    city = parkhaus["city"]
    horizon_hours = (at - now).total_seconds() / 3600
    if horizon_hours <= 8.5:
        rows = db.query(
            """
            SELECT model_type, predicted_free, predicted_occ, target_time
            FROM ai_predictions
            WHERE city = %s AND pls_id = %s
              AND target_time BETWEEN %s AND %s
            ORDER BY created_at DESC, model_type
            """,
            (city, parkhaus["pls_id"], at - timedelta(minutes=45),
             at + timedelta(minutes=45)), env=env,
        )
        best = next((r for r in rows if r["model_type"] == "ml"), rows[0] if rows else None)
        if best:
            occ_pct = round(float(best["predicted_occ"]) * 100)
            text = (f"Prognose für {parkhaus['name']} ({R.city_name(city)}) "
                    f"{R.fmt_time(best['target_time'], now)}: voraussichtlich "
                    f"{best['predicted_free']} freie Plätze "
                    f"(Belegung ca. {occ_pct} %).")
            return text, {"type": "forecast", "house": parkhaus["name"],
                          "at": best["target_time"].isoformat(),
                          "predicted_free": best["predicted_free"],
                          "model": best["model_type"]}
        return (f"Für {parkhaus['name']} liegt noch keine Prognose vor - "
                f"bitte in ein paar Minuten nochmals fragen."), None

    # Ausserhalb des 8h-Modellfensters: saisonale Schaetzung
    baseline = services.load_active_baseline(env)
    if baseline:
        occ = baseline.predict_one(city, parkhaus["pls_id"], at)
        snap = next((s for s in da.latest_snapshots(env=env, city=city, max_age_hours=24)
                     if s["pls_id"] == parkhaus["pls_id"]), None)
        if occ is not None and snap and snap["total"]:
            free = max(0, min(int(round((1 - occ) * snap["total"])), snap["total"]))
            text = (f"{R.fmt_time(at, now)} liegt ausserhalb meines 8-Stunden-"
                    f"Prognosefensters. Erfahrungsgemäss (saisonaler Durchschnitt) "
                    f"sind im {parkhaus['name']} dann etwa {free} von "
                    f"{snap['total']} Plätzen frei - ohne Gewähr.")
            return text, {"type": "forecast", "house": parkhaus["name"],
                          "at": at.isoformat(), "predicted_free": free,
                          "model": "baseline_seasonal"}
    return ("So weit in die Zukunft kann ich noch keine verlässliche "
            "Prognose machen (Fenster: 8 Stunden)."), None


def best_parking(env, entities, now):
    city = entities["city"]
    t = entities.get("time")
    at = t["at"] if t else now
    result = services.best_parking(env, city, at, entities.get("min_free") or 0)
    recs = result["recommendations"]
    if not recs:
        return (f"Für {R.city_name(city)} habe ich zu diesem Zeitpunkt "
                f"keine Prognosen. Versuche es mit einem Zeitpunkt innerhalb "
                f"der nächsten 8 Stunden."), None
    mapping = {m["pls_id"]: m for m in da.get_mapping(env=env, city=city)}
    when = R.fmt_time(at, now) if at > now else "jetzt"
    caveat = (" (saisonale Schätzung, ausserhalb des 8h-Prognosefensters)"
              if result["method"] == "baseline_seasonal" else "")
    text = f"Empfehlung für {R.city_name(city)} {when}{caveat}:\n"
    lines = []
    for r in recs[:3]:
        m = mapping.get(r.get("pls_id", ""), {})
        line = f"• {r['name']}: voraussichtlich {r['predicted_free']} von {r['total']} frei"
        if r.get("recent_mae_free"):
            line += f" (±{r['recent_mae_free']:.0f})"
        if m.get("price_category"):
            line += f" · {m['price_category']}"
        if m.get("url"):
            line += f"\n  Info: {m['url']}"
        if m.get("latitude") and m.get("longitude"):
            line += f"\n  Route: https://www.google.com/maps/dir/?api=1&destination={float(m['latitude'])},{float(m['longitude'])}"
        lines.append(line)
    text += "\n".join(lines)
    return text, {"type": "best_parking", **result}


def weather(env, entities, now):
    city = entities["city"]
    t = entities.get("time")
    at = t["at"] if t else now
    df = da.weather_range(env=env, start=at.replace(minute=0, second=0, microsecond=0),
                          end=at + timedelta(hours=6), city=city)
    if df.empty:
        return f"Für {R.city_name(city)} habe ich gerade keine Wetterdaten.", None
    first = df.iloc[0]
    rain = float(df["precipitation"].fillna(0).sum())
    text = (f"Wetter in {R.city_name(city)} {R.fmt_time(at, now)}: "
            f"{first['temperature']:.0f} °C, ")
    text += ("kein Niederschlag erwartet." if rain < 0.2 else
             f"insgesamt ca. {rain:.1f} mm Niederschlag in den nächsten Stunden - "
             f"die Parkhäuser dürften etwas voller werden.")
    payload = {"type": "weather", "city": city, "hours": [
        {"ts": r.ts.isoformat(), "temperature": r.temperature,
         "precipitation": r.precipitation} for r in df.itertuples()
    ]}
    return text, payload


def events(env, entities, now):
    city = entities["city"]
    t = entities.get("time")
    day = (t["at"] if t else now).date()
    df = da.events_range(env=env,
                         start=datetime.combine(day, datetime.min.time()),
                         end=datetime.combine(day, datetime.max.time()), city=city)
    if df.empty:
        return (f"Für {R.city_name(city)} sind am "
                f"{day.strftime('%d.%m.%Y')} keine Veranstaltungen erfasst."), None
    lines, seen, ev_payload = [], set(), []
    for _, e in df.iterrows():
        if e["event_id"] in seen:
            continue
        seen.add(e["event_id"])
        affected = df[df["event_id"] == e["event_id"]]["pls_id"].dropna().tolist()
        lines.append(f"• {e['title']} ({e['venue']}), "
                     f"{e['start_time'].strftime('%H:%M')}-{e['end_time'].strftime('%H:%M')}")
        ev_payload.append({"title": e["title"], "venue": e["venue"],
                           "start": e["start_time"].isoformat(),
                           "affected_pls": affected})
    text = (f"Veranstaltungen in {R.city_name(city)} am {day.strftime('%d.%m.%Y')}:\n"
            + "\n".join(lines)
            + "\nRund um diese Zeiten sind die umliegenden Parkhäuser erfahrungsgemäss voller.")
    return text, {"type": "events", "events": ev_payload}


def accuracy(env, entities, now):
    since = (now - timedelta(days=14)).date()
    rows = db.query(
        """
        SELECT model_type, horizon_h,
               SUM(n) AS n, SUM(mae_free * n) / SUM(n) AS mae_free
        FROM ai_accuracy_daily
        WHERE city = '' AND pls_id = '' AND day >= %s
        GROUP BY model_type, horizon_h ORDER BY horizon_h
        """,
        (since,), env=env,
    )
    ml = {int(r["horizon_h"]): float(r["mae_free"]) for r in rows if r["model_type"] == "ml"}
    base = {int(r["horizon_h"]): float(r["mae_free"]) for r in rows if r["model_type"] == "baseline"}
    if not ml and not base:
        return ("Es liegen noch keine ausgewerteten Prognosen vor - das "
                "Monitoring füllt sich, sobald Prognosen reifen."), None
    lines = []
    for h in sorted(set(ml) | set(base)):
        line = f"• {h} h voraus: "
        if h in ml:
            line += f"KI-Modell ±{ml[h]:.1f} Plätze"
        if h in base:
            line += f" (einfacher Durchschnitt: ±{base[h]:.1f})"
        lines.append(line)
    text = ("Mittlerer Prognosefehler der letzten 14 Tage über alle Städte:\n"
            + "\n".join(lines)
            + "\nDetails pro Stadt und Parkhaus findest du auf der Seite «Genauigkeit».")
    return text, {"type": "accuracy", "ml": ml, "baseline": base}


def _build_context(env, entities, now):
    parts = [f"Datum/Zeit: {now.strftime('%d.%m.%Y %H:%M')}"]
    city = entities.get("city")
    if city:
        snaps = da.latest_snapshots(env=env, city=city)
        if snaps:
            lines = [f"  {s['name']}: {s['free']}/{s['total']} frei" for s in snaps[:5]]
            parts.append(f"Aktuelle Belegung {R.city_name(city)}:\n" + "\n".join(lines))
    return "\n".join(parts)


def fallback(env, entities, now):
    reply = llm.ask(entities.get("_raw_text", ""), env, _build_context(env, entities, now))
    if reply:
        return reply, {"type": "llm_fallback"}
    return R.FALLBACK, None


def _snap_payload(s, mapping=None) -> dict:
    d = {"pls_id": s["pls_id"], "name": s["name"], "free": s["free"],
         "total": s["total"], "city": s["city"]}
    if mapping:
        m = mapping.get(s["pls_id"], {})
        d["price_category"] = m.get("price_category")
        d["url"] = m.get("url")
        d["lat"] = float(m["latitude"]) if m.get("latitude") else None
        d["lon"] = float(m["longitude"]) if m.get("longitude") else None
    return d


HANDLERS = {
    "greeting": greeting,
    "help": help_,
    "current": current,
    "forecast": forecast,
    "best_parking": best_parking,
    "weather": weather,
    "events": events,
    "accuracy": accuracy,
    "fallback": fallback,
}
