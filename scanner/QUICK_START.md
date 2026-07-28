# Quick Start - Simulation Mode

## 1️⃣ Installation

Replace three files in your `scanner/` directory:
```bash
scanner/db_utils.py       → db_utils_refactored.py
scanner/base.py           → base_refactored.py
scanner/collect_data.py   → collect_data_refactored.py
```

No dependencies added. No breaking changes.

---

## 2️⃣ Basic Usage

### ✅ Test Mode (No Database Writes)
```bash
python collect_data.py --simulation
```

### ✅ Production Mode (Writes to Database)
```bash
python collect_data.py
```

---

## 3️⃣ Common Commands

| Command | Purpose |
|---------|---------|
| `python collect_data.py` | Normal collection, writes to DB |
| `python collect_data.py --simulation` | Simulation mode, dry-run |
| `python collect_data.py --dry-run` | Same as `--simulation` |
| `python collect_data.py --simulation --trace` | Show parking names in simulation |
| `python collect_data.py --trace` | Show parking names in production |

---

## 4️⃣ Docker Usage

### Build (no changes needed)
```bash
docker build -t parking-crawler .
```

### Run in Simulation Mode
```bash
docker run parking-crawler python collect_data.py --simulation
```

### Run in Production Mode
```bash
docker run parking-crawler python collect_data.py
```

---

## 5️⃣ For Developers

### Adding Simulation to a New Collector

When you create a new collector, it automatically inherits simulation support:

```python
from base import BaseParkingCollector

class MyNewCollector(BaseParkingCollector):
    def normalize_data(self, raw_data):
        # Your normalization logic
        return {...}

# Simulation mode is automatic - nothing to do!
# The save_data() method already handles it
```

### Testing Your Collector

```bash
# Test without touching database
python collect_data.py --simulation
# ✅ Check API connectivity
# ✅ Check data normalization
# ✅ Check log output
# ✅ No database changes!
```

### Debugging

Enable tracing to see which parking places are processed:
```bash
python collect_data.py --simulation --trace
```

Output will show:
```
[TIME] City: Data saved (SIMULATION MODE) (Inserted: 25, Duplicates: 0, Failed: 0)
  └─ Inserted: Parking A, Parking B, Parking C, ...
```

---

## 6️⃣ Scheduling

### Cron - Test Run (daily)
```bash
0 3 * * * cd /home/parking && python collect_data.py --simulation >> /var/log/parking-test.log 2>&1
```

### Cron - Production Run (every hour)
```bash
0 * * * * cd /home/parking && python collect_data.py >> /var/log/parking-prod.log 2>&1
```

### SystemD Service (Production)
```ini
[Unit]
Description=Parking Data Collector
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/parking
ExecStart=/usr/bin/python3 collect_data.py
Restart=on-failure
User=parking

[Install]
WantedBy=multi-user.target
```

---

## 7️⃣ Troubleshooting

### Issue: "No database writes even without --simulation"
**Solution:** Check that you're not passing `--simulation` flag
```bash
# ❌ Writes nothing
python collect_data.py --simulation

# ✅ Writes to database
python collect_data.py
```

### Issue: "Simulation mode is slow"
**Expected behavior** - Simulation mode is actually faster than production. If it seems slow, the issue is API latency (network calls), not the collector.

### Issue: "Simulation says 'SIMULATION MODE' but I didn't use --simulation"
**Solution:** Check your cron job or scheduler. Make sure the command doesn't include `--simulation`.

### Issue: "Schema mismatch between simulation and real database"
**Not possible** - Simulation mode doesn't touch the database at all. If you get schema errors in production mode, the database configuration is the issue, not the simulation mode.

---

## 8️⃣ Verification Checklist

After integration, verify:

- [ ] `python collect_data.py --simulation` runs without errors
- [ ] Output shows "(SIMULATION MODE)" in log messages
- [ ] No new database records appear after simulation run
- [ ] `python collect_data.py` (without flag) still writes to database
- [ ] `--trace` flag works with both modes
- [ ] Database logs appear only in production mode
- [ ] "⚠️ SIMULATION MODE" warning appears at the end of simulation runs

---

## 9️⃣ API Reference

### BaseParkingCollector Constructor
```python
BaseParkingCollector(
    city_id="luzern",              # Required
    city_name="Luzern",             # Required
    api_url="https://...",          # Required
    simulation_mode=False           # Optional, defaults to False
)
```

### get_connection Function
```python
from db_utils import get_connection

# Production mode
conn = get_connection()

# Simulation mode
conn = get_connection(simulation_mode=True)
```

---

## 🔟 Real-World Example

### Test a new collector before production:
```bash
# Step 1: Add new city to cities.json
# Step 2: Create collector in scanner/mynewcity.py
# Step 3: Test it safely
python collect_data.py --simulation --trace

# Step 4: Check output for:
#   ✅ Correct number of parking records
#   ✅ Correct city name and parking names
#   ✅ Correct free/total numbers
#   ✅ No database errors (even though DB isn't written)

# Step 5: Run production
python collect_data.py
# ✅ Now data is written to database
```

---

## Questions?

**"Will this break my existing setup?"**
No. All changes are backward compatible. If you don't use `--simulation`, behavior is identical to before.

**"Can I use simulation mode in production?"**
Yes, but it's pointless - the whole point is to safely test without production data changes. For production, omit the flag.

**"Does simulation mode slow things down?"**
Actually, it's faster because there's no database I/O. If you need to test API connectivity, use simulation mode - it's perfect for that.

**"Can I see what queries would be executed?"**
The `MockCursor.executed_queries` list tracks all queries. You could add logging to see them:
```python
# In db_utils.py MockCursor.execute():
print(f"[SIMULATION] Would execute: {query}")
```

**"What if simulation mode finds an error?"**
Good! That's the point - find bugs in the safe test environment, not in production. The error will be logged and you can fix it before running production mode.
