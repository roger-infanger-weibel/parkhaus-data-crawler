import json
import logging
import requests
import re
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

EVENTS_FILE = Path(__file__).parent / "events.json"
PAST_EVENTS_FILE = Path(__file__).parent / "past_events.json"
MAPPINGS_FILE = Path(__file__).parent / "event_mappings.json"
GROUPS_FILE = Path(__file__).parent / "groups.json"

def parse_german_date(date_str):
    """
    Parse dates like "Do, 26. Feb. 2026 | 19:30" (KKL) 
    or "Sa 24.01. 10.00" (Theater)
    """
    # Clean up non-breaking spaces
    date_str = date_str.replace('\xa0', ' ').replace('\u00a0', ' ')
    
    months = {
        "Jan": 1, "Feb": 2, "Mär": 3, "Apr": 4, "Mai": 5, "Jun": 6,
        "Jul": 7, "Aug": 8, "Sep": 9, "Okt": 10, "Nov": 11, "Dez": 12,
        "Januar": 1, "Februar": 2, "März": 3, "April": 4, "Mai": 5, "Juni": 6,
        "Juli": 7, "August": 8, "September": 9, "Oktober": 10, "November": 11, "Dezember": 12
    }
    
    now = datetime.now()
    try:
        # KKL Format: Do, 26. Feb. 2026 | 19:30
        if "202" in date_str and "|" in date_str:
            match = re.search(r'(\d+)\.\s*([A-Za-zä]+)\.?\s*(\d{4})\s*\|\s*(\d{1,2}):(\d{2})', date_str)
            if match:
                day, month_str, year, hour, minute = match.groups()
                month = months.get(month_str.strip('.'), 1)
                return datetime(int(year), month, int(day), int(hour), int(minute))

        # Theater Format: "Sa 24.01. 10.00 - 10.30 Uhr" or similar
        # Extract DD.MM.
        match_date = re.search(r'(\d{1,2})\.(\d{1,2})\.', date_str)
        if match_date:
            day = int(match_date.group(1))
            month = int(match_date.group(2))
            
            # Only search for time in the part AFTER the date to avoid matching 24.01 as 24:01
            remaining_str = date_str[match_date.end():]
            match_time = re.search(r'(\d{1,2})[:.](\d{2})', remaining_str)
            
            hour, minute = 0, 0
            if match_time:
                hour = int(match_time.group(1))
                minute = int(match_time.group(2))
            
            year = now.year
            # Logic for year rollover if needed
            if now.month == 12 and month < 3:
                year += 1
            
            return datetime(year, month, day, hour, minute)
            
    except Exception as e:
        logger.warning(f"Could not parse date: {date_str} ({e})")
        return None
    
    return None

def fetch_kkl_events():
    url = "https://www.kkl-luzern.ch/de/events"
    events = []
    logger.info(f"Fetching KKL events from {url}")
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Look for links containing /events/
        # Based on subagent finding: <a href="/events/..."> <article> ... <h2>Title</h2> ... <dt>Datum</dt><dd>...
        
        for link in soup.find_all('a', href=True):
            href = link['href']
            if not href.startswith('/events/') and not href.startswith('/de/events/'):
                continue
                
            article = link.find('article')
            if not article:
                continue
                
            title_tag = article.find('h2')
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            
            # Find date
            date_str = ""
            # Search for 'Datum' dt then get next dd
            for dt in article.find_all('dt'):
                if "Datum" in dt.get_text():
                    # The dd should be the next sibling or in the same grouping
                    # Subagent snippet: <div><dt>Datum</dt><dd>...</dd></div>
                    parent_div = dt.parent
                    dd = parent_div.find('dd')
                    if dd:
                        date_str = dd.get_text(strip=True)
                    break
            
            if not date_str:
                continue
                
            start_dt = parse_german_date(date_str)
            if start_dt:
                events.append({
                    "title": title,
                    "location": "KKL Luzern",
                    "start": start_dt.isoformat(),
                    "end": (start_dt + timedelta(hours=3)).isoformat(),
                    "description": f"KKL Event: {title}"
                })
                
    except Exception as e:
        logger.error(f"Error fetching KKL events: {e}")
        
    logger.info(f"Found {len(events)} KKL events.")
    return events

def fetch_theater_events():
    url = "https://www.luzernertheater.ch/spielplan/kalender"
    events = []
    logger.info(f"Fetching Theater events from {url}")
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Subagent snippet: .spielplan-item > .spielplan-item__date, .spielplan-item__link, .spielplan-item__stage
        items = soup.select('.spielplan-item')
        
        for item in items:
            title_tag = item.select_one('.spielplan-item__link')
            if not title_tag: continue
            # Clean up title (remove "Link to production" which is often hidden accessible text)
            title = title_tag.get_text(" ", strip=True).replace("Link to production", "").strip()
            # Collapse multiple spaces
            title = re.sub(r'\s+', ' ', title)
            
            date_tag = item.select_one('.spielplan-item__date')
            if not date_tag: continue
            date_text = date_tag.get_text(" ", strip=True) 
            
            start_dt = parse_german_date(date_text)
            
            # Location
            loc_tag = item.select_one('.spielplan-item__stage')
            location = loc_tag.get_text(strip=True) if loc_tag else "Luzerner Theater"
            
            if start_dt:
                events.append({
                    "title": title,
                    "location": location,
                    "start": start_dt.isoformat(),
                    "end": (start_dt + timedelta(hours=2)).isoformat(),
                    "description": f"Theater: {title} ({location})"
                })

    except Exception as e:
        logger.error(f"Error fetching Theater events: {e}")

    logger.info(f"Found {len(events)} Theater events.")
    return events

def update_events():
    logger.info("Starting event update...")
    
    # Load existing to preserve any manual ones if needed? 
    # Or just fetch fresh. User said "fetched... events that are past - could be taken to a other file"
    # This implies we process the LIST.
    
    all_events = []
    all_events.extend(fetch_kkl_events())
    all_events.extend(fetch_theater_events())
    
    # Sort by date
    all_events.sort(key=lambda x: x['start'])
    
    now = datetime.now()
    future_events = []
    past_events = []
    
    for evt in all_events:
        try:
            start = datetime.fromisoformat(evt['start'])
            # Keep events from today onwards (include today's earlier events just in case)
            if start.date() >= now.date():
                future_events.append(evt)
            else:
                past_events.append(evt)
        except ValueError:
            pass
            
    # Load Mappings
    mappings = {}
    if MAPPINGS_FILE.exists():
        try:
            with open(MAPPINGS_FILE, 'r', encoding='utf-8') as f:
                mappings = json.load(f).get("mappings", {})
        except Exception as e:
            logger.error(f"Error loading mappings: {e}")

    # Save to events.json (legacy/standard)
    logger.info(f"Saving {len(future_events)} future events to events.json")
    output_data = {
        "last_updated": now.isoformat(),
        "mappings": mappings,
        "events": future_events
    }
    with open(EVENTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=4, ensure_ascii=False)

    # Update groups.json with "current" events and mappings
    if GROUPS_FILE.exists():
        logger.info("Updating groups.json with current events and mappings")
        try:
            with open(GROUPS_FILE, 'r', encoding='utf-8') as f:
                groups_data = json.load(f)
            
            groups_data["event_mappings"] = mappings
            # Only include events for the next ~7 days in groups.json to avoid bloating
            next_week = now + timedelta(days=7)
            current_events = [e for e in future_events if datetime.fromisoformat(e['start']) < next_week]
            groups_data["current_events"] = current_events
            
            with open(GROUPS_FILE, 'w', encoding='utf-8') as f:
                json.dump(groups_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error updating groups.json: {e}")
        
    # Append Past Events to history
    if past_events:
        logger.info(f"Archiving {len(past_events)} past events to past_events.json")
        history = []
        if PAST_EVENTS_FILE.exists():
            try:
                with open(PAST_EVENTS_FILE, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if content:
                        history = json.loads(content)
            except Exception:
                pass
        
        # Merge and deduplicate based on start+title
        existing_sigs = {f"{e['start']}_{e['title']}" for e in history}
        for pe in past_events:
            sig = f"{pe['start']}_{pe['title']}"
            if sig not in existing_sigs:
                history.append(pe)
                existing_sigs.add(sig)
                
        with open(PAST_EVENTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=4, ensure_ascii=False)

    logger.info("Event update completed.")

if __name__ == "__main__":
    update_events()
