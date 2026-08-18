"""
Base parking collector class for all city-specific collectors.
"""

import requests
import time
from datetime import datetime
from abc import ABC, abstractmethod

import mysql.connector

from constants import SWISS_TZ, USER_AGENT, STALE_THRESHOLD_MINUTES
from db_utils import get_connection, insert_measurement


def _now():
    return datetime.now(SWISS_TZ)


def error_result(error, simulation_mode=False, failed=0):
    """Standard error dict — replaces 13+ inline constructions."""
    return {
        'success': False, 'inserted': 0, 'duplicates': 0,
        'failed': failed, 'error': error,
        'latest_data_ts': None, 'simulation_mode': simulation_mode,
    }


class BaseParkingCollector(ABC):
    """Abstract base class for parking data collectors."""

    FALLBACK_URL = None

    def __init__(self, city_id, city_name, api_url, simulation_mode=False):
        self.city_id = city_id
        self.city_name = city_name
        self.api_url = api_url
        self.simulation_mode = simulation_mode

    def fetch_raw_data(self, max_retries=5):
        """Fetch raw data from the API with retry logic and exponential backoff."""
        headers = {
            'User-Agent': USER_AGENT,
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive'
        }

        last_exception = None

        for attempt in range(max_retries):
            try:
                response = requests.get(
                    self.api_url, timeout=30,
                    headers=headers, verify=True,
                )
                response.raise_for_status()
                data = response.json()
                if attempt > 0:
                    print(f"[{_now()}] {self.city_name}: Successfully retrieved data on attempt {attempt + 1}")
                return data

            except requests.exceptions.Timeout as e:
                last_exception = e
                wait_time = min(2 ** (attempt + 1), 60)
                if attempt < max_retries - 1:
                    print(f"[{_now()}] {self.city_name}: Timeout (attempt {attempt + 1}/{max_retries}), waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                else:
                    print(f"[{_now()}] {self.city_name}: Timeout after {max_retries} attempts")

            except requests.exceptions.ConnectionError as e:
                last_exception = e
                wait_time = min(2 ** (attempt + 1), 60)
                if attempt < max_retries - 1:
                    print(f"[{_now()}] {self.city_name}: Connection error (attempt {attempt + 1}/{max_retries}), waiting {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    print(f"[{_now()}] {self.city_name}: Connection error after {max_retries} attempts")

            except requests.exceptions.HTTPError as e:
                last_exception = e
                status_code = e.response.status_code
                if status_code in [429, 500, 502, 503, 504]:
                    wait_time = min(2 ** (attempt + 1), 60)
                    if attempt < max_retries - 1:
                        print(f"[{_now()}] {self.city_name}: Server error {status_code} (attempt {attempt + 1}/{max_retries}), waiting {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        print(f"[{_now()}] {self.city_name}: Server error {status_code} after {max_retries} attempts")
                else:
                    print(f"[{_now()}] {self.city_name}: HTTP error {status_code} (not retryable)")
                    raise

            except requests.exceptions.JSONDecodeError as e:
                print(f"[{_now()}] {self.city_name}: Invalid JSON response")
                raise

            except requests.RequestException as e:
                print(f"[{_now()}] {self.city_name}: Request error: {str(e)[:100]}")
                raise

        print(f"[{_now()}] Error fetching data for {self.city_name}: All {max_retries} retry attempts failed")
        raise last_exception if last_exception else Exception("Failed to fetch data after all retries")

    @abstractmethod
    def normalize_data(self, raw_data):
        """Convert raw API data to unified format."""
        pass

    def _is_stale(self, timestamp_str):
        """Check if a timestamp is older than STALE_THRESHOLD_MINUTES."""
        try:
            dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=SWISS_TZ)
            age_minutes = (_now() - dt.astimezone(SWISS_TZ)).total_seconds() / 60
            return age_minutes > STALE_THRESHOLD_MINUTES
        except (ValueError, TypeError):
            return True

    def normalize_parkendd(self, raw_data, use_global_ts=False):
        """Normalize ParkenDD API data (shared by Basel and Zürich)."""
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
                "timestamp": raw_data.get("last_updated", _now().isoformat()),
            }

        ts = _now().isoformat() if use_global_ts else raw_data.get("last_updated", _now().isoformat())
        return {
            "status": "success",
            "city": self.city_id,
            "data": {"parkings": parkings},
            "timestamp": ts,
        }

    def _fetch_fallback(self):
        """Fetch data from the fallback API. Override for non-JSON formats."""
        print(f"[{_now()}] {self.city_name}: Primary data stale, switching to fallback...")
        headers = {'User-Agent': USER_AGENT, 'Accept': 'application/json'}
        response = requests.get(self.FALLBACK_URL, timeout=30, headers=headers)
        response.raise_for_status()
        return response.json()

    def _normalize_fallback(self, raw_data):
        """Normalize fallback data. Must be overridden by subclasses with fallback."""
        return None

    def _collect_fallback(self):
        """Run full collect cycle using the fallback API."""
        try:
            raw_data = self._fetch_fallback()
            normalized = self._normalize_fallback(raw_data)
            if normalized:
                print(f"[{_now()}] {self.city_name}: Using fallback data")
                return self.save_data(normalized)
            return error_result('Fallback returned no data', self.simulation_mode)
        except Exception as e:
            print(f"[{_now()}] {self.city_name}: Fallback also failed: {e}")
            return error_result(f'Both APIs failed: {e}', self.simulation_mode)

    def collect(self):
        """Main collection method: fetch, normalize, and save data."""
        try:
            print(f"[{_now()}] {self.city_name}: Fetching data...")
            raw_data = self.fetch_raw_data()

            if not raw_data:
                if self.FALLBACK_URL:
                    return self._collect_fallback()
                return error_result('No data received', self.simulation_mode)

            if self.FALLBACK_URL:
                last_updated = raw_data.get("last_updated", "")
                if self._is_stale(last_updated):
                    print(f"[{_now()}] {self.city_name}: Data from {last_updated} is stale")
                    return self._collect_fallback()

            self._post_fetch_hook(raw_data)

            normalized = self.normalize_data(raw_data)
            if not normalized:
                if self.FALLBACK_URL:
                    return self._collect_fallback()
                return error_result('Data normalization failed', self.simulation_mode)

            return self.save_data(normalized)

        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            if self.FALLBACK_URL:
                print(f"[{_now()}] {self.city_name}: Primary failed ({e}), trying fallback...")
                return self._collect_fallback()
            return error_result(str(e)[:200], self.simulation_mode)
        except Exception as e:
            if self.FALLBACK_URL:
                print(f"[{_now()}] {self.city_name}: Primary failed ({e}), trying fallback...")
                return self._collect_fallback()
            return error_result(str(e)[:200], self.simulation_mode)

    def _post_fetch_hook(self, raw_data):
        """Hook called after successful primary fetch (e.g. to update parking map)."""
        pass

    def save_data(self, data):
        """Save normalized data to MariaDB."""
        if not data:
            return error_result('No data', self.simulation_mode)

        now = _now()
        date_str = now.strftime("%Y-%m-%d")

        try:
            conn = get_connection(simulation_mode=self.simulation_mode)
            cursor = conn.cursor()

            parkings = data.get("data", {}).get("parkings", {})
            fetch_ts = data.get("timestamp")
            if fetch_ts:
                try:
                    dt = datetime.fromisoformat(fetch_ts.replace('Z', '+00:00'))
                    if dt.tzinfo is not None:
                        dt = dt.astimezone(SWISS_TZ)
                    fetch_ts = dt.strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    fetch_ts = now.strftime("%Y-%m-%d %H:%M:%S")
            else:
                fetch_ts = now.strftime("%Y-%m-%d %H:%M:%S")

            success_count = 0
            fail_count = 0
            inserted_names = []

            for pid, pdata in parkings.items():
                pname = pdata.get('name', pid)
                db_data = {
                    'day': date_str, 'fetch_ts': fetch_ts,
                    'city': self.city_id, 'id': pid, 'name': pname,
                    'free': pdata.get('free', 0), 'total': pdata.get('total', 0),
                }
                try:
                    insert_measurement(cursor, db_data)
                    success_count += 1
                    inserted_names.append(pname)
                except Exception as e:
                    fail_count += 1
                    print(f"[{now}] {self.city_name}: Failed to upsert parking {pid}: {e}")

            conn.commit()
            cursor.close()
            conn.close()

            mode_info = " (SIMULATION MODE)" if self.simulation_mode else ""
            print(f"[{now}] {self.city_name}: Data saved{mode_info} (Upserted: {success_count}, Failed: {fail_count})")

            return {
                'success': True, 'inserted': success_count, 'duplicates': 0,
                'failed': fail_count, 'error': None,
                'latest_data_ts': fetch_ts, 'inserted_names': inserted_names,
                'simulation_mode': self.simulation_mode,
            }

        except Exception as e:
            print(f"[{now}] {self.city_name}: Error saving data: {e}")
            return error_result(str(e), self.simulation_mode,
                                failed=len(parkings) if 'parkings' in locals() else 0)
