
import os
import json
import logging
import mysql.connector
from mysql.connector import Error

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def load_db_config():
    """Load database configuration from a config file, with environment variable overrides."""
    # Start with defaults
    config = {
        'host': 'localhost',
        'user': 'root',
        'password': '',
        'database': 'parking_monitoring',
        'port': 3306
    }
    
    # 1. Load from db_config.json if it exists
    config_path = os.path.join(os.path.dirname(__file__), 'db_config.json')
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                file_config = json.load(f)
                config.update(file_config)
        except Exception as e:
            logging.error(f"Error reading db_config.json: {e}")
    
    # 2. Override with environment variables if provided
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

def get_connection():
    """Establish a connection to the MariaDB database."""
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
    Insert a single measurement record using the provided cursor.
    Does NOT commit the transaction.
    
    Args:
        cursor: Active database cursor.
        data (dict): Dictionary containing the data to insert.
    """
    
    insert_query = """
    INSERT INTO pls_fetch_current 
    (day, fetch_ts, city, id, name, free, total)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
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
        cursor.execute(insert_query, record)
    except Error as e:
        logging.error(f"Error inserting record {data}: {e}")
        raise

def insert_log(cursor, severity, text):
    """
    Insert a log entry into the log table.
    
    Args:
        cursor: Active database cursor.
        severity (str): Log severity (I=Info, W=Warning, E=Error).
        text (str): Log message text.
    """
    
    insert_query = """
    INSERT INTO log (timestamp, severity, text)
    VALUES (NOW(), %s, %s)
    """
    
    try:
        # Truncate text if it's too long for the database column (assuming 65535 for TEXT or similar)
        safe_text = text[:60000] if text else ""
        cursor.execute(insert_query, (severity, safe_text))
    except Error as e:
        logging.error(f"Error inserting log: {e}")
        raise