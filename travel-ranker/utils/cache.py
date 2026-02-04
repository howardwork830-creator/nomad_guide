"""
JSON file caching utilities with TTL support.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

# Default cache directory
CACHE_DIR = Path(__file__).parent.parent / "data" / "cache"

# Cache TTLs in hours
CACHE_TTL = {
    "flights": 48,      # 48 hours for flight data
    "exchange": 4,      # 4 hours for exchange rates
    "col": 720,         # 30 days for CoL (static)
}


def get_cache_path(cache_type: str, key: str = "") -> Path:
    """
    Get the cache file path for a given type and optional key.

    Args:
        cache_type: Type of cache ('flights', 'exchange', 'col')
        key: Optional key for specific cache entry (e.g., country code)

    Returns:
        Path to cache file
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if key:
        filename = f"{cache_type}_{key}.json"
    else:
        filename = f"{cache_type}.json"

    return CACHE_DIR / filename


def is_cache_valid(cache_path: Path, cache_type: str) -> bool:
    """
    Check if cache file exists and is within TTL.

    Args:
        cache_path: Path to cache file
        cache_type: Type of cache for TTL lookup

    Returns:
        True if cache is valid, False otherwise
    """
    if not cache_path.exists():
        return False

    try:
        with open(cache_path, "r") as f:
            data = json.load(f)

        timestamp_str = data.get("_timestamp")
        if not timestamp_str:
            return False

        cached_time = datetime.fromisoformat(timestamp_str)
        ttl_hours = CACHE_TTL.get(cache_type, 24)
        expiry_time = cached_time + timedelta(hours=ttl_hours)

        return datetime.now() < expiry_time

    except (json.JSONDecodeError, ValueError, KeyError):
        return False


def fetch_cached_data(
    cache_type: str,
    key: str = "",
    default: Any = None
) -> Optional[Any]:
    """
    Fetch data from cache if valid.

    Args:
        cache_type: Type of cache ('flights', 'exchange', 'col')
        key: Optional key for specific cache entry
        default: Default value if cache miss

    Returns:
        Cached data or default value
    """
    cache_path = get_cache_path(cache_type, key)

    if not is_cache_valid(cache_path, cache_type):
        return default

    try:
        with open(cache_path, "r") as f:
            data = json.load(f)
        # Return data without metadata
        return {k: v for k, v in data.items() if not k.startswith("_")}
    except (json.JSONDecodeError, IOError):
        return default


def save_cache(
    cache_type: str,
    data: Any,
    key: str = ""
) -> bool:
    """
    Save data to cache with timestamp.

    Args:
        cache_type: Type of cache ('flights', 'exchange', 'col')
        data: Data to cache
        key: Optional key for specific cache entry

    Returns:
        True if save successful, False otherwise
    """
    cache_path = get_cache_path(cache_type, key)

    try:
        # Add timestamp metadata
        cache_data = {
            "_timestamp": datetime.now().isoformat(),
            "_cache_type": cache_type,
            **data
        }

        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        with open(cache_path, "w") as f:
            json.dump(cache_data, f, indent=2)

        return True
    except (IOError, TypeError) as e:
        print(f"Cache save error: {e}")
        return False


def get_cache_age(cache_type: str, key: str = "") -> Optional[str]:
    """
    Get human-readable cache age.

    Args:
        cache_type: Type of cache
        key: Optional key

    Returns:
        Human-readable age string or None if no cache
    """
    cache_path = get_cache_path(cache_type, key)

    if not cache_path.exists():
        return None

    try:
        with open(cache_path, "r") as f:
            data = json.load(f)

        timestamp_str = data.get("_timestamp")
        if not timestamp_str:
            return None

        cached_time = datetime.fromisoformat(timestamp_str)
        age = datetime.now() - cached_time

        if age.days > 0:
            return f"{age.days} day(s) ago"
        elif age.seconds > 3600:
            hours = age.seconds // 3600
            return f"{hours} hour(s) ago"
        elif age.seconds > 60:
            minutes = age.seconds // 60
            return f"{minutes} minute(s) ago"
        else:
            return "just now"

    except (json.JSONDecodeError, ValueError, IOError):
        return None


def clear_cache(cache_type: Optional[str] = None) -> int:
    """
    Clear cache files.

    Args:
        cache_type: Optional type to clear (clears all if None)

    Returns:
        Number of files deleted
    """
    deleted = 0

    if not CACHE_DIR.exists():
        return 0

    for cache_file in CACHE_DIR.glob("*.json"):
        if cache_type is None or cache_file.name.startswith(cache_type):
            try:
                cache_file.unlink()
                deleted += 1
            except IOError:
                pass

    return deleted
