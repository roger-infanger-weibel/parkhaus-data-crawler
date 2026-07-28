# Simulation Mode - Implementation Guide

## Overview

The refactored code adds **simulation mode** (also called "dry-run mode") to the parking data crawler. This allows you to:

- ✅ Test the entire data collection pipeline
- ✅ Fetch data from all city APIs
- ✅ Process and normalize the data
- ✅ Verify the collection works correctly
- ❌ WITHOUT writing any data to the database

## What Changed

### 1. **db_utils.py**

**New Classes:**
- `MockCursor` - A mock database cursor that records queries instead of executing them
- `MockConnection` - A mock database connection that returns the mock cursor

**Modified Function:**
- `get_connection(simulation_mode=False)` - Now accepts a `simulation_mode` parameter
  - When `True`: Returns a `MockConnection` that doesn't write to the database
  - When `False`: Returns a real database connection (original behavior)

**Example:**
```python
# Real database connection
conn = get_connection(simulation_mode=False)

# Simulation mode - no database writes
conn = get_connection(simulation_mode=True)
```

### 2. **base.py**

**Constructor Change:**
```python
def __init__(self, city_id, city_name, api_url, simulation_mode=False):
    # ... existing code ...
    self.simulation_mode = simulation_mode
```

**Modified save_data() Method:**
- Now passes `simulation_mode` to `get_connection()`
- Adds "(SIMULATION MODE)" indicator to log messages
- Returns stats with `'simulation_mode': True/False` flag

**Example:**
```python
# Simulation mode enabled
collector = LuzernCollector(
    city_id="luzern",
    city_name="Luzern",
    api_url="https://api.example.com",
    simulation_mode=True
)
```

### 3. **collect_data.py**

**New Command-line Arguments:**
```bash
--simulation   or   --dry-run
```

Enables simulation mode for the entire collection run.

**Modified Functions:**
- `create_collector()` - Accepts and passes `simulation_mode` parameter
- `collect_city_data()` - Accepts and passes `simulation_mode` parameter
- `collect_all_cities()` - Accepts and passes `simulation_mode` parameter
- `main()` - Parses `--simulation`/`--dry-run` flags and uses them throughout

**Behavior:**
- When `--simulation` is used, database logging is also skipped
- Clear warning message is printed at the end: "⚠️  SIMULATION MODE: No data was written to the database"

## Usage

### Run in Normal Mode (Write to Database)
```bash
python collect_data.py
```

### Run in Simulation Mode (No Database Writes)
```bash
python collect_data.py --simulation
```

Or:
```bash
python collect_data.py --dry-run
```

### With Additional Flags

```bash
# Simulation mode + show inserted parking names
python collect_data.py --simulation --trace
```

## Example Output (Simulation Mode)

```
Job started
Swiss Parking Monitor - Starting at 2026-07-28 10:30:45.123456 [SIMULATION MODE]

============================================================
Collecting data for: Luzern
============================================================
[2026-07-28 10:30:45.234567] Luzern: Fetching data...
[2026-07-28 10:30:46.345678] Luzern: Normalizing data...
[2026-07-28 10:30:46.456789] Luzern: Saving data...
[2026-07-28 10:30:46.567890] Luzern: Data saved (SIMULATION MODE) (Inserted: 25, Duplicates: 0, Failed: 0)

...

================================================================================
Collection Summary:
================================================================================
City            Status     Inserted   Duplicates   Failed     Latest Data
--------------------------------------------------------------------------------
luzern          SUCCESS    25         0            0          2026-07-28 10:30:46
basel           SUCCESS    18         0            0          2026-07-28 10:30:47
...

⚠️  SIMULATION MODE: No data was written to the database
Job finished
```

## How It Works

### Without Simulation Mode (Original)
```
1. Fetch API data
   ↓
2. Normalize data
   ↓
3. Connect to database
   ↓
4. Insert records
   ↓
5. Commit transaction
   ↓
6. Log to database
```

### With Simulation Mode
```
1. Fetch API data
   ↓
2. Normalize data
   ↓
3. Create MOCK connection (no actual DB connection)
   ↓
4. Record queries to mock cursor (don't execute)
   ↓
5. Mock commit (no-op)
   ↓
6. Skip database logging
```

## When to Use Simulation Mode

✅ **Use simulation mode when:**
- Testing the code in development
- Verifying API connectivity works
- Checking data normalization logic
- Running scheduled tests without side effects
- Debugging collection issues
- Onboarding new city collectors
- Testing in CI/CD pipelines

❌ **Don't use simulation mode when:**
- You want to actually store data
- Running production data collection

## Integration Notes

### For Docker
Add to your docker command:
```bash
docker run your-image python collect_data.py --simulation
```

### For Scheduled Jobs
Update your cron job or scheduler:
```bash
# Production run
0 * * * * cd /path/to/scanner && python collect_data.py

# Simulation test run
*/15 * * * * cd /path/to/scanner && python collect_data.py --simulation
```

## Migration Steps

To integrate these changes into your existing repository:

1. **Backup your current files:**
   ```bash
   cp scanner/db_utils.py scanner/db_utils.py.backup
   cp scanner/base.py scanner/base.py.backup
   cp scanner/collect_data.py scanner/collect_data.py.backup
   ```

2. **Replace the three main files:**
   - `scanner/db_utils.py` → Use `db_utils_refactored.py`
   - `scanner/base.py` → Use `base_refactored.py`
   - `scanner/collect_data.py` → Use `collect_data_refactored.py`

3. **No changes needed to:**
   - City-specific collectors (luzern.py, basel.py, etc.)
   - Configuration files (cities.json)
   - Database schema

4. **Test the changes:**
   ```bash
   # Test simulation mode
   python collect_data.py --simulation
   
   # Verify normal mode still works
   python collect_data.py
   ```

## Key Benefits

1. **Safe Testing** - Test the entire pipeline without touching production data
2. **Backwards Compatible** - Existing code works without changes
3. **Minimal Refactoring** - Only three files modified
4. **Performance** - Simulation mode is actually faster (no DB I/O)
5. **Clear Feedback** - Log messages clearly indicate simulation mode
6. **Easy Integration** - Works with existing Docker, cron, and scheduler setups
