# Swiss Parking Crawler

A standalone data collection tool for Swiss parking availability (Parkleitsystem).

## Features

- Collects real-time parking data from:
  - Luzern
  - Basel
  - St. Gallen
  - Zürich
- Collects real-time parking data from Swiss cities.
- Normalizes data into a unified format.
- Stores data in MariaDB for historical analysis and visualization.

## Requirements

- Python 3.7+
- `requests` library

## Installation

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

Run the collector once to fetch current data for all cities and save to database:
```bash
python collect_data.py
```

Run with trace to see exactly which parking places are being updated:
```bash
python collect_data.py --trace
```


## Project Structure

- `collect_data.py`: Main orchestrator script.
- `base.py`: Base collector class.
- `luzern.py`, `basel.py`, `stgallen.py`, `zurich.py`: City-specific implementations.
- `cities.json`: Configuration for cities and APIs.
- `db_utils.py`: Database connection and helper functions.
- `web_server.py`: Flask API to serve data from the database.
- `index.html`: Dashboard for data visualization.



