
import os
import json
import logging
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class MockCursor:
    """Mock cursor for simulation mode - doesn't actually write to database."""

    def __init__(self):
        self.executed_queries = []

    def execute(self, query, args=None):
        """Record the query without executing it."""
        self.executed_queries.append({'query': query, 'args': args})

    def fetchall(self):
        return []

    def fetchone(self):
        return None

    def close(self):
        """No-op in simulation mode."""
        pass

class MockConnection:
    """Mock connection for simulation mode."""

    def __init__(self):
        self.cursor_obj = MockCursor()

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        """No-op in simulation mode."""
        pass

    def close(self):
        """No-op in simulation mode."""
        pass

    def is_connected(self):
        return True

def load_db_config():
    """Load database configuration from a config file, with environment variable overrides."""
    config = {
        'host': 'localhost',
        'user': 'root',
        'password': '',
        'database': 'parking_monitoring',
        'port': 3306
    }

    config_path = os.path.join(os.path.dirname(__file__), 'db_config.json')
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                file_config = json.load(f)
                config.update(file_config)
        except Exception as e:
            logging.error(f"Error reading db_config.json: {e}")

    config['host'] = os.environ.get('DB_HOST', config['host'])
    config['user'] = os.environ.get('DB_USER', config['user'])
    config['password'] = os.environ.get('DB_PASSWORD', config['password'])
    config['database'] = os.environ.get('DB_NAME', config['database'])

    env_port = os.environ.get('DB_PORT')
    if env_port:
        try:
            config['port'] = int(env_port)
        except ValueError:
            logging.warning(f"Invalid DB_PORT environment variable: {env_port}. Using {config['port']}")

    return config

def get_connection(simulation_mode=False):
    """
    Establish a connection to the MariaDB database.

    Args:
        simulation_mode (bool): If True, return a mock connection that doesn't write.

    Returns:
        Connection object (real or mock)
    """
    if simulation_mode:
        logging.info("Running in simulation mode - database writes disabled")
        return MockConnection()

    config = load_db_config()
    try:
        connection = mysql.connector.connect(
            host=config['host'],
            user=config['user'],
            password=config['password'],
            database=config['database'],
            port=config['port']
        )
        if connection.is_connected():
            return connection
    except Error as e:
        logging.error(f"Error connecting to MariaDB: {e}")
        raise e

def insert_measurement(cursor, data):
    """
    Insert or update a single measurement record using UPSERT pattern.
    Prevents duplicates by updating existing records instead of failing.
    Does NOT commit the transaction.

    Args:
        cursor: Active database cursor (can be real or mock).
        data (dict): Dictionary containing the data to insert.
    """

    upsert_query = """
    INSERT INTO pls_fetch_current
    (day, fetch_ts, city, id, name, free, total)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        fetch_ts = VALUES(fetch_ts),
        name = VALUES(name),
        free = VALUES(free),
        total = VALUES(total)
    """

    try:
        record = (
            data.get('day'),
            data.get('fetch_ts'),
            data.get('city'),
            data.get('id'),
            data.get('name'),
            data.get('free'),
            data.get('total')
        )
        cursor.execute(upsert_query, record)
    except Error as e:
        logging.error(f"Error upserting record {data}: {e}")
        raise

def insert_log(cursor, severity, text):
    """
    Insert a log entry into the log table.

    Args:
        cursor: Active database cursor (can be real or mock).
        severity (str): Log severity (I=Info, W=Warning, E=Error).
        text (str): Log message text.
    """

    insert_query = """
    INSERT INTO log (timestamp, severity, text)
    VALUES (NOW(), %s, %s)
    """

    try:
        safe_text = text[:60000] if text else ""
        cursor.execute(insert_query, (severity, safe_text))
    except Error as e:
        logging.error(f"Error inserting log: {e}")
        raise
