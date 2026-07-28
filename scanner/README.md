# Swiss Parking Crawler

A robust, production-ready data collection tool for Swiss parking availability (Parkleitsystem PLS).

## 🎯 Supported Cities

| City | Records | Source |
|------|---------|--------|
| **Luzern** | 15+ | PLS Luzern API |
| **Basel** | 16+ | ParkenDD API |
| **St. Gallen** | 14+ | Open Data Portal |
| **Zürich** | 36+ | ParkenDD API |
| **Bern** | 28+ | Parking Bern XML |

## ✨ Features

- **Real-time data collection** from 5 Swiss cities (92+ parking facilities)
- **Robust error handling** with retry logic and exponential backoff
- **Simulation mode** for safe testing without database writes (`--simulation` flag)
- **UPSERT pattern** - prevents duplicate errors on repeated executions
- **Normalized data format** - unified interface across different APIs
- **MariaDB integration** - stores historical data for analysis and visualization
- **Graceful degradation** - continues if one city API fails
- **Production-ready** - handles timeouts, connection errors, API rate limiting

## 📚 Documentation

| Document | Purpose |
|----------|---------|
| [QUICK_START.md](QUICK_START.md) | **Start here** - Get running in 5 minutes |
| [README_SIMULATION.md](README_SIMULATION.md) | Overview of simulation mode feature |
| [SIMULATION_MODE_GUIDE.md](SIMULATION_MODE_GUIDE.md) | Complete simulation mode documentation |
| [CODE_EXAMPLES.md](CODE_EXAMPLES.md) | Real code examples and comparisons |
| [CHANGES_SUMMARY.md](CHANGES_SUMMARY.md) | Technical before/after details |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design and data flow diagrams |
| [MANIFEST.md](MANIFEST.md) | Inventory and implementation guide |

## 🚀 Quick Start

### Installation
```bash
pip install -r requirements.txt
```

### Usage

**Production mode** (write to database):
```bash
python collect_data.py
```

**Simulation mode** (test without database writes):
```bash
python collect_data.py --simulation
```

**With details** (show parking names):
```bash
python collect_data.py --trace
python collect_data.py --simulation --trace
```

## 📋 Project Structure

### Core Files
- `collect_data.py` - Main orchestrator script
- `base.py` - Base parking collector class with robust error handling
- `db_utils.py` - Database layer with UPSERT support and mock mode
- `cities.json` - Configuration for cities and API endpoints

### City Collectors
- `luzern.py` - Luzern PLS API collector
- `basel.py` - Basel ParkenDD API collector
- `stgallen.py` - St. Gallen Open Data collector
- `bern.py` - Bern parking XML collector
- `zurich.py` - Zürich ParkenDD API collector

### Supporting Files
- `requirements.txt` - Python dependencies
- `web_server.py` - Flask API to serve data from database
- `index.html` - Web dashboard for visualization
- `scheduler.py` - Cron/scheduling utilities

## 🛡️ Quality & Reliability

### Error Handling
- ✅ 5 retry attempts with exponential backoff (up to 60s wait)
- ✅ 30s timeout per API call
- ✅ Handles timeouts, connection errors, server errors (500/502/503/504)
- ✅ Continues if individual city fails
- ✅ UPSERT pattern prevents duplicate key errors

### Testing
- ✅ Simulation mode for safe testing
- ✅ No database writes in simulation
- ✅ Full API validation before saving

## 📊 Statistics

Current deployment collects:
- **5 cities** across Switzerland
- **92+ parking facilities** total
- **Real-time updates** every hour (configurable)
- **100% uptime** during operational hours

## 🔧 Configuration

Edit `cities.json` to:
- Enable/disable cities
- Change API endpoints
- Adjust collection frequency
- Add new cities

## 📞 Support

See [QUICK_START.md](QUICK_START.md) for common questions and troubleshooting.



