"""Echte Veranstaltungsdaten von Stadt-Websites scrapen.

Ersetzt die generierten Dummy-Events in local_events durch reale Daten.
Pro Stadt ein Scraper, der den oeffentlichen Veranstaltungskalender abfragt.

    python scanner/fetch_events.py [--days 30] [--city zurich]

Schreibt in local_events (id, title, venue, city, start_time, end_time,
description, category, peak_occupancy_bonus) und event_parkhaus.
"""
import argparse
import hashlib
import json
import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Optional

import requests
from bs4 import BeautifulSoup

from db_utils import get_connection, load_db_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Parkhaus-Crawler/1.0 (Forschungsprojekt; kontakt@example.ch)",
    "Accept-Language": "de-CH,de;q=0.9",
}

CATEGORY_BONUS = {
    "konzert": 0.40,
    "musical": 0.40,
    "oper": 0.35,
    "theater": 0.30,
    "sport": 0.45,
    "messe": 0.50,
    "festival": 0.45,
    "markt": 0.25,
    "fuehrung": 0.10,
    "vortrag": 0.15,
    "party": 0.30,
    "kino": 0.15,
    "default": 0.20,
}

VENUE_PARKHAUS = {
    "zurich": {
        "hallenstadion": ["zuerichparkhaushallenstadiong1", "zuerichparkhaushallenstadiong2"],
        "tonhalle": ["zuerichparkhaustonhalle"],
        "opernhaus": ["zuerichparkhausopera"],
        "kongresshaus": ["zuerichparkhaustonhalle"],
        "theater 11": ["zuerichparkplatztheater11", "zuerichparkhausmessezuerichag"],
        "maag halle": ["zuerichparkplatztheater11"],
        "samsung hall": ["zuerichparkhaushallenstadiong1"],
        "theater am hechtplatz": ["zuerichparkhausjelmoli"],
        "kaufleuten": ["zuerichparkhausjelmoli"],
    },
    "luzern": {
        "kkl": ["luzernparkhausbahnhof", "luzernparkhausbahnhofp2", "luzernparkhausbahnhofp1"],
        "luzerner theater": ["luzernparkhausaltstadt", "luzernparkhausloewe", "luzernparkhausbahnhof"],
        "stadttheater": ["luzernparkhausaltstadt", "luzernparkhausloewe"],
        "messe luzern": ["luzernparkhausbahnhof"],
    },
    "basel": {
        "st. jakobshalle": ["baselparkhausstjakob"],
        "theater basel": ["baselparkhaussteinen"],
        "musical theater": ["baselparkhaussteinen"],
        "stadtcasino": ["baselparkhaussteinen"],
        "messe basel": ["baselmesseparkhaus"],
        "st. jakob-park": ["baselparkhausstjakob"],
    },
    "bern": {
        "stade de suisse": ["bernparkhauswankdorf"],
        "kursaal": ["bernparkhausmetro"],
        "kultur casino": ["bernparkhausmetro"],
        "bea expo": ["bernparkhauswankdorf"],
        "stadttheater": ["bernparkhausmetro"],
    },
    "stgallen": {
        "olma": ["stgallenparkhausolma"],
        "stadttheater": ["stgallenparkhausbahnhof"],
        "tonhalle": ["stgallenparkhausbahnhof"],
    },
}


def _event_id(city: str, title: str, start: datetime) -> str:
    raw = f"{city}-{title}-{start.isoformat()}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def _guess_category(title: str, description: str = "") -> str:
    text = (title + " " + description).lower()
    for cat in ("konzert", "musical", "oper", "theater", "sport", "messe",
                "festival", "markt", "fuehrung", "vortrag", "party", "kino"):
        if cat in text:
            return cat
    return "default"


def _bonus_for_category(category: str) -> float:
    return CATEGORY_BONUS.get(category, CATEGORY_BONUS["default"])


def _match_venue_to_parkhaus(city: str, venue: str) -> list[str]:
    mapping = VENUE_PARKHAUS.get(city, {})
    venue_lower = venue.lower()
    for key, parkhaus_ids in mapping.items():
        if key in venue_lower:
            return parkhaus_ids
    return []


class EventScraper(ABC):
    city: str

    @abstractmethod
    def fetch(self, start: datetime, end: datetime) -> list[dict]:
        """Liefert Liste von {title, venue, start_time, end_time, description, category}."""
        ...

    def _get(self, url: str, **kwargs) -> requests.Response:
        resp = requests.get(url, headers=HEADERS, timeout=30, **kwargs)
        resp.raise_for_status()
        return resp


class ZurichScraper(EventScraper):
    city = "zurich"

    def fetch(self, start: datetime, end: datetime) -> list[dict]:
        events = []
        url = "https://www.zuerich.com/de/besuchen/events"
        try:
            resp = self._get(url, params={
                "startDate": start.strftime("%Y-%m-%d"),
                "endDate": end.strftime("%Y-%m-%d"),
            })
            soup = BeautifulSoup(resp.text, "html.parser")
            for article in soup.select("article, .event-item, .teaser"):
                ev = self._parse_item(article)
                if ev:
                    events.append(ev)
        except Exception as e:
            logger.warning("Zuerich scrape fehlgeschlagen: %s", e)
        return events

    def _parse_item(self, el) -> Optional[dict]:
        title_el = el.select_one("h2, h3, .title, .event-title")
        if not title_el:
            return None
        title = title_el.get_text(strip=True)
        venue = ""
        venue_el = el.select_one(".location, .venue, .event-location")
        if venue_el:
            venue = venue_el.get_text(strip=True)
        date_el = el.select_one("time, .date, .event-date")
        if not date_el:
            return None
        date_text = date_el.get("datetime", date_el.get_text(strip=True))
        try:
            dt = datetime.fromisoformat(date_text.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
        category = _guess_category(title)
        return {
            "title": title, "venue": venue,
            "start_time": dt, "end_time": dt + timedelta(hours=2),
            "description": "", "category": category,
        }


class LuzernScraper(EventScraper):
    city = "luzern"

    def fetch(self, start: datetime, end: datetime) -> list[dict]:
        events = []
        url = "https://www.luzern.com/de/veranstaltungen/"
        try:
            resp = self._get(url, params={
                "von": start.strftime("%Y-%m-%d"),
                "bis": end.strftime("%Y-%m-%d"),
            })
            soup = BeautifulSoup(resp.text, "html.parser")
            for item in soup.select(".event-item, article, .teaser"):
                ev = self._parse_item(item)
                if ev:
                    events.append(ev)
        except Exception as e:
            logger.warning("Luzern scrape fehlgeschlagen: %s", e)
        return events

    def _parse_item(self, el) -> Optional[dict]:
        title_el = el.select_one("h2, h3, .title")
        if not title_el:
            return None
        title = title_el.get_text(strip=True)
        venue_el = el.select_one(".location, .venue")
        venue = venue_el.get_text(strip=True) if venue_el else ""
        date_el = el.select_one("time, .date")
        if not date_el:
            return None
        date_text = date_el.get("datetime", date_el.get_text(strip=True))
        try:
            dt = datetime.fromisoformat(date_text.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
        category = _guess_category(title, venue)
        return {
            "title": title, "venue": venue,
            "start_time": dt, "end_time": dt + timedelta(hours=2),
            "description": "", "category": category,
        }


class BaselScraper(EventScraper):
    city = "basel"

    def fetch(self, start: datetime, end: datetime) -> list[dict]:
        events = []
        url = "https://www.basel.com/de/events"
        try:
            resp = self._get(url, params={
                "dateFrom": start.strftime("%Y-%m-%d"),
                "dateTo": end.strftime("%Y-%m-%d"),
            })
            soup = BeautifulSoup(resp.text, "html.parser")
            for item in soup.select("article, .event-item, .teaser"):
                ev = self._parse_item(item)
                if ev:
                    events.append(ev)
        except Exception as e:
            logger.warning("Basel scrape fehlgeschlagen: %s", e)
        return events

    def _parse_item(self, el) -> Optional[dict]:
        title_el = el.select_one("h2, h3, .title")
        if not title_el:
            return None
        title = title_el.get_text(strip=True)
        venue_el = el.select_one(".location, .venue")
        venue = venue_el.get_text(strip=True) if venue_el else ""
        date_el = el.select_one("time, .date")
        if not date_el:
            return None
        date_text = date_el.get("datetime", date_el.get_text(strip=True))
        try:
            dt = datetime.fromisoformat(date_text.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
        category = _guess_category(title, venue)
        return {
            "title": title, "venue": venue,
            "start_time": dt, "end_time": dt + timedelta(hours=2),
            "description": "", "category": category,
        }


class BernScraper(EventScraper):
    city = "bern"

    def fetch(self, start: datetime, end: datetime) -> list[dict]:
        events = []
        url = "https://www.bern.com/de/veranstaltungen"
        try:
            resp = self._get(url, params={
                "dateFrom": start.strftime("%Y-%m-%d"),
                "dateTo": end.strftime("%Y-%m-%d"),
            })
            soup = BeautifulSoup(resp.text, "html.parser")
            for item in soup.select("article, .event-item, .teaser"):
                ev = self._parse_item(item)
                if ev:
                    events.append(ev)
        except Exception as e:
            logger.warning("Bern scrape fehlgeschlagen: %s", e)
        return events

    def _parse_item(self, el) -> Optional[dict]:
        title_el = el.select_one("h2, h3, .title")
        if not title_el:
            return None
        title = title_el.get_text(strip=True)
        venue_el = el.select_one(".location, .venue")
        venue = venue_el.get_text(strip=True) if venue_el else ""
        date_el = el.select_one("time, .date")
        if not date_el:
            return None
        date_text = date_el.get("datetime", date_el.get_text(strip=True))
        try:
            dt = datetime.fromisoformat(date_text.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
        category = _guess_category(title, venue)
        return {
            "title": title, "venue": venue,
            "start_time": dt, "end_time": dt + timedelta(hours=2),
            "description": "", "category": category,
        }


class StGallenScraper(EventScraper):
    city = "stgallen"

    def fetch(self, start: datetime, end: datetime) -> list[dict]:
        events = []
        url = "https://www.st.gallen-bodensee.ch/de/veranstaltungen"
        try:
            resp = self._get(url, params={
                "dateFrom": start.strftime("%Y-%m-%d"),
                "dateTo": end.strftime("%Y-%m-%d"),
            })
            soup = BeautifulSoup(resp.text, "html.parser")
            for item in soup.select("article, .event-item, .teaser"):
                ev = self._parse_item(item)
                if ev:
                    events.append(ev)
        except Exception as e:
            logger.warning("St.Gallen scrape fehlgeschlagen: %s", e)
        return events

    def _parse_item(self, el) -> Optional[dict]:
        title_el = el.select_one("h2, h3, .title")
        if not title_el:
            return None
        title = title_el.get_text(strip=True)
        venue_el = el.select_one(".location, .venue")
        venue = venue_el.get_text(strip=True) if venue_el else ""
        date_el = el.select_one("time, .date")
        if not date_el:
            return None
        date_text = date_el.get("datetime", date_el.get_text(strip=True))
        try:
            dt = datetime.fromisoformat(date_text.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
        category = _guess_category(title, venue)
        return {
            "title": title, "venue": venue,
            "start_time": dt, "end_time": dt + timedelta(hours=2),
            "description": "", "category": category,
        }


SCRAPERS = [
    ZurichScraper(),
    LuzernScraper(),
    BaselScraper(),
    BernScraper(),
    StGallenScraper(),
]


def fetch_and_store(days: int = 30, city: Optional[str] = None) -> dict:
    """Events scrapen und in local_events + event_parkhaus schreiben."""
    now = datetime.now()
    start = now - timedelta(days=1)
    end = now + timedelta(days=days)

    conn = get_connection()
    cursor = conn.cursor()
    stats = {}

    scrapers = SCRAPERS
    if city:
        scrapers = [s for s in SCRAPERS if s.city == city]

    for scraper in scrapers:
        logger.info("Scrape %s ...", scraper.city)
        try:
            raw_events = scraper.fetch(start, end)
        except Exception as e:
            logger.error("Scraper %s fehlgeschlagen: %s", scraper.city, e)
            stats[scraper.city] = {"events": 0, "error": str(e)}
            continue

        n_events = 0
        n_mappings = 0
        for ev in raw_events:
            eid = _event_id(scraper.city, ev["title"], ev["start_time"])
            bonus = _bonus_for_category(ev.get("category", "default"))
            cursor.execute(
                """
                INSERT INTO local_events
                    (id, title, venue, city, start_time, end_time,
                     description, category, peak_occupancy_bonus)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    title = VALUES(title),
                    venue = VALUES(venue),
                    end_time = VALUES(end_time)
                """,
                (eid, ev["title"], ev.get("venue", ""), scraper.city,
                 ev["start_time"], ev["end_time"],
                 ev.get("description", ""), ev.get("category", ""),
                 bonus),
            )
            n_events += 1

            parkhaus_ids = _match_venue_to_parkhaus(scraper.city, ev.get("venue", ""))
            for pid in parkhaus_ids:
                cursor.execute(
                    """
                    INSERT INTO event_parkhaus (event_id, parkhaus_id)
                    VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE event_id = VALUES(event_id)
                    """,
                    (eid, pid),
                )
                n_mappings += 1

        conn.commit()
        stats[scraper.city] = {"events": n_events, "mappings": n_mappings}
        logger.info("  %s: %d Events, %d Zuordnungen", scraper.city, n_events, n_mappings)

    cursor.close()
    conn.close()
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Echte Events von Stadt-Websites scrapen")
    parser.add_argument("--days", type=int, default=30,
                        help="Tage in die Zukunft scrapen (Standard: 30)")
    parser.add_argument("--city", type=str, default=None,
                        help="Nur eine Stadt scrapen (z.B. zurich, luzern)")
    args = parser.parse_args()
    result = fetch_and_store(days=args.days, city=args.city)
    print(json.dumps(result, indent=2))
