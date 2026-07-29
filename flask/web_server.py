
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import sys
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

import db_utils

app = Flask(__name__, static_folder='.')
CORS(app)

DB_PROD = os.environ.get('DB_DATABASE_PROD', 'ph_fetch_prod')
DB_TEST = os.environ.get('DB_DATABASE_TEST', 'ph_fetch_test')

def get_db_name():
    """Get database name from query parameter 'env' (prod/test)."""
    env = request.args.get('env', 'prod').lower()
    return DB_PROD if env == 'prod' else DB_TEST

def get_conn():
    """Get a database connection for the selected environment."""
    return db_utils.get_connection(database_override=get_db_name())

@app.route('/api/environments')
def get_environments():
    return jsonify({
        'prod': DB_PROD,
        'test': DB_TEST
    })

@app.route('/api/cities')
def get_cities():
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT city FROM pls_fetch_current ORDER BY city")
        cities = [row[0] for row in cursor.fetchall()]
        conn.close()
        return jsonify(cities)
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

@app.route('/api/data/<city>/<date>')
def get_data(city, date):
    try:
        conn = get_conn()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT fetch_ts, id, name, free, total
            FROM pls_fetch_current
            WHERE city = %s AND day = %s
            ORDER BY fetch_ts ASC
        """
        cursor.execute(query, (city, date))
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
        query = "SELECT timestamp, severity, text FROM log ORDER BY timestamp DESC"
        cursor.execute(query)
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
        query = """
            SELECT DATE(timestamp) as day, COUNT(*) as count
            FROM log
            GROUP BY DATE(timestamp)
            ORDER BY day DESC
        """
        cursor.execute(query)
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
        query = """
            SELECT
                YEARWEEK(timestamp, 3) as week_code,
                MIN(DATE(timestamp)) as week_start,
                SUBSTRING_INDEX(text, ' ', 1) as parkhaus,
                severity,
                COUNT(*) as count
            FROM log
            GROUP BY week_code, parkhaus, severity
            ORDER BY week_code DESC, parkhaus
        """
        cursor.execute(query)
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
        query = """
            SELECT
                city,
                name,
                day,
                MIN(free) as min_free,
                MAX(free) as max_free,
                COUNT(*) as record_count,
                MIN(fetch_ts) as first_fetch,
                MAX(fetch_ts) as last_fetch
            FROM pls_fetch_current
            WHERE fetch_ts >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
            GROUP BY city, name, day
            HAVING MIN(free) = MAX(free)
            ORDER BY city, name, day DESC
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()

        for row in rows:
            if isinstance(row.get('day'), datetime):
                row['day'] = row['day'].isoformat()
            if isinstance(row.get('first_fetch'), datetime):
                row['first_fetch'] = row['first_fetch'].isoformat()
            if isinstance(row.get('last_fetch'), datetime):
                row['last_fetch'] = row['last_fetch'].isoformat()

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

@app.route('/cities.json')
def serve_cities_json():
    return send_from_directory(BASE_DIR, 'cities.json')

@app.route('/groups.json')
def serve_groups_json():
    return send_from_directory(BASE_DIR, 'groups.json')

@app.route('/events.json')
def serve_events_json():
    return send_from_directory(BASE_DIR, 'events.json')

if __name__ == '__main__':
    print(f"Server base directory: {BASE_DIR}")
    print(f"Database PROD: {DB_PROD}")
    print(f"Database TEST: {DB_TEST}")
    try:
        app.run(host='0.0.0.0', port=80)
    except Exception as e:
        print(f"Critical error starting server: {e}")
