"""
JSON file caching utilities with TTL support.

Enhanced with:
- Cache versioning for schema compatibility
- Checksum-based corruption detection
- Stale-while-revalidate pattern
- LRU eviction support
- Auto-invalidation of corrupted entries
"""

import hashlib
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.logging_config import get_logger, metrics
from utils.data_quality import DataSource

# Logger
logger = get_logger("cache")

# Default cache directory
CACHE_DIR = Path(__file__).parent.parent / "data" / "cache"

# Cache TTLs in hours
CACHE_TTL = {
    "flights": 48,      # 48 hours for flight data
    "exchange": 4,      # 4 hours for exchange rates
    "col": 720,         # 30 days for CoL (static)
}

# Stale TTL multiplier (2x normal TTL for stale-while-revalidate)
STALE_TTL_MULTIPLIER = 2

# Cache version for schema compatibility
CACHE_VERSION = "1.1"

# Maximum cache size in bytes (100 MB)
MAX_CACHE_SIZE_BYTES = 100 * 1024 * 1024


# ============================================================================
# Cache Path Management
# ============================================================================

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


# ============================================================================
# Checksum Functions
# ============================================================================

def calculate_checksum(data: Dict[str, Any]) -> str:
    """
    Calculate SHA-256 checksum of cache data.

    Args:
        data: Data dictionary (without metadata fields)

    Returns:
        Hex digest of SHA-256 hash
    """
    # Remove metadata fields for checksum calculation
    data_for_hash = {
        k: v for k, v in data.items()
        if not k.startswith("_")
    }
    json_str = json.dumps(data_for_hash, sort_keys=True, default=str)
    return hashlib.sha256(json_str.encode()).hexdigest()[:16]


def verify_checksum(data: Dict[str, Any]) -> bool:
    """
    Verify the checksum of cached data.

    Args:
        data: Cached data dictionary with _checksum field

    Returns:
        True if checksum is valid or missing, False if corrupted
    """
    stored_checksum = data.get("_checksum")
    if not stored_checksum:
        # Old cache format without checksum, consider valid
        return True

    calculated = calculate_checksum(data)
    return stored_checksum == calculated


# ============================================================================
# Cache Validation
# ============================================================================

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

        # Check version compatibility
        version = data.get("_version")
        if version and version != CACHE_VERSION:
            logger.info(
                f"Cache version mismatch: {version} != {CACHE_VERSION}",
                extra={"cache_path": str(cache_path)}
            )
            return False

        # Check checksum
        if not verify_checksum(data):
            logger.warning(
                f"Cache corruption detected: {cache_path}",
                extra={"cache_path": str(cache_path)}
            )
            metrics.record_error("cache_corruption")
            # Auto-invalidate corrupted cache
            invalidate_cache(cache_path)
            return False

        # Check timestamp
        timestamp_str = data.get("_timestamp")
        if not timestamp_str:
            return False

        cached_time = datetime.fromisoformat(timestamp_str)
        ttl_hours = CACHE_TTL.get(cache_type, 24)
        expiry_time = cached_time + timedelta(hours=ttl_hours)

        return datetime.now() < expiry_time

    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.warning(f"Cache validation error: {e}")
        return False


def is_cache_stale_but_usable(cache_path: Path, cache_type: str) -> bool:
    """
    Check if cache is past TTL but still within stale window.

    For stale-while-revalidate pattern.

    Args:
        cache_path: Path to cache file
        cache_type: Type of cache

    Returns:
        True if cache is stale but usable, False otherwise
    """
    if not cache_path.exists():
        return False

    try:
        with open(cache_path, "r") as f:
            data = json.load(f)

        # Check checksum first
        if not verify_checksum(data):
            return False

        timestamp_str = data.get("_timestamp")
        if not timestamp_str:
            return False

        cached_time = datetime.fromisoformat(timestamp_str)
        ttl_hours = CACHE_TTL.get(cache_type, 24)

        # Normal expiry
        expiry_time = cached_time + timedelta(hours=ttl_hours)

        # Stale expiry (2x TTL)
        stale_expiry = cached_time + timedelta(hours=ttl_hours * STALE_TTL_MULTIPLIER)

        now = datetime.now()

        # Past normal TTL but within stale window
        return expiry_time <= now < stale_expiry

    except (json.JSONDecodeError, ValueError, KeyError):
        return False


def invalidate_cache(cache_path: Path) -> bool:
    """
    Invalidate (delete) a cache file.

    Args:
        cache_path: Path to cache file

    Returns:
        True if deleted, False otherwise
    """
    try:
        if cache_path.exists():
            cache_path.unlink()
            logger.info(f"Invalidated cache: {cache_path}")
            return True
    except IOError as e:
        logger.error(f"Failed to invalidate cache: {e}")
    return False


# ============================================================================
# Cache Read/Write
# ============================================================================

def fetch_cached_data(
    cache_type: str,
    key: str = "",
    default: Any = None,
    allow_stale: bool = False
) -> Tuple[Optional[Any], DataSource]:
    """
    Fetch data from cache if valid.

    Args:
        cache_type: Type of cache ('flights', 'exchange', 'col')
        key: Optional key for specific cache entry
        default: Default value if cache miss
        allow_stale: If True, return stale data with warning

    Returns:
        Tuple of (cached_data or default, data_source)
    """
    cache_path = get_cache_path(cache_type, key)

    # Check fresh cache first
    if is_cache_valid(cache_path, cache_type):
        try:
            with open(cache_path, "r") as f:
                data = json.load(f)

            # Return data without metadata
            result = {k: v for k, v in data.items() if not k.startswith("_")}

            metrics.record_cache_hit()
            logger.debug(
                f"Cache hit: {cache_type}/{key}",
                extra={"cache_type": cache_type, "key": key}
            )
            return result, DataSource.CACHE

        except (json.JSONDecodeError, IOError):
            pass

    # Check stale cache if allowed
    if allow_stale and is_cache_stale_but_usable(cache_path, cache_type):
        try:
            with open(cache_path, "r") as f:
                data = json.load(f)

            result = {k: v for k, v in data.items() if not k.startswith("_")}

            logger.warning(
                f"Using stale cache: {cache_type}/{key}",
                extra={"cache_type": cache_type, "key": key}
            )
            return result, DataSource.STALE_CACHE

        except (json.JSONDecodeError, IOError):
            pass

    metrics.record_cache_miss()
    logger.debug(
        f"Cache miss: {cache_type}/{key}",
        extra={"cache_type": cache_type, "key": key}
    )
    return default, DataSource.MOCK


def save_cache(
    cache_type: str,
    data: Any,
    key: str = "",
    schema: Optional[str] = None
) -> bool:
    """
    Save data to cache with timestamp and checksum.

    Args:
        cache_type: Type of cache ('flights', 'exchange', 'col')
        data: Data to cache
        key: Optional key for specific cache entry
        schema: Optional schema identifier

    Returns:
        True if save successful, False otherwise
    """
    cache_path = get_cache_path(cache_type, key)

    try:
        # Calculate checksum of data
        checksum = calculate_checksum(data) if isinstance(data, dict) else ""

        # Add metadata
        cache_data = {
            "_version": CACHE_VERSION,
            "_schema": schema or f"{cache_type}_v1",
            "_timestamp": datetime.now().isoformat(),
            "_cache_type": cache_type,
            "_checksum": checksum,
            **data
        }

        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        with open(cache_path, "w") as f:
            json.dump(cache_data, f, indent=2, default=str)

        logger.debug(
            f"Cache saved: {cache_type}/{key}",
            extra={"cache_type": cache_type, "key": key}
        )
        return True

    except (IOError, TypeError) as e:
        logger.error(f"Cache save error: {e}")
        return False


# ============================================================================
# Cache Age/Info Functions
# ============================================================================

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


def get_cache_age_seconds(cache_type: str, key: str = "") -> Optional[int]:
    """
    Get cache age in seconds.

    Args:
        cache_type: Type of cache
        key: Optional key

    Returns:
        Age in seconds or None
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
        return int(age.total_seconds())

    except (json.JSONDecodeError, ValueError, IOError):
        return None


def get_cache_info(cache_type: str, key: str = "") -> Optional[Dict[str, Any]]:
    """
    Get detailed cache metadata.

    Args:
        cache_type: Type of cache
        key: Optional key

    Returns:
        Cache metadata dictionary or None
    """
    cache_path = get_cache_path(cache_type, key)

    if not cache_path.exists():
        return None

    try:
        with open(cache_path, "r") as f:
            data = json.load(f)

        file_stat = cache_path.stat()

        return {
            "version": data.get("_version"),
            "schema": data.get("_schema"),
            "timestamp": data.get("_timestamp"),
            "checksum": data.get("_checksum"),
            "file_size_bytes": file_stat.st_size,
            "is_valid": is_cache_valid(cache_path, cache_type),
            "is_stale": is_cache_stale_but_usable(cache_path, cache_type),
            "age_seconds": get_cache_age_seconds(cache_type, key),
        }

    except (json.JSONDecodeError, IOError):
        return None


# ============================================================================
# Cache Management
# ============================================================================

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

    logger.info(f"Cleared {deleted} cache files")
    return deleted


def get_cache_size() -> int:
    """
    Get total cache size in bytes.

    Returns:
        Total size in bytes
    """
    if not CACHE_DIR.exists():
        return 0

    total_size = 0
    for cache_file in CACHE_DIR.glob("*.json"):
        try:
            total_size += cache_file.stat().st_size
        except IOError:
            pass

    return total_size


def get_cache_files() -> List[Dict[str, Any]]:
    """
    Get list of all cache files with metadata.

    Returns:
        List of cache file info dictionaries
    """
    if not CACHE_DIR.exists():
        return []

    files = []
    for cache_file in CACHE_DIR.glob("*.json"):
        try:
            stat = cache_file.stat()
            files.append({
                "name": cache_file.name,
                "size_bytes": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
        except IOError:
            pass

    # Sort by modification time, newest first
    files.sort(key=lambda x: x["modified"], reverse=True)
    return files


def evict_lru_caches(target_size: int = MAX_CACHE_SIZE_BYTES) -> int:
    """
    Evict least recently used cache files to meet target size.

    Args:
        target_size: Target maximum cache size in bytes

    Returns:
        Number of files evicted
    """
    current_size = get_cache_size()
    if current_size <= target_size:
        return 0

    files = get_cache_files()
    # Sort by modification time, oldest first (for LRU eviction)
    files.sort(key=lambda x: x["modified"])

    evicted = 0
    for file_info in files:
        if current_size <= target_size:
            break

        cache_path = CACHE_DIR / file_info["name"]
        try:
            file_size = file_info["size_bytes"]
            cache_path.unlink()
            current_size -= file_size
            evicted += 1
            logger.info(f"Evicted LRU cache: {file_info['name']}")
        except IOError:
            pass

    return evicted


def warm_cache(countries: List[str]) -> None:
    """
    Pre-warm cache for specified countries (placeholder for future implementation).

    Args:
        countries: List of country keys to warm cache for
    """
    # This would typically fetch fresh data for specified countries
    # Implementation depends on API client availability
    logger.info(f"Cache warming requested for {len(countries)} countries")
    pass


# ============================================================================
# Cache Health Check
# ============================================================================

def check_cache_health() -> Dict[str, Any]:
    """
    Check cache health and return status.

    Returns:
        Dictionary with cache health information
    """
    total_size = get_cache_size()
    files = get_cache_files()

    # Count valid vs stale vs corrupted
    valid_count = 0
    stale_count = 0
    corrupted_count = 0

    for file_info in files:
        cache_path = CACHE_DIR / file_info["name"]
        # Determine cache type from filename
        cache_type = file_info["name"].split("_")[0]

        if is_cache_valid(cache_path, cache_type):
            valid_count += 1
        elif is_cache_stale_but_usable(cache_path, cache_type):
            stale_count += 1
        else:
            corrupted_count += 1

    return {
        "total_files": len(files),
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "valid_count": valid_count,
        "stale_count": stale_count,
        "corrupted_count": corrupted_count,
        "size_limit_mb": MAX_CACHE_SIZE_BYTES / (1024 * 1024),
        "size_usage_pct": round((total_size / MAX_CACHE_SIZE_BYTES) * 100, 1),
    }
