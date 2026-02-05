# Digital Nomad Destination Ranker

A Streamlit-based dashboard for ranking travel destinations based on exchange rates, flight costs, and cost of living. Built for digital nomads departing from Taiwan (TPE).

## Features

- **Smart Scoring Algorithm**: Hybrid momentum/absolute scoring across 3 factors
  - Exchange rate momentum (30% weight)
  - Flight cost (20% weight) - 70% momentum, 30% absolute
  - Cost of living (50% weight) - 80% absolute, 20% momentum
- **26 Global Destinations**: Asia, Europe, Americas, Middle East, and Oceania
- **Data Quality Tracking**: Full provenance for every data point (live API, cache, or baseline)
- **Historical Trends**: 30-day trend charts with score breakdown
- **API Resilience**: Circuit breaker pattern with graceful degradation
- **Structured Logging**: JSON logs with metrics for monitoring

## Quick Start

### Prerequisites

- Python 3.10+
- pip

### Installation

```bash
# Clone the repository
cd travel-ranker

# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Configuration

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Add your API keys to `.env`:
   ```
   SERPAPI_KEY=your_serpapi_key
   EXCHANGERATE_API_KEY=your_exchangerate_api_key
   ```

3. Or run in demo mode with baseline data:
   ```
   USE_MOCK_DATA=true
   ```

### Run

```bash
streamlit run app.py
```

The app will be available at `http://localhost:8501`

## Configuration

| Variable | Description | Required |
|----------|-------------|----------|
| `SERPAPI_KEY` | SerpApi key for Google Flights search | No (uses baseline) |
| `EXCHANGERATE_API_KEY` | ExchangeRate-API key for currency rates | No (uses baseline) |
| `USE_MOCK_DATA` | Set to `true` to use baseline data only | No (default: false) |

## Scoring Algorithm

The destination score is calculated using a weighted combination:

```
Final Score = (Exchange Score * 0.30) + (Flight Score * 0.20) + (CoL Score * 0.50)
```

### Component Scoring

| Component | Formula | Weight |
|-----------|---------|--------|
| Exchange Rate | 100% momentum (current vs baseline) | 30% |
| Flight Cost | 70% momentum + 30% absolute position | 20% |
| Cost of Living | 80% absolute position + 20% momentum | 50% |

### Badges

- **EXCELLENT**: Score >= 85
- **HOT DEAL**: Overall change > 15%
- **CURRENCY WIN**: Exchange rate improvement > 20%
- **FLIGHT DEAL**: Flight cost decrease > 25%
- **DEFLATION**: Cost of living decrease > 15%

## Project Structure

```
travel-ranker/
├── app.py                    # Main Streamlit application
├── requirements.txt          # Python dependencies
├── .env.example              # Environment template
├── .gitignore
├── data/
│   ├── countries.json        # Destination configuration
│   ├── col_data.json         # Cost of living data
│   ├── baselines_v2.json     # Baseline values with provenance
│   └── cache/                # API response cache
├── utils/
│   ├── api_clients.py        # SerpApi & ExchangeRate clients
│   ├── cache.py              # Caching with TTL
│   ├── circuit_breaker.py    # Resilience patterns
│   ├── data_quality.py       # Provenance tracking
│   ├── database.py           # SQLite storage
│   ├── health.py             # Health monitoring
│   ├── logging_config.py     # Structured JSON logging
│   ├── scoring.py            # Scoring algorithm
│   ├── ui_helpers.py         # UI components
│   └── validators.py         # Pydantic validation
├── scripts/
│   └── backfill_history.py   # Generate historical data
├── tests/
│   └── test_scoring.py       # Unit tests
├── styles/
│   └── theme.css             # Custom styling
└── logs/                     # Application logs
```

## Running Tests

```bash
python3 -m pytest tests/test_scoring.py -v
```

## Generating Historical Data

To populate trend charts with historical data:

```bash
# Generate 365 days of synthetic historical data
python3 scripts/backfill_history.py --days 365

# Preview without inserting
python3 scripts/backfill_history.py --days 30 --dry-run
```

## API Limits & Costs

| API | Free Tier | Notes |
|-----|-----------|-------|
| SerpApi | 100 searches/month | Google Flights search |
| ExchangeRate-API | 1,500 calls/month | Currency conversion |

The app uses aggressive caching (24h for flights, 6h for exchange rates) and falls back to baseline data when APIs are unavailable.

## License

MIT License
