import os
import sys
import datetime
import json
import requests
import pymysql
from dotenv import load_dotenv
load_dotenv()

# --- KONFIGURATION ---
DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_USER = os.environ.get("DB_USER", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_NAME = os.environ.get("DB_NAME", "ph_fetch_test")

CITIES = [
    {"id": "basel", "name": "Basel", "lat": 47.5596, "lon": 7.5886},
    {"id": "zurich", "name": "Zürich", "lat": 47.3769, "lon": 8.5417},
    {"id": "bern", "name": "Bern", "lat": 46.9480, "lon": 7.4474},
    {"id": "luzern", "name": "Luzern", "lat": 47.0502, "lon": 8.3093},
    {"id": "stgallen", "name": "St. Gallen", "lat": 47.4239, "lon": 9.3748}
]


def fetch_and_store_historical_weather():
    print("--- 1. Hole historische Wetterdaten ab 01.01.2026 ---")
    connection = pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            autocommit=True
        )

    cursor = connection.cursor()
    cursor.execute("SET time_zone = '+00:00';")

    start_date = "2026-07-01"
    end_date = datetime.date.today().strftime("%Y-%m-%d")

    for city in CITIES:
        print(f"Lade Wetter für {city['name']} ({start_date} bis {end_date})...")
        url = (
            f"https://archive-api.open-meteo.com/v1/archive?"
            f"latitude={city['lat']}&longitude={city['lon']}&"
            f"start_date={start_date}&end_date={end_date}&"
            f"hourly=temperature_2m,precipitation&timezone=Europe/Zurich"
        )

        try:
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            data = r.json()

            times = data["hourly"]["time"]
            temps = data["hourly"]["temperature_2m"]
            precs = data["hourly"]["precipitation"]

            # Batch Insert vorbereiten
            sql = """
                INSERT INTO weather_forecasts (city_id, timestamp, temperature, precipitation)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                    temperature = VALUES(temperature),
                    precipitation = VALUES(precipitation)
            """

            batch = []
            for i in range(len(times)):
                # API liefert z.B. "2026-01-01T00:00" -> formatiere für MariaDB
                dt_str = times[i].replace("T", " ") + ":00"
                batch.append((city["id"], dt_str, temps[i], precs[i]))

            cursor.executemany(sql, batch)
            connection.commit()
            print(f"-> {len(batch)} Wetter-Datensätze für {city['name']} importiert.")

        except Exception as e:
            print(f"Fehler bei {city['name']}: {e}")

    cursor.close()
    connection.close()


def store_historical_events():
    print("\n--- 2. Generiere plausible Kultur- & Theater-Events ab 01.01.2026 ---")
    connection = pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            autocommit=True
        )
    cursor = connection.cursor()

    # Lokale Events (inkl. Luzern Stadt Theater, KKL und Zürcher Bühnen)
    # Für historische Vergleiche generieren wir wöchentlich wiederkehrende Events ab dem 01.01.2026
    events_to_insert = []
    event_mappings = []

    start_date = datetime.datetime(2026, 1, 1)
    end_date = datetime.datetime.now() + datetime.timedelta(days=14)  # 2 Wochen Zukunft

    current_day = start_date
    event_counter = 1

    while current_day <= end_date:
        weekday = current_day.weekday()  # 0=Mo, 4=Fr, 5=Sa, 6=So

        # A) Stadt Theater Luzern (Jeden Freitag- und Samstagabend)
        if weekday in (4, 5):
            e_id = f"lu-theater-hist-{event_counter}"
            start_time = current_day.replace(hour=19, minute=30, second=0)
            end_time = current_day.replace(hour=22, minute=0, second=0)
            events_to_insert.append((
                e_id, "Theateraufführung - Stadt Theater Luzern",
                "Stadt Theater Luzern", "Luzern",
                start_time.strftime("%Y-%m-%d %H:%M:%S"),
                end_time.strftime("%Y-%m-%d %H:%M:%S"),
                "Klassisches Schauspiel im Herzen von Luzern. Hohe Nachfrage in den Parkhäusern Süd.",
                "Theater", 0.35
            ))
            # Betroffene Parkhäuser: Stadt Theater, Kantonalbank, Kesselturm
            for g_id in ["luzernparkingstadttheater", "luzernparkhauskantonalbank", "luzernparkhauskesselturm"]:
                event_mappings.append((e_id, g_id))
            event_counter += 1

        # B) KKL Luzern - Lucerne Festival Konzerte (Jeden Samstag- und Sonntagabend)
        if weekday in (5, 6):
            e_id = f"lu-kkl-hist-{event_counter}"
            start_time = current_day.replace(hour=19, minute=15, second=0)
            end_time = current_day.replace(hour=21, minute=45, second=0)
            events_to_insert.append((
                e_id, "Sinfoniekonzert - KKL Luzern",
                "KKL Luzern (Konzertsaal)", "Luzern",
                start_time.strftime("%Y-%m-%d %H:%M:%S"),
                end_time.strftime("%Y-%m-%d %H:%M:%S"),
                "Meisterkonzert im berühmten KKL direkt am See. Betrifft die Bahnhofsparkhäuser.",
                "Konzert", 0.40
            ))
            for g_id in ["luzernparkhausbahnhof", "luzernparkhausbahnhofp1p2", "luzernparkhausbahnhofp3"]:
                event_mappings.append((e_id, g_id))
            event_counter += 1

        # C) Zürich Theater 11 (Oerlikon - Freitags)
        if weekday == 4:
            e_id = f"zh-theater11-hist-{event_counter}"
            start_time = current_day.replace(hour=20, minute=0, second=0)
            end_time = current_day.replace(hour=22, minute=30, second=0)
            events_to_insert.append((
                e_id, "Musical Chicago - Theater 11",
                "Theater 11 Zürich", "Zürich",
                start_time.strftime("%Y-%m-%d %H:%M:%S"),
                end_time.strftime("%Y-%m-%d %H:%M:%S"),
                "Broadway-Klassiker live im Zürcher Norden.",
                "Theater", 0.38
            ))
            for g_id in ["zuerichparkplatztheater11", "zuerichparkhausmessezuerichag"]:
                event_mappings.append((e_id, g_id))
            event_counter += 1

        current_day += datetime.timedelta(days=1)

    # In DB schreiben
    sql_events = """
        INSERT INTO local_events (id, title, venue, city, start_time, end_time, description, category, peak_occupancy_bonus)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE title=VALUES(title)
    """
    cursor.executemany(sql_events, events_to_insert)

    sql_mappings = """
        INSERT INTO event_parkhaus (event_id, parkhaus_id)
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE event_id=VALUES(event_id)
    """
    cursor.executemany(sql_mappings, event_mappings)

    connection.commit()
    print(f"-> {len(events_to_insert)} historische Events in Tabelle 'local_events' importiert.")
    print(f"-> {len(event_mappings)} Zuordnungen in 'event_parkhaus' angelegt.")

    cursor.close()
    connection.close()


if __name__ == "__main__":
    fetch_and_store_historical_weather()
    store_historical_events()
    print("\nFertig! Alle historischen Daten ab 01.01.2026 sind importiert.")