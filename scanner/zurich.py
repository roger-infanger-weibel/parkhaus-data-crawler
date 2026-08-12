"""
Zuerich parking data collector.
Primary: ParkenDD API
Fallback: Stadt Zuerich Parkleitsystem RSS (pls-zh.ch)
"""

import json
import re
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from base import BaseParkingCollector
from constants import SWISS_TZ, USER_AGENT


def _load_parking_map():
    map_path = Path(__file__).parent / "zurich_parking_map.json"
    with open(map_path, "r", encoding="utf-8") as f:
        return json.load(f)

RSS_PARKING_MAP = _load_parking_map()


class ZurichCollector(BaseParkingCollector):
    """Collector for Zuerich parking data from ParkenDD API with PLS RSS fallback."""

    FALLBACK_URL = "https://www.pls-zh.ch/plsFeed/rss"

    def normalize_data(self, raw_data):
        return self.normalize_parkendd(raw_data, use_global_ts=True)

    def _post_fetch_hook(self, raw_data):
        """Update zurich_parking_map.json with fresh total values from ParkenDD."""
        global RSS_PARKING_MAP
        try:
            lots = raw_data.get("lots", [])
            if not lots:
                return

            pid_to_rss = {}
            for rss_pid, info in RSS_PARKING_MAP.items():
                pid_to_rss[info["id"]] = rss_pid

            updated = False
            for lot in lots:
                parkendd_id = lot.get("id", "")
                total = lot.get("total", 0)
                name = lot.get("name", "")
                rss_pid = pid_to_rss.get(parkendd_id)
                if rss_pid and RSS_PARKING_MAP[rss_pid]["total"] != total:
                    RSS_PARKING_MAP[rss_pid]["total"] = total
                    updated = True
                if rss_pid and name and RSS_PARKING_MAP[rss_pid]["name"] != name:
                    RSS_PARKING_MAP[rss_pid]["name"] = name
                    updated = True

            if updated:
                map_path = Path(__file__).parent / "zurich_parking_map.json"
                with open(map_path, "w", encoding="utf-8") as f:
                    json.dump(RSS_PARKING_MAP, f, indent=4, ensure_ascii=False)
                print(f"[{datetime.now(SWISS_TZ)}] Zuerich: zurich_parking_map.json updated from ParkenDD")

        except Exception as e:
            print(f"[{datetime.now(SWISS_TZ)}] Zuerich: Failed to update parking map: {e}")

    def _fetch_fallback(self):
        """Fetch data from Stadt Zuerich PLS RSS feed."""
        print(f"[{datetime.now(SWISS_TZ)}] Zuerich: ParkenDD data is stale, switching to pls-zh.ch RSS fallback...")
        headers = {'User-Agent': USER_AGENT, 'Accept': 'application/xml'}
        response = requests.get(self.FALLBACK_URL, timeout=30, headers=headers)
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
                parking_id = mapping["id"]
                name = mapping["name"]
                total = mapping["total"]
            else:
                title_el = item.find('title')
                name = title_el.text.split('/')[0].strip() if title_el is not None else pid
                parking_id = f"zuerichparkhaus{pid}"
                total = 0

            parkings[parking_id] = {
                "id": parking_id, "name": name,
                "free": free, "total": total,
                "status": status, "timestamp": ts,
            }

            if latest_ts is None or ts > latest_ts:
                latest_ts = ts

        return {
            "status": "success",
            "city": self.city_id,
            "data": {"parkings": parkings},
            "timestamp": latest_ts or datetime.now(SWISS_TZ).isoformat(),
        }
