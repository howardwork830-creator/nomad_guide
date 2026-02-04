"""
SQLite database operations for historical data storage.
"""

import sqlite3
import json
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Any, List, Optional

# Database path
DB_PATH = Path(__file__).parent.parent / "data" / "travel_ranker.db"


def get_connection() -> sqlite3.Connection:
    """Get database connection with row factory."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_database() -> None:
    """Initialize database tables."""
    conn = get_connection()
    cursor = conn.cursor()

    # Daily snapshots table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date DATE NOT NULL,
            country_key TEXT NOT NULL,
            country_name TEXT NOT NULL,
            final_score REAL NOT NULL,
            overall_change REAL,
            exchange_score REAL,
            exchange_change REAL,
            exchange_rate REAL,
            flight_score REAL,
            flight_change REAL,
            flight_cost REAL,
            col_score REAL,
            col_change REAL,
            col_amount REAL,
            badges TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(snapshot_date, country_key)
        )
    """)

    # Create indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_snapshot_date
        ON daily_snapshots(snapshot_date)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_country_key
        ON daily_snapshots(country_key)
    """)

    conn.commit()
    conn.close()


def store_daily_snapshot(
    country_key: str,
    country_name: str,
    score_data: Dict[str, Any],
    badges: List[str],
    snapshot_date: Optional[date] = None
) -> bool:
    """
    Store a daily snapshot for a country.

    Args:
        country_key: Country identifier key
        country_name: Display name of country
        score_data: Score calculation results
        badges: List of earned badges
        snapshot_date: Date for snapshot (defaults to today)

    Returns:
        True if stored successfully
    """
    if snapshot_date is None:
        snapshot_date = date.today()

    conn = get_connection()
    cursor = conn.cursor()

    components = score_data.get("components", {})
    exchange = components.get("exchange", {})
    flight = components.get("flight", {})
    col = components.get("col", {})

    try:
        cursor.execute("""
            INSERT OR REPLACE INTO daily_snapshots (
                snapshot_date, country_key, country_name,
                final_score, overall_change,
                exchange_score, exchange_change, exchange_rate,
                flight_score, flight_change, flight_cost,
                col_score, col_change, col_amount,
                badges
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            snapshot_date.isoformat(),
            country_key,
            country_name,
            score_data.get("final_score", 0),
            score_data.get("overall_change", 0),
            exchange.get("score", 0),
            exchange.get("change", 0),
            exchange.get("current", 0),
            flight.get("score", 0),
            flight.get("change", 0),
            flight.get("current", 0),
            col.get("score", 0),
            col.get("change", 0),
            col.get("current", 0),
            json.dumps(badges)
        ))

        conn.commit()
        return True

    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return False

    finally:
        conn.close()


def get_history(
    country_key: Optional[str] = None,
    days: int = 30
) -> List[Dict[str, Any]]:
    """
    Retrieve historical snapshot data.

    Args:
        country_key: Optional country to filter by
        days: Number of days of history to retrieve

    Returns:
        List of snapshot records
    """
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT * FROM daily_snapshots
        WHERE snapshot_date >= date('now', ?)
    """
    params = [f"-{days} days"]

    if country_key:
        query += " AND country_key = ?"
        params.append(country_key)

    query += " ORDER BY snapshot_date DESC, final_score DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        record = dict(row)
        # Parse badges JSON
        if record.get("badges"):
            try:
                record["badges"] = json.loads(record["badges"])
            except json.JSONDecodeError:
                record["badges"] = []
        results.append(record)

    return results


def get_latest_snapshot(country_key: str) -> Optional[Dict[str, Any]]:
    """
    Get the most recent snapshot for a country.

    Args:
        country_key: Country identifier

    Returns:
        Latest snapshot record or None
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM daily_snapshots
        WHERE country_key = ?
        ORDER BY snapshot_date DESC
        LIMIT 1
    """, (country_key,))

    row = cursor.fetchone()
    conn.close()

    if row:
        record = dict(row)
        if record.get("badges"):
            try:
                record["badges"] = json.loads(record["badges"])
            except json.JSONDecodeError:
                record["badges"] = []
        return record

    return None


def get_score_trend(country_key: str, days: int = 7) -> List[float]:
    """
    Get score trend for a country over specified days.

    Args:
        country_key: Country identifier
        days: Number of days

    Returns:
        List of scores (oldest to newest)
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT final_score FROM daily_snapshots
        WHERE country_key = ?
        AND snapshot_date >= date('now', ?)
        ORDER BY snapshot_date ASC
    """, (country_key, f"-{days} days"))

    rows = cursor.fetchall()
    conn.close()

    return [row["final_score"] for row in rows]


def get_all_countries_latest() -> List[Dict[str, Any]]:
    """
    Get the latest snapshot for all countries.

    Returns:
        List of latest snapshots per country
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT ds.* FROM daily_snapshots ds
        INNER JOIN (
            SELECT country_key, MAX(snapshot_date) as max_date
            FROM daily_snapshots
            GROUP BY country_key
        ) latest ON ds.country_key = latest.country_key
        AND ds.snapshot_date = latest.max_date
        ORDER BY ds.final_score DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        record = dict(row)
        if record.get("badges"):
            try:
                record["badges"] = json.loads(record["badges"])
            except json.JSONDecodeError:
                record["badges"] = []
        results.append(record)

    return results
