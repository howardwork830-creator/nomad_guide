# Travel Cost Calculation System - Project Documentation

**Project Type:** Digital Nomad Destination Ranking System  
**Tech Stack:** Python (Streamlit), Free APIs  
**Scoring Model:** Hybrid momentum-based composite (0-100 scale)  
**Last Updated:** 3 February 2026

---

## Executive Summary

This system calculates a **0-100 score** for all countries globally, ranking them as travel destinations from Taiwan (or any manually set origin). The scoring uses a **hybrid momentum approach** that combines:

### Weighting Structure
- **20%** - Flight Cost (cheapest one-way)
- **30%** - Exchange Rate (TWD strength)
- **50%** - Cost of Living (accommodation > food > tourism)

### Scoring Philosophy: "Better to Visit NOW"
Each component combines **absolute affordability** with **trending momentum** against historical baselines:

| Component | Absolute Weight | Momentum Weight | Logic |
|-----------|----------------|-----------------|-------|
| **Exchange Rate** | 0% | 100% | Pure momentum - captures currency opportunities (e.g., Japan yen weakening) |
| **Flight Cost** | 30% | 70% | Mostly momentum - seasonal deals matter, but some flights always cheap |
| **Cost of Living** | 80% | 20% | Mostly absolute - inherent affordability dominant, inflation trends secondary |

**Example:** Japan's yen weakens 38% → Exchange score jumps from 35/100 to 88/100 → Overall score increases 16 points → "HOT DEAL" badge appears

**Target Use Case:** Short-term digital nomad stays with real-time opportunity detection.

---

## System Architecture

### Logical Data Flow

```
┌─────────────────────┐
│  User Input Layer   │
│  - Origin: Taiwan   │
│  - Date Range       │
└──────────┬──────────┘
           │
           ▼
┌──────────────────────────────────────────┐
│     Data Aggregation Layer               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐│
│  │Flight API│ │Exchange  │ │Cost      ││
│  │          │ │Rate API  │ │Living API││
│  └────┬─────┘ └────┬─────┘ └────┬─────┘│
└───────┼────────────┼──────────────┼──────┘
        │            │              │
        ▼            ▼              ▼
┌──────────────────────────────────────────┐
│   Historical Baseline Comparison Engine  │
│  • Load 3-year average baselines         │
│  • Calculate momentum (% change)         │
│  • Detect trending opportunities         │
└──────────┬───────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────┐
│    Hybrid Scoring Engine                 │
│  • Absolute scores (min-max 0-100)       │
│  • Momentum scores (% change → 0-100)    │
│  • Weighted blend per component          │
│  • Final composite: 0.2F + 0.3E + 0.5C   │
└──────────┬───────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────┐
│      Streamlit UI Layer                  │
│  • Trend arrows (↑↓→ Unicode arrows)    │
│  • Hot deal badges (styled pills)        │
│  • Score breakdown + momentum %          │
│  • 30-day score history chart            │
└──────────────────────────────────────────┘
```

---

## Component 1: Flight Cost (20% Weight)

### API Options Analysis

| API | Free Tier | Coverage | Rate Limit | Status |
|-----|-----------|----------|------------|--------|
| **Amadeus Flight Offers** | ✅ 2,000/month | Global | ~67/day | **RECOMMENDED** |
| FlightAPI | ❌ 50 calls only | 700+ airlines | Trial only | Backup |
| Skyscanner (RapidAPI) | ✅ Limited | Global | 500/month | Alternative |

### Recommended: Amadeus Flight Offers API

**Endpoint:**  
```
GET https://api.amadeus.com/v2/shopping/flight-offers
```

**Key Parameters:**
```python
{
    "originLocationCode": "TPE",  # Taipei
    "destinationLocationCode": "BKK",  # Bangkok (example)
    "departureDate": "2026-03-15",
    "adults": 1,
    "currencyCode": "TWD",
    "max": 1  # Only cheapest flight
}
```

**Response Structure:**
```json
{
  "data": [{
    "price": {
      "total": "5240.00",
      "currency": "TWD"
    },
    "itineraries": [{
      "duration": "PT3H45M"
    }]
  }]
}
```

**Implementation Strategy:**
- **Batch Processing:** Query top 100 countries (2 groups of 50, alternating days)
- **Caching:** Store results for 48 hours (each country refreshes every 2 days)
- **Fallback:** If API fails for specific route → use average regional flight cost
- **One-Way Logic:** Always query single direction from origin

**API Usage Optimisation:**
```
100 countries ÷ 2 = 50 countries/day
50 calls/day × 30 days = 1,500 calls/month (within 2,000 limit ✅)
```

**Sign-Up:** https://developers.amadeus.com/  
**Rate Limit Management:** Rotate country groups to stay within daily limits

---

## Component 2: Exchange Rate (30% Weight)

### API Options Analysis

| API | Free Tier | TWD Support | Update Freq | Status |
|-----|-----------|-------------|-------------|--------|
| **ExchangeRate-API** | ✅ 1,500/month | ✅ TWD | Hourly | **RECOMMENDED** |
| QCurrency | ✅ Unlimited | ✅ TWD-specific | 15min | Taiwan-focused |
| FreeCurrencyAPI | ✅ Unlimited | ✅ TWD | 60sec | Alternative |

### Recommended: ExchangeRate-API

**Endpoint:**
```
GET https://v6.exchangerate-api.com/v6/YOUR_KEY/latest/TWD
```

**Response Structure:**
```json
{
  "result": "success",
  "base_code": "TWD",
  "conversion_rates": {
    "USD": 0.032,
    "EUR": 0.029,
    "THB": 1.09,
    "VND": 803.45,
    "JPY": 5.8
  }
}
```

**Momentum-Based Scoring Logic:**

**Pure Momentum (100%)** - No absolute component for exchange rates

1. **Calculate Percentage Change:**
```python
baseline_rate = baselines['JPY']  # e.g., 4.2 JPY per TWD
current_rate = country_data['exchange_rate']  # e.g., 5.8 JPY

rate_change_pct = ((current_rate - baseline_rate) / baseline_rate) * 100
# Example: ((5.8 - 4.2) / 4.2) * 100 = +38.1%
```

2. **Normalize to 0-100 Score:**
```python
# Assumption: ±50% is extreme range
# -50% = 0/100 (currency strengthened massively, bad)
# 0% = 50/100 (no change, neutral)
# +50% = 100/100 (currency weakened massively, excellent)

exchange_score = np.clip((rate_change_pct + 50) * 2, 0, 100)

# Examples:
# Japan (+38%) → (38 + 50) × 2 = 88/100  (Hot!)
# Thailand (+3.8%) → (3.8 + 50) × 2 = 61/100  (Stable)
# Switzerland (0%) → (0 + 50) × 2 = 50/100  (Stable)
# UK (-15%) → (-15 + 50) × 2 = 35/100  (Down)
```

3. **Trend Classification:**
```python
if rate_change_pct > 15:
    trend = "STRONG GAIN"
elif rate_change_pct > 5:
    trend = "Gaining"
elif rate_change_pct > -5:
    trend = "Stable"
elif rate_change_pct > -15:
    trend = "Weakening"
else:
    trend = "STRONG LOSS"
```

**Alternative Option for Taiwan Context:**  
**QCurrency API** (https://github.com/qcl/QCurrency)  
- Specifically designed for TWD exchange rates
- Free, unlimited usage
- Data from Bank of Taiwan

**Sign-Up:** https://www.exchangerate-api.com/  
**Rate Limit:** 1,500 requests/month  
**Refresh Strategy:** Every 4 hours (6x/day = 180 calls/month, well within limit)

---

## Component 3: Cost of Living (50% Weight)

### API Options Analysis

| API | Free Tier | Cities | Categories | Status |
|-----|-----------|--------|------------|--------|
| **Cities Cost of Living API** | ✅ 50 calls/trial | 8,000+ | Detailed breakdown | **RECOMMENDED** |
| Col_Api (GitHub) | ✅ Self-hosted | 265 cities | Property/Food/Transport | Backup |
| Numbeo API | ❌ $260/month | Global | Most comprehensive | NOT VIABLE |

### Recommended: Cities Cost of Living API (via Zyla Labs)

**Endpoint:**
```
GET https://zylalabs.com/api/cities-cost-of-living-and-average-prices-api/prices
```

**Request:**
```python
{
  "city_name": "Bangkok",
  "country_name": "Thailand"
}
```

**Response Structure:**
```json
{
  "prices": {
    "Apartment (1 bedroom) in City Centre": "15,000 THB",
    "Meal, Inexpensive Restaurant": "120 THB",
    "Cappuccino": "85 THB",
    "One-way Ticket (Local Transport)": "35 THB",
    "Monthly Pass (Regular Price)": "1,400 THB",
    "Basic Utilities": "2,500 THB"
  }
}
```

### Cost of Living Calculation Logic

**Sub-Components with Weights:**
1. **Accommodation (60%)** - Apartment rent (1-bedroom city centre)
2. **Food (30%)** - Average of:
   - Inexpensive restaurant meal × 20 (daily lunch)
   - Groceries (milk, bread, eggs, chicken) × 30 (monthly)
3. **Tourism (10%)** - Average of:
   - Local transport monthly pass
   - Museum/attraction entry (× 4 visits/month)
   - Cappuccino/café × 15 (coworking café culture)

**Hybrid Scoring (80% Absolute, 20% Momentum):**

```python
# Step 1: Calculate monthly cost
monthly_cost = (
    accommodation * 0.60 +
    food_cost * 0.30 +
    tourism_cost * 0.10
)

# Step 2: Absolute score (lower cost = higher score)
col_min, col_max = 500, 4000  # USD monthly range
col_absolute = 100 - ((monthly_cost - col_min) / (col_max - col_min)) * 100

# Step 3: Momentum score (inflation/deflation trends)
baseline_col = baselines['monthly_col']  # e.g., $800
col_change_pct = ((baseline_col - monthly_cost) / baseline_col) * 100
# Note: Inverted - if cost increased, change is negative (bad)

col_momentum = np.clip((col_change_pct + 20) * 2.5, 0, 100)
# Assumption: ±20% is extreme inflation/deflation range

# Step 4: Weighted blend
col_score = col_absolute * 0.80 + col_momentum * 0.20
```

**Example Calculation:**
```
Bangkok TODAY:
- Accommodation: 15,000 THB (~$470)
- Food: 5,400 THB (~$170)
- Tourism: 3,475 THB (~$109)
- Total Monthly: $749 USD

Bangkok BASELINE (3-year avg): $800 USD

Absolute Score:
col_absolute = 100 - ((749 - 500) / (4000 - 500)) * 100 = 93/100

Momentum Score:
col_change = ((800 - 749) / 800) * 100 = +6.4% (deflation, good!)
col_momentum = (6.4 + 20) × 2.5 = 66/100

Final CoL Score:
col_score = 93 × 0.80 + 66 × 0.20 = 87.6/100
```

**Fallback Strategy:**  
If API limit exhausted, use **Col_Api** (self-hosted GitHub project):
- Clone: `https://github.com/jacobpalinski/Col_Api`
- Deploy on free tier Render/Railway
- Covers 265 major cities (sufficient for major destinations)

**Sign-Up:** https://zylalabs.com/  
**Rate Limit:** 50 API calls during 7-day trial  
**Strategy:** Query top 50 destinations once, cache for 30 days, then switch to self-hosted

---

## Composite Scoring Algorithm (Hybrid Momentum)

### Master Formula

```python
import numpy as np

def calculate_destination_score(country_data, baselines):
    """
    Hybrid momentum-aware scoring with TODAY as comparison baseline
    
    Parameters:
    -----------
    country_data : dict
        {
            'flight_cost': float,      # In TWD
            'exchange_rate': float,    # TWD to local currency
            'monthly_col': float       # In USD
        }
    
    baselines : dict
        {
            'flight_cost': float,      # 3-year average TWD
            'exchange_rate': float,    # 3-year average rate
            'monthly_col': float       # 3-year average USD
        }
    
    Returns:
    --------
    dict: {
        'score': float (0-100),
        'breakdown': dict,
        'trends': dict,
        'badges': list
    }
    """
    
    # ========================================
    # 1. EXCHANGE RATE (30% weight) - PURE MOMENTUM
    # ========================================
    rate_change_pct = (
        (country_data['exchange_rate'] - baselines['exchange_rate']) 
        / baselines['exchange_rate']
    ) * 100
    
    # Normalize: -50% to +50% → 0 to 100
    exchange_score = np.clip((rate_change_pct + 50) * 2, 0, 100)
    
    # Trend classification
    if rate_change_pct > 15:
        exchange_trend = "STRONG"
    elif rate_change_pct > 5:
        exchange_trend = "Up"
    elif rate_change_pct > -5:
        exchange_trend = "Stable"
    elif rate_change_pct > -15:
        exchange_trend = "Down"
    else:
        exchange_trend = "WEAK"
    
    # ========================================
    # 2. FLIGHT COST (20% weight) - HYBRID (70% momentum, 30% absolute)
    # ========================================
    
    # Momentum component (cheaper than baseline = good)
    flight_change_pct = (
        (baselines['flight_cost'] - country_data['flight_cost'])
        / baselines['flight_cost']
    ) * 100
    
    flight_momentum = np.clip((flight_change_pct + 30) * 1.67, 0, 100)
    # Assumption: ±30% is typical seasonal/demand variation
    
    # Absolute component (inherent cheapness)
    flight_min, flight_max = 2000, 50000  # TWD range
    flight_absolute = 100 - (
        (country_data['flight_cost'] - flight_min) / 
        (flight_max - flight_min) * 100
    )
    
    # Blend: 70% momentum, 30% absolute
    flight_score = flight_momentum * 0.70 + flight_absolute * 0.30
    
    # Trend classification
    if flight_change_pct > 20:
        flight_trend = "BARGAIN"
    elif flight_change_pct > 10:
        flight_trend = "Cheaper"
    elif flight_change_pct > -10:
        flight_trend = "Stable"
    elif flight_change_pct > -20:
        flight_trend = "Higher"
    else:
        flight_trend = "PEAK"
    
    # ========================================
    # 3. COST OF LIVING (50% weight) - HYBRID (80% absolute, 20% momentum)
    # ========================================
    
    # Absolute component (inherent affordability)
    col_min, col_max = 500, 4000  # USD monthly range
    col_absolute = 100 - (
        (country_data['monthly_col'] - col_min) / 
        (col_max - col_min) * 100
    )
    
    # Momentum component (inflation/deflation trends)
    col_change_pct = (
        (baselines['monthly_col'] - country_data['monthly_col'])
        / baselines['monthly_col']
    ) * 100
    
    col_momentum = np.clip((col_change_pct + 20) * 2.5, 0, 100)
    # Assumption: ±20% is extreme inflation/deflation
    
    # Blend: 80% absolute, 20% momentum
    col_score = col_absolute * 0.80 + col_momentum * 0.20
    
    # Trend classification
    if col_change_pct > 10:
        col_trend = "Deflating"
    elif col_change_pct > 3:
        col_trend = "Cheaper"
    elif col_change_pct > -3:
        col_trend = "Stable"
    elif col_change_pct > -10:
        col_trend = "Rising"
    else:
        col_trend = "Inflating"
    
    # ========================================
    # 4. WEIGHTED COMPOSITE
    # ========================================
    final_score = (
        flight_score * 0.20 +
        exchange_score * 0.30 +
        col_score * 0.50
    )
    
    # Calculate overall trend (weighted average of changes)
    overall_change = (
        flight_change_pct * 0.20 +
        rate_change_pct * 0.30 +
        col_change_pct * 0.50
    )
    
    # ========================================
    # 5. BADGE ASSIGNMENT
    # ========================================
    badges = []
    
    if final_score >= 85:
        badges.append("EXCELLENT")

    if overall_change > 15:
        badges.append("HOT DEAL")

    if rate_change_pct > 20:
        badges.append("CURRENCY WIN")

    if flight_change_pct > 25:
        badges.append("FLIGHT DEAL")

    if col_change_pct > 15:
        badges.append("DEFLATION")
    
    # ========================================
    # 6. RETURN STRUCTURED RESULT
    # ========================================
    return {
        'score': round(final_score, 1),
        'breakdown': {
            'exchange': round(exchange_score, 1),
            'flight': round(flight_score, 1),
            'col': round(col_score, 1)
        },
        'trends': {
            'exchange': {
                'change_pct': round(rate_change_pct, 1),
                'indicator': exchange_trend
            },
            'flight': {
                'change_pct': round(flight_change_pct, 1),
                'indicator': flight_trend
            },
            'col': {
                'change_pct': round(col_change_pct, 1),
                'indicator': col_trend
            },
            'overall': round(overall_change, 1)
        },
        'badges': badges
    }
```

### Score Interpretation Guide (Updated for Momentum)

| Score Range | Interpretation | Momentum Context |
|-------------|----------------|------------------|
| 85-100 | **Excellent Value** | Top deals TODAY - strong positive trends |
| 70-84 | **Good Value** | Solid opportunity - moderate positive trends |
| 55-69 | **Moderate** | Fair value - stable or mixed trends |
| 40-54 | **Expensive** | Not ideal timing - negative trends |
| 0-39 | **Very Expensive** | Poor timing - strong negative trends |

**Key Insight:** A country can move between categories week-to-week based on currency/flight trends!

---

## Baseline Data Management

### Historical Baseline Structure

**Purpose:** Provide stable comparison points for momentum calculation

```json
{
  "version": "1.0",
  "calculation_date": "2023-02-03",
  "methodology": "3-year rolling average (2023-2026)",
  "data_sources": {
    "exchange": "OANDA Historical",
    "flights": "Amadeus Historical API",
    "col": "Numbeo Archives"
  },
  "baselines": {
    "Japan": {
      "exchange_rate": 4.2,
      "flight_cost": 18500,
      "monthly_col": 2800,
      "currency": "JPY",
      "region": "East Asia"
    },
    "Thailand": {
      "exchange_rate": 1.05,
      "flight_cost": 4200,
      "monthly_col": 800,
      "currency": "THB",
      "region": "Southeast Asia"
    },
    "Switzerland": {
      "exchange_rate": 0.028,
      "flight_cost": 32000,
      "monthly_col": 3800,
      "currency": "CHF",
      "region": "Western Europe"
    }
  }
}
```

### Initial Baseline Generation Strategy

**Phase 1: MVP (Manual Research)**
1. Use OANDA historical data for 3-year average exchange rates
2. Estimate flight costs from:
   - Amadeus historical API (if available)
   - Manual sampling from flight search engines
   - Regional averages for missing data
3. Use Numbeo's archived data for CoL baselines

**Data Sources:**
- **Exchange Rates:** https://www.oanda.com/fx-for-business/historical-rates
- **Cost of Living:** Numbeo's "Quality of Life Index" archives (2023-2026)
- **Flights:** Manual sampling + regional estimates

**Timeline:** 2-3 days of research for top 100 countries

**Phase 2: Dynamic Evolution (Future)**
After 30 days of operation, switch to rolling averages:
```python
# Rolling 30-day baseline (self-updating)
baseline = df.last_30_days.mean()
```

---

## Data Management Strategy

### Country/City Mapping (Enhanced with Baselines)

**Challenge:** APIs use different identifiers + need baseline storage

**Solution:** Enhanced mapping database

```python
# countries.json (enhanced)
{
  "Thailand": {
    "airport_code": "BKK",
    "major_city": "Bangkok",
    "currency_code": "THB",
    "region": "Southeast Asia",
    "baselines": {
      "exchange_rate": 1.05,
      "flight_cost": 4200,
      "monthly_col": 800
    }
  },
  "Japan": {
    "airport_code": "NRT",
    "major_city": "Tokyo",
    "currency_code": "JPY",
    "region": "East Asia",
    "baselines": {
      "exchange_rate": 4.2,
      "flight_cost": 18500,
      "monthly_col": 2800
    }
  }
}
```

**Data Source for Generation:**  
- Airport codes: https://github.com/datasets/airport-codes (Open Data)
- Country-City mapping: https://github.com/datasets/country-codes (Open Data)
- Baselines: Manual research + OANDA/Numbeo archives

### Caching Architecture (Updated for Momentum Tracking)

**Purpose:** Reduce API calls + enable trend tracking

```python
import streamlit as st
from datetime import datetime, timedelta
import json
import sqlite3

# ========================================
# OPTION A: JSON Files (MVP)
# ========================================

@st.cache_data(ttl=172800)  # 48-hour cache (flights refresh every 2 days)
def fetch_flight_costs(origin, country_group):
    """
    Cached flight cost data
    country_group: 'A' or 'B' (alternating days for 100 countries)
    """
    cache_file = f"data/cache/flights_{country_group}_{datetime.now().date()}.json"
    if os.path.exists(cache_file):
        return json.load(open(cache_file))
    else:
        # Fetch from Amadeus API for 50 countries
        data = amadeus_client.fetch_flights(origin, country_group)
        json.dump(data, open(cache_file, 'w'))
        return data

@st.cache_data(ttl=14400)  # 4-hour cache (exchange rates)
def fetch_exchange_rates():
    """Cached exchange rates"""
    cache_file = f"data/cache/exchange_{datetime.now().strftime('%Y%m%d_%H')}.json"
    if os.path.exists(cache_file):
        return json.load(open(cache_file))
    else:
        data = exchange_api.fetch_rates('TWD')
        json.dump(data, open(cache_file, 'w'))
        return data

@st.cache_data(ttl=2592000)  # 30-day cache (CoL stable)
def fetch_cost_of_living():
    """Cached CoL data"""
    cache_file = "data/cache/col_latest.json"
    if os.path.exists(cache_file):
        cache_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(cache_file))
        if cache_age.days < 30:
            return json.load(open(cache_file))
    
    # Fetch fresh data
    data = col_api.fetch_top_100()
    json.dump(data, open(cache_file, 'w'))
    return data

# ========================================
# OPTION B: SQLite Database (Production)
# ========================================

def init_database():
    """Initialize SQLite for historical tracking"""
    conn = sqlite3.connect('data/travel_ranker.db')
    cursor = conn.cursor()
    
    # Daily snapshots table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            country TEXT NOT NULL,
            snapshot_date DATE NOT NULL,
            exchange_rate REAL,
            flight_cost REAL,
            monthly_col REAL,
            score REAL,
            UNIQUE(country, snapshot_date)
        )
    ''')
    
    # Baselines table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS baselines (
            country TEXT PRIMARY KEY,
            exchange_rate REAL,
            flight_cost REAL,
            monthly_col REAL,
            last_updated DATE
        )
    ''')
    
    conn.commit()
    conn.close()

def store_daily_snapshot(country, data):
    """Store today's data for trend tracking"""
    conn = sqlite3.connect('data/travel_ranker.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR REPLACE INTO daily_snapshots 
        (country, snapshot_date, exchange_rate, flight_cost, monthly_col, score)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        country,
        datetime.now().date(),
        data['exchange_rate'],
        data['flight_cost'],
        data['monthly_col'],
        data['score']
    ))
    
    conn.commit()
    conn.close()

def get_30day_history(country):
    """Retrieve 30-day score history for charts"""
    conn = sqlite3.connect('data/travel_ranker.db')
    df = pd.read_sql_query('''
        SELECT snapshot_date, score, exchange_rate, flight_cost, monthly_col
        FROM daily_snapshots
        WHERE country = ?
        AND snapshot_date >= date('now', '-30 days')
        ORDER BY snapshot_date
    ''', conn, params=(country,))
    conn.close()
    return df
```

**Storage Strategy:**
- **Development:** JSON files in `/data/cache` directory
- **Production:** SQLite database for historical tracking (enables 30-day charts)
- **Refresh Schedule:** 
  - Exchange: Every 4 hours (6x/day)
  - Flights: Daily rotation (Group A/B alternating, 2-day refresh per country)
  - CoL: Monthly (stable metric)

**API Usage Impact:**
```
Daily API Calls:
- Exchange: 6 calls/day = 180/month (within 1,500 limit ✅)
- Flights: 50 calls/day = 1,500/month (within 2,000 limit ✅)
- CoL: 0 calls most days (cached 30 days) = ~50/month total ✅

Total: All within free tier limits!
```

---

## Streamlit UI Design Specification (Enhanced with Momentum)

### Page Layout Structure

```
┌──────────────────────────────────────────────────────────┐
│         🌍 Digital Nomad Travel Ranker (MOMENTUM)        │
│                      (Header)                            │
│  📊 Real-time opportunity detector • Updated 4 hrs ago   │
├──────────────────────────────────────────────────────────┤
│  Sidebar (Filters)                                       │
│  ┌───────────────────┐                                  │
│  │ 📍 Origin         │                                  │
│  │ [Taiwan      ▼]   │                                  │
│  │                   │                                  │
│  │ 📅 Travel Date    │                                  │
│  │ [Date Picker]     │                                  │
│  │                   │                                  │
│  │ 🌏 Region Filter  │                                  │
│  │ ☑ Southeast Asia  │                                  │
│  │ ☑ East Asia       │                                  │
│  │ ☐ Europe          │                                  │
│  │                   │                                  │
│  │ 💰 Budget Range   │                                  │
│  │ [0────────●─4000] │                                  │
│  │                   │                                  │
│  │ 🔥 Show Only Hot  │                                  │
│  │ □ Deals (+15%)    │                                  │
│  └───────────────────┘                                  │
├──────────────────────────────────────────────────────────┤
│  Main Panel                                              │
│  ┌────────────────────────────────────────────────┐     │
│  │  🔥 Hot Deals This Week (Badge Filter)        │     │
│  │  ┌──────────┬──────────┬──────────┐          │     │
│  │  │  JAPAN   │ Vietnam  │ Turkey   │          │     │
│  │  │ 🔥💱✈️   │ 🔥       │ 🔥💱     │          │     │
│  │  │  68/100  │  89/100  │  72/100  │          │     │
│  │  │  📈 +16  │  📈 +8   │  📈 +12  │          │     │
│  │  ├──────────┼──────────┼──────────┤          │     │
│  │  │💱 +38% ⬆│ 💱 +12% ⬆│ 💱 +28% ⬆│          │     │
│  │  │✈️ +5% ⬆ │ ✈️ -3% ⬇ │ ✈️ +15% ⬆│          │     │
│  │  │🏠 -2% ⬇ │ 🏠 +2% ⬆ │ 🏠 +8% ⬆ │          │     │
│  │  └──────────┴──────────┴──────────┘          │     │
│  └────────────────────────────────────────────────┘     │
│                                                          │
│  ┌────────────────────────────────────────────────┐     │
│  │  All Destinations (Sortable + Trend Columns)  │     │
│  │  Rank│Country │Score│Trend│💱    │✈️   │🏠   │     │
│  │  1   │Japan   │68.5 │📈+16│+38%⬆│+5%⬆│-2%⬇│     │
│  │  2   │Vietnam │89.0 │📈+8 │+12%⬆│-3%⬇│+2%⬆│     │
│  │  3   │Thailand│92.0 │➡️+2 │+3%⬆ │0%➡️│+1%⬆│     │
│  │  4   │Turkey  │72.3 │📈+12│+28%⬆│+15%⬆│+8%⬆│    │
│  │  ... (scrollable with 100 countries)          │     │
│  └────────────────────────────────────────────────┘     │
│                                                          │
│  ┌────────────────────────────────────────────────┐     │
│  │  Score History (30 Days) - Click country      │     │
│  │  [Line chart: Japan score 45→68 over 30 days] │     │
│  │  [Annotation: "Yen weakening started Jan 15"]  │     │
│  └────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────┘
```

### Component Details (Enhanced)

#### 1. Header Section with Update Status
```python
st.set_page_config(page_title="Digital Nomad Ranker • Momentum", layout="wide")

col1, col2 = st.columns([3, 1])
with col1:
    st.title("🌍 Digital Nomad Destination Ranker")
    st.markdown("**Hybrid momentum scoring** - Find the best value destinations *right now*")

with col2:
    last_update = get_last_update_time()
    time_ago = humanize_timedelta(datetime.now() - last_update)
    st.metric(
        label="Last Updated",
        value=time_ago,
        delta="Live data"
    )
```

#### 2. Sidebar Controls (Enhanced with Hot Deal Filter)
```python
with st.sidebar:
    st.header("⚙️ Filters")
    
    origin = st.selectbox(
        "📍 Origin Location",
        options=["Taiwan", "Hong Kong", "Singapore", "Tokyo"],
        index=0
    )
    
    travel_date = st.date_input(
        "📅 Departure Date",
        value=datetime.now() + timedelta(days=30)
    )
    
    regions = st.multiselect(
        "🌏 Regions",
        options=["Southeast Asia", "East Asia", "Europe", "Americas", "Africa", "Middle East"],
        default=["Southeast Asia", "East Asia"]
    )
    
    budget_range = st.slider(
        "💰 Monthly Budget (USD)",
        min_value=500,
        max_value=4000,
        value=(500, 2000),
        step=100
    )
    
    st.divider()
    
    # NEW: Hot Deal Filter
    show_hot_deals_only = st.checkbox(
        "🔥 Show Only Hot Deals",
        value=False,
        help="Filter to destinations with >15% positive momentum"
    )
    
    if show_hot_deals_only:
        st.caption("Showing countries trending +15% or more")
```

#### 3. Hot Deals Section (NEW)
```python
# Filter for hot deals (overall_change > 15%)
hot_deals = df[df['overall_change'] > 15].sort_values('score', ascending=False).head(3)

if not hot_deals.empty:
    st.header("🔥 Hot Deals This Week")
    st.caption("Destinations with strong positive momentum (+15% or more)")
    
    cols = st.columns(len(hot_deals))
    
    for idx, (_, country) in enumerate(hot_deals.iterrows()):
        with cols[idx]:
            # Country card with badges
            badge_html = " ".join([f"<span>{badge}</span>" for badge in country['badges']])
            
            st.markdown(f"""
            <div style="border: 2px solid #ff4444; border-radius: 10px; padding: 15px; background: #fff5f5;">
                <h3>{country['name']}</h3>
                <div style="font-size: 24px; font-weight: bold;">{country['score']}/100</div>
                <div style="color: #ff4444; font-size: 18px;">📈 +{country['overall_change']:.0f} pts</div>
                <hr>
                <div style="font-size: 14px;">
                    💱 {country['trends']['exchange']['change_pct']:+.1f}% {country['trends']['exchange']['indicator']}<br>
                    ✈️ {country['trends']['flight']['change_pct']:+.1f}% {country['trends']['flight']['indicator']}<br>
                    🏠 {country['trends']['col']['change_pct']:+.1f}% {country['trends']['col']['indicator']}
                </div>
                <div style="margin-top: 10px;">{badge_html}</div>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button(f"View {country['name']} Details", key=f"hot_{idx}"):
                st.session_state.selected_country = country['name']
else:
    st.info("No hot deals this week (no destinations with +15% momentum)")
```

#### 4. Enhanced Table with Trend Columns
```python
import pandas as pd

# Prepare display dataframe with trend indicators
df_display = df.copy()
df_display['trend_arrow'] = df_display['overall_change'].apply(
    lambda x: "▲▲" if x > 10 else "▲" if x > 3 else "●" if x > -3 else "▼" if x > -10 else "▼▼"
)
df_display['trend_value'] = df_display['overall_change'].apply(lambda x: f"{x:+.0f}")

st.header("📊 All Destinations")

st.dataframe(
    df_display,
    column_config={
        "rank": "Rank",
        "name": "Country",
        "score": st.column_config.NumberColumn(
            "Score",
            format="%.1f ⭐",
        ),
        "trend_arrow": "Trend",
        "trend_value": "+/- Pts",
        "exchange_trend": st.column_config.Column(
            "💱 Exchange",
            help="Exchange rate momentum"
        ),
        "flight_trend": st.column_config.Column(
            "✈️ Flight",
            help="Flight cost momentum"
        ),
        "col_trend": st.column_config.Column(
            "🏠 Cost of Living",
            help="CoL momentum"
        ),
        "badges": st.column_config.ListColumn(
            "🏅 Badges",
            help="Special achievements"
        )
    },
    hide_index=True,
    use_container_width=True,
    height=500
)

# Export functionality
if st.button("📥 Export to CSV"):
    csv = df_display.to_csv(index=False)
    st.download_button(
        label="Download CSV",
        data=csv,
        file_name=f"nomad_scores_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv"
    )
```

#### 5. Score History Chart (NEW)
```python
import plotly.graph_objects as go

st.header("📈 Score Trends (Past 30 Days)")

# Country selector
selected_country = st.selectbox(
    "Select country to view history",
    options=df['name'].tolist(),
    index=0  # Default to top-ranked
)

# Fetch 30-day history from database
history_df = get_30day_history(selected_country)

if not history_df.empty:
    fig = go.Figure()
    
    # Main score line
    fig.add_trace(go.Scatter(
        x=history_df['snapshot_date'],
        y=history_df['score'],
        mode='lines+markers',
        name='Overall Score',
        line=dict(color='#4CAF50', width=3),
        marker=dict(size=8)
    ))
    
    # Component breakdown (secondary y-axis)
    fig.add_trace(go.Scatter(
        x=history_df['snapshot_date'],
        y=history_df['exchange_rate'],
        mode='lines',
        name='Exchange Rate',
        line=dict(color='#2196F3', width=2, dash='dot'),
        yaxis='y2'
    ))
    
    fig.update_layout(
        title=f"{selected_country} - 30 Day Score History",
        xaxis_title="Date",
        yaxis=dict(title="Score (0-100)", range=[0, 100]),
        yaxis2=dict(title="Exchange Rate", overlaying='y', side='right'),
        hovermode='x unified',
        height=400
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Key insights
    score_change = history_df['score'].iloc[-1] - history_df['score'].iloc[0]
    
    if abs(score_change) > 10:
        st.info(f"📊 **Significant movement**: Score changed {score_change:+.1f} points over past 30 days")
else:
    st.warning("No historical data available yet. Check back after a few days!")
```

#### 6. Regional Comparison (Momentum-Aware)
```python
import plotly.express as px

st.header("🌏 Regional Comparison")

# Group by region and calculate averages
regional_summary = df.groupby('region').agg({
    'score': 'mean',
    'overall_change': 'mean',
    'name': 'count'
}).reset_index()
regional_summary.columns = ['Region', 'Avg Score', 'Avg Momentum', 'Countries']

# Bubble chart: Score vs Momentum, sized by country count
fig = px.scatter(
    regional_summary,
    x='Avg Score',
    y='Avg Momentum',
    size='Countries',
    color='Region',
    hover_name='Region',
    hover_data={
        'Avg Score': ':.1f',
        'Avg Momentum': ':+.1f%',
        'Countries': True
    },
    title='Regional Averages: Score vs Momentum',
    labels={
        'Avg Score': 'Average Score (0-100)',
        'Avg Momentum': 'Average Momentum (%)'
    }
)

fig.add_hline(y=0, line_dash="dash", line_color="gray", annotation_text="No momentum")
fig.add_vline(x=70, line_dash="dash", line_color="gray", annotation_text="Good value threshold")

st.plotly_chart(fig, use_container_width=True)

# Key regional insights
best_momentum_region = regional_summary.loc[regional_summary['Avg Momentum'].idxmax(), 'Region']
st.success(f"🏆 **Trending Region**: {best_momentum_region} (+{regional_summary['Avg Momentum'].max():.1f}% avg momentum)")
```

---

## Implementation Roadmap (Updated for Momentum Features)

### Phase 1: Foundation + Baseline Research (Week 1)
**Objective:** Data pipeline + historical baselines

- [ ] Set up project structure
  ```
  travel-ranker/
  ├── app.py
  ├── requirements.txt
  ├── data/
  │   ├── countries.json (with baselines)
  │   ├── baselines_methodology.md
  │   └── cache/
  ├── utils/
  │   ├── api_clients.py
  │   ├── scoring.py (momentum-aware)
  │   ├── baseline_loader.py
  │   └── data_processing.py
  └── tests/
  ```
- [ ] Register for APIs (Amadeus, ExchangeRate-API, Zyla Labs)
- [ ] **Research historical baselines** (2-3 days):
  - [ ] OANDA exchange rate 3-year averages (100 countries)
  - [ ] Numbeo CoL archives scraping
  - [ ] Flight cost estimation (manual sampling + regional averages)
- [ ] Create `countries.json` with embedded baselines
- [ ] Build momentum-aware scoring module
- [ ] Write unit tests for hybrid scoring logic

**Deliverable:** Working script with momentum calculations for 5 test countries

---

### Phase 2: Core Logic + Database (Week 2)
**Objective:** Momentum scoring + historical tracking

- [ ] Implement `calculate_destination_score()` with momentum
- [ ] Build absolute + momentum normalisation functions
- [ ] Set up SQLite database for daily snapshots
- [ ] Create data aggregation pipeline
- [ ] Implement badge assignment logic
- [ ] Build batch processing for 100 countries (Group A/B rotation)
- [ ] Validate scoring with real Japan/Thailand examples

**Deliverable:** Console application with momentum indicators

---

### Phase 3: Streamlit UI with Momentum (Week 3)
**Objective:** User interface with trend visualisation

- [ ] Create Streamlit layout with momentum sections
- [ ] Implement "Hot Deals" card section
- [ ] Build enhanced table with trend columns
- [ ] Add trend arrows and percentage displays
- [ ] Implement hot deal filter checkbox
- [ ] Create badge display system
- [ ] Add responsive design

**Deliverable:** Interactive web app with momentum UI

---

### Phase 4: Visualisations + History (Week 4)
**Objective:** 30-day charts and trend analysis

- [ ] Build 30-day score history chart (Plotly)
- [ ] Implement regional momentum comparison
- [ ] Create component breakdown visualisations
- [ ] Add export to CSV with trend data
- [ ] Build "score change alert" system
- [ ] Implement country detail modal

**Deliverable:** Full analytics dashboard

---

### Phase 5: Optimisation + Deployment (Week 5)
**Objective:** Production-ready with monitoring

- [ ] Implement robust error handling
- [ ] Add retry logic for API failures
- [ ] Optimise database queries
- [ ] Set up daily snapshot cronjob
- [ ] Write user documentation (explain momentum)
- [ ] Deploy to Streamlit Cloud
- [ ] Set up GitHub repository with CI/CD
- [ ] Add monitoring for baseline drift

**Deliverable:** Live URL with momentum tracking

---

## Technical Specification (Updated)

### Dependencies
```txt
# requirements.txt
streamlit==1.31.0
pandas==2.2.0
plotly==5.18.0
numpy==1.26.0
requests==2.31.0
python-dotenv==1.0.0
amadeus==8.1.0
humanize==4.9.0  # For "2 hours ago" formatting
```

### Environment Variables
```bash
# .env
AMADEUS_API_KEY=your_key_here
AMADEUS_API_SECRET=your_secret_here
EXCHANGERATE_API_KEY=your_key_here
ZYLA_API_KEY=your_key_here
DATABASE_PATH=data/travel_ranker.db
```

### Estimated API Usage (Monthly)

| API | Calls/Day | Monthly Total | Free Tier Limit | Status |
|-----|-----------|---------------|-----------------|--------|
| Amadeus | 50 (alternating groups) | ~1,500 | 2,000 | ✅ Within limit |
| ExchangeRate | 6 (every 4hrs) | ~180 | 1,500 | ✅ Well within |
| Zyla CoL | 0 (cached 30d) | ~50 | 50 (trial) | ✅ Tight fit, then self-host |

**Cost Projection:** $0/month (all within free tiers)

---

## Risk Analysis & Mitigation (Updated)

### Risk 1: Baseline Accuracy
**Probability:** MEDIUM  
**Impact:** Momentum calculations may be off

**Mitigation:**
- Manual validation of top 20 country baselines
- Use regional averages for less critical countries
- Document methodology transparently in UI
- Plan migration to rolling 30-day averages after sufficient data

### Risk 2: False "Hot Deal" Alerts
**Probability:** MEDIUM  
**Impact:** Users book based on incorrect momentum signals

**Mitigation:**
- Conservative badge thresholds (+15% for hot deals)
- Show percentage changes alongside scores
- Add disclaimer: "Momentum is relative to 3-year average"
- Validate exchange rate data against multiple sources

### Risk 3: API Rate Limits
**Probability:** HIGH  
**Impact:** Application breaks

**Mitigation:**
- Aggressive caching (48hr flights, 4hr exchange, 30d CoL)
- Group A/B rotation for flight queries
- Fallback to secondary APIs
- Store last successful fetch as emergency dataset

### Risk 4: Database Growth
**Probability:** LOW  
**Impact:** Storage costs increase

**Mitigation:**
- SQLite sufficient for 100 countries × 365 days = 36,500 rows/year (~5MB)
- Implement auto-cleanup after 90 days
- Only store daily snapshots (not hourly)

---

## Success Metrics (Updated for Momentum)

### MVP Definition
✅ **Application displays momentum scores for 100 countries**  
✅ **Scores update every 4 hours (exchange), 2 days (flights), 30 days (CoL)**  
✅ **Hot deal badges appear for +15% momentum**  
✅ **30-day score history charts functional**  
✅ **Deployment on Streamlit Cloud (public URL)**

### Performance Targets
- Page load time: <3 seconds
- Momentum calculation: <100ms per country
- API failure rate: <5%
- Cache hit rate: >80%
- Baseline accuracy: ±10% of true historical average

### User Engagement Metrics
- % of users clicking hot deal countries: >40%
- % of users viewing 30-day charts: >25%
- Avg session duration: >3 minutes

---

## Appendix C: Sample Momentum Output

### Japan Example (Yen Weakening Scenario)

```json
{
  "country": "Japan",
  "score": 68.5,
  "breakdown": {
    "exchange": 88.0,
    "flight": 62.5,
    "col": 47.2
  },
  "trends": {
    "exchange": {
      "change_pct": 38.1,
      "indicator": "STRONG"
    },
    "flight": {
      "change_pct": 5.4,
      "indicator": "Cheaper"
    },
    "col": {
      "change_pct": -2.1,
      "indicator": "Rising"
    },
    "overall": 16.3
  },
  "badges": ["HOT DEAL", "CURRENCY WIN"],
  "current_data": {
    "exchange_rate": 5.8,
    "flight_cost": 17500,
    "monthly_col": 2860
  },
  "baselines": {
    "exchange_rate": 4.2,
    "flight_cost": 18500,
    "monthly_col": 2800
  }
}
```

### Thailand Example (Stable Performance)

```json
{
  "country": "Thailand",
  "score": 92.0,
  "breakdown": {
    "exchange": 61.0,
    "flight": 88.5,
    "col": 95.1
  },
  "trends": {
    "exchange": {
      "change_pct": 3.8,
      "indicator": "Stable"
    },
    "flight": {
      "change_pct": 0.2,
      "indicator": "Stable"
    },
    "col": {
      "change_pct": 1.3,
      "indicator": "Stable"
    },
    "overall": 1.8
  },
  "badges": ["EXCELLENT"],
  "current_data": {
    "exchange_rate": 1.09,
    "flight_cost": 4210,
    "monthly_col": 787
  },
  "baselines": {
    "exchange_rate": 1.05,
    "flight_cost": 4200,
    "monthly_col": 800
  }
}
```

---

## Document Control

**Version:** 2.0 (Momentum Update)  
**Author:** Project Architect  
**Date:** 3 February 2026  
**Status:** APPROVED - Ready for Development  
**Next Review:** After Phase 2 Completion (Baseline Research)

---

## Appendix D: Baseline Research Checklist

**For each of top 100 countries, research and document:**

- [ ] **Exchange Rate Baseline** (3-year average from OANDA)
  - Source URL logged
  - Calculation method: Simple average or weighted?
  - Date range: 2023-02-03 to 2026-02-03

- [ ] **Flight Cost Baseline** (manual sampling or Amadeus historical)
  - Minimum 5 price samples per route
  - Average of one-way economy fares
  - Peak season vs off-peak consideration

- [ ] **Cost of Living Baseline** (Numbeo archives)
  - Apartment 1BR city centre (monthly)
  - Restaurant meal (inexpensive)
  - Local transport pass
  - Cappuccino price
  - Date of Numbeo snapshot used

**Confidence Levels:**
- High: Direct historical data available
- Medium: Estimated from regional averages
- Low: Placeholder pending better data

**Timeline:** 2-3 days for 100 countries (~ 30 mins per country)

---

**🎯 Ready to proceed with momentum-based implementation! All design decisions finalized.**