"""
Basel parking data collector.
Primary: ParkenDD API
Fallback: Open Data Basel-Stadt (data.bs.ch, Dataset 100088)
"""

import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from base import BaseParkingCollector

SWISS_TZ = ZoneInfo("Europe/Zurich")

FALLBACK_URL = "https://data.bs.ch/api/records/1.0/search/?dataset=100088&rows=100"
STALE_THRESHOLD_HOURS = 2


class BaselCollector(BaseParkingCollector):
    """Collector for Basel parking data from ParkenDD API with data.bs.ch fallback."""

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
        """Fetch data from Open Data Basel-Stadt (data.bs.ch)."""
        print(f"[{datetime.now(SWISS_TZ)}] Basel: ParkenDD data is stale, switching to data.bs.ch fallback...")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Accept': 'application/json'
        }
        response = requests.get(FALLBACK_URL, timeout=30, headers=headers)
        response.raise_for_status()
        return response.json()

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
        """Collect with automatic fallback to data.bs.ch if ParkenDD is stale."""
        try:
            result = super().collect()

            if result.get('success') and result.get('latest_data_ts'):
                if self._is_stale(result['latest_data_ts']):
                    print(f"[{datetime.now(SWISS_TZ)}] Basel: ParkenDD data from {result['latest_data_ts']} is stale")
                    return self._collect_fallback()

            return result

        except Exception as e:
            print(f"[{datetime.now(SWISS_TZ)}] Basel: ParkenDD failed ({e}), trying fallback...")
            return self._collect_fallback()

    def _collect_fallback(self):
        """Run full collect cycle using the fallback API."""
        try:
            raw_data = self._fetch_fallback()
            normalized = self._normalize_fallback(raw_data)
            if normalized:
                print(f"[{datetime.now(SWISS_TZ)}] Basel: Using data.bs.ch fallback data")
                return self.save_data(normalized)
            return {'success': False, 'inserted': 0, 'duplicates': 0, 'failed': 0,
                    'error': 'Fallback returned no data', 'latest_data_ts': None,
                    'simulation_mode': self.simulation_mode}
        except Exception as e:
            print(f"[{datetime.now(SWISS_TZ)}] Basel: Fallback also failed: {e}")
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
            "timestamp": raw_data.get("last_updated", datetime.now(SWISS_TZ).isoformat())
        }
