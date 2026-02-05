"""
Circuit breaker pattern implementation for API resilience.

Provides fault tolerance for external API calls with automatic
recovery after failure thresholds are exceeded.
"""

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
from threading import Lock
from typing import Any, Callable, Dict, Optional, TypeVar

try:
    import pybreaker
    PYBREAKER_AVAILABLE = True
except ImportError:
    PYBREAKER_AVAILABLE = False


# ============================================================================
# Circuit Breaker States
# ============================================================================

class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"        # Normal operation, requests pass through
    OPEN = "open"            # Failure threshold exceeded, requests blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


# ============================================================================
# Configuration
# ============================================================================

@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""

    failure_threshold: int = 5          # Failures before opening circuit
    success_threshold: int = 2          # Successes before closing circuit
    timeout_seconds: float = 60.0       # Time before attempting recovery
    excluded_exceptions: tuple = ()     # Exceptions that don't count as failures

    # Rate limiting
    rate_limit_threshold: int = 10      # Max requests per window
    rate_limit_window: float = 60.0     # Window size in seconds


# Default configurations per API
DEFAULT_CONFIGS = {
    "serpapi": CircuitBreakerConfig(
        failure_threshold=3,
        success_threshold=2,
        timeout_seconds=120.0,  # 2 minutes for external API
    ),
    "exchange_api": CircuitBreakerConfig(
        failure_threshold=5,
        success_threshold=2,
        timeout_seconds=60.0,
    ),
    "default": CircuitBreakerConfig(),
}


# ============================================================================
# Circuit Breaker Implementation
# ============================================================================

@dataclass
class CircuitBreakerStats:
    """Statistics for circuit breaker monitoring."""

    failures: int = 0
    successes: int = 0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    state_changes: int = 0
    total_requests: int = 0
    blocked_requests: int = 0


class SimpleCircuitBreaker:
    """
    Simple circuit breaker implementation without external dependencies.

    States:
    - CLOSED: Normal operation
    - OPEN: Blocking requests after failures
    - HALF_OPEN: Testing if service recovered
    """

    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None
    ):
        """
        Initialize circuit breaker.

        Args:
            name: Identifier for this circuit breaker
            config: Configuration options
        """
        self.name = name
        self.config = config or DEFAULT_CONFIGS.get(name, DEFAULT_CONFIGS["default"])
        self._state = CircuitState.CLOSED
        self._stats = CircuitBreakerStats()
        self._last_state_change = datetime.now()
        self._lock = Lock()

        # Rate limiting
        self._request_times: list = []

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        with self._lock:
            return self._state

    @property
    def stats(self) -> CircuitBreakerStats:
        """Get circuit breaker statistics."""
        return self._stats

    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        return self.state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (blocking requests)."""
        return self.state == CircuitState.OPEN

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt recovery."""
        if self._state != CircuitState.OPEN:
            return False

        timeout = timedelta(seconds=self.config.timeout_seconds)
        return datetime.now() - self._last_state_change >= timeout

    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state."""
        if self._state != new_state:
            self._state = new_state
            self._last_state_change = datetime.now()
            self._stats.state_changes += 1

    def _check_rate_limit(self) -> bool:
        """Check if request is within rate limit."""
        now = time.time()
        window_start = now - self.config.rate_limit_window

        # Clean old requests
        self._request_times = [t for t in self._request_times if t > window_start]

        return len(self._request_times) < self.config.rate_limit_threshold

    def record_success(self) -> None:
        """Record a successful request."""
        with self._lock:
            self._stats.successes += 1
            self._stats.total_requests += 1
            self._stats.consecutive_successes += 1
            self._stats.consecutive_failures = 0
            self._stats.last_success_time = datetime.now()

            if self._state == CircuitState.HALF_OPEN:
                if self._stats.consecutive_successes >= self.config.success_threshold:
                    self._transition_to(CircuitState.CLOSED)

    def record_failure(self, exception: Optional[Exception] = None) -> None:
        """Record a failed request."""
        with self._lock:
            # Check if exception is excluded
            if exception and isinstance(exception, self.config.excluded_exceptions):
                return

            self._stats.failures += 1
            self._stats.total_requests += 1
            self._stats.consecutive_failures += 1
            self._stats.consecutive_successes = 0
            self._stats.last_failure_time = datetime.now()

            if self._state == CircuitState.CLOSED:
                if self._stats.consecutive_failures >= self.config.failure_threshold:
                    self._transition_to(CircuitState.OPEN)
            elif self._state == CircuitState.HALF_OPEN:
                self._transition_to(CircuitState.OPEN)

    def can_execute(self) -> bool:
        """
        Check if a request can be executed.

        Returns:
            True if request should proceed, False if blocked
        """
        with self._lock:
            # Check rate limit first
            if not self._check_rate_limit():
                return False

            if self._state == CircuitState.CLOSED:
                self._request_times.append(time.time())
                return True

            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._transition_to(CircuitState.HALF_OPEN)
                    self._stats.consecutive_successes = 0
                    self._request_times.append(time.time())
                    return True
                self._stats.blocked_requests += 1
                return False

            if self._state == CircuitState.HALF_OPEN:
                self._request_times.append(time.time())
                return True

            return False

    def __call__(self, func: Callable) -> Callable:
        """Decorator to wrap function with circuit breaker."""
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not self.can_execute():
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{self.name}' is OPEN"
                )
            try:
                result = func(*args, **kwargs)
                self.record_success()
                return result
            except self.config.excluded_exceptions:
                raise
            except Exception as e:
                self.record_failure(e)
                raise
        return wrapper

    def reset(self) -> None:
        """Reset circuit breaker to initial state."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._stats = CircuitBreakerStats()
            self._last_state_change = datetime.now()
            self._request_times = []

    def get_status(self) -> Dict[str, Any]:
        """Get current status for monitoring."""
        return {
            "name": self.name,
            "state": self._state.value,
            "stats": {
                "failures": self._stats.failures,
                "successes": self._stats.successes,
                "consecutive_failures": self._stats.consecutive_failures,
                "total_requests": self._stats.total_requests,
                "blocked_requests": self._stats.blocked_requests,
            },
            "last_failure": (
                self._stats.last_failure_time.isoformat()
                if self._stats.last_failure_time else None
            ),
            "last_success": (
                self._stats.last_success_time.isoformat()
                if self._stats.last_success_time else None
            ),
        }


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and blocking requests."""
    pass


# ============================================================================
# Circuit Breaker Registry
# ============================================================================

class CircuitBreakerRegistry:
    """
    Registry for managing multiple circuit breakers.

    Provides a central place to get/create circuit breakers by name.
    """

    def __init__(self):
        self._breakers: Dict[str, SimpleCircuitBreaker] = {}
        self._lock = Lock()

    def get(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None
    ) -> SimpleCircuitBreaker:
        """
        Get or create a circuit breaker by name.

        Args:
            name: Circuit breaker identifier
            config: Optional configuration override

        Returns:
            Circuit breaker instance
        """
        with self._lock:
            if name not in self._breakers:
                breaker_config = config or DEFAULT_CONFIGS.get(name, DEFAULT_CONFIGS["default"])
                self._breakers[name] = SimpleCircuitBreaker(name, breaker_config)
            return self._breakers[name]

    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all circuit breakers."""
        return {name: breaker.get_status() for name, breaker in self._breakers.items()}

    def reset_all(self) -> None:
        """Reset all circuit breakers."""
        with self._lock:
            for breaker in self._breakers.values():
                breaker.reset()


# Global registry instance
circuit_breakers = CircuitBreakerRegistry()


# ============================================================================
# Convenience Functions
# ============================================================================

def get_circuit_breaker(name: str) -> SimpleCircuitBreaker:
    """
    Get a circuit breaker by name from the global registry.

    Args:
        name: Circuit breaker identifier

    Returns:
        Circuit breaker instance
    """
    return circuit_breakers.get(name)


def with_circuit_breaker(name: str):
    """
    Decorator factory for applying circuit breaker to a function.

    Args:
        name: Circuit breaker identifier

    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        breaker = get_circuit_breaker(name)
        return breaker(func)
    return decorator


# ============================================================================
# PyBreaker Integration (if available)
# ============================================================================

if PYBREAKER_AVAILABLE:
    class PyBreakerWrapper:
        """
        Wrapper around pybreaker for advanced circuit breaker functionality.

        Provides:
        - Listener support for monitoring
        - More sophisticated state management
        - Better thread safety
        """

        def __init__(
            self,
            name: str,
            fail_max: int = 5,
            reset_timeout: int = 60
        ):
            """
            Initialize PyBreaker-based circuit breaker.

            Args:
                name: Circuit breaker identifier
                fail_max: Maximum failures before opening
                reset_timeout: Seconds before attempting recovery
            """
            self.name = name
            self._breaker = pybreaker.CircuitBreaker(
                fail_max=fail_max,
                reset_timeout=reset_timeout,
                name=name
            )

        @property
        def state(self) -> str:
            """Get current state name."""
            return self._breaker.current_state

        @property
        def is_closed(self) -> bool:
            """Check if circuit is closed."""
            return self._breaker.current_state == "closed"

        def call(self, func: Callable, *args, **kwargs) -> Any:
            """Execute function through circuit breaker."""
            return self._breaker.call(func, *args, **kwargs)

        def __call__(self, func: Callable) -> Callable:
            """Decorator to wrap function."""
            @wraps(func)
            def wrapper(*args, **kwargs):
                return self._breaker.call(func, *args, **kwargs)
            return wrapper
