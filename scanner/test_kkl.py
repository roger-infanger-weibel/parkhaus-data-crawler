#!/usr/bin/env python3
"""Test KKL Scraper ohne DB-Zugriff."""

import json
import sys
from fetch_events import KKLLuzernScraper

def main():
    scraper = KKLLuzernScraper()
    print("🔍 Starte KKL-Scraper (Playwright)...")

    events = scraper.fetch()

    print(f"\n✅ {len(events)} Events gefunden:\n")
    for i, ev in enumerate(events, 1):
        print(f"{i}. {ev['start_time'].strftime('%d.%m.%Y %H:%M')} - {ev['title']}")
        print(f"   Venue: {ev['venue']}")
        print(f"   Category: {ev['category']}\n")

    # JSON-Output für weitere Verarbeitung
    json_output = [
        {
            "title": e["title"],
            "venue": e["venue"],
            "start_time": e["start_time"].isoformat(),
            "end_time": e["end_time"].isoformat(),
            "category": e["category"]
        }
        for e in events
    ]

    with open("kkl_events.json", "w") as f:
        json.dump(json_output, f, indent=2, ensure_ascii=False)

    print(f"💾 Events gespeichert in: kkl_events.json")

if __name__ == "__main__":
    main()
