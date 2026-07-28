"""
St. Gallen parking data collector.
"""

from datetime import datetime
from base import BaseParkingCollector


class StGallenCollector(BaseParkingCollector):
    """Collector for St. Gallen parking data from Open Data API."""
    
    def normalize_data(self, raw_data):
        """
        Normalize St. Gallen Open Data API to unified format.

        St. Gallen format:
        {
            "nhits": 14,
            "records": [
                {
                    "fields": {
                        "ph_id": "32",
                        "ph_name": "Parkgarage Raiffeisenzentrum",
                        "ph_status": "offen",
                        "frei": 56,
                        "besetzt": 40,
                        "anzahl_parkplatze": 96,
                        "letzte_aktualisierung": "2026-07-28T12:50:00+00:00"
                    }
                }
            ]
        }
        """
        if not raw_data or "records" not in raw_data:
            return None

        parkings = {}

        for record in raw_data.get("records", []):
            fields = record.get("fields", {})
            parking_id = str(fields.get("ph_id", ""))
            if not parking_id or parking_id == "":
                continue

            # Map St. Gallen status to standard status
            status_map = {
                "offen": "open",
                "geschlossen": "closed",
                "nicht verfügbar": "nodata"
            }
            raw_status = fields.get("ph_status", "").lower()
            status = status_map.get(raw_status, "unknown")

            parkings[parking_id] = {
                "id": parking_id,
                "name": fields.get("ph_name", parking_id),
                "free": int(fields.get("frei", 0)),
                "total": int(fields.get("anzahl_parkplatze", 0)),
                "status": status,
                "timestamp": fields.get("letzte_aktualisierung", datetime.now().isoformat())
            }

        return {
            "status": "success",
            "city": self.city_id,
            "data": {
                "parkings": parkings
            },
            "timestamp": raw_data.get("records", [{}])[0].get("fields", {}).get("letzte_aktualisierung", datetime.now().isoformat()) if raw_data.get("records") else datetime.now().isoformat()
        }
