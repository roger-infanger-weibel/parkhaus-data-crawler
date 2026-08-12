import datetime
import requests

from constants import SWISS_TZ
from db_utils import get_connection

CITIES = [
    {"id": "basel", "name": "Basel", "lat": 47.5596, "lon": 7.5886},
    {"id": "zurich", "name": "Zuerich", "lat": 47.3769, "lon": 8.5417},
    {"id": "bern", "name": "Bern", "lat": 46.9480, "lon": 7.4474},
    {"id": "luzern", "name": "Luzern", "lat": 47.0502, "lon": 8.3093},
    {"id": "stgallen", "name": "St. Gallen", "lat": 47.4239, "lon": 9.3748},
]


def _fetch_weather(cursor, connection, api_base, label, extra_params=""):
    """Shared logic for historical and forecast weather fetching."""
    for city in CITIES:
        print(f"Lade {label} fuer {city['name']}...")
        url = (
            f"{api_base}?"
            f"latitude={city['lat']}&longitude={city['lon']}&"
            f"hourly=temperature_2m,precipitation&timezone=Europe/Zurich"
            f"{extra_params}"
        )

        try:
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            data = r.json()

            times = data["hourly"]["time"]
            temps = data["hourly"]["temperature_2m"]
            precs = data["hourly"]["precipitation"]

            sql = """
                INSERT INTO weather_forecasts (city_id, timestamp, temperature, precipitation)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    temperature = VALUES(temperature),
                    precipitation = VALUES(precipitation)
            """

            batch = []
            for i in range(len(times)):
                dt_str = times[i].replace("T", " ") + ":00"
                batch.append((city["id"], dt_str, temps[i], precs[i]))

            cursor.executemany(sql, batch)
            connection.commit()
            print(f"-> {len(batch)} {label}-Datensaetze fuer {city['name']} importiert.")

        except Exception as e:
            print(f"Fehler bei {city['name']}: {e}")


def fetch_and_store_historical_weather():
    print("--- 1. Hole historische Wetterdaten ---")
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("SET time_zone = '+00:00';")

    start_date = "2026-07-01"
    end_date = datetime.date.today().strftime("%Y-%m-%d")

    _fetch_weather(
        cursor, connection,
        api_base="https://archive-api.open-meteo.com/v1/archive",
        label="Wetter",
        extra_params=f"&start_date={start_date}&end_date={end_date}",
    )

    cursor.close()
    connection.close()


def fetch_and_store_forecast_weather():
    print("\n--- 1b. Hole Wettervorhersage (heute + 7 Tage) ---")
    connection = get_connection()
    cursor = connection.cursor()

    _fetch_weather(
        cursor, connection,
        api_base="https://api.open-meteo.com/v1/forecast",
        label="Vorhersage",
        extra_params="&forecast_days=7",
    )

    cursor.close()
    connection.close()


if __name__ == "__main__":
    fetch_and_store_historical_weather()
    fetch_and_store_forecast_weather()
    print("\nFertig! Wetterdaten importiert.")
    print("Hinweis: Events werden via fetch_events.py automatisch gescraped.")
