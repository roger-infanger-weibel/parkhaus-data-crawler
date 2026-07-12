"""
Multi-city parking data collection orchestrator.

This script coordinates data collection from multiple Swiss cities with
PLS (Parkleitsystem) parking guidance systems.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

from luzern import LuzernCollector
from basel import BaselCollector
from stgallen import StGallenCollector
from zurich import ZurichCollector
from bern import BernCollector

import db_utils



# Collector class mapping
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


def create_collector(city_id, city_config):
    """
    Create a collector instance for a city.
    
    Args:
        city_id: City identifier
        city_config: City configuration dict
    
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
        api_url=city_config.get("api_url")
    )


def collect_city_data(city_id, config):
    """
    Collect data for a specific city.
    
    Args:
        city_id: City identifier
        config: Full configuration dict
    
    Returns:
        dict: Statistics of the collection result
    """
    cities = config.get("cities", {})
    
    if city_id not in cities:
        print(f"Error: City '{city_id}' not found in configuration")
        return {'success': False, 'inserted': 0, 'duplicates': 0, 'failed': 0, 'error': 'City not found'}
    
    city_config = cities[city_id]
    
    if not city_config.get("enabled", True):
        print(f"Info: City '{city_id}' is disabled in configuration")
        return {'success': False, 'inserted': 0, 'duplicates': 0, 'failed': 0, 'error': 'Disabled'}
    
    collector = create_collector(city_id, city_config)
    if not collector:
        return {'success': False, 'inserted': 0, 'duplicates': 0, 'failed': 0, 'error': 'Collector not found'}
    
    return collector.collect()


def collect_all_cities(config):
    """
    Collect data for all enabled cities.
    
    Args:
        config: Configuration dict
    
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
        
        stats = collect_city_data(city_id, config)
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
    
    args = parser.parse_args()

    # Load configuration
    config = load_config()
    
    print("Job started")
    print(f"Swiss Parking Monitor - Starting at {datetime.now()}")
    
    # Collect all cities
    results = collect_all_cities(config)
    
    # Print summary header
    print(f"\n{'='*80}")
    print("Collection Summary:")
    print(f"{'='*80}")
    print(f"{'City':<15} {'Status':<10} {'Inserted':<10} {'Duplicates':<12} {'Failed':<10} {'Latest Data':<20}")
    print("-" * 80)
    
    # Initialize DB connection for logging
    conn = None
    cursor = None
    try:
        conn = db_utils.get_connection()
        if conn:
            cursor = conn.cursor()
    except Exception as e:
        print(f"Error connecting to database for logging: {e}")

    # Aggressive Garbage Collection nach intensiven DB-Operationen
    gc.collect()
    
    for city_id, stats in results.items():
        success = stats.get('success', False)
        status = "SUCCESS" if success else "FAILED"
        ins = stats.get('inserted', 0)
        dup = stats.get('duplicates', 0)
        fail = stats.get('failed', 0)
        latest_ts = stats.get('latest_data_ts') or "N/A"
        
        # Determine severity for this city
        severity = 'I'
        if not success or fail > 0:
            severity = 'E'
        elif dup > 0:
            severity = 'W'
            
        # Format log line
        log_text = f"{city_id:15} {status:10} {ins:<10} {dup:<12} {fail:<10} {latest_ts:<20}"
        print(log_text)
        
        # Trace output if requested
        if args.trace and success and ins > 0:
            names = stats.get('inserted_names', [])
            if names:
                print(f"  └─ Inserted: {', '.join(names)}")
        
        # Log to database
        if cursor:
            try:
                db_utils.insert_log(cursor, severity, log_text)
            except Exception as e:
                print(f"Error inserting individual log for {city_id}: {e}")

        # Optional: Pro Stadt GC triggern falls Memory kritisch
        if gc.get_count()[0] > 500:  # Objekt-Count
            gc.collect()
            
    # Commit and close
    if conn:
        try:
            conn.commit()
            conn.close()
            print("Individual city logs saved to database.")
        except Exception as e:
            print(f"Error committing logs: {e}")
    
    # Exit with error if any city failed
    all_success = all(res.get('success', False) for res in results.values())
    
    print("Job finished")
    
    sys.exit(0 if all_success else 1)


if __name__ == "__main__":
    main()
