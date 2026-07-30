
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import sys
import os
from datetime import datetime, date
from dotenv import load_dotenv

load_dotenv()

import db_utils

app = Flask(__name__, static_folder='.')
CORS(app)

DB_PROD = os.environ.get('DB_DATABASE_PROD', 'ph_fetch_prod')
DB_TEST = os.environ.get('DB_DATABASE_TEST', 'ph_fetch_test')

def get_db_name():
    env = request.args.get('env', 'prod').lower()
    return DB_PROD if env == 'prod' else DB_TEST

def get_conn():
    return db_utils.get_connection(database_override=get_db_name())

@app.route('/api/environments')
def get_environments():
    return jsonify({'prod': DB_PROD, 'test': DB_TEST})

@app.route('/api/cities')
def get_cities():
    try:
        conn = get_conn()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, name, url, latitude, longitude, collector, api_url FROM cities ORDER BY name")
        rows = cursor.fetchall()
        conn.close()
        for row in rows:
            if row.get('latitude'):
                row['latitude'] = float(row['latitude'])
            if row.get('longitude'):
                row['longitude'] = float(row['longitude'])
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/groups/<city>')
def get_groups(city):
    try:
        conn = get_conn()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT p.id AS parkhaus_id, p.name AS full_name, p.parking_group,
                   pf.name AS short_name
            FROM parkhaeuser p
            LEFT JOIN (
                SELECT id, name FROM pls_fetch_current
                WHERE city = %s
                GROUP BY id, name
            ) pf ON pf.id = p.id
            WHERE p.city_id = %s AND p.is_active = 1
            ORDER BY p.parking_group, p.name
        """, (city, city))
        rows = cursor.fetchall()
        conn.close()

        groups = {}
        for row in rows:
            group_name = row['parking_group'] or 'Andere'
            if group_name not in groups:
                groups[group_name] = []
            display_name = row['short_name'] or row['full_name']
            groups[group_name].append(display_name)

        result = [{"name": name, "parkings": parkings} for name, parkings in groups.items()]
        result.append({"name": "All", "parkings": []})
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/events/<city>/<date_str>')
def get_events(city, date_str):
    try:
        conn = get_conn()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT e.id, e.title, e.venue, e.city, e.start_time, e.end_time,
                   e.description, e.category, e.peak_occupancy_bonus
            FROM local_events e
            WHERE e.city = %s AND DATE(e.start_time) = %s
            ORDER BY e.start_time
        """, (city, date_str))
        events = cursor.fetchall()

        event_ids = [e['id'] for e in events]
        parkhaus_map = {}
        if event_ids:
            placeholders = ','.join(['%s'] * len(event_ids))
            cursor.execute(f"""
                SELECT ep.event_id, p.name
                FROM event_parkhaus ep
                JOIN parkhaeuser p ON ep.parkhaus_id = p.id
                WHERE ep.event_id IN ({placeholders})
            """, event_ids)
            for row in cursor.fetchall():
                parkhaus_map.setdefault(row['event_id'], []).append(row['name'])

        conn.close()

        for event in events:
            if isinstance(event.get('start_time'), datetime):
                event['start_time'] = event['start_time'].isoformat()
            if isinstance(event.get('end_time'), datetime):
                event['end_time'] = event['end_time'].isoformat()
            if event.get('peak_occupancy_bonus') is not None:
                event['peak_occupancy_bonus'] = float(event['peak_occupancy_bonus'])
            event['parkings'] = parkhaus_map.get(event['id'], [])

        return jsonify(events)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/weather/<city>/<date_str>')
def get_weather(city, date_str):
    try:
        conn = get_conn()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT timestamp, temperature, precipitation
            FROM weather_forecasts
            WHERE city_id = %s AND DATE(timestamp) = %s
            ORDER BY timestamp
        """, (city, date_str))
        rows = cursor.fetchall()
        conn.close()

        for row in rows:
            if isinstance(row.get('timestamp'), datetime):
                row['timestamp'] = row['timestamp'].isoformat()
            if row.get('temperature') is not None:
                row['temperature'] = float(row['temperature'])
            if row.get('precipitation') is not None:
                row['precipitation'] = float(row['precipitation'])

        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/dates/<city>')
def get_dates(city):
    try:
        conn = get_conn()
        cursor = conn.cursor()
        query = "SELECT DISTINCT day FROM pls_fetch_current WHERE city = %s ORDER BY day DESC"
        cursor.execute(query, (city,))
        rows = cursor.fetchall()
        dates = [str(row[0]) for row in rows]
        conn.close()
        return jsonify(dates)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/data/<city>/<date_str>')
def get_data(city, date_str):
    try:
        conn = get_conn()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT fetch_ts, id, name, free, total
            FROM pls_fetch_current
            WHERE city = %s AND day = %s
            ORDER BY fetch_ts ASC
        """
        cursor.execute(query, (city, date_str))
        rows = cursor.fetchall()
        conn.close()

        for row in rows:
            if isinstance(row['fetch_ts'], datetime):
                row['fetch_ts'] = row['fetch_ts'].isoformat()

        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/logs')
def get_logs():
    try:
        conn = get_conn()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT timestamp, severity, text FROM log ORDER BY timestamp DESC")
        rows = cursor.fetchall()
        conn.close()

        for row in rows:
            if isinstance(row['timestamp'], datetime):
                row['timestamp'] = row['timestamp'].isoformat()

        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/logs/daily_counts')
def get_daily_log_counts():
    try:
        conn = get_conn()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT DATE(timestamp) as day, COUNT(*) as count
            FROM log
            GROUP BY DATE(timestamp)
            ORDER BY day DESC
        """)
        rows = cursor.fetchall()
        conn.close()

        for row in rows:
            if row['day']:
                row['day'] = row['day'].isoformat()

        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/logs/weekly_stats')
def get_weekly_log_stats():
    try:
        conn = get_conn()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                YEARWEEK(timestamp, 3) as week_code,
                MIN(DATE(timestamp)) as week_start,
                SUBSTRING_INDEX(text, ' ', 1) as parkhaus,
                severity,
                COUNT(*) as count
            FROM log
            GROUP BY week_code, parkhaus, severity
            ORDER BY week_code DESC, parkhaus
        """)
        rows = cursor.fetchall()
        conn.close()

        for row in rows:
            if row['week_start']:
                row['week_start'] = row['week_start'].isoformat()

        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/logs/stuck_parking')
def get_stuck_parking():
    try:
        conn = get_conn()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                city, name, day,
                MIN(free) as min_free, MAX(free) as max_free,
                COUNT(*) as record_count,
                MIN(fetch_ts) as first_fetch, MAX(fetch_ts) as last_fetch
            FROM pls_fetch_current
            WHERE fetch_ts >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
            GROUP BY city, name, day
            HAVING MIN(free) = MAX(free)
            ORDER BY city, name, day DESC
        """)
        rows = cursor.fetchall()
        conn.close()

        for row in rows:
            for field in ('day', 'first_fetch', 'last_fetch'):
                if isinstance(row.get(field), (datetime, date)):
                    row[field] = row[field].isoformat()

        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'index.html')

@app.route('/logs')
def logs():
    return send_from_directory(BASE_DIR, 'logs.html')

if __name__ == '__main__':
    print(f"Server base directory: {BASE_DIR}")
    print(f"Database PROD: {DB_PROD}")
    print(f"Database TEST: {DB_TEST}")
    try:
        app.run(host='0.0.0.0', port=80)
    except Exception as e:
        print(f"Critical error starting server: {e}")
