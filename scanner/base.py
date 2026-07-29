"""
Base parking collector class for all city-specific collectors.
"""

import requests
import json
import os
import time
from datetime import datetime
from abc import ABC, abstractmethod
from zoneinfo import ZoneInfo

SWISS_TZ = ZoneInfo("Europe/Zurich")


class BaseParkingCollector(ABC):
    """Abstract base class for parking data collectors."""

    def __init__(self, city_id, city_name, api_url, simulation_mode=False):
        """
        Initialize the collector.

        Args:
            city_id: City identifier (e.g., 'luzern', 'basel')
            city_name: Display name of the city
            api_url: API endpoint URL
            simulation_mode (bool): If True, don't write to database
        """
        self.city_id = city_id
        self.city_name = city_name
        self.api_url = api_url
        self.simulation_mode = simulation_mode

    def fetch_raw_data(self, max_retries=5):
        """
        Fetch raw data from the API with robust retry logic and exponential backoff.

        Args:
            max_retries (int): Maximum number of retry attempts

        Returns:
            dict: Raw API response as JSON

        Raises:
            requests.RequestException: If the API request fails after all retries
        """
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)',
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive'
        }

        last_exception = None

        for attempt in range(max_retries):
            try:
                response = requests.get(
                    self.api_url,
                    timeout=30,
                    headers=headers,
                    verify=True
                )
                response.raise_for_status()
                data = response.json()
                if attempt > 0:
                    print(f"[{datetime.now(SWISS_TZ)}] {self.city_name}: Successfully retrieved data on attempt {attempt + 1}")
                return data

            except requests.exceptions.Timeout as e:
                last_exception = e
                wait_time = min(2 ** (attempt + 1), 60)
                if attempt < max_retries - 1:
                    print(f"[{datetime.now(SWISS_TZ)}] {self.city_name}: Timeout (attempt {attempt + 1}/{max_retries}), waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                else:
                    print(f"[{datetime.now(SWISS_TZ)}] {self.city_name}: Timeout after {max_retries} attempts (waited {wait_time}s max)")

            except requests.exceptions.ConnectionError as e:
                last_exception = e
                wait_time = min(2 ** (attempt + 1), 60)
                if attempt < max_retries - 1:
                    print(f"[{datetime.now(SWISS_TZ)}] {self.city_name}: Connection error (attempt {attempt + 1}/{max_retries}), waiting {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    print(f"[{datetime.now(SWISS_TZ)}] {self.city_name}: Connection error after {max_retries} attempts")

            except requests.exceptions.HTTPError as e:
                last_exception = e
                status_code = e.response.status_code

                if status_code in [429, 500, 502, 503, 504]:
                    wait_time = min(2 ** (attempt + 1), 60)
                    if attempt < max_retries - 1:
                        print(f"[{datetime.now(SWISS_TZ)}] {self.city_name}: Server error {status_code} (attempt {attempt + 1}/{max_retries}), waiting {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        print(f"[{datetime.now(SWISS_TZ)}] {self.city_name}: Server error {status_code} after {max_retries} attempts")
                else:
                    print(f"[{datetime.now(SWISS_TZ)}] {self.city_name}: HTTP error {status_code} (not retryable)")
                    raise

            except requests.exceptions.JSONDecodeError as e:
                last_exception = e
                print(f"[{datetime.now(SWISS_TZ)}] {self.city_name}: Invalid JSON response")
                raise

            except requests.RequestException as e:
                last_exception = e
                print(f"[{datetime.now(SWISS_TZ)}] {self.city_name}: Request error: {str(e)[:100]}")
                raise

        print(f"[{datetime.now(SWISS_TZ)}] Error fetching data for {self.city_name}: All {max_retries} retry attempts failed")
        raise last_exception if last_exception else Exception("Failed to fetch data after all retries")

    @abstractmethod
    def normalize_data(self, raw_data):
        """
        Convert raw API data to unified format.

        Args:
            raw_data: Raw data from API

        Returns:
            dict: Normalized data in unified format:
            {
                "status": "success",
                "city": "city_id",
                "data": {
                    "parkings": {
                        "PARKING_ID": {
                            "id": "PARKING_ID",
                            "name": "Parking Name",
                            "free": 150,
                            "total": 200,
                            "status": "open",
                            "timestamp": "2026-01-06T07:30:00+01:00"
                        }
                    }
                },
                "timestamp": "2026-01-06T07:30:00+01:00"
            }
        """
        pass

    def save_data(self, data):
        """
        Save normalized data to JSON file and MariaDB.

        Args:
            data: Normalized parking data

        Returns:
            dict: Statistics of the save operation
        """
        if not data:
            return {'success': False, 'inserted': 0, 'duplicates': 0, 'failed': 0, 'error': 'No data'}

        now = datetime.now(SWISS_TZ)
        date_str = now.strftime("%Y-%m-%d")

        try:
            from db_utils import get_connection, insert_measurement
            import mysql.connector
            from mysql.connector import errorcode

            conn = get_connection(simulation_mode=self.simulation_mode)
            cursor = conn.cursor()

            parkings = data.get("data", {}).get("parkings", {})
            fetch_ts = data.get("timestamp")
            if fetch_ts:
                try:
                    dt = datetime.fromisoformat(fetch_ts.replace('Z', '+00:00'))
                    fetch_ts = dt.astimezone(SWISS_TZ).strftime("%Y-%m-%d %H:%M:%S")
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
                    'day': date_str,
                    'fetch_ts': fetch_ts,
                    'city': self.city_id,
                    'id': pid,
                    'name': pname,
                    'free': pdata.get('free', 0),
                    'total': pdata.get('total', 0)
                }
                try:
                    insert_measurement(cursor, db_data)
                    success_count += 1
                    inserted_names.append(pname)
                except mysql.connector.Error as err:
                    fail_count += 1
                    print(f"[{now}] {self.city_name}: Failed to upsert parking {pid}: {err}")
                except Exception as e:
                    fail_count += 1
                    print(f"[{now}] {self.city_name}: Failed to upsert parking {pid}: {e}")

            conn.commit()
            cursor.close()
            conn.close()

            mode_info = " (SIMULATION MODE)" if self.simulation_mode else ""
            print(f"[{now}] {self.city_name}: Data saved{mode_info} (Upserted: {success_count}, Failed: {fail_count})")

            return {
                'success': True,
                'inserted': success_count,
                'duplicates': 0,
                'failed': fail_count,
                'error': None,
                'latest_data_ts': fetch_ts,
                'inserted_names': inserted_names,
                'simulation_mode': self.simulation_mode
            }

        except Exception as e:
            print(f"[{now}] {self.city_name}: Error saving data: {e}")
            return {
                'success': False,
                'inserted': 0,
                'duplicates': 0,
                'failed': len(parkings) if 'parkings' in locals() else 0,
                'error': str(e),
                'latest_data_ts': None,
                'simulation_mode': self.simulation_mode
            }

    def collect(self):
        """
        Main collection method: fetch, normalize, and save data.

        Returns:
            dict: Statistics of the collection result
        """
        try:
            print(f"[{datetime.now(SWISS_TZ)}] {self.city_name}: Fetching data...")
            raw_data = self.fetch_raw_data()

            if not raw_data:
                print(f"[{datetime.now(SWISS_TZ)}] {self.city_name}: No data received from API")
                return {
                    'success': False,
                    'inserted': 0,
                    'duplicates': 0,
                    'failed': 0,
                    'error': 'No data received',
                    'latest_data_ts': None,
                    'simulation_mode': self.simulation_mode
                }

            print(f"[{datetime.now(SWISS_TZ)}] {self.city_name}: Normalizing data...")
            normalized_data = self.normalize_data(raw_data)

            if not normalized_data:
                print(f"[{datetime.now(SWISS_TZ)}] {self.city_name}: Failed to normalize data (check API format)")
                return {
                    'success': False,
                    'inserted': 0,
                    'duplicates': 0,
                    'failed': 0,
                    'error': 'Data normalization failed',
                    'latest_data_ts': None,
                    'simulation_mode': self.simulation_mode
                }

            print(f"[{datetime.now(SWISS_TZ)}] {self.city_name}: Saving data...")
            return self.save_data(normalized_data)

        except requests.exceptions.Timeout as e:
            print(f"[{datetime.now(SWISS_TZ)}] {self.city_name}: Timeout - API is slow or unreachable")
            return {
                'success': False,
                'inserted': 0,
                'duplicates': 0,
                'failed': 0,
                'error': 'API timeout',
                'latest_data_ts': None,
                'simulation_mode': self.simulation_mode
            }
        except requests.exceptions.ConnectionError as e:
            print(f"[{datetime.now(SWISS_TZ)}] {self.city_name}: Connection error - network issue or API down")
            return {
                'success': False,
                'inserted': 0,
                'duplicates': 0,
                'failed': 0,
                'error': 'Connection error',
                'latest_data_ts': None,
                'simulation_mode': self.simulation_mode
            }
        except Exception as e:
            error_msg = str(e)[:200]
            print(f"[{datetime.now(SWISS_TZ)}] {self.city_name}: Collection error: {error_msg}")
            return {
                'success': False,
                'inserted': 0,
                'duplicates': 0,
                'failed': 0,
                'error': error_msg,
                'latest_data_ts': None,
                'simulation_mode': self.simulation_mode
            }
