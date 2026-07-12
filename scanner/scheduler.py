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

def run_update_events():
    """Execute the update_events.py script."""
    script_path = Path(__file__).parent / "update_events.py"
    
    if not script_path.exists():
        # Ideally we would log this, but let's just return silently if not present yet
        # or log a warning if we expect it.
        # logger.warning(f"{script_path} not found.")
        return

    try:
        logger.info("Running update_events.py...")
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            logger.info("update_events.py completed successfully")
        else:
            logger.error(f"update_events.py failed with return code {result.returncode}")
            if result.stderr:
                logger.error(f"Error: {result.stderr}")
        
        if result.stdout:
            logger.info(f"Output: {result.stdout}")
            
    except Exception as e:
        logger.exception(f"Error running update_events.py: {e}")

def main():
    """Main entry point."""
    try:
        schedule.every(15).minutes.do(run_collect_data)
        
        # Run event update daily at 04:00
        schedule.every().day.at("04:00").do(run_update_events)
        
        # Run first collection immediately
        run_collect_data()
        
        # Try running event update on startup too, if needed
        # run_update_events() 
        
        logger.info("Scheduler started - will run collect_data every 15 minutes and update_events daily")
        
        while True:
            schedule.run_pending()
            time.sleep(60)
            
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
