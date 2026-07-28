# Simulation Mode - Changes Summary

## File: db_utils.py

### Added Classes

#### MockCursor
```python
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
```

#### MockConnection
```python
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
```

### Modified Function: get_connection()

**Before:**
```python
def get_connection():
    """Establish a connection to the MariaDB database."""
    config = load_db_config()
    try:
        connection = mysql.connector.connect(...)
        if connection.is_connected():
            return connection
    except Error as e:
        logging.error(f"Error connecting to MariaDB: {e}")
        raise e
```

**After:**
```python
def get_connection(simulation_mode=False):
    """
    Establish a connection to the MariaDB database.
    
    Args:
        simulation_mode (bool): If True, return a mock connection that doesn't write.
    """
    if simulation_mode:
        logging.info("Running in simulation mode - database writes disabled")
        return MockConnection()
    
    # ... rest of original code ...
```

**Key Change:** Single parameter addition with conditional return

---

## File: base.py

### Modified Constructor

**Before:**
```python
def __init__(self, city_id, city_name, api_url):
    self.city_id = city_id
    self.city_name = city_name
    self.api_url = api_url
```

**After:**
```python
def __init__(self, city_id, city_name, api_url, simulation_mode=False):
    self.city_id = city_id
    self.city_name = city_name
    self.api_url = api_url
    self.simulation_mode = simulation_mode
```

### Modified save_data() - Key Changes

**Change 1: Database Connection**
```python
# Before
conn = get_connection()

# After
conn = get_connection(simulation_mode=self.simulation_mode)
```

**Change 2: Log Message**
```python
# Before
print(f"[{now}] {self.city_name}: Data saved (Inserted: {success_count}, ...)")

# After
mode_info = " (SIMULATION MODE)" if self.simulation_mode else ""
print(f"[{now}] {self.city_name}: Data saved{mode_info} (Inserted: {success_count}, ...)")
```

**Change 3: Return Value**
```python
# Before - returns stats without simulation flag
return {
    'success': True,
    'inserted': success_count,
    'duplicates': duplicate_count,
    'failed': fail_count,
    'error': None,
    'latest_data_ts': fetch_ts,
    'inserted_names': inserted_names
}

# After - includes simulation_mode flag
return {
    'success': True,
    'inserted': success_count,
    'duplicates': duplicate_count,
    'failed': fail_count,
    'error': None,
    'latest_data_ts': fetch_ts,
    'inserted_names': inserted_names,
    'simulation_mode': self.simulation_mode  # NEW
}
```

### Modified collect() Method

Returns now include `'simulation_mode': self.simulation_mode` in both success and error cases.

---

## File: collect_data.py

### Added Import
```python
import gc  # (was imported implicitly - now explicit for clarity)
```

### Modified Argument Parser

**Added:**
```python
parser.add_argument(
    "--simulation",
    "--dry-run",
    action="store_true",
    dest="simulation",
    help="Run in simulation mode - fetch and process data without writing to database"
)
```

### Modified create_collector() Function

**Before:**
```python
def create_collector(city_id, city_config):
    collector_class_name = city_config.get("collector")
    collector_class = COLLECTOR_MAP.get(collector_class_name)
    
    if not collector_class:
        print(f"Warning: Collector '{collector_class_name}' not found for {city_id}")
        return None
    
    return collector_class(
        city_id=city_id,
        city_name=city_config.get("name", city_id),
        api_url=city_config.get("api_url")
    )
```

**After:**
```python
def create_collector(city_id, city_config, simulation_mode=False):
    # ... same logic ...
    return collector_class(
        city_id=city_id,
        city_name=city_config.get("name", city_id),
        api_url=city_config.get("api_url"),
        simulation_mode=simulation_mode  # NEW
    )
```

### Modified collect_city_data() Function

**Before:**
```python
def collect_city_data(city_id, config):
    # ... validation ...
    collector = create_collector(city_id, city_config)
    return collector.collect()
```

**After:**
```python
def collect_city_data(city_id, config, simulation_mode=False):
    # ... validation, with NEW return field ...
    return {'success': False, ..., 'simulation_mode': simulation_mode}
    # ...
    collector = create_collector(city_id, city_config, simulation_mode=simulation_mode)
    return collector.collect()
```

### Modified collect_all_cities() Function

**Added parameter:** `simulation_mode=False`

```python
def collect_all_cities(config, simulation_mode=False):
    # ...
    stats = collect_city_data(city_id, config, simulation_mode=simulation_mode)
```

### Modified main() Function

**Change 1: Mode Detection**
```python
mode_label = "SIMULATION MODE" if args.simulation else "NORMAL MODE"
print(f"Swiss Parking Monitor - Starting at {datetime.now()} [{mode_label}]")
```

**Change 2: Pass Simulation Flag**
```python
# Before
results = collect_all_cities(config)

# After
results = collect_all_cities(config, simulation_mode=args.simulation)
```

**Change 3: Conditional Database Logging**
```python
# Before - always tried to connect
conn = None
cursor = None
try:
    conn = db_utils.get_connection()
    # ...

# After - only connect if not in simulation mode
if not args.simulation:
    try:
        conn = db_utils.get_connection(simulation_mode=False)
```

**Change 4: Final Warning Message**
```python
if args.simulation:
    print("\n⚠️  SIMULATION MODE: No data was written to the database")
```

---

## Backward Compatibility

✅ **All changes are backward compatible**

| File | Changes | Impact |
|------|---------|--------|
| db_utils.py | Added optional parameter, new classes | None - parameter defaults to `False` |
| base.py | Added optional parameter, new instance var | None - parameter defaults to `False` |
| collect_data.py | Added optional parameter, new CLI flag | None - flag is optional |

**Calling without new parameters:**
```python
# These still work exactly as before
collector = LuzernCollector("luzern", "Luzern", "https://...")
result = collector.collect()

# And with the script
python collect_data.py  # No --simulation flag = normal mode
```

---

## Testing Checklist

- [ ] Test with `--simulation` flag
- [ ] Test without `--simulation` flag (normal mode)
- [ ] Test with `--simulation --trace` flags together
- [ ] Verify normal mode still writes to database
- [ ] Verify simulation mode does NOT write to database
- [ ] Check log output shows "(SIMULATION MODE)" when appropriate
- [ ] Verify warning message appears at end in simulation mode
- [ ] Test with single city: `python collect_data.py` + modify cities.json
- [ ] Test Docker execution with both modes

---

## Lines of Code Changed

- **db_utils.py**: +60 lines (2 new classes, 1 modified function)
- **base.py**: +15 lines (1 parameter, 1 instance var, log message, return field)
- **collect_data.py**: +25 lines (1 arg parser addition, 5 function parameter additions, 1 logging condition)

**Total:** ~100 lines added across 3 files, 0 lines removed (full backward compatibility)
