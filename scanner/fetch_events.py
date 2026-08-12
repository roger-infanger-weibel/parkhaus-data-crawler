"""Echte Veranstaltungsdaten von Venue-Websites scrapen.

Pro Venue ein Scraper, der die oeffentliche Programmseite abfragt.
Wird 2x taeglich automatisch vom Scanner-Scheduler aufgerufen.

    python scanner/fetch_events.py [--days 30] [--venue hallenstadion]

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

from db_utils import get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

from constants import SWISS_TZ

HEADERS = {
    "User-Agent": "Parkhaus-Crawler/1.0 (Forschungsprojekt)",
    "Accept-Language": "de-CH,de;q=0.9",
}

CATEGORY_BONUS = {
    "konzert": 0.40, "musical": 0.40, "oper": 0.35, "theater": 0.30,
    "sport": 0.45, "messe": 0.50, "festival": 0.45, "comedy": 0.30,
    "show": 0.35, "klassik": 0.30, "default": 0.20,
}

MONATE_DE = {
    "jan": 1, "feb": 2, "mär": 3, "mar": 3, "apr": 4, "mai": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "okt": 10, "oct": 10, "nov": 11, "dez": 12, "dec": 12,
}


def _event_id(venue: str, title: str, start: datetime) -> str:
    raw = f"{venue}-{title}-{start.isoformat()}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def _guess_category(title: str) -> str:
    text = title.lower()
    for cat in ("konzert", "musical", "oper", "theater", "sport", "messe",
                "festival", "comedy", "show", "klassik"):
        if cat in text:
            return cat
    return "default"


def _bonus(category: str) -> float:
    return CATEGORY_BONUS.get(category, CATEGORY_BONUS["default"])


def _parse_de_date(text: str, year: int = None) -> Optional[datetime]:
    """Parst deutsche Datumsformate wie '31 Aug', 'Mi 19. Aug', '22.08.2026'."""
    if year is None:
        year = datetime.now().year
    text = text.strip().lower()

    # DD.MM.YYYY
    m = re.search(r'(\d{1,2})\.(\d{1,2})\.(\d{4})', text)
    if m:
        return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))

    # DD.MM.
    m = re.search(r'(\d{1,2})\.(\d{1,2})\.', text)
    if m:
        return datetime(year, int(m.group(2)), int(m.group(1)))

    # DD Mon or Mon DD
    for mon_str, mon_num in MONATE_DE.items():
        if mon_str in text:
            m = re.search(r'(\d{1,2})', text)
            if m:
                return datetime(year, mon_num, int(m.group(1)))
    return None


def _parse_time(text: str) -> Optional[tuple[int, int]]:
    """Extrahiert HH:MM aus '20:00 Uhr' o.ä."""
    m = re.search(r'(\d{1,2})[:\.](\d{2})', text)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


class VenueScraper(ABC):
    name: str
    city: str
    parkhaus_ids: list[str]

    @abstractmethod
    def fetch(self) -> list[dict]:
        ...

    def _get(self, url: str, **kwargs) -> requests.Response:
        resp = requests.get(url, headers=HEADERS, timeout=30, **kwargs)
        resp.raise_for_status()
        return resp


class HallenstadionScraper(VenueScraper):
    name = "Hallenstadion"
    city = "zurich"
    parkhaus_ids = ["zuerichparkhausmessezuerichag"]

    def fetch(self) -> list[dict]:
        events = []
        try:
            resp = self._get("https://www.hallenstadion.ch/de/events")
            soup = BeautifulSoup(resp.text, "html.parser")
            for card in soup.select("a[href*='/events/']"):
                h5 = card.select_one("h5")
                if not h5:
                    continue
                title = h5.get_text(strip=True)
                card_text = card.get_text(" ", strip=True)
                dt = _parse_de_date(card_text)
                if not dt:
                    continue
                time = _parse_time(card_text)
                if time:
                    dt = dt.replace(hour=time[0], minute=time[1])
                else:
                    dt = dt.replace(hour=20)
                events.append({
                    "title": title, "venue": self.name,
                    "start_time": dt, "end_time": dt + timedelta(hours=3),
                    "category": _guess_category(title),
                })
        except Exception as e:
            logger.warning("Hallenstadion: %s", e)
        return events


class TonhalleScraper(VenueScraper):
    name = "Tonhalle"
    city = "zurich"
    parkhaus_ids = ["zuerichparkhausutoquai", "zuerichparkhaushohepromenade"]

    def fetch(self) -> list[dict]:
        events = []
        try:
            resp = self._get("https://www.tonhalle-orchester.ch/konzerte/kalender/")
            soup = BeautifulSoup(resp.text, "html.parser")
            for div in soup.select("div.event[data-timestamp]"):
                h3 = div.select_one("h3")
                if not h3:
                    continue
                title = h3.get_text(strip=True)
                ts = int(div["data-timestamp"])
                dt = datetime.fromtimestamp(ts)
                events.append({
                    "title": title, "venue": self.name,
                    "start_time": dt, "end_time": dt + timedelta(hours=2),
                    "category": "klassik",
                })
        except Exception as e:
            logger.warning("Tonhalle: %s", e)
        return events


class StadtcasinoBaselScraper(VenueScraper):
    name = "Stadtcasino Basel"
    city = "basel"
    parkhaus_ids = ["baselparkhaussteinen"]

    def fetch(self) -> list[dict]:
        events = []
        try:
            resp = self._get("https://www.stadtcasino-basel.ch/de/programm")
            soup = BeautifulSoup(resp.text, "html.parser")
            seen = set()
            for link in soup.select("a[href*='/programm/veranstaltungen/']"):
                href = link.get("href", "")
                if href in seen or href == "/de/programm/veranstaltungen/":
                    continue
                seen.add(href)
                title = link.get_text(strip=True)
                if len(title) < 3:
                    continue
                m = re.search(r'/(\d{6})_', href)
                if m:
                    ds = m.group(1)
                    dt = datetime(2000 + int(ds[4:6]), int(ds[2:4]), int(ds[0:2]))
                else:
                    dt = _parse_de_date(link.get_text(" ", strip=True))
                if not dt:
                    continue
                dt = dt.replace(hour=19, minute=30)
                events.append({
                    "title": title, "venue": self.name,
                    "start_time": dt, "end_time": dt + timedelta(hours=2),
                    "category": "klassik",
                })
        except Exception as e:
            logger.warning("Stadtcasino Basel: %s", e)
        return events


class MusicalChScraper(VenueScraper):
    """musical.ch listet Shows in mehreren Schweizer Staedten."""
    name = "Musical.ch"
    city = ""  # wird pro Event bestimmt
    parkhaus_ids = []

    VENUE_CITY_MAP = {
        "theater 11": ("zurich", ["zuerichparkplatztheater11", "zuerichparkhausmessezuerichag"]),
        "musical theater": ("basel", ["baselparkhaussteinen"]),
        "st. jakobshalle": ("basel", ["baselparkhausmesse"]),
        "theater basel": ("basel", ["baselparkhaussteinen"]),
        "hallenstadion": ("zurich", ["zuerichparkhausmessezuerichag"]),
        "samsung hall": ("zurich", ["zuerichparkhausmessezuerichag"]),
        "kkl": ("luzern", ["luzernparkhausbahnhof", "luzernparkhausbahnhofp1p2"]),
        "stade de suisse": ("bern", ["bernparkhausbahnhof"]),
    }

    def fetch(self) -> list[dict]:
        events = []
        try:
            resp = self._get("https://www.musical.ch/de/spielplan")
            soup = BeautifulSoup(resp.text, "html.parser")
            for card in soup.select("a[href*='/de/']"):
                heading = card.select_one("h2, h3, h4, strong")
                if not heading:
                    continue
                title = heading.get_text(strip=True)
                if len(title) < 3:
                    continue
                text = card.get_text(" ", strip=True)
                dt = _parse_de_date(text)
                if not dt:
                    continue
                venue_text = text.lower()
                city = ""
                pids = []
                for key, (c, p) in self.VENUE_CITY_MAP.items():
                    if key in venue_text:
                        city = c
                        pids = p
                        break
                if not city:
                    continue
                events.append({
                    "title": title, "venue": key.title() if city else "",
                    "start_time": dt.replace(hour=19, minute=30),
                    "end_time": dt.replace(hour=22),
                    "category": "musical",
                    "_city": city, "_parkhaus_ids": pids,
                })
        except Exception as e:
            logger.warning("Musical.ch: %s", e)
        return events


class OlmaScraper(VenueScraper):
    name = "OLMA Messen"
    city = "stgallen"
    parkhaus_ids = ["stgallenparkhausolmamessen", "stgallenparkhausolmaparkplatz"]

    def fetch(self) -> list[dict]:
        events = []
        try:
            resp = self._get("https://www.olma-messen.ch/veranstaltungen/")
            soup = BeautifulSoup(resp.text, "html.parser")
            for link in soup.select("a[href*='/veranstaltung/']"):
                title = link.get_text(strip=True)
                if len(title) < 3:
                    continue
                text = title
                dt = _parse_de_date(text)
                if not dt:
                    m = re.search(r'(\d{1,2})\.\s*(\w+)\s*(\d{4})', text)
                    if m:
                        dt = _parse_de_date(m.group(0))
                if not dt:
                    continue
                events.append({
                    "title": title.split(dt.strftime("%d"))[0].strip() or title,
                    "venue": self.name,
                    "start_time": dt.replace(hour=9),
                    "end_time": dt.replace(hour=18),
                    "category": "messe",
                })
        except Exception as e:
            logger.warning("OLMA: %s", e)
        return events


class LuzernerTheaterScraper(VenueScraper):
    name = "Luzerner Theater"
    city = "luzern"
    parkhaus_ids = ["luzernparkingstadttheater", "luzernparkhauskesselturm"]

    def fetch(self) -> list[dict]:
        events = []
        try:
            resp = self._get("https://www.luzernertheater.ch/spielplan/kalender")
            soup = BeautifulSoup(resp.text, "html.parser")
            for item in soup.select("div.spielplan-item[id]"):
                date_id = item.get("id", "")
                m = re.match(r"(\d{4})-(\d{2})-(\d{2})", date_id)
                if not m:
                    continue
                link = item.select_one("a.spielplan-item__link")
                if not link:
                    continue
                span = link.select_one("span")
                title = span.get_text(strip=True).replace("Link to production", "").strip() if span else ""
                if not title:
                    continue
                dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                time_el = item.select_one("p.time_start")
                if time_el:
                    t = _parse_time(time_el.get_text())
                    if t:
                        dt = dt.replace(hour=t[0], minute=t[1])
                    else:
                        dt = dt.replace(hour=19, minute=30)
                else:
                    dt = dt.replace(hour=19, minute=30)
                cat_el = item.select_one("[class*=category]")
                cat_text = cat_el.get_text(strip=True).lower() if cat_el else ""
                category = "oper" if "oper" in cat_text else "theater"
                events.append({
                    "title": title, "venue": self.name,
                    "start_time": dt, "end_time": dt + timedelta(hours=2, minutes=30),
                    "category": category,
                })
        except Exception as e:
            logger.warning("Luzerner Theater: %s", e)
        return events


ALL_SCRAPERS = [
    HallenstadionScraper(),
    TonhalleScraper(),
    StadtcasinoBaselScraper(),
    LuzernerTheaterScraper(),
    MusicalChScraper(),
    OlmaScraper(),
]


def fetch_and_store(venue_filter: Optional[str] = None) -> dict:
    """Events scrapen und in local_events + event_parkhaus schreiben."""
    conn = get_connection()
    cursor = conn.cursor()
    stats = {}

    scrapers = ALL_SCRAPERS
    if venue_filter:
        scrapers = [s for s in ALL_SCRAPERS if venue_filter.lower() in s.name.lower()]

    for scraper in scrapers:
        logger.info("Scrape %s ...", scraper.name)
        try:
            raw_events = scraper.fetch()
        except Exception as e:
            logger.error("%s fehlgeschlagen: %s", scraper.name, e)
            stats[scraper.name] = {"events": 0, "error": str(e)}
            continue

        n_events = 0
        n_mappings = 0
        for ev in raw_events:
            city = ev.pop("_city", scraper.city)
            pids = ev.pop("_parkhaus_ids", scraper.parkhaus_ids)
            if not city:
                continue

            eid = _event_id(ev["venue"], ev["title"], ev["start_time"])
            bonus = _bonus(ev.get("category", "default"))
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
                (eid, ev["title"], ev.get("venue", ""), city,
                 ev["start_time"], ev["end_time"],
                 ev.get("description", ""), ev.get("category", ""),
                 bonus),
            )
            n_events += 1

            for pid in pids:
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
        stats[scraper.name] = {"events": n_events, "mappings": n_mappings}
        logger.info("  %s: %d Events, %d Zuordnungen", scraper.name, n_events, n_mappings)

    cursor.close()
    conn.close()
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Echte Events von Venue-Websites scrapen")
    parser.add_argument("--venue", type=str, default=None,
                        help="Nur einen Venue scrapen (z.B. hallenstadion, tonhalle)")
    args = parser.parse_args()
    result = fetch_and_store(venue_filter=args.venue)
    print(json.dumps(result, indent=2))
