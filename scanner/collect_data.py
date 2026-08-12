"""
Multi-city parking data collection orchestrator with simulation mode support.

This script coordinates data collection from multiple Swiss cities with
PLS (Parkleitsystem) parking guidance systems. Supports dry-run/simulation
mode to test the collection pipeline without writing to the database.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from constants import SWISS_TZ

sys.path.insert(0, os.path.dirname(__file__))

from luzern import LuzernCollector
from basel import BaselCollector
from stgallen import StGallenCollector
from zurich import ZurichCollector
from bern import BernCollector

import db_utils


COLLECTOR_MAP = {
    "luzern.LuzernCollector": LuzernCollector,
    "basel.BaselCollector": BaselCollector,
    "stgallen.StGallenCollector": StGallenCollector,
    "zurich.ZurichCollector": ZurichCollector,
    "bern.BernCollector": BernCollector,
}


def load_config():
    """Load city configuration from cities.json."""
    config_path = Path(__file__).parent / "cities.json"

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: Configuration file not found at {config_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in configuration file: {e}")
        sys.exit(1)


def create_collector(city_id, city_config, simulation_mode=False):
    """
    Create a collector instance for a city.

    Args:
        city_id: City identifier
        city_config: City configuration dict
        simulation_mode (bool): If True, don't write to database

    Returns:
        BaseParkingCollector instance or None if collector not found
    """
    collector_class_name = city_config.get("collector")
    collector_class = COLLECTOR_MAP.get(collector_class_name)

    if not collector_class:
        print(f"Warning: Collector '{collector_class_name}' not found for {city_id}")
        return None

    return collector_class(
        city_id=city_id,
        city_name=city_config.get("name", city_id),
        api_url=city_config.get("api_url"),
        simulation_mode=simulation_mode
    )


def collect_city_data(city_id, config, simulation_mode=False):
    """
    Collect data for a specific city.

    Args:
        city_id: City identifier
        config: Full configuration dict
        simulation_mode (bool): If True, don't write to database

    Returns:
        dict: Statistics of the collection result
    """
    cities = config.get("cities", {})

    if city_id not in cities:
        print(f"Error: City '{city_id}' not found in configuration")
        return {'success': False, 'inserted': 0, 'duplicates': 0, 'failed': 0, 'error': 'City not found', 'simulation_mode': simulation_mode}

    city_config = cities[city_id]

    if not city_config.get("enabled", True):
        print(f"Info: City '{city_id}' is disabled in configuration")
        return {'success': False, 'inserted': 0, 'duplicates': 0, 'failed': 0, 'error': 'Disabled', 'simulation_mode': simulation_mode}

    collector = create_collector(city_id, city_config, simulation_mode=simulation_mode)
    if not collector:
        return {'success': False, 'inserted': 0, 'duplicates': 0, 'failed': 0, 'error': 'Collector not found', 'simulation_mode': simulation_mode}

    return collector.collect()


def collect_all_cities(config, simulation_mode=False):
    """
    Collect data for all enabled cities.

    Args:
        config: Configuration dict
        simulation_mode (bool): If True, don't write to database

    Returns:
        dict: Results for each city {city_id: stats_dict}
    """
    cities = config.get("cities", {})
    results = {}

    for city_id, city_config in cities.items():
        if not city_config.get("enabled", True):
            print(f"Skipping disabled city: {city_id}")
            continue

        print(f"\n{'='*60}")
        print(f"Collecting data for: {city_config.get('name', city_id)}")
        print(f"{'='*60}")

        stats = collect_city_data(city_id, config, simulation_mode=simulation_mode)
        results[city_id] = stats

    return results


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Monitor parking data from Swiss cities with PLS systems"
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        help="Print the names of inserted parking places"
    )
    parser.add_argument(
        "--simulation",
        "--dry-run",
        action="store_true",
        dest="simulation",
        help="Run in simulation mode - fetch and process data without writing to database"
    )

    args = parser.parse_args()

    config = load_config()

    mode_label = "SIMULATION MODE" if args.simulation else "NORMAL MODE"
    print("Job started")
    print(f"Swiss Parking Monitor - Starting at {datetime.now(SWISS_TZ)} [{mode_label}]")

    results = collect_all_cities(config, simulation_mode=args.simulation)

    print(f"\n{'='*80}")
    print("Collection Summary:")
    print(f"{'='*80}")
    print(f"{'City':<15} {'Status':<10} {'Inserted':<10} {'Duplicates':<12} {'Failed':<10} {'Latest Data':<20}")
    print("-" * 80)

    conn = None
    cursor = None

    if not args.simulation:
        try:
            conn = db_utils.get_connection(simulation_mode=False)
            if conn:
                cursor = conn.cursor()
        except Exception as e:
            print(f"Error connecting to database for logging: {e}")

    for city_id, stats in results.items():
        success = stats.get('success', False)
        status = "SUCCESS" if success else "FAILED"
        ins = stats.get('inserted', 0)
        dup = stats.get('duplicates', 0)
        fail = stats.get('failed', 0)
        latest_ts = stats.get('latest_data_ts') or "N/A"

        severity = 'I'
        if not success or fail > 0:
            severity = 'E'
        elif dup > 0:
            severity = 'W'

        log_text = f"{city_id:15} {status:10} {ins:<10} {dup:<12} {fail:<10} {latest_ts:<20}"
        print(log_text)

        if args.trace and success and ins > 0:
            names = stats.get('inserted_names', [])
            if names:
                print(f"  └─ Inserted: {', '.join(names)}")

        if cursor and not args.simulation:
            try:
                db_utils.insert_log(cursor, severity, log_text)
            except Exception as e:
                print(f"Error inserting individual log for {city_id}: {e}")

    if conn:
        try:
            conn.commit()
            conn.close()
            print("Individual city logs saved to database.")
        except Exception as e:
            print(f"Error committing logs: {e}")

    all_success = all(res.get('success', False) for res in results.values())

    if args.simulation:
        print("\n[!] SIMULATION MODE: No data was written to the database")

    print("Job finished")

    sys.exit(0 if all_success else 1)


if __name__ == "__main__":
    main()
