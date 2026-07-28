"""Scheduler to run collect_data.py every 15 minutes."""
import schedule
import time
import subprocess
import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_collect_data():
    """Execute the collect_data.py script."""
    script_path = Path(__file__).parent / "collect_data.py"
    
    try:
        logger.info("Running collect_data.py...")
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            logger.info("collect_data.py completed successfully")
        else:
            logger.error(f"collect_data.py failed with return code {result.returncode}")
            if result.stderr:
                logger.error(f"Error: {result.stderr}")
        
        if result.stdout:
            logger.info(f"Output: {result.stdout}")
            
    except Exception as e:
        logger.exception(f"Error running collect_data.py: {e}")

def run_get_event_and_weather_data():
    """Execute the get_event_and_weather_data.py script."""
    script_path = Path(__file__).parent / "get_event_and_weather_data.py"

    try:
        logger.info("Running get_event_and_weather_data.py...")
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            logger.info("get_event_and_weather_data.py completed successfully")
        else:
            logger.error(f"get_event_and_weather_data.py failed with return code {result.returncode}")
            if result.stderr:
                logger.error(f"Error: {result.stderr}")

        if result.stdout:
            logger.info(f"Output: {result.stdout}")

    except Exception as e:
        logger.exception(f"Error running get_event_and_weather_data.py: {e}")

def main():
    """Main entry point."""
    try:
        schedule.every(15).minutes.do(run_collect_data)

        # Run event and weather data collection twice daily
        schedule.every().day.at("06:00").do(run_get_event_and_weather_data)
        schedule.every().day.at("18:00").do(run_get_event_and_weather_data)

        # Run first collection immediately
        run_collect_data()

        logger.info("Scheduler started - will run collect_data every 15 minutes and get_event_and_weather_data twice daily")
        
        while True:
            schedule.run_pending()
            time.sleep(60)
            
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
