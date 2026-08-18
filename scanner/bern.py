"""
Bern parking data collector.
Parses XML data from parking-bern.ch.
"""

import json
import xml.etree.ElementTree as ET
import requests
from datetime import datetime
from pathlib import Path

from base import BaseParkingCollector
from constants import SWISS_TZ


def _load_parking_map():
    config_path = Path(__file__).parent / "cities.json"
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["cities"]["bern"].get("parking_map", {})


class BernCollector(BaseParkingCollector):
    """Collector for Bern parking data."""

    def fetch_raw_data(self):
        """
        Fetch raw XML data from the Bern parking API.
        
        Returns:
            str: Raw XML string
        """
        try:
            response = requests.get(self.api_url, timeout=10)
            response.raise_for_status()
            # Return bytes to handle BOM correctly
            return response.content
        except requests.RequestException as e:
            print(f"[{datetime.now(SWISS_TZ)}] Error fetching data for {self.city_name}: {e}")
            raise

    def normalize_data(self, raw_data):
        """
        Normalize Bern XML data to unified format.
        
        Example XML structure:
        <parkdata updated="09.01.2026 07:44:02">
            <parking name="P10" state="1" spacecount="240" spacefree="50" open="00:00" close="00:00"/>
        </parkdata>
        """
        if not raw_data:
            return None

        try:
            # ET.fromstring can handle bytes with XML declaration and BOM
            root = ET.fromstring(raw_data)
            updated_str = root.get("updated", datetime.now(SWISS_TZ).strftime("%d.%m.%Y %H:%M:%S"))
            
            # Convert DD.MM.YYYY HH:MM:SS to ISO format
            try:
                dt = datetime.strptime(updated_str, "%d.%m.%Y %H:%M:%S")
                timestamp = dt.isoformat()
            except ValueError:
                timestamp = datetime.now(SWISS_TZ).isoformat()

            parking_map = _load_parking_map()

            parkings = {}
            for parking in root.findall("parking"):
                xml_name = parking.get("name")
                if not xml_name or xml_name not in parking_map:
                    continue

                mapping = parking_map[xml_name]
                parking_id = mapping["id"]
                name = mapping["name"]
                
                try:
                    free = int(parking.get("spacefree", 0))
                    total = int(parking.get("spacecount", 0))
                except (ValueError, TypeError):
                    free = 0
                    total = 0
                
                # Skip invalid data
                if total < 0:
                    continue

                state = parking.get("state", "1")
                
                parkings[parking_id] = {
                    "id": parking_id,
                    "name": name,
                    "free": free,
                    "total": total,
                    "status": "open" if state == "1" else "closed",
                    "timestamp": timestamp
                }

            return {
                "status": "success",
                "city": self.city_id,
                "data": {
                    "parkings": parkings
                },
                "timestamp": timestamp
            }
        except ET.ParseError as e:
            print(f"[{datetime.now(SWISS_TZ)}] Bern: Error parsing XML: {e}")
            return None
