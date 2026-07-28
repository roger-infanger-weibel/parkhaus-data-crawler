"""
Base parking collector class for all city-specific collectors.
"""

import requests
import json
import os
from datetime import datetime
from abc import ABC, abstractmethod


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

    def fetch_raw_data(self):
        """
        Fetch raw data from the API.

        Returns:
            dict: Raw API response as JSON

        Raises:
            requests.RequestException: If the API request fails
        """
        try:
            response = requests.get(self.api_url, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"[{datetime.now()}] Error fetching data for {self.city_name}: {e}")
            raise

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

        now = datetime.now()
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
                    fetch_ts = dt.strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    fetch_ts = now.strftime("%Y-%m-%d %H:%M:%S")
            else:
                fetch_ts = now.strftime("%Y-%m-%d %H:%M:%S")

            success_count = 0
            fail_count = 0
            duplicate_count = 0
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
                    if err.errno == errorcode.ER_DUP_ENTRY:
                        duplicate_count += 1
                    else:
                        fail_count += 1
                        print(f"[{now}] {self.city_name}: Failed to insert parking {pid}: {err}")
                except Exception as e:
                    fail_count += 1
                    print(f"[{now}] {self.city_name}: Failed to insert parking {pid}: {e}")

            conn.commit()
            cursor.close()
            conn.close()

            mode_info = " (SIMULATION MODE)" if self.simulation_mode else ""
            print(f"[{now}] {self.city_name}: Data saved{mode_info} (Inserted: {success_count}, Duplicates: {duplicate_count}, Failed: {fail_count})")

            return {
                'success': True,
                'inserted': success_count,
                'duplicates': duplicate_count,
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
                'failed': 0,
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
            print(f"[{datetime.now()}] {self.city_name}: Fetching data...")
            raw_data = self.fetch_raw_data()

            print(f"[{datetime.now()}] {self.city_name}: Normalizing data...")
            normalized_data = self.normalize_data(raw_data)

            print(f"[{datetime.now()}] {self.city_name}: Saving data...")
            return self.save_data(normalized_data)

        except Exception as e:
            print(f"[{datetime.now()}] {self.city_name}: Collection failed: {e}")
            return {
                'success': False,
                'inserted': 0,
                'duplicates': 0,
                'failed': 0,
                'error': str(e),
                'latest_data_ts': None,
                'simulation_mode': self.simulation_mode
            }
