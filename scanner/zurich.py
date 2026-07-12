"""
Zürich parking data collector.
"""

from datetime import datetime
from base import BaseParkingCollector


class ZurichCollector(BaseParkingCollector):
    """Collector for Zürich parking data from ParkenDD API."""
    
    def normalize_data(self, raw_data):
        """
        Normalize Zürich ParkenDD API data to unified format.
        
        Same format as Basel (ParkenDD), but for Zürich.
        """
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
                "timestamp": raw_data.get("last_updated", datetime.now().isoformat())
            }
        
        return {
            "status": "success",
            "city": self.city_id,
            "data": {
                "parkings": parkings
            },
            "timestamp": datetime.now().isoformat()
        }
