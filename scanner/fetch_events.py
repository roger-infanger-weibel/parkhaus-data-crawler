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
import time as _time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

from db_utils import get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

from constants import SWISS_TZ, USER_AGENT

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "de-CH,de;q=0.9",
}


def _load_venues_config():
    config_path = Path(__file__).parent / "venues.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


_VENUES_CONFIG = _load_venues_config()
CATEGORY_BONUS = _VENUES_CONFIG["category_bonus"]


def _venue_config(scraper_name):
    for v in _VENUES_CONFIG["venues"]:
        if v["scraper"] == scraper_name:
            return v
    return {}

MONATE_DE = {
    "jan": 1, "feb": 2, "mär": 3, "mar": 3, "apr": 4, "mai": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "okt": 10, "oct": 10, "nov": 11, "dez": 12, "dec": 12,
}


def _event_id(venue: str, title: str, start: datetime) -> str:
    raw = f"{venue}-{title}-{start.isoformat()}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def _existing_event_ids(venue: str) -> set[str]:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM local_events WHERE venue = %s", (venue,))
        ids = {row[0] for row in cursor.fetchall()}
        cursor.close()
        conn.close()
        return ids
    except Exception:
        return set()


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

    def _get(self, url: str, retries: int = 2, **kwargs) -> requests.Response:
        for attempt in range(retries + 1):
            resp = requests.get(url, headers=HEADERS, timeout=60, **kwargs)
            if resp.status_code == 429 and attempt < retries:
                wait = 5 * (attempt + 1)
                logger.info("429 von %s — warte %ds", url, wait)
                _time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        resp.raise_for_status()
        return resp


class HallenstadionScraper(VenueScraper):
    _cfg = _venue_config("HallenstadionScraper")
    name = _cfg.get("name", "Hallenstadion")
    city = _cfg.get("city", "zurich")
    parkhaus_ids = _cfg.get("parkhaus_ids", [])

    def fetch(self) -> list[dict]:
        events = []
        try:
            resp = self._get(self._cfg["url"])
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
    _cfg = _venue_config("TonhalleScraper")
    name = _cfg.get("name", "Tonhalle")
    city = _cfg.get("city", "zurich")
    parkhaus_ids = _cfg.get("parkhaus_ids", [])

    def fetch(self) -> list[dict]:
        events = []
        try:
            resp = self._get(self._cfg["url"])
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
    _cfg = _venue_config("StadtcasinoBaselScraper")
    name = _cfg.get("name", "Stadtcasino Basel")
    city = _cfg.get("city", "basel")
    parkhaus_ids = _cfg.get("parkhaus_ids", [])

    def fetch(self) -> list[dict]:
        events = []
        try:
            resp = self._get(self._cfg["url"])
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
    _cfg = _venue_config("MusicalChScraper")
    name = _cfg.get("name", "Musical.ch")
    city = _cfg.get("city", "")
    parkhaus_ids = _cfg.get("parkhaus_ids", [])

    VENUE_CITY_MAP = {
        k: (v["city"], v["parkhaus_ids"])
        for k, v in _cfg.get("venue_city_map", {}).items()
    }

    def fetch(self) -> list[dict]:
        events = []
        try:
            resp = self._get(self._cfg["url"])
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
    _cfg = _venue_config("OlmaScraper")
    name = _cfg.get("name", "OLMA Messen")
    city = _cfg.get("city", "stgallen")
    parkhaus_ids = _cfg.get("parkhaus_ids", [])

    def fetch(self) -> list[dict]:
        events = []
        try:
            resp = self._get(self._cfg["url"])
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
    _cfg = _venue_config("LuzernerTheaterScraper")
    name = _cfg.get("name", "Luzerner Theater")
    city = _cfg.get("city", "luzern")
    parkhaus_ids = _cfg.get("parkhaus_ids", [])

    def fetch(self) -> list[dict]:
        events = []
        try:
            resp = self._get(self._cfg["url"])
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


class OpernhausZurichScraper(VenueScraper):
    _cfg = _venue_config("OpernhausZurichScraper")
    name = _cfg.get("name", "Opernhaus Zürich")
    city = _cfg.get("city", "zurich")
    parkhaus_ids = _cfg.get("parkhaus_ids", [])

    def fetch(self) -> list[dict]:
        events = []
        try:
            resp = self._get(self._cfg["url"])
            soup = BeautifulSoup(resp.text, "html.parser")
            for script in soup.select('script[type="application/ld+json"]'):
                try:
                    data = json.loads(script.string or "")
                except json.JSONDecodeError:
                    continue
                if not isinstance(data, dict) or data.get("@type") != "Event":
                    continue
                title = data.get("name", "")
                if len(title) < 3:
                    continue
                try:
                    dt = datetime.fromisoformat(data["startDate"])
                except (ValueError, KeyError):
                    continue
                end_str = data.get("endDate")
                if end_str:
                    try:
                        end = datetime.fromisoformat(end_str)
                    except ValueError:
                        end = dt + timedelta(hours=3)
                else:
                    end = dt + timedelta(hours=3)
                events.append({
                    "title": title, "venue": self.name,
                    "start_time": dt, "end_time": end,
                    "category": "oper",
                })
        except Exception as e:
            logger.warning("Opernhaus Zürich: %s", e)
        return events


class SchauspielhausZurichScraper(VenueScraper):
    _cfg = _venue_config("SchauspielhausZurichScraper")
    name = _cfg.get("name", "Schauspielhaus Zürich")
    city = _cfg.get("city", "zurich")
    parkhaus_ids = _cfg.get("parkhaus_ids", [])

    def fetch(self) -> list[dict]:
        events = []
        try:
            resp = self._get(self._cfg["url"])
            soup = BeautifulSoup(resp.text, "html.parser")
            for section in soup.select("section.calendar-section[data-date]"):
                date_str = section.get("data-date", "")
                try:
                    base_date = datetime.strptime(date_str, "%Y-%m-%d")
                except ValueError:
                    continue
                for article in section.select("article.calendar-item"):
                    title_el = article.select_one("a.calendar-item__title")
                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)
                    if len(title) < 3:
                        continue
                    time_span = article.select_one("div.calendar-item__date span[aria-label]")
                    if time_span:
                        t = _parse_time(time_span.get("aria-label", ""))
                        if t:
                            dt = base_date.replace(hour=t[0], minute=t[1])
                        else:
                            dt = base_date.replace(hour=20)
                    else:
                        text = article.get_text(" ", strip=True)
                        t = _parse_time(text)
                        dt = base_date.replace(hour=t[0], minute=t[1]) if t else base_date.replace(hour=20)
                    events.append({
                        "title": title.title(), "venue": self.name,
                        "start_time": dt, "end_time": dt + timedelta(hours=2, minutes=30),
                        "category": "theater",
                    })
        except Exception as e:
            logger.warning("Schauspielhaus Zürich: %s", e)
        return events


class KongresshausZurichScraper(VenueScraper):
    _cfg = _venue_config("KongresshausZurichScraper")
    name = _cfg.get("name", "Kongresshaus Zürich")
    city = _cfg.get("city", "zurich")
    parkhaus_ids = _cfg.get("parkhaus_ids", [])

    def fetch(self) -> list[dict]:
        events = []
        try:
            resp = self._get(self._cfg["url"])
            soup = BeautifulSoup(resp.text, "html.parser")
            for item in soup.select(".event_item_list, .event-item, a[href*='/event']"):
                title_el = item.select_one("h2, h3, h4, .title, strong")
                if not title_el:
                    title_el = item
                title = title_el.get_text(strip=True)
                if len(title) < 3:
                    continue
                time_el = item.select_one("time[datetime]")
                if time_el and time_el.get("datetime"):
                    try:
                        dt = datetime.fromisoformat(time_el["datetime"].replace("Z", "+00:00"))
                        dt = dt.replace(tzinfo=None)
                    except ValueError:
                        dt = _parse_de_date(item.get_text(" ", strip=True))
                else:
                    dt = _parse_de_date(item.get_text(" ", strip=True))
                if not dt:
                    continue
                if dt.hour == 0:
                    time = _parse_time(item.get_text(" ", strip=True))
                    if time:
                        dt = dt.replace(hour=time[0], minute=time[1])
                    else:
                        dt = dt.replace(hour=19, minute=30)
                events.append({
                    "title": title, "venue": self.name,
                    "start_time": dt, "end_time": dt + timedelta(hours=3),
                    "category": _guess_category(title),
                })
        except Exception as e:
            logger.warning("Kongresshaus Zürich: %s", e)
        return events


class TheHallScraper(VenueScraper):
    _cfg = _venue_config("TheHallScraper")
    name = _cfg.get("name", "THE HALL")
    city = _cfg.get("city", "zurich")
    parkhaus_ids = _cfg.get("parkhaus_ids", [])

    def fetch(self) -> list[dict]:
        events = []
        try:
            resp = self._get(self._cfg["url"])
            soup = BeautifulSoup(resp.text, "html.parser")
            for card in soup.select(".c-tile--events, a[href*='/eventkalender/']"):
                title_el = card.select_one(".c-tile__title, h5, h3, h4")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                if len(title) < 3:
                    continue
                date_el = card.select_one(".c-tile__text, span")
                text = date_el.get_text(strip=True) if date_el else card.get_text(" ", strip=True)
                dt = _parse_de_date(text)
                if not dt:
                    continue
                time = _parse_time(text)
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
            logger.warning("THE HALL: %s", e)
        return events


class TheaterBaselScraper(VenueScraper):
    _cfg = _venue_config("TheaterBaselScraper")
    name = _cfg.get("name", "Theater Basel")
    city = _cfg.get("city", "basel")
    parkhaus_ids = _cfg.get("parkhaus_ids", [])

    def fetch(self) -> list[dict]:
        events = []
        try:
            resp = self._get(self._cfg["url"])
            soup = BeautifulSoup(resp.text, "html.parser")
            seen = set()
            for article in soup.select("article.activity-teaser-calendar"):
                atc_start = article.select_one("var.atc_date_start")
                atc_title = article.select_one("var.atc_title")
                if not atc_start or not atc_title:
                    continue
                title = atc_title.get_text(strip=True)
                if len(title) < 3:
                    continue
                try:
                    dt = datetime.strptime(atc_start.get_text(strip=True), "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue
                key = f"{title}-{dt.date()}"
                if key in seen:
                    continue
                seen.add(key)
                atc_end = article.select_one("var.atc_date_end")
                if atc_end:
                    try:
                        end = datetime.strptime(atc_end.get_text(strip=True), "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        end = dt + timedelta(hours=2, minutes=30)
                else:
                    end = dt + timedelta(hours=2, minutes=30)
                genre_el = article.select_one("a.production-link span.red-title")
                genre = genre_el.get_text(strip=True).lower() if genre_el else ""
                cat = "oper" if "oper" in genre or "oper" in title.lower() else "theater"
                events.append({
                    "title": title, "venue": self.name,
                    "start_time": dt, "end_time": end,
                    "category": cat,
                })
        except Exception as e:
            logger.warning("Theater Basel: %s", e)
        return events


class StJakobshalleScraper(VenueScraper):
    _cfg = _venue_config("StJakobshalleScraper")
    name = _cfg.get("name", "St. Jakobshalle")
    city = _cfg.get("city", "basel")
    parkhaus_ids = _cfg.get("parkhaus_ids", [])

    def fetch(self) -> list[dict]:
        events = []
        try:
            resp = self._get(self._cfg["url"])
            soup = BeautifulSoup(resp.text, "html.parser")
            for card in soup.select("div.eventon_list_event"):
                title_el = card.select_one("span.evcal_event_title")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                if len(title) < 3:
                    continue
                start_meta = card.select_one("meta[itemprop='startDate']")
                if not start_meta or not start_meta.get("content"):
                    continue
                date_str = start_meta["content"]
                try:
                    parts = date_str.split("-")
                    dt = datetime(int(parts[0]), int(parts[1]), int(parts[2]))
                except (ValueError, IndexError):
                    continue
                time = _parse_time(card.get_text(" ", strip=True))
                if time:
                    dt = dt.replace(hour=time[0], minute=time[1])
                else:
                    dt = dt.replace(hour=20)
                end_meta = card.select_one("meta[itemprop='endDate']")
                if end_meta and end_meta.get("content"):
                    try:
                        ep = end_meta["content"].split("-")
                        end = datetime(int(ep[0]), int(ep[1]), int(ep[2]), 22)
                    except (ValueError, IndexError):
                        end = dt + timedelta(hours=3)
                else:
                    end = dt + timedelta(hours=3)
                events.append({
                    "title": title, "venue": self.name,
                    "start_time": dt, "end_time": end,
                    "category": _guess_category(title),
                })
        except Exception as e:
            logger.warning("St. Jakobshalle: %s", e)
        return events


class TheaterStGallenScraper(VenueScraper):
    _cfg = _venue_config("TheaterStGallenScraper")
    name = _cfg.get("name", "Konzert & Theater St. Gallen")
    city = _cfg.get("city", "stgallen")
    parkhaus_ids = _cfg.get("parkhaus_ids", [])

    def fetch(self) -> list[dict]:
        events = []
        try:
            resp = self._get(self._cfg["url"])
            soup = BeautifulSoup(resp.text, "html.parser")
            for card in soup.select("div.performance"):
                title_el = card.select_one("span[itemprop='name']")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                if len(title) < 3:
                    continue
                start_meta = card.select_one("meta[itemprop='startDate']")
                if start_meta and start_meta.get("content"):
                    try:
                        dt = datetime.fromisoformat(start_meta["content"])
                    except ValueError:
                        continue
                else:
                    day_token = card.get("data-day-token")
                    if not day_token:
                        continue
                    try:
                        dt = datetime.strptime(day_token, "%Y-%m-%d")
                    except ValueError:
                        continue
                    time = _parse_time(card.get_text(" ", strip=True))
                    if time:
                        dt = dt.replace(hour=time[0], minute=time[1])
                    else:
                        dt = dt.replace(hour=19, minute=30)
                cat_el = card.select_one("div.performance__category")
                cat_text = cat_el.get_text(strip=True).lower() if cat_el else ""
                cat = "oper" if "oper" in cat_text or "oper" in title.lower() else "theater"
                events.append({
                    "title": title, "venue": self.name,
                    "start_time": dt, "end_time": dt + timedelta(hours=2, minutes=30),
                    "category": cat,
                })
        except Exception as e:
            logger.warning("Theater St. Gallen: %s", e)
        return events


class BernExpoScraper(VenueScraper):
    _cfg = _venue_config("BernExpoScraper")
    name = _cfg.get("name", "BernExpo")
    city = _cfg.get("city", "bern")
    parkhaus_ids = _cfg.get("parkhaus_ids", [])

    def fetch(self) -> list[dict]:
        events = []
        try:
            resp = self._get(self._cfg["url"])
            soup = BeautifulSoup(resp.text, "html.parser")
            for card in soup.select(".group\\/agenda-teaser-card, a[href*='/veranstaltung'], .event-card"):
                title_el = card.select_one(".text-title-lg, h2, h3, h4, strong, p.text-title-lg")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                if len(title) < 3:
                    continue
                date_el = card.select_one(".text-overline, p.text-overline")
                text = date_el.get_text(strip=True) if date_el else card.get_text(" ", strip=True)
                m = re.search(r'(\d{1,2})\.\s*(\w+)', text)
                if m:
                    dt = _parse_de_date(text)
                else:
                    dt = _parse_de_date(card.get_text(" ", strip=True))
                if not dt:
                    continue
                events.append({
                    "title": title, "venue": self.name,
                    "start_time": dt.replace(hour=9),
                    "end_time": dt.replace(hour=18),
                    "category": "messe",
                })
        except Exception as e:
            logger.warning("BernExpo: %s", e)
        return events


class KKLLuzernScraper(VenueScraper):
    """KKL Luzern: nutzt TicketCorner als Datenquelle (76+ Events)."""
    _cfg = _venue_config("KKLLuzernScraper")
    name = _cfg.get("name", "KKL Luzern")
    city = _cfg.get("city", "luzern")
    parkhaus_ids = _cfg.get("parkhaus_ids", [])

    def fetch(self) -> list[dict]:
        events = []
        try:
            # JamBase: englische Event-Liste
            url = "https://www.jambase.com/venue/kkl-luzern"
            _time.sleep(2)
            resp = self._get(url, retries=2)
            soup = BeautifulSoup(resp.text, "html.parser")

            MONATE_EN = {
                "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
                "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
            }

            lines = [l.strip() for l in soup.get_text("\n").split("\n") if l.strip()]

            # Struktur: Wochentag, Datum, Title auf separaten Zeilen
            i = 0
            while i < len(lines):
                # Suche Datum-Zeile: "Oct 9, 2026" oder "Nov 2, 2026"
                m = re.search(r'([A-Za-z]{3})\s+(\d{1,2}),\s+(\d{4})', lines[i])
                if not m:
                    i += 1
                    continue

                mon_str = m.group(1).lower()
                day = int(m.group(2))
                year = int(m.group(3))

                mon = MONATE_EN.get(mon_str[:3])
                if not mon:
                    i += 1
                    continue

                # Title ist die nächste Zeile (nach Datum)
                if i + 1 < len(lines):
                    title = lines[i + 1].strip()

                    # Ignoriere KKL-Meta-Zeilen
                    if len(title) >= 3 and not title.startswith("KKL") and not title in ["Tickets", "Info", "Calendar", "Infos anzeigen"]:
                        try:
                            dt = datetime(year, mon, day, 19, 30)
                            events.append({
                                "title": title, "venue": self.name,
                                "start_time": dt, "end_time": dt + timedelta(hours=2, minutes=30),
                                "category": _guess_category(title),
                            })
                        except ValueError:
                            pass

                i += 1

        except Exception as e:
            logger.warning("KKL Luzern (JamBase): %s", e)
        logger.info("KKL Luzern: %d Events gefunden", len(events))
        return events


class ObrassoKKLScraper(VenueScraper):
    """KKL Luzern: Obrasso Concerts Quelle (Ergänzung zu JamBase)."""
    _cfg = _venue_config("KKLLuzernScraper")  # Nutze gleiche Config
    name = _cfg.get("name", "KKL Luzern")
    city = _cfg.get("city", "luzern")
    parkhaus_ids = _cfg.get("parkhaus_ids", [])

    def fetch(self) -> list[dict]:
        events = []
        try:
            url = "https://www.obrassoconcerts.ch/programm/kkl-luzern"
            _time.sleep(2)
            resp = self._get(url, retries=2)
            soup = BeautifulSoup(resp.text, "html.parser")

            # Suche Event-Zeilen: "SA 19 SEP 2026 19:30 BRASS-GALA"
            for line in soup.get_text("\n").split("\n"):
                line = line.strip()
                # Pattern: [WOCHENTAG] [TAG] [MONAT] [JAHR] [STUNDE:MINUTE]
                m = re.search(r'(MO|DI|MI|DO|FR|SA|SO)\s+(\d{1,2})\s+(JAN|FEB|MÄR|MAR|APR|MAI|JUN|JUL|AUG|SEP|OKT|OCT|NOV|DEZ|DEC)\s+(\d{4})\s+(\d{1,2}):(\d{2})', line, re.IGNORECASE)
                if not m:
                    continue

                day = int(m.group(2))
                mon_str = m.group(3).lower()[:3]
                year = int(m.group(4))
                hour = int(m.group(5))
                minute = int(m.group(6))

                # Title ist nach der Zeit
                title_start = m.end()
                title = line[title_start:].strip()

                if len(title) < 3:
                    continue

                mon = MONATE_DE.get(mon_str)
                if not mon:
                    continue

                try:
                    dt = datetime(year, mon, day, hour, minute)
                except ValueError:
                    continue

                events.append({
                    "title": title, "venue": self.name,
                    "start_time": dt, "end_time": dt + timedelta(hours=2, minutes=30),
                    "category": _guess_category(title),
                })
        except Exception as e:
            logger.warning("KKL Luzern (Obrasso): %s", e)
        logger.info("KKL Luzern (Obrasso): %d Events gefunden", len(events))
        return events


class MesseLuzernScraper(VenueScraper):
    _cfg = _venue_config("MesseLuzernScraper")
    name = _cfg.get("name", "Messe Luzern")
    city = _cfg.get("city", "luzern")
    parkhaus_ids = _cfg.get("parkhaus_ids", [])

    def fetch(self) -> list[dict]:
        events = []
        try:
            resp = self._get(self._cfg["url"])
            soup = BeautifulSoup(resp.text, "html.parser")
            for li in soup.select("ul.event__list li.events"):
                title_el = li.select_one("div.event__name")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                if len(title) < 3:
                    continue
                date_el = li.select_one("div.event__dates")
                if not date_el:
                    continue
                date_text = date_el.get_text(" ", strip=True)
                m = re.search(r'(\d{1,2})\.(\d{2})\.(\d{2})', date_text)
                if not m:
                    m = re.search(r'(\d{1,2})\.(\d{2})', date_text)
                    if not m:
                        continue
                if len(m.groups()) == 3:
                    year = 2000 + int(m.group(3))
                    dt = datetime(year, int(m.group(2)), int(m.group(1)))
                else:
                    dt = datetime(datetime.now().year, int(m.group(2)), int(m.group(1)))
                events.append({
                    "title": title, "venue": self.name,
                    "start_time": dt.replace(hour=9),
                    "end_time": dt.replace(hour=18),
                    "category": "messe",
                })
        except Exception as e:
            logger.warning("Messe Luzern: %s", e)
        return events


class StadtkellerLuzernScraper(VenueScraper):
    _cfg = _venue_config("StadtkellerLuzernScraper")
    name = _cfg.get("name", "Stadtkeller Luzern")
    city = _cfg.get("city", "luzern")
    parkhaus_ids = _cfg.get("parkhaus_ids", [])

    def fetch(self) -> list[dict]:
        events = []
        try:
            resp = self._get(self._cfg["url"])
            soup = BeautifulSoup(resp.text, "html.parser")
            for card in soup.select("div.link-box-content"):
                title_el = card.select_one("h3.eventtitle")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                if len(title) < 3:
                    continue
                date_el = card.select_one("p.eventdate")
                if not date_el:
                    continue
                date_text = date_el.get_text(strip=True)
                dt = _parse_de_date(date_text)
                if not dt:
                    continue
                dt = dt.replace(hour=19, minute=30)
                events.append({
                    "title": title, "venue": self.name,
                    "start_time": dt, "end_time": dt + timedelta(hours=3),
                    "category": _guess_category(title),
                })
        except Exception as e:
            logger.warning("Stadtkeller Luzern: %s", e)
        return events


class LuzernTopEventsScraper(VenueScraper):
    """Scraper für luzern.com Top-Events mit Detail-Lookup für exakte Daten."""
    _cfg = _venue_config("LuzernTopEventsScraper")
    name = _cfg.get("name", "Luzern Top Events")
    city = _cfg.get("city", "luzern")
    parkhaus_ids = _cfg.get("parkhaus_ids", [])

    def _parse_detail_date(self, url: str) -> Optional[datetime]:
        try:
            resp = self._get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            for script in soup.select('script[type="application/ld+json"]'):
                try:
                    data = json.loads(script.string or "")
                    if isinstance(data, list):
                        data = next((d for d in data if "Event" in (d.get("@type") or [])), None)
                    if data and data.get("startDate"):
                        iso = data["startDate"]
                        return datetime.fromisoformat(iso.replace("Z", "+00:00")).replace(tzinfo=None)
                except (json.JSONDecodeError, ValueError, StopIteration):
                    continue
            for h2 in soup.select("h2"):
                if "datum" in h2.get_text(strip=True).lower():
                    p = h2.find_next_sibling("p")
                    if p:
                        return _parse_de_date(p.get_text(strip=True))
            text = soup.get_text(" ", strip=True)
            m = re.search(r'Findet statt am (\d{1,2}\.\d{2}\.\d{2,4})', text)
            if m:
                return _parse_de_date(m.group(1))
        except Exception as e:
            logger.debug("Detail-Lookup %s: %s", url, e)
        return None

    def fetch(self) -> list[dict]:
        events = []
        try:
            resp = self._get(self._cfg["url"])
            soup = BeautifulSoup(resp.text, "html.parser")
            for tile in soup.select("div.tile"):
                link = tile.select_one("a.tile__link")
                if not link or not link.get("href"):
                    continue
                title_el = tile.select_one(".header__head")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True).strip("\xa0").strip()
                if len(title) < 3:
                    continue
                detail_url = link["href"]
                if not detail_url.startswith("http"):
                    detail_url = "https://www.luzern.com" + detail_url
                dt = self._parse_detail_date(detail_url)
                if not dt:
                    continue
                if dt.hour == 0:
                    dt = dt.replace(hour=10)
                cat = "sport" if any(w in title.lower() for w in ("marathon", "regatta", "athletics")) else _guess_category(title)
                if cat == "default":
                    cat = "festival"
                events.append({
                    "title": title, "venue": self.name,
                    "start_time": dt, "end_time": dt + timedelta(hours=6),
                    "category": cat,
                })
        except Exception as e:
            logger.warning("Luzern Top Events: %s", e)
        return events


ALL_SCRAPERS = [
    HallenstadionScraper(),
    TonhalleScraper(),
    StadtcasinoBaselScraper(),
    LuzernerTheaterScraper(),
    MusicalChScraper(),
    OlmaScraper(),
    OpernhausZurichScraper(),
    SchauspielhausZurichScraper(),
    KongresshausZurichScraper(),
    TheHallScraper(),
    TheaterBaselScraper(),
    StJakobshalleScraper(),
    TheaterStGallenScraper(),
    BernExpoScraper(),
    KKLLuzernScraper(),  # JamBase: 13+ Events
    MesseLuzernScraper(),
    StadtkellerLuzernScraper(),
    LuzernTopEventsScraper(),
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
        n_filtered = 0
        for ev in raw_events:
            city = ev.pop("_city", scraper.city)
            pids = ev.pop("_parkhaus_ids", scraper.parkhaus_ids)
            if not city:
                continue

            # Filter: nur Events mit sinnvollem Titel
            title = ev.get("title", "").strip()
            venue = ev.get("venue", "").strip()

            # Filtere Events wo Title == Venue (nur generischer Venue-Name)
            if title.lower() == venue.lower():
                logger.debug("  Gefiltert (Title==Venue): %s", title)
                n_filtered += 1
                continue

            # Filtere Events mit zu kurzem Titel (< 5 Zeichen)
            if len(title) < 5:
                logger.debug("  Gefiltert (zu kurz): %s", title)
                n_filtered += 1
                continue

            # Filtere Events mit nur Whitespace/Zahlen
            if not any(c.isalpha() for c in title):
                logger.debug("  Gefiltert (keine Buchstaben): %s", title)
                n_filtered += 1
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
        stats[scraper.name] = {"events": n_events, "mappings": n_mappings, "filtered": n_filtered}
        if n_filtered > 0:
            logger.info("  %s: %d Events, %d Zuordnungen, %d gefiltert", scraper.name, n_events, n_mappings, n_filtered)
        else:
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
