"""
Zürich parking data collector.
Primary: ParkenDD API
Fallback: Stadt Zürich Parkleitsystem RSS (pls-zh.ch)
"""

import re
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo
from base import BaseParkingCollector

SWISS_TZ = ZoneInfo("Europe/Zurich")

FALLBACK_URL = "https://www.pls-zh.ch/plsFeed/rss"
STALE_THRESHOLD_HOURS = 2

# RSS pid → ParkenDD id mapping + known total capacities
RSS_PARKING_MAP = {
    "accu": ("zuerichparkhausaccu", "Accu", 194),
    "albisriederplatz": ("zuerichparkhausalbisriederplatz", "Albisriederplatz", 66),
    "bleicherweg": ("zuerichparkhausbleicherweg", "Bleicherweg", 275),
    "center_11": ("zuerichparkhauscentereleven", "Center Eleven", 342),
    "cp": ("zuerichparkhauscityparking", "City Parking", 620),
    "cityport": ("zuerichparkhauscityport", "Cityport", 153),
    "crowne_plaza": ("zuerichparkhauscrowneplaza", "Crowne Plaza", 520),
    "dorflinde": ("zuerichparkhausdorflinde", "Dorflinde", 98),
    "feldegg": ("zuerichparkhausfeldegg", "Feldegg", 346),
    "globus": ("zuerichparkhausglobus", "Globus", 178),
    "hardau": ("zuerichparkhaushardauii", "Hardau II", 982),
    "hb": ("zuerichparkhaushauptbahnhof", "Hauptbahnhof", 176),
    "helvetia": ("zuerichparkhaushelvetiaplatz", "Helvetiaplatz", 0),
    "promenade": ("zuerichparkhaushohepromenade", "Hohe Promenade", 556),
    "jelmoli": ("zuerichparkhausjelmoli", "Jelmoli", 222),
    "jungholz": ("zuerichparkhausjungholz", "Jungholz", 124),
    "max_bill_platz": ("zuerichparkplatzmax_bill_platz", "Max-Bill-Platz", 59),
    "messe": ("zuerichparkhausmessezuerichag", "Messe Zürich AG", 2000),
    "nordhaus": ("zuerichparkhausnordhaus", "Nordhaus", 175),
    "octavo": ("zuerichparkhausoctavo", "Octavo", 123),
    "opera": ("zuerichparkhausopera", "Opéra", 299),
    "p_west": ("zuerichparkhauspwest", "P West", 1000),
    "park_hyatt": ("zuerichparkhausparkhyatt", "Park Hyatt", 267),
    "parkside": ("zuerichparkhausparkside", "Parkside", 38),
    "pfingstweid": ("zuerichparkhauspfingstweid", "Pfingstweid", 276),
    "stampfenbach": ("zuerichparkhaustampfenbach", "Stampfenbach", 237),
    "talgarten": ("zuerichparkhaustalgarten", "Talgarten", 110),
    "unispital_nord": ("zuerichparkhaususznord", "USZ Nord", 90),
    "uni_irchel": ("zuerichparkhausuniirchel", "Uni Irchel", 1227),
    "urania": ("zuerichparkhausurania", "Urania", 607),
    "utoquai": ("zuerichparkhausutoquai", "Utoquai", 175),
    "zueri11": ("zuerichparkhauszueri11shopping", "Züri 11 Shopping", 60),
    "zuerichhorn": ("zuerichparkhauszuerichhorn", "Zürichhorn", 245),
    "theater_11": ("zuerichparkplatztheater11", "Theater 11", 188),
    "unispital_sued": ("zuerichparkplatzuszsued", "USZ Süd", 80),
    "puls5": ("zuerichpuls5parkgarage", "Puls 5 Parkgarage", 0),
}


class ZurichCollector(BaseParkingCollector):
    """Collector for Zürich parking data from ParkenDD API with PLS RSS fallback."""

    def _is_stale(self, timestamp_str):
        """Check if a timestamp is older than STALE_THRESHOLD_HOURS."""
        try:
            dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=SWISS_TZ)
            age_hours = (datetime.now(SWISS_TZ) - dt.astimezone(SWISS_TZ)).total_seconds() / 3600
            return age_hours > STALE_THRESHOLD_HOURS
        except (ValueError, TypeError):
            return True

    def _fetch_fallback(self):
        """Fetch data from Stadt Zürich PLS RSS feed."""
        print(f"[{datetime.now(SWISS_TZ)}] Zürich: ParkenDD data is stale, switching to pls-zh.ch RSS fallback...")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Accept': 'application/xml'
        }
        response = requests.get(FALLBACK_URL, timeout=30, headers=headers)
        response.raise_for_status()
        return response.text

    def _normalize_fallback(self, rss_text):
        """Normalize PLS RSS XML format."""
        root = ET.fromstring(rss_text)
        items = root.findall('.//item')
        if not items:
            return None

        parkings = {}
        latest_ts = None

        for item in items:
            link = item.find('link')
            if link is None:
                continue
            pid_match = re.search(r'pid=(\w+)', link.text or '')
            if not pid_match:
                continue
            pid = pid_match.group(1)

            desc = item.find('description')
            desc_text = desc.text.strip() if desc is not None and desc.text else ""
            desc_match = re.match(r'(\w+)\s*/\s*(\d+)', desc_text)
            status = desc_match.group(1) if desc_match else "unknown"
            free = int(desc_match.group(2)) if desc_match else 0

            ns = {'dc': 'http://purl.org/dc/elements/1.1/'}
            dc_date = item.find('dc:date', ns)
            ts = dc_date.text if dc_date is not None else datetime.now(SWISS_TZ).isoformat()

            mapping = RSS_PARKING_MAP.get(pid)
            if mapping:
                parking_id, name, total = mapping
            else:
                title_el = item.find('title')
                name = title_el.text.split('/')[0].strip() if title_el is not None else pid
                parking_id = f"zuerichparkhaus{pid}"
                total = 0

            parkings[parking_id] = {
                "id": parking_id,
                "name": name,
                "free": free,
                "total": total,
                "status": status,
                "timestamp": ts
            }

            if latest_ts is None or ts > latest_ts:
                latest_ts = ts

        return {
            "status": "success",
            "city": self.city_id,
            "data": {"parkings": parkings},
            "timestamp": latest_ts or datetime.now(SWISS_TZ).isoformat()
        }

    def collect(self):
        """Collect with automatic fallback to PLS RSS if ParkenDD is stale."""
        try:
            result = super().collect()

            if result.get('success') and result.get('latest_data_ts'):
                if self._is_stale(result['latest_data_ts']):
                    print(f"[{datetime.now(SWISS_TZ)}] Zürich: ParkenDD data from {result['latest_data_ts']} is stale")
                    return self._collect_fallback()

            return result

        except Exception as e:
            print(f"[{datetime.now(SWISS_TZ)}] Zürich: ParkenDD failed ({e}), trying fallback...")
            return self._collect_fallback()

    def _collect_fallback(self):
        """Run full collect cycle using the RSS fallback."""
        try:
            rss_text = self._fetch_fallback()
            normalized = self._normalize_fallback(rss_text)
            if normalized:
                print(f"[{datetime.now(SWISS_TZ)}] Zürich: Using pls-zh.ch RSS fallback data")
                return self.save_data(normalized)
            return {'success': False, 'inserted': 0, 'duplicates': 0, 'failed': 0,
                    'error': 'Fallback returned no data', 'latest_data_ts': None,
                    'simulation_mode': self.simulation_mode}
        except Exception as e:
            print(f"[{datetime.now(SWISS_TZ)}] Zürich: Fallback also failed: {e}")
            return {'success': False, 'inserted': 0, 'duplicates': 0, 'failed': 0,
                    'error': f'Both APIs failed: {e}', 'latest_data_ts': None,
                    'simulation_mode': self.simulation_mode}

    def normalize_data(self, raw_data):
        """Normalize ParkenDD API data."""
        if not raw_data or "lots" not in raw_data:
            return None

        parkings = {}

        for lot in raw_data.get("lots", []):
            parking_id = lot.get("id", "")
            if not parking_id:
                continue

            parkings[parking_id] = {
                "id": parking_id,
                "name": lot.get("name", parking_id),
                "free": lot.get("free", 0),
                "total": lot.get("total", 0),
                "status": lot.get("state", "unknown"),
                "timestamp": raw_data.get("last_updated", datetime.now(SWISS_TZ).isoformat())
            }

        return {
            "status": "success",
            "city": self.city_id,
            "data": {"parkings": parkings},
            "timestamp": datetime.now(SWISS_TZ).isoformat()
        }
