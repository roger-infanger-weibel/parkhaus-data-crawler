"""
Luzern parking data collector.
"""

from datetime import datetime
from base import BaseParkingCollector


class LuzernCollector(BaseParkingCollector):
    """Collector for Luzern parking data."""
    
    def normalize_data(self, raw_data):
        """
        Normalize Luzern API data to unified format.
        
        Luzern API already provides well-structured data, minimal transformation needed.
        """
        if not raw_data or raw_data.get("status") != "success":
            return None
        
        parkings = {}
        raw_parkings = raw_data.get("data", {}).get("parkings", {})
        
        for parking_id, parking_data in raw_parkings.items():
            parkings[parking_id] = {
                "id": parking_id,
                "name": parking_data.get("description", parking_id),
                "free": parking_data.get("vacancy", 0),
                "total": parking_data.get("capacity", 0),
                "status": "open" if parking_data.get("opened", True) and not parking_data.get("maintenance", False) else "closed",
                "timestamp": parking_data.get("datestamp", datetime.now().isoformat())
            }
        
        return {
            "status": "success",
            "city": self.city_id,
            "data": {
                "parkings": parkings
            },
            "timestamp": raw_data.get("data", {}).get("time", datetime.now().isoformat())
        }
