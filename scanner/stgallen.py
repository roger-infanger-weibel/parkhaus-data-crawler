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
            "nhits": 16,
            "records": [
                {
                    "fields": {
                        "phid": "P23",
                        "phname": "Manor",
                        "phstate": "offen",
                        "shortfree": 130,
                        "shortoccupied": 2,
                        "shortmax": 132,
                        "zeitpunkt": "2026-01-06T05:36:05+00:00"
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
            parking_id = fields.get("phid", "")
            if not parking_id:
                continue
            
            # Map St. Gallen status to standard status
            status_map = {
                "offen": "open",
                "geschlossen": "closed",
                "nicht verfügbar": "nodata"
            }
            raw_status = fields.get("phstate", "").lower()
            status = status_map.get(raw_status, "unknown")
            
            parkings[parking_id] = {
                "id": parking_id,
                "name": fields.get("phname", parking_id),
                "free": fields.get("shortfree", 0),
                "total": fields.get("shortmax", 0),
                "status": status,
                "timestamp": fields.get("zeitpunkt", datetime.now().isoformat())
            }
        
        return {
            "status": "success",
            "city": self.city_id,
            "data": {
                "parkings": parkings
            },
            "timestamp": datetime.now().isoformat()
        }
