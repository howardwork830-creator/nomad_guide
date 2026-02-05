# Digital Nomad Destination Ranker

A Streamlit-based dashboard for ranking travel destinations based on exchange rates, flight costs, cost of living, safety, visa requirements, and travel accessibility. Built for digital nomads departing from Taiwan (TPE).

## Features

- **Smart Scoring Algorithm**: Hybrid momentum/absolute scoring across 6 factors
  - Exchange rate momentum (20% weight)
  - Flight cost (15% weight) - 70% momentum, 30% absolute
  - Cost of living (35% weight) - 80% absolute, 20% momentum
  - Safety index (15% weight) - composite GPI + Numbeo score
  - Visa ease (10% weight) - Taiwan passport requirements
  - Travel accessibility (5% weight) - flight connectivity from TPE
- **52 Global Destinations**: Asia, Europe, Americas, Middle East, Africa, and Oceania
- **Comparison Mode**: Side-by-side comparison with radar charts for 2-3 destinations
- **Interactive Map View**: Multiple visualization modes (choropleth, bubble, flight routes)
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
Final Score = (Exchange * 0.20) + (Flight * 0.15) + (CoL * 0.35) + (Safety * 0.15) + (Visa * 0.10) + (Access * 0.05)
```

### Component Scoring

| Component | Formula | Weight |
|-----------|---------|--------|
| Exchange Rate | 100% momentum (current vs baseline) | 20% |
| Flight Cost | 70% momentum + 30% absolute position | 15% |
| Cost of Living | 80% absolute position + 20% momentum | 35% |
| Safety Index | Composite GPI + Numbeo safety score | 15% |
| Visa Ease | Taiwan passport visa requirements | 10% |
| Travel Access | Flight connectivity from TPE | 5% |

### Visa Scoring

| Visa Type | Score |
|-----------|-------|
| Visa-free | 100 |
| Visa-on-arrival | 80 |
| E-visa | 60 |
| Visa required | 20 |

### Badges

**Performance Badges:**
- **EXCELLENT**: Score >= 85
- **HOT DEAL**: Overall change > 15%
- **CURRENCY WIN**: Exchange rate improvement > 20%
- **FLIGHT DEAL**: Flight cost decrease > 25%
- **DEFLATION**: Cost of living decrease > 15%

**New Indicator Badges:**
- **SAFE HAVEN**: Safety index >= 85
- **EASY ENTRY**: Visa-free entry for Taiwan passport
- **NOMAD VISA**: Country offers digital nomad visa program
- **WELL CONNECTED**: Travel accessibility score >= 80

## Destinations

52 destinations across 8 regions:

| Region | Countries |
|--------|-----------|
| East Asia | Japan, South Korea, Hong Kong, China |
| Southeast Asia | Thailand, Vietnam, Malaysia, Indonesia, Philippines, Singapore, Cambodia, Laos |
| South Asia | India, Sri Lanka, Nepal |
| Europe | UK, Germany, France, Spain, Portugal, Netherlands, Georgia, Estonia, Croatia, Czech Republic, Poland, Hungary, Greece, Albania, Romania, Bulgaria, Iceland, Switzerland |
| Americas | USA, Mexico, Colombia, Argentina, Brazil, Peru, Costa Rica, Chile, Panama, Canada |
| Middle East | UAE, Turkey, Israel |
| Africa | Morocco, South Africa, Egypt, Kenya |
| Oceania | Australia, New Zealand |

## Project Structure

```
travel-ranker/
├── app.py                    # Main Streamlit application
├── requirements.txt          # Python dependencies
├── .env.example              # Environment template
├── .gitignore
├── .streamlit/
│   └── config.toml           # Streamlit deployment configuration
├── data/
│   ├── countries.json        # Destination configuration (52 countries)
│   ├── col_data.json         # Cost of living data
│   ├── baselines_v2.json     # Baseline values with provenance
│   ├── safety_index.json     # GPI + Numbeo safety scores
│   ├── visa_requirements.json # Taiwan passport visa requirements
│   ├── travel_access.json    # Flight accessibility from TPE
│   └── cache/                # API response cache
├── utils/
│   ├── api_clients.py        # SerpApi & ExchangeRate clients
│   ├── cache.py              # Caching with TTL
│   ├── circuit_breaker.py    # Resilience patterns
│   ├── comparison.py         # Destination comparison module
│   ├── data_quality.py       # Provenance tracking
│   ├── database.py           # SQLite storage
│   ├── health.py             # Health monitoring
│   ├── logging_config.py     # Structured JSON logging
│   ├── map_view.py           # Interactive map visualization
│   ├── scoring.py            # Scoring algorithm
│   ├── ui_helpers.py         # UI components
│   └── validators.py         # Pydantic validation
├── scripts/
│   └── backfill_history.py   # Generate historical data
├── tests/
│   ├── test_scoring.py       # Scoring algorithm tests
│   ├── test_new_indicators.py # Safety, visa, access tests
│   ├── test_comparison.py    # Comparison module tests
│   └── test_map_view.py      # Map visualization tests
├── styles/
│   └── theme.css             # Custom styling
└── logs/                     # Application logs
```

## Running Tests

```bash
# Run all tests
python3 -m pytest tests/ -v

# Run specific test file
python3 -m pytest tests/test_scoring.py -v

# Run with coverage
python3 -m pytest tests/ -v --cov=utils --cov-report=term-missing
```

## Generating Historical Data

To populate trend charts with historical data:

```bash
# Generate 365 days of synthetic historical data
python3 scripts/backfill_history.py --days 365

# Preview without inserting
python3 scripts/backfill_history.py --days 30 --dry-run
```

## Data Sources

| Data Type | Source |
|-----------|--------|
| Exchange Rates | ExchangeRate-API |
| Flight Costs | Google Flights via SerpApi |
| Cost of Living | Numbeo |
| Safety Index | Global Peace Index + Numbeo Safety |
| Visa Requirements | Taiwan MOFA / VisaIndex |
| Travel Accessibility | Flight schedules from TPE |

## API Limits & Costs

| API | Free Tier | Notes |
|-----|-----------|-------|
| SerpApi | 100 searches/month | Google Flights search |
| ExchangeRate-API | 1,500 calls/month | Currency conversion |

The app uses aggressive caching (24h for flights, 6h for exchange rates) and falls back to baseline data when APIs are unavailable.

## Deployment

The app is configured for Streamlit Cloud deployment. See `.streamlit/config.toml` for configuration.

## License

MIT License
