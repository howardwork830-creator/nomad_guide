"""
Structured logging configuration for the Digital Nomad Destination Ranker.

Provides JSON-formatted logs with consistent structure for
monitoring, debugging, and observability.
"""

import logging
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, Optional
import time
import json

try:
    import structlog
    STRUCTLOG_AVAILABLE = True
except ImportError:
    STRUCTLOG_AVAILABLE = False

# ============================================================================
# Context Variables for Request Tracking
# ============================================================================

# Request ID for correlation across log entries
request_id_var: ContextVar[str] = ContextVar("request_id", default="")

# Component name for identifying log source
component_var: ContextVar[str] = ContextVar("component", default="app")


def get_request_id() -> str:
    """Get current request ID or generate new one."""
    rid = request_id_var.get()
    if not rid:
        rid = str(uuid.uuid4())[:8]
        request_id_var.set(rid)
    return rid


def set_request_id(request_id: str) -> None:
    """Set request ID for current context."""
    request_id_var.set(request_id)


def set_component(component: str) -> None:
    """Set component name for current context."""
    component_var.set(component)


# ============================================================================
# Log Directory Setup
# ============================================================================

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_FILE = LOG_DIR / "app.log"


def ensure_log_dir() -> None:
    """Ensure log directory exists."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================================
# JSON Log Formatter
# ============================================================================

class JSONFormatter(logging.Formatter):
    """
    Custom formatter that outputs JSON-structured log entries.

    Format:
    {
        "timestamp": "2026-02-04T10:30:00.000Z",
        "level": "INFO",
        "request_id": "abc12345",
        "component": "api_client",
        "message": "Request completed",
        "context": {...},
        "metrics": {...}
    }
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "request_id": get_request_id(),
            "component": component_var.get() or record.name,
            "message": record.getMessage(),
        }

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
            }

        # Add extra fields if present
        extra_fields = {}
        for key, value in record.__dict__.items():
            if key not in (
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "pathname", "process", "processName", "relativeCreated",
                "stack_info", "exc_info", "exc_text", "thread", "threadName",
                "message", "taskName"
            ):
                extra_fields[key] = value

        if extra_fields:
            # Separate context and metrics
            context = {}
            metrics = {}
            for key, value in extra_fields.items():
                if key.endswith("_ms") or key.endswith("_count") or key.endswith("_rate"):
                    metrics[key] = value
                else:
                    context[key] = value

            if context:
                log_entry["context"] = context
            if metrics:
                log_entry["metrics"] = metrics

        return json.dumps(log_entry, default=str)


# ============================================================================
# Logger Setup
# ============================================================================

def setup_logging(
    level: str = "INFO",
    json_output: bool = True,
    log_to_file: bool = True,
    log_to_console: bool = True
) -> logging.Logger:
    """
    Configure application logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        json_output: If True, output JSON format; if False, human-readable
        log_to_file: If True, write logs to file
        log_to_console: If True, write logs to console

    Returns:
        Configured root logger
    """
    ensure_log_dir()

    # Get root logger for the application
    logger = logging.getLogger("travel_ranker")
    logger.setLevel(getattr(logging, level.upper()))
    logger.handlers = []  # Clear existing handlers

    # Create formatters
    if json_output:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

    # Console handler
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # File handler
    if log_to_file:
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for a specific component.

    Args:
        name: Component name (e.g., 'api_client', 'cache', 'scoring')

    Returns:
        Logger instance
    """
    return logging.getLogger(f"travel_ranker.{name}")


# ============================================================================
# Structlog Configuration (if available)
# ============================================================================

if STRUCTLOG_AVAILABLE:
    def setup_structlog(
        level: str = "INFO",
        json_output: bool = True
    ) -> None:
        """
        Configure structlog for enhanced structured logging.

        Args:
            level: Log level
            json_output: If True, output JSON; if False, console output
        """
        ensure_log_dir()

        # Configure processors
        shared_processors = [
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
        ]

        if json_output:
            processors = shared_processors + [
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer()
            ]
        else:
            processors = shared_processors + [
                structlog.dev.ConsoleRenderer(colors=True)
            ]

        structlog.configure(
            processors=processors,
            wrapper_class=structlog.make_filtering_bound_logger(
                getattr(logging, level.upper())
            ),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )

    def get_structlog_logger(name: str = "") -> "structlog.BoundLogger":
        """Get a structlog logger."""
        return structlog.get_logger(name)


# ============================================================================
# Logging Decorators
# ============================================================================

def log_function_call(
    logger: Optional[logging.Logger] = None,
    level: str = "DEBUG",
    include_args: bool = False,
    include_result: bool = False
) -> Callable:
    """
    Decorator to log function entry and exit.

    Args:
        logger: Logger to use (defaults to function's module logger)
        level: Log level for entries
        include_args: If True, log function arguments
        include_result: If True, log function result

    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal logger
            if logger is None:
                logger = get_logger(func.__module__.split(".")[-1])

            log_level = getattr(logging, level.upper())
            func_name = func.__qualname__

            # Log entry
            entry_msg = f"Entering {func_name}"
            extra = {"function": func_name}
            if include_args:
                extra["args"] = str(args)[:200]  # Truncate long args
                extra["kwargs"] = str(kwargs)[:200]
            logger.log(log_level, entry_msg, extra=extra)

            # Execute function
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                elapsed_ms = (time.time() - start_time) * 1000

                # Log success
                exit_msg = f"Exiting {func_name}"
                extra = {"function": func_name, "duration_ms": round(elapsed_ms, 2)}
                if include_result:
                    extra["result"] = str(result)[:200]
                logger.log(log_level, exit_msg, extra=extra)

                return result

            except Exception as e:
                elapsed_ms = (time.time() - start_time) * 1000
                logger.error(
                    f"Exception in {func_name}: {e}",
                    extra={
                        "function": func_name,
                        "duration_ms": round(elapsed_ms, 2),
                        "error_type": type(e).__name__,
                    },
                    exc_info=True
                )
                raise

        return wrapper
    return decorator


def log_api_call(api_name: str) -> Callable:
    """
    Decorator specifically for API calls with metrics.

    Args:
        api_name: Name of the API being called

    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger = get_logger("api_client")
            start_time = time.time()

            logger.info(
                f"API call started: {api_name}",
                extra={
                    "api": api_name,
                    "operation": func.__name__,
                }
            )

            try:
                result = func(*args, **kwargs)
                elapsed_ms = (time.time() - start_time) * 1000

                logger.info(
                    f"API call completed: {api_name}",
                    extra={
                        "api": api_name,
                        "operation": func.__name__,
                        "latency_ms": round(elapsed_ms, 2),
                        "success": True,
                    }
                )
                return result

            except Exception as e:
                elapsed_ms = (time.time() - start_time) * 1000
                logger.error(
                    f"API call failed: {api_name}",
                    extra={
                        "api": api_name,
                        "operation": func.__name__,
                        "latency_ms": round(elapsed_ms, 2),
                        "success": False,
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                    }
                )
                raise

        return wrapper
    return decorator


# ============================================================================
# Metrics Collection
# ============================================================================

class MetricsCollector:
    """
    Simple metrics collector for tracking application metrics.

    Tracks:
    - API request latency
    - Error rates
    - Cache hit rates
    - Data quality scores
    """

    def __init__(self):
        self._metrics: Dict[str, Any] = {
            "api_requests": {},
            "cache_stats": {"hits": 0, "misses": 0},
            "errors": {},
            "data_quality": [],
        }

    def record_api_latency(self, api: str, latency_ms: float) -> None:
        """Record API request latency."""
        if api not in self._metrics["api_requests"]:
            self._metrics["api_requests"][api] = {
                "count": 0,
                "total_ms": 0,
                "min_ms": float("inf"),
                "max_ms": 0,
            }

        stats = self._metrics["api_requests"][api]
        stats["count"] += 1
        stats["total_ms"] += latency_ms
        stats["min_ms"] = min(stats["min_ms"], latency_ms)
        stats["max_ms"] = max(stats["max_ms"], latency_ms)

    def record_cache_hit(self) -> None:
        """Record cache hit."""
        self._metrics["cache_stats"]["hits"] += 1

    def record_cache_miss(self) -> None:
        """Record cache miss."""
        self._metrics["cache_stats"]["misses"] += 1

    def record_error(self, error_type: str) -> None:
        """Record error occurrence."""
        if error_type not in self._metrics["errors"]:
            self._metrics["errors"][error_type] = 0
        self._metrics["errors"][error_type] += 1

    def record_data_quality(self, score: float) -> None:
        """Record data quality score."""
        self._metrics["data_quality"].append(score)
        # Keep last 100 scores
        if len(self._metrics["data_quality"]) > 100:
            self._metrics["data_quality"] = self._metrics["data_quality"][-100:]

    def get_metrics(self) -> Dict[str, Any]:
        """Get all collected metrics."""
        # Calculate derived metrics
        cache_stats = self._metrics["cache_stats"]
        total_cache = cache_stats["hits"] + cache_stats["misses"]
        cache_hit_rate = (
            cache_stats["hits"] / total_cache if total_cache > 0 else 0
        )

        api_metrics = {}
        for api, stats in self._metrics["api_requests"].items():
            api_metrics[api] = {
                **stats,
                "avg_ms": stats["total_ms"] / stats["count"] if stats["count"] > 0 else 0,
            }

        dq_scores = self._metrics["data_quality"]
        avg_quality = sum(dq_scores) / len(dq_scores) if dq_scores else 0

        return {
            "api_requests": api_metrics,
            "cache_hit_rate": round(cache_hit_rate, 3),
            "errors": self._metrics["errors"],
            "avg_data_quality": round(avg_quality, 1),
        }

    def reset(self) -> None:
        """Reset all metrics."""
        self.__init__()


# Global metrics collector
metrics = MetricsCollector()


# ============================================================================
# Initialize Default Logger
# ============================================================================

# Set up default logging configuration
_default_logger = setup_logging(level="INFO", json_output=True)
