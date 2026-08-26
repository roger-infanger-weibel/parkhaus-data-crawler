"""Scheduler to run collect_data.py every 15 minutes."""
import schedule
import time
import subprocess
import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SCANNER_DIR = Path(__file__).parent


def _run_script(name, timeout=None):
    """Run a Python script in the scanner directory."""
    script_path = SCANNER_DIR / name
    try:
        logger.info("Running %s...", name)
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=SCANNER_DIR,
            capture_output=True, text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            logger.info("%s completed successfully", name)
        else:
            logger.error("%s failed with return code %d", name, result.returncode)
            if result.stderr:
                logger.error("Error: %s", result.stderr)
        if result.stdout:
            logger.info("Output: %s", result.stdout)
    except Exception:
        logger.exception("Error running %s", name)


def main():
    """Main entry point."""
    try:
        schedule.every(15).minutes.do(_run_script, "collect_data.py")
        schedule.every().day.at("06:00").do(_run_script, "get_event_and_weather_data.py")
        schedule.every().day.at("18:00").do(_run_script, "get_event_and_weather_data.py")
        schedule.every().day.at("06:30").do(_run_script, "fetch_events.py", timeout=300)
        schedule.every().day.at("18:30").do(_run_script, "fetch_events.py", timeout=300)
        schedule.every().monday.at("07:00").do(_run_script, "check_parkhaus_urls.py", timeout=120)

        _run_script("collect_data.py")

        logger.info("Scheduler started - collect_data every 15 min, weather 2x daily, events 2x daily, URL check weekly Mon 07:00")

        while True:
            schedule.run_pending()
            time.sleep(60)

    except Exception:
        logger.exception("Fatal error")
        sys.exit(1)

if __name__ == "__main__":
    main()
