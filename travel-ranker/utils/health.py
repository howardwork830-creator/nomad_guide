"""
Health check endpoints for the Digital Nomad Destination Ranker.

Provides system health monitoring including:
- API availability checks
- Database connectivity
- Cache status
- Overall system health
"""

import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests

from utils.circuit_breaker import circuit_breakers


# ============================================================================
# Health Status Types
# ============================================================================

class HealthStatus(Enum):
    """Overall health status levels."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ComponentHealth:
    """Health status for a single component."""

    name: str
    status: HealthStatus
    latency_ms: Optional[float] = None
    message: Optional[str] = None
    last_check: datetime = field(default_factory=datetime.now)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": self.status.value,
            "latency_ms": round(self.latency_ms, 2) if self.latency_ms else None,
            "message": self.message,
            "last_check": self.last_check.isoformat(),
            "details": self.details,
        }


@dataclass
class SystemHealth:
    """Overall system health status."""

    status: HealthStatus
    checks: Dict[str, ComponentHealth]
    last_successful_update: Optional[datetime] = None
    version: str = "1.0.0"
    uptime_seconds: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON response."""
        return {
            "status": self.status.value,
            "checks": {name: check.to_dict() for name, check in self.checks.items()},
            "last_successful_update": (
                self.last_successful_update.isoformat()
                if self.last_successful_update else None
            ),
            "version": self.version,
            "uptime_seconds": round(self.uptime_seconds, 1) if self.uptime_seconds else None,
        }


# ============================================================================
# Health Check Functions
# ============================================================================

# Application start time for uptime calculation
_start_time = datetime.now()

# Track last successful data update
_last_successful_update: Optional[datetime] = None


def set_last_successful_update(timestamp: Optional[datetime] = None) -> None:
    """Record timestamp of last successful data update."""
    global _last_successful_update
    _last_successful_update = timestamp or datetime.now()


def get_last_successful_update() -> Optional[datetime]:
    """Get timestamp of last successful data update."""
    return _last_successful_update


def check_serpapi_health(api_key: str = "") -> ComponentHealth:
    """
    Check SerpApi availability.

    Args:
        api_key: SerpApi key (if empty, returns degraded status)

    Returns:
        ComponentHealth with status and latency
    """
    name = "serpapi"

    if not api_key:
        return ComponentHealth(
            name=name,
            status=HealthStatus.DEGRADED,
            message="API key not configured",
        )

    # Check circuit breaker status
    breaker = circuit_breakers.get("serpapi")
    if breaker.is_open:
        return ComponentHealth(
            name=name,
            status=HealthStatus.UNHEALTHY,
            message="Circuit breaker is open",
            details=breaker.get_status(),
        )

    # Try a lightweight request to check API availability
    try:
        start_time = time.time()
        response = requests.get(
            "https://serpapi.com/account",
            params={"api_key": api_key},
            timeout=5
        )
        latency_ms = (time.time() - start_time) * 1000

        if response.status_code == 200:
            data = response.json()
            return ComponentHealth(
                name=name,
                status=HealthStatus.HEALTHY,
                latency_ms=latency_ms,
                details={
                    "searches_remaining": data.get("total_searches_left", "unknown"),
                },
            )
        elif response.status_code == 401:
            return ComponentHealth(
                name=name,
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency_ms,
                message="Invalid API key",
            )
        else:
            return ComponentHealth(
                name=name,
                status=HealthStatus.DEGRADED,
                latency_ms=latency_ms,
                message=f"Unexpected status: {response.status_code}",
            )

    except requests.Timeout:
        return ComponentHealth(
            name=name,
            status=HealthStatus.UNHEALTHY,
            message="Request timeout",
        )
    except requests.RequestException as e:
        return ComponentHealth(
            name=name,
            status=HealthStatus.UNHEALTHY,
            message=f"Connection error: {str(e)}",
        )


def check_exchange_api_health(api_key: str = "") -> ComponentHealth:
    """
    Check ExchangeRate-API availability.

    Args:
        api_key: ExchangeRate-API key

    Returns:
        ComponentHealth with status and latency
    """
    name = "exchange_api"

    if not api_key:
        return ComponentHealth(
            name=name,
            status=HealthStatus.DEGRADED,
            message="API key not configured",
        )

    # Check circuit breaker status
    breaker = circuit_breakers.get("exchange_api")
    if breaker.is_open:
        return ComponentHealth(
            name=name,
            status=HealthStatus.UNHEALTHY,
            message="Circuit breaker is open",
            details=breaker.get_status(),
        )

    try:
        start_time = time.time()
        response = requests.get(
            f"https://v6.exchangerate-api.com/v6/{api_key}/latest/TWD",
            timeout=5
        )
        latency_ms = (time.time() - start_time) * 1000

        if response.status_code == 200:
            data = response.json()
            if data.get("result") == "success":
                return ComponentHealth(
                    name=name,
                    status=HealthStatus.HEALTHY,
                    latency_ms=latency_ms,
                    details={
                        "base_code": data.get("base_code"),
                        "time_last_update": data.get("time_last_update_utc"),
                    },
                )

        return ComponentHealth(
            name=name,
            status=HealthStatus.DEGRADED,
            latency_ms=latency_ms,
            message=f"Unexpected response",
        )

    except requests.Timeout:
        return ComponentHealth(
            name=name,
            status=HealthStatus.UNHEALTHY,
            message="Request timeout",
        )
    except requests.RequestException as e:
        return ComponentHealth(
            name=name,
            status=HealthStatus.UNHEALTHY,
            message=f"Connection error: {str(e)}",
        )


def check_database_health(db_path: Optional[Path] = None) -> ComponentHealth:
    """
    Check SQLite database connectivity.

    Args:
        db_path: Path to database file

    Returns:
        ComponentHealth with status and latency
    """
    name = "database"

    if db_path is None:
        db_path = Path(__file__).parent.parent / "data" / "travel_ranker.db"

    if not db_path.exists():
        return ComponentHealth(
            name=name,
            status=HealthStatus.DEGRADED,
            message="Database file not found (will be created)",
        )

    try:
        start_time = time.time()
        conn = sqlite3.connect(str(db_path), timeout=5)
        cursor = conn.cursor()

        # Test query
        cursor.execute("SELECT COUNT(*) FROM daily_snapshots")
        count = cursor.fetchone()[0]

        # Check table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='daily_snapshots'"
        )
        table_exists = cursor.fetchone() is not None

        conn.close()
        latency_ms = (time.time() - start_time) * 1000

        if table_exists:
            return ComponentHealth(
                name=name,
                status=HealthStatus.HEALTHY,
                latency_ms=latency_ms,
                details={
                    "snapshot_count": count,
                    "file_size_kb": round(db_path.stat().st_size / 1024, 1),
                },
            )
        else:
            return ComponentHealth(
                name=name,
                status=HealthStatus.DEGRADED,
                latency_ms=latency_ms,
                message="Required tables not found",
            )

    except sqlite3.Error as e:
        return ComponentHealth(
            name=name,
            status=HealthStatus.UNHEALTHY,
            message=f"Database error: {str(e)}",
        )


def check_cache_health(cache_dir: Optional[Path] = None) -> ComponentHealth:
    """
    Check cache directory status.

    Args:
        cache_dir: Path to cache directory

    Returns:
        ComponentHealth with status and details
    """
    name = "cache"

    if cache_dir is None:
        cache_dir = Path(__file__).parent.parent / "data" / "cache"

    if not cache_dir.exists():
        return ComponentHealth(
            name=name,
            status=HealthStatus.DEGRADED,
            message="Cache directory not found",
        )

    try:
        start_time = time.time()
        cache_files = list(cache_dir.glob("*.json"))
        total_size = sum(f.stat().st_size for f in cache_files)
        latency_ms = (time.time() - start_time) * 1000

        # Check for exchange rate cache specifically
        exchange_cache = cache_dir / "exchange.json"
        has_exchange = exchange_cache.exists()

        flight_caches = [f for f in cache_files if f.name.startswith("flights_")]

        return ComponentHealth(
            name=name,
            status=HealthStatus.HEALTHY,
            latency_ms=latency_ms,
            details={
                "files": len(cache_files),
                "total_size_kb": round(total_size / 1024, 1),
                "has_exchange_cache": has_exchange,
                "flight_caches": len(flight_caches),
            },
        )

    except OSError as e:
        return ComponentHealth(
            name=name,
            status=HealthStatus.UNHEALTHY,
            message=f"Cache access error: {str(e)}",
        )


# ============================================================================
# Main Health Check
# ============================================================================

def get_system_health(
    serpapi_key: str = "",
    exchange_api_key: str = "",
    db_path: Optional[Path] = None,
    cache_dir: Optional[Path] = None
) -> SystemHealth:
    """
    Perform comprehensive system health check.

    Args:
        serpapi_key: SerpApi key
        exchange_api_key: ExchangeRate-API key
        db_path: Database path
        cache_dir: Cache directory path

    Returns:
        SystemHealth with all component statuses
    """
    checks = {}

    # Check each component
    checks["serpapi"] = check_serpapi_health(serpapi_key)
    checks["exchange_api"] = check_exchange_api_health(exchange_api_key)
    checks["database"] = check_database_health(db_path)
    checks["cache"] = check_cache_health(cache_dir)

    # Determine overall status
    statuses = [check.status for check in checks.values()]

    if all(s == HealthStatus.HEALTHY for s in statuses):
        overall_status = HealthStatus.HEALTHY
    elif any(s == HealthStatus.UNHEALTHY for s in statuses):
        # If critical components are unhealthy, system is unhealthy
        critical = ["database"]
        critical_unhealthy = any(
            checks[c].status == HealthStatus.UNHEALTHY
            for c in critical if c in checks
        )
        if critical_unhealthy:
            overall_status = HealthStatus.UNHEALTHY
        else:
            overall_status = HealthStatus.DEGRADED
    else:
        overall_status = HealthStatus.DEGRADED

    # Calculate uptime
    uptime = (datetime.now() - _start_time).total_seconds()

    return SystemHealth(
        status=overall_status,
        checks=checks,
        last_successful_update=_last_successful_update,
        uptime_seconds=uptime,
    )


def get_health_summary() -> Dict[str, Any]:
    """
    Get a quick health summary without API checks.

    Returns:
        Dictionary with basic health info
    """
    db_health = check_database_health()
    cache_health = check_cache_health()

    # Quick status based on local components
    if db_health.status == HealthStatus.HEALTHY and cache_health.status == HealthStatus.HEALTHY:
        status = "healthy"
    elif db_health.status == HealthStatus.UNHEALTHY:
        status = "unhealthy"
    else:
        status = "degraded"

    return {
        "status": status,
        "database": db_health.status.value,
        "cache": cache_health.status.value,
        "uptime_seconds": round((datetime.now() - _start_time).total_seconds(), 1),
        "last_update": (
            _last_successful_update.isoformat() if _last_successful_update else None
        ),
    }


# ============================================================================
# Circuit Breaker Health
# ============================================================================

def get_circuit_breaker_health() -> Dict[str, Any]:
    """
    Get health status of all circuit breakers.

    Returns:
        Dictionary with circuit breaker statuses
    """
    return circuit_breakers.get_all_status()


# ============================================================================
# Readiness and Liveness Probes
# ============================================================================

def is_ready() -> bool:
    """
    Readiness probe - check if system is ready to serve requests.

    Returns:
        True if ready, False otherwise
    """
    db_health = check_database_health()
    return db_health.status != HealthStatus.UNHEALTHY


def is_alive() -> bool:
    """
    Liveness probe - check if system is alive and running.

    Returns:
        True if alive (always returns True unless critical failure)
    """
    return True
