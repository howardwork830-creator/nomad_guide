"""
Backfill historical data for trend charts.

Generates synthetic historical snapshots based on baseline values
with realistic variations over time.

Usage:
    python scripts/backfill_history.py [--days 365]
"""

import sys
import math
import random
import argparse
from datetime import date, timedelta
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.database import init_database, get_connection
from utils.api_clients import load_countries
from utils.scoring import calculate_destination_score, assign_badges
import json


def generate_variation(base_value: float, day_offset: int, total_days: int,
                       volatility: float = 0.05, trend: float = 0) -> float:
    """
    Generate a realistic value with gradual drift and noise.

    Args:
        base_value: The baseline value
        day_offset: Days from start (0 = oldest)
        total_days: Total number of days being generated
        volatility: How much random variation (0.05 = 5%)
        trend: Overall trend direction (-0.1 to 0.1 typical)

    Returns:
        Varied value
    """
    # Gradual trend component
    trend_factor = 1 + (trend * day_offset / total_days)

    # Random walk component (accumulated small changes)
    random.seed(hash((base_value, day_offset)) % 2**32)
    noise = sum(random.gauss(0, volatility / 10) for _ in range(day_offset + 1))
    noise = max(-volatility * 2, min(volatility * 2, noise))  # Clamp extreme values

    # Seasonal component (optional, mild)
    seasonal = 0.02 * math.sin(2 * math.pi * day_offset / 365)

    return base_value * (trend_factor + noise + seasonal)


def backfill_country(cursor, country_key: str, country_info: dict,
                     start_date: date, end_date: date):
    """Generate and insert historical data for one country."""
    baseline = country_info.get("baseline", {})
    country_name = country_info.get("name", country_key)

    base_exchange = baseline.get("exchange_rate", 1.0)
    base_flight = baseline.get("flight_cost_twd", 15000)
    base_col = baseline.get("monthly_col_usd", 1500)

    total_days = (end_date - start_date).days
    current = start_date

    # Random trends for this country (slight bias)
    random.seed(hash(country_key) % 2**32)
    exchange_trend = random.uniform(-0.08, 0.08)
    flight_trend = random.uniform(-0.05, 0.1)
    col_trend = random.uniform(0, 0.06)  # CoL tends to increase

    inserted = 0
    while current <= end_date:
        day_offset = (current - start_date).days

        # Generate varied values
        exchange_rate = generate_variation(base_exchange, day_offset, total_days,
                                          volatility=0.03, trend=exchange_trend)
        flight_cost = generate_variation(base_flight, day_offset, total_days,
                                        volatility=0.08, trend=flight_trend)
        col_amount = generate_variation(base_col, day_offset, total_days,
                                       volatility=0.02, trend=col_trend)

        # Ensure positive values
        exchange_rate = max(0.01, exchange_rate)
        flight_cost = max(1000, flight_cost)
        col_amount = max(100, col_amount)

        # Calculate score
        score_data = calculate_destination_score(
            current_exchange_rate=exchange_rate,
            baseline_exchange_rate=base_exchange,
            current_flight_cost=flight_cost,
            baseline_flight_cost=base_flight,
            current_col=col_amount,
            baseline_col=base_col,
            currency=country_info.get("currency_code", "USD"),
            country=country_name
        )

        badges = assign_badges(score_data)
        components = score_data.get("components", {})

        try:
            cursor.execute("""
                INSERT OR IGNORE INTO daily_snapshots (
                    snapshot_date, country_key, country_name,
                    final_score, overall_change,
                    exchange_score, exchange_change, exchange_rate,
                    flight_score, flight_change, flight_cost,
                    col_score, col_change, col_amount,
                    badges,
                    data_source, data_quality_score,
                    exchange_source, flight_source, col_source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                current.isoformat(),
                country_key,
                country_name,
                score_data.get("final_score", 0),
                score_data.get("overall_change", 0),
                components.get("exchange", {}).get("score", 0),
                components.get("exchange", {}).get("change", 0),
                exchange_rate,
                components.get("flight", {}).get("score", 0),
                components.get("flight", {}).get("change", 0),
                flight_cost,
                components.get("col", {}).get("score", 0),
                components.get("col", {}).get("change", 0),
                col_amount,
                json.dumps(badges),
                "synthetic",
                30.0,  # Lower quality score for synthetic data
                "synthetic",
                "synthetic",
                "synthetic",
            ))
            inserted += 1
        except Exception as e:
            print(f"  Error inserting {current}: {e}")

        current += timedelta(days=1)

    return inserted


def main():
    parser = argparse.ArgumentParser(description="Backfill historical data")
    parser.add_argument("--days", type=int, default=365,
                       help="Number of days of history to generate (default: 365)")
    parser.add_argument("--dry-run", action="store_true",
                       help="Show what would be done without inserting")
    args = parser.parse_args()

    print(f"Backfilling {args.days} days of historical data...")

    # Initialize database
    init_database()

    # Load countries
    countries = load_countries()
    destinations = countries.get("destinations", {})

    print(f"Found {len(destinations)} destinations")

    # Calculate date range
    end_date = date.today() - timedelta(days=1)  # Yesterday (today may have real data)
    start_date = end_date - timedelta(days=args.days - 1)

    print(f"Date range: {start_date} to {end_date}")

    if args.dry_run:
        print("\nDry run - no data will be inserted")
        print(f"Would insert ~{args.days * len(destinations)} rows")
        return

    conn = get_connection()
    cursor = conn.cursor()

    total_inserted = 0
    for country_key, country_info in destinations.items():
        print(f"  Processing {country_info.get('name', country_key)}...", end=" ")
        inserted = backfill_country(cursor, country_key, country_info,
                                   start_date, end_date)
        print(f"{inserted} rows")
        total_inserted += inserted

    conn.commit()
    conn.close()

    print(f"\nDone! Inserted {total_inserted} historical snapshots.")
    print("Run 'streamlit run app.py' to see the trend charts.")


if __name__ == "__main__":
    main()
