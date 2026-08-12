"""
Basel parking data collector.
Primary: ParkenDD API
Fallback: Open Data Basel-Stadt (data.bs.ch, Dataset 100088)
"""

from datetime import datetime

from base import BaseParkingCollector
from constants import SWISS_TZ


class BaselCollector(BaseParkingCollector):
    """Collector for Basel parking data from ParkenDD API with data.bs.ch fallback."""

    FALLBACK_URL = "https://data.bs.ch/api/records/1.0/search/?dataset=100088&rows=100"

    def normalize_data(self, raw_data):
        return self.normalize_parkendd(raw_data)

    def _normalize_fallback(self, raw_data):
        """Normalize data.bs.ch Opendatasoft format."""
        records = raw_data.get("records", [])
        if not records:
            return None

        parkings = {}
        latest_ts = None

        for record in records:
            fields = record.get("fields", {})
            parking_id = fields.get("id", "")
            if not parking_id:
                continue

            ts = fields.get("published", datetime.now(SWISS_TZ).isoformat())

            parkings[parking_id] = {
                "id": parking_id,
                "name": fields.get("name", parking_id),
                "free": fields.get("free", 0),
                "total": fields.get("total", 0),
                "status": "open" if fields.get("status") == "offen" else fields.get("status", "unknown"),
                "timestamp": ts,
            }

            if latest_ts is None or ts > latest_ts:
                latest_ts = ts

        return {
            "status": "success",
            "city": self.city_id,
            "data": {"parkings": parkings},
            "timestamp": latest_ts or datetime.now(SWISS_TZ).isoformat(),
        }
