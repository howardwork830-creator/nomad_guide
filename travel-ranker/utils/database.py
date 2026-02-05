"""
SQLite database operations for historical data storage.

Enhanced with:
- Data provenance columns (source, quality scores)
- Migration support for schema updates
- Validation before storage
"""

import sqlite3
import json
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Any, List, Optional

from utils.logging_config import get_logger
from utils.data_quality import DataSource, ProvenanceMetadata

# Logger
logger = get_logger("database")

# Database path
DB_PATH = Path(__file__).parent.parent / "data" / "travel_ranker.db"

# Current schema version
SCHEMA_VERSION = 2


def get_connection() -> sqlite3.Connection:
    """Get database connection with row factory."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Get current schema version from database."""
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT version FROM schema_version")
        row = cursor.fetchone()
        return row["version"] if row else 0
    except sqlite3.OperationalError:
        return 0


def set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    """Set schema version in database."""
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            version INTEGER NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        INSERT OR REPLACE INTO schema_version (id, version, updated_at)
        VALUES (1, ?, CURRENT_TIMESTAMP)
    """, (version,))
    conn.commit()


def migrate_to_v2(conn: sqlite3.Connection) -> None:
    """
    Migrate database from v1 to v2.

    Adds provenance columns:
    - data_source
    - data_quality_score
    - exchange_source
    - flight_source
    - col_source
    """
    cursor = conn.cursor()

    # Check if columns already exist
    cursor.execute("PRAGMA table_info(daily_snapshots)")
    columns = {row["name"] for row in cursor.fetchall()}

    new_columns = [
        ("data_source", "TEXT DEFAULT 'baseline'"),
        ("data_quality_score", "REAL DEFAULT 50.0"),
        ("exchange_source", "TEXT DEFAULT 'baseline'"),
        ("flight_source", "TEXT DEFAULT 'baseline'"),
        ("col_source", "TEXT DEFAULT 'baseline'"),
    ]

    for col_name, col_def in new_columns:
        if col_name not in columns:
            cursor.execute(f"ALTER TABLE daily_snapshots ADD COLUMN {col_name} {col_def}")
            logger.info(f"Added column {col_name} to daily_snapshots")

    conn.commit()
    logger.info("Migration to v2 complete")


def init_database() -> None:
    """Initialize database tables with migrations."""
    conn = get_connection()
    cursor = conn.cursor()

    # Create main table with base columns first (v1 schema)
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

    # Create base indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_snapshot_date
        ON daily_snapshots(snapshot_date)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_country_key
        ON daily_snapshots(country_key)
    """)

    conn.commit()

    # Run migrations if needed - BEFORE creating indexes on new columns
    current_version = get_schema_version(conn)
    if current_version < 2:
        migrate_to_v2(conn)
        set_schema_version(conn, 2)

    # Create index on new columns after migration
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_data_quality
        ON daily_snapshots(data_quality_score)
    """)
    conn.commit()

    conn.close()
    logger.info("Database initialized")


def store_daily_snapshot(
    country_key: str,
    country_name: str,
    score_data: Dict[str, Any],
    badges: List[str],
    snapshot_date: Optional[date] = None,
    provenance: Optional[ProvenanceMetadata] = None
) -> bool:
    """
    Store a daily snapshot for a country.

    Args:
        country_key: Country identifier key
        country_name: Display name of country
        score_data: Score calculation results
        badges: List of earned badges
        snapshot_date: Date for snapshot (defaults to today)
        provenance: Data provenance metadata

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

    # Get provenance values
    if provenance:
        prov_data = provenance.to_db_columns()
    else:
        prov_data = {
            "data_source": DataSource.BASELINE.value,
            "data_quality_score": 50.0,
            "exchange_source": DataSource.BASELINE.value,
            "flight_source": DataSource.BASELINE.value,
            "col_source": DataSource.BASELINE.value,
        }

    try:
        cursor.execute("""
            INSERT OR REPLACE INTO daily_snapshots (
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
            json.dumps(badges),
            prov_data["data_source"],
            prov_data["data_quality_score"],
            prov_data["exchange_source"],
            prov_data["flight_source"],
            prov_data["col_source"],
        ))

        conn.commit()
        logger.debug(
            f"Stored snapshot for {country_key}",
            extra={
                "country_key": country_key,
                "score": score_data.get("final_score", 0),
                "data_source": prov_data["data_source"],
                "quality_score": prov_data["data_quality_score"],
            }
        )
        return True

    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return False

    finally:
        conn.close()


def get_history(
    country_key: Optional[str] = None,
    days: int = 30,
    min_quality_score: Optional[float] = None
) -> List[Dict[str, Any]]:
    """
    Retrieve historical snapshot data.

    Args:
        country_key: Optional country to filter by
        days: Number of days of history to retrieve
        min_quality_score: Optional minimum quality score filter

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

    if min_quality_score is not None:
        query += " AND data_quality_score >= ?"
        params.append(min_quality_score)

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


def get_country_trend_data(country_key: str, days: int = 30) -> List[Dict[str, Any]]:
    """Get historical trend data for charts."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT snapshot_date, exchange_rate, flight_cost, col_amount
        FROM daily_snapshots
        WHERE country_key = ?
        AND snapshot_date >= date('now', ?)
        ORDER BY snapshot_date ASC
    """, (country_key, f"-{days} days"))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


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


def get_data_quality_stats() -> Dict[str, Any]:
    """
    Get data quality statistics across all snapshots.

    Returns:
        Dictionary with quality statistics
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            AVG(data_quality_score) as avg_quality,
            MIN(data_quality_score) as min_quality,
            MAX(data_quality_score) as max_quality,
            COUNT(*) as total_snapshots,
            SUM(CASE WHEN data_source = 'live_api' THEN 1 ELSE 0 END) as live_api_count,
            SUM(CASE WHEN data_source = 'cache' THEN 1 ELSE 0 END) as cache_count,
            SUM(CASE WHEN data_source = 'stale_cache' THEN 1 ELSE 0 END) as stale_cache_count,
            SUM(CASE WHEN data_source = 'baseline' THEN 1 ELSE 0 END) as baseline_count,
            SUM(CASE WHEN data_source = 'mock' THEN 1 ELSE 0 END) as mock_count
        FROM daily_snapshots
        WHERE snapshot_date >= date('now', '-30 days')
    """)

    row = cursor.fetchone()
    conn.close()

    if row:
        return {
            "avg_quality": round(row["avg_quality"] or 0, 1),
            "min_quality": row["min_quality"] or 0,
            "max_quality": row["max_quality"] or 0,
            "total_snapshots": row["total_snapshots"] or 0,
            "source_distribution": {
                "live_api": row["live_api_count"] or 0,
                "cache": row["cache_count"] or 0,
                "stale_cache": row["stale_cache_count"] or 0,
                "baseline": row["baseline_count"] or 0,
                "mock": row["mock_count"] or 0,
            },
        }

    return {}


def get_countries_by_quality(min_score: float = 80) -> List[str]:
    """
    Get list of countries with data quality above threshold.

    Args:
        min_score: Minimum quality score

    Returns:
        List of country keys
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT country_key
        FROM daily_snapshots
        WHERE data_quality_score >= ?
        AND snapshot_date >= date('now', '-7 days')
    """, (min_score,))

    rows = cursor.fetchall()
    conn.close()

    return [row["country_key"] for row in rows]


def cleanup_old_snapshots(days_to_keep: int = 90) -> int:
    """
    Remove snapshots older than specified days.

    Args:
        days_to_keep: Number of days of data to retain

    Returns:
        Number of rows deleted
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM daily_snapshots
        WHERE snapshot_date < date('now', ?)
    """, (f"-{days_to_keep} days",))

    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    if deleted > 0:
        logger.info(f"Cleaned up {deleted} old snapshots")

    return deleted
