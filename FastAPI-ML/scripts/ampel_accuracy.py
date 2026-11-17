"""Ampel-Trefferquote: wie oft stimmt gruen/gelb/rot zwischen Prognose und Ist?

Aufruf auf dem Server:
    source /root/.venv/bin/activate
    cd /root/FastAPI-ML
    python -m scripts.ampel_accuracy --env prod
"""
import argparse
from collections import defaultdict

import db
from core.timeutil import now_local
from datetime import timedelta


def ampel(free, total):
    """Gleiche Logik wie ampelKlasse() in forecast.js."""
    if not total or total == 0:
        return "gelb"
    ratio = free / total
    if ratio > 0.1 and free > 15:
        return "gruen"
    if ratio > 0.05 and free > 15:
        return "gelb"
    return "rot"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default="prod")
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    since = now_local() - timedelta(days=args.days)

    rows = db.query(
        """
        SELECT city, pls_id, horizon_h, model_type,
               predicted_free, actual_free, total_at_pred
        FROM ai_predictions
        WHERE actual_free IS NOT NULL
          AND total_at_pred IS NOT NULL AND total_at_pred > 0
          AND model_type = 'ml'
          AND target_time >= %s
        """,
        (since,),
        env=args.env,
    )

    print(f"Auswertung der letzten {args.days} Tage")
    print(f"ML-Prognosen mit Ist-Wert: {len(rows):,}\n")

    if not rows:
        print("Keine Daten gefunden.")
        return

    # -- Pro Horizont --
    print("=== Ampel-Trefferquote pro Horizont ===")
    for hz in [1, 2, 4, 8]:
        subset = [r for r in rows if r["horizon_h"] == hz]
        if not subset:
            continue
        correct = sum(
            1 for r in subset
            if ampel(r["predicted_free"], r["total_at_pred"])
            == ampel(r["actual_free"], r["total_at_pred"])
        )
        pct = correct / len(subset) * 100
        print(f"  +{hz}h:  {pct:.1f}%  ({correct:,} / {len(subset):,})")

    # -- Pro Stadt (1h) --
    print("\n=== Pro Stadt (1h-Prognose) ===")
    cities = sorted({r["city"] for r in rows})
    for city in cities:
        subset = [r for r in rows if r["city"] == city and r["horizon_h"] == 1]
        if not subset:
            continue
        correct = sum(
            1 for r in subset
            if ampel(r["predicted_free"], r["total_at_pred"])
            == ampel(r["actual_free"], r["total_at_pred"])
        )
        pct = correct / len(subset) * 100
        print(f"  {city:10s}: {pct:.1f}%  ({correct:,} / {len(subset):,})")

    # -- Nachbar-Genauigkeit (1 Stufe daneben = OK) --
    ADJACENT = {
        ("gruen", "gelb"), ("gelb", "gruen"),
        ("gelb", "rot"), ("rot", "gelb"),
    }
    adj_correct = sum(
        1 for r in rows
        if ampel(r["predicted_free"], r["total_at_pred"])
        == ampel(r["actual_free"], r["total_at_pred"])
        or (ampel(r["predicted_free"], r["total_at_pred"]),
            ampel(r["actual_free"], r["total_at_pred"])) in ADJACENT
    )
    print(f"\n=== Nachbar-Genauigkeit (1 Stufe daneben zaehlt als OK) ===")
    print(f"  {adj_correct / len(rows) * 100:.1f}%  ({adj_correct:,} / {len(rows):,})")

    # -- Confusion Matrix --
    print("\n=== Fehlerkategorien ===")
    cats = defaultdict(int)
    for r in rows:
        p = ampel(r["predicted_free"], r["total_at_pred"])
        a = ampel(r["actual_free"], r["total_at_pred"])
        cats[(p, a)] += 1

    total_n = len(rows)
    for (pred, act), n in sorted(cats.items(), key=lambda x: -x[1]):
        marker = ""
        if pred == "gruen" and act == "rot":
            marker = "  <-- GEFAEHRLICH"
        elif pred == "rot" and act == "gruen":
            marker = "  <-- unnoetig abgeschreckt"
        print(f"  Prognose={pred:5s}  Ist={act:5s}:  {n:>6,}  ({n / total_n * 100:.1f}%){marker}")

    dangerous = cats.get(("gruen", "rot"), 0)
    print(f"\n=> Gefaehrliche Fehler (gruen gesagt, war rot): "
          f"{dangerous:,} = {dangerous / total_n * 100:.2f}%")


if __name__ == "__main__":
    main()
