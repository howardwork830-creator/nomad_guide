"""
API clients for SerpApi (flights) and ExchangeRate-API (currency).

Enhanced with:
- Retry logic with exponential backoff (tenacity)
- Circuit breaker pattern for resilience
- Pydantic validation for responses
- Structured logging
- Rate limit handling
"""

import os
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional

import requests
from dotenv import load_dotenv

try:
    from tenacity import (
        retry,
        stop_after_attempt,
        wait_exponential,
        retry_if_exception_type,
        before_sleep_log,
        RetryError
    )
    TENACITY_AVAILABLE = True
except ImportError:
    TENACITY_AVAILABLE = False

from utils.logging_config import get_logger, log_api_call, metrics
from utils.circuit_breaker import (
    get_circuit_breaker,
    CircuitBreakerOpenError
)
from utils.validators import (
    FlightPriceResponse,
    ExchangeRateResponse,
    validate_exchange_rate,
    validate_flight_cost,
)
from utils.data_quality import DataWithProvenance, DataSource

# Load environment variables
load_dotenv()

# Logger
logger = get_logger("api_client")

# Data paths
DATA_DIR = Path(__file__).parent.parent / "data"
COL_DATA_PATH = DATA_DIR / "col_data.json"
COUNTRIES_PATH = DATA_DIR / "countries.json"
BASELINES_V2_PATH = DATA_DIR / "baselines_v2.json"


# ============================================================================
# Retry Configuration
# ============================================================================

def create_retry_decorator(api_name: str):
    """
    Create a retry decorator for API calls.

    Args:
        api_name: Name of API for logging

    Returns:
        Retry decorator or passthrough if tenacity unavailable
    """
    if not TENACITY_AVAILABLE:
        return lambda f: f

    return retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((
            requests.RequestException,
            requests.Timeout,
            ConnectionError,
        )),
        before_sleep=before_sleep_log(logger, log_level=20),  # INFO level
        reraise=True
    )


# ============================================================================
# Rate Limit Handler
# ============================================================================

class RateLimitHandler:
    """
    Handles rate limiting with backoff strategy.
    """

    def __init__(self, api_name: str):
        self.api_name = api_name
        self.last_429_time: Optional[datetime] = None
        self.backoff_until: Optional[datetime] = None
        self.consecutive_429s = 0

    def check_rate_limit(self) -> bool:
        """
        Check if we should make a request or wait.

        Returns:
            True if request can proceed, False if should wait
        """
        if self.backoff_until and datetime.now() < self.backoff_until:
            remaining = (self.backoff_until - datetime.now()).total_seconds()
            logger.warning(
                f"Rate limit backoff active for {self.api_name}",
                extra={"backoff_remaining_seconds": remaining}
            )
            return False
        return True

    def handle_429(self, retry_after: Optional[int] = None) -> None:
        """
        Handle 429 rate limit response.

        Args:
            retry_after: Retry-After header value in seconds
        """
        self.consecutive_429s += 1
        self.last_429_time = datetime.now()

        # Calculate backoff time
        if retry_after:
            backoff_seconds = retry_after
        else:
            # Exponential backoff: 60, 120, 240, 480... capped at 30 minutes
            backoff_seconds = min(60 * (2 ** (self.consecutive_429s - 1)), 1800)

        self.backoff_until = datetime.now() + timedelta(seconds=backoff_seconds)

        logger.warning(
            f"Rate limit hit for {self.api_name}",
            extra={
                "consecutive_429s": self.consecutive_429s,
                "backoff_seconds": backoff_seconds,
            }
        )
        metrics.record_error("rate_limit_429")

    def reset(self) -> None:
        """Reset rate limit state after successful request."""
        self.consecutive_429s = 0
        self.backoff_until = None


# ============================================================================
# SerpApi Client
# ============================================================================

class SerpApiClient:
    """Client for SerpApi Google Flights with resilience features."""

    BASE_URL = "https://serpapi.com/search"

    def __init__(self):
        self.api_key = os.getenv("SERPAPI_KEY", "")
        self.circuit_breaker = get_circuit_breaker("serpapi")
        self.rate_limiter = RateLimitHandler("serpapi")

    @property
    def is_configured(self) -> bool:
        """Check if API key is configured."""
        return bool(self.api_key)

    def _make_request(
        self,
        params: Dict[str, Any],
        timeout: int = 30
    ) -> Optional[Dict[str, Any]]:
        """
        Make HTTP request with error handling.

        Args:
            params: Request parameters
            timeout: Request timeout in seconds

        Returns:
            JSON response or None
        """
        # Check circuit breaker
        if not self.circuit_breaker.can_execute():
            logger.warning("SerpApi circuit breaker is open")
            raise CircuitBreakerOpenError("SerpApi circuit breaker is open")

        # Check rate limit
        if not self.rate_limiter.check_rate_limit():
            return None

        start_time = time.time()

        try:
            response = requests.get(
                self.BASE_URL,
                params={**params, "api_key": self.api_key},
                timeout=timeout
            )

            latency_ms = (time.time() - start_time) * 1000
            metrics.record_api_latency("serpapi", latency_ms)

            # Handle rate limiting
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                self.rate_limiter.handle_429(
                    int(retry_after) if retry_after else None
                )
                self.circuit_breaker.record_failure()
                return None

            response.raise_for_status()
            data = response.json()

            # Check for API error in response
            if "error" in data:
                logger.error(
                    f"SerpApi error response: {data['error']}",
                    extra={"error": data["error"]}
                )
                self.circuit_breaker.record_failure()
                return None

            self.circuit_breaker.record_success()
            self.rate_limiter.reset()
            return data

        except requests.Timeout:
            logger.error("SerpApi request timeout")
            self.circuit_breaker.record_failure()
            metrics.record_error("timeout")
            raise

        except requests.RequestException as e:
            logger.error(
                f"SerpApi request error: {e}",
                extra={"error_type": type(e).__name__}
            )
            self.circuit_breaker.record_failure()
            metrics.record_error("request_error")
            raise

    @log_api_call("serpapi")
    def get_flight_price(
        self,
        origin: str,
        destination: str,
        departure_date: Optional[str] = None,
        return_date: Optional[str] = None
    ) -> Optional[DataWithProvenance]:
        """
        Get lowest flight price for route using SerpApi Google Flights.

        Args:
            origin: Origin airport code (e.g., 'TPE')
            destination: Destination airport code (e.g., 'NRT')
            departure_date: Departure date (YYYY-MM-DD), defaults to 30 days out
            return_date: Return date, defaults to 7 days after departure

        Returns:
            DataWithProvenance with price in TWD, or None if unavailable
        """
        if not self.is_configured:
            logger.debug("SerpApi not configured, skipping")
            return None

        # Default dates: 30 days out, 7 day trip
        if not departure_date:
            departure_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        if not return_date:
            dep = datetime.strptime(departure_date, "%Y-%m-%d")
            return_date = (dep + timedelta(days=7)).strftime("%Y-%m-%d")

        params = {
            "engine": "google_flights",
            "departure_id": origin,
            "arrival_id": destination,
            "outbound_date": departure_date,
            "return_date": return_date,
            "currency": "TWD",
            "hl": "en",
        }

        # Retry wrapper
        if TENACITY_AVAILABLE:
            @create_retry_decorator("serpapi")
            def fetch():
                return self._make_request(params)

            try:
                data = fetch()
            except RetryError:
                logger.error("SerpApi max retries exceeded")
                return None
            except CircuitBreakerOpenError:
                return None
        else:
            try:
                data = self._make_request(params)
            except (requests.RequestException, CircuitBreakerOpenError):
                return None

        if not data:
            return None

        # Extract prices from best_flights or other_flights
        prices = []

        for flight in data.get("best_flights", []):
            price = flight.get("price")
            if price:
                prices.append(float(price))

        for flight in data.get("other_flights", []):
            price = flight.get("price")
            if price:
                prices.append(float(price))

        if not prices:
            logger.warning(
                f"No prices found for {origin}-{destination}",
                extra={"origin": origin, "destination": destination}
            )
            return None

        min_price = min(prices)

        # Validate the price
        validation = validate_flight_cost(min_price, origin, destination)
        if not validation.is_valid:
            logger.warning(
                f"Invalid flight price: {validation.errors}",
                extra={"price": min_price, "errors": validation.errors}
            )
            return None

        # Return with provenance
        result = DataWithProvenance.from_api(
            value=min_price,
            field_name="flight_cost",
            quality_score=validation.confidence * 100
        )
        result.validation_warnings = validation.warnings

        logger.info(
            f"Flight price retrieved: {origin}-{destination} = {min_price} TWD",
            extra={
                "origin": origin,
                "destination": destination,
                "price": min_price,
                "quality_score": result.quality_score,
            }
        )

        return result


# ============================================================================
# ExchangeRate-API Client
# ============================================================================

class ExchangeRateClient:
    """Client for ExchangeRate-API with resilience features."""

    BASE_URL = "https://v6.exchangerate-api.com/v6"

    def __init__(self):
        self.api_key = os.getenv("EXCHANGERATE_API_KEY", "")
        self.circuit_breaker = get_circuit_breaker("exchange_api")
        self.rate_limiter = RateLimitHandler("exchange_api")

    @property
    def is_configured(self) -> bool:
        """Check if API key is configured."""
        return bool(self.api_key)

    def _make_request(self, url: str, timeout: int = 10) -> Optional[Dict[str, Any]]:
        """
        Make HTTP request with error handling.

        Args:
            url: Full request URL
            timeout: Request timeout

        Returns:
            JSON response or None
        """
        # Check circuit breaker
        if not self.circuit_breaker.can_execute():
            logger.warning("ExchangeRate API circuit breaker is open")
            raise CircuitBreakerOpenError("ExchangeRate API circuit breaker is open")

        # Check rate limit
        if not self.rate_limiter.check_rate_limit():
            return None

        start_time = time.time()

        try:
            response = requests.get(url, timeout=timeout)

            latency_ms = (time.time() - start_time) * 1000
            metrics.record_api_latency("exchange_api", latency_ms)

            # Handle rate limiting
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                self.rate_limiter.handle_429(
                    int(retry_after) if retry_after else None
                )
                self.circuit_breaker.record_failure()
                return None

            response.raise_for_status()
            data = response.json()

            if data.get("result") != "success":
                logger.error(
                    f"ExchangeRate API error: {data.get('error-type')}",
                    extra={"error": data.get("error-type")}
                )
                self.circuit_breaker.record_failure()
                return None

            self.circuit_breaker.record_success()
            self.rate_limiter.reset()
            return data

        except requests.Timeout:
            logger.error("ExchangeRate API request timeout")
            self.circuit_breaker.record_failure()
            metrics.record_error("timeout")
            raise

        except requests.RequestException as e:
            logger.error(
                f"ExchangeRate API request error: {e}",
                extra={"error_type": type(e).__name__}
            )
            self.circuit_breaker.record_failure()
            metrics.record_error("request_error")
            raise

    @log_api_call("exchange_api")
    def get_rates(self, base_currency: str = "TWD") -> Optional[Dict[str, DataWithProvenance]]:
        """
        Get exchange rates with TWD as base.

        Args:
            base_currency: Base currency code

        Returns:
            Dictionary of currency code to DataWithProvenance, or None
        """
        if not self.is_configured:
            logger.debug("ExchangeRate API not configured, skipping")
            return None

        url = f"{self.BASE_URL}/{self.api_key}/latest/{base_currency}"

        # Retry wrapper
        if TENACITY_AVAILABLE:
            @create_retry_decorator("exchange_api")
            def fetch():
                return self._make_request(url)

            try:
                data = fetch()
            except RetryError:
                logger.error("ExchangeRate API max retries exceeded")
                return None
            except CircuitBreakerOpenError:
                return None
        else:
            try:
                data = self._make_request(url)
            except (requests.RequestException, CircuitBreakerOpenError):
                return None

        if not data:
            return None

        raw_rates = data.get("conversion_rates", {})
        if not raw_rates:
            return None

        # Validate and wrap with provenance
        validated_rates = {}
        for currency, rate in raw_rates.items():
            validation = validate_exchange_rate(rate, currency)

            if validation.is_valid:
                result = DataWithProvenance.from_api(
                    value=validation.sanitized_value,
                    field_name=f"exchange_rate_{currency}",
                    quality_score=validation.confidence * 100
                )
                result.validation_warnings = validation.warnings
                validated_rates[currency] = result
            else:
                logger.warning(
                    f"Invalid exchange rate for {currency}: {validation.errors}",
                    extra={"currency": currency, "rate": rate, "errors": validation.errors}
                )

        logger.info(
            f"Exchange rates retrieved: {len(validated_rates)} currencies",
            extra={"currency_count": len(validated_rates)}
        )

        return validated_rates

    @log_api_call("exchange_api")
    def get_rate(
        self,
        target_currency: str,
        base_currency: str = "TWD"
    ) -> Optional[DataWithProvenance]:
        """
        Get single exchange rate.

        Args:
            target_currency: Target currency code
            base_currency: Base currency code

        Returns:
            DataWithProvenance with rate or None
        """
        rates = self.get_rates(base_currency)
        if rates:
            return rates.get(target_currency)
        return None


# ============================================================================
# Cost of Living Data Functions
# ============================================================================

def get_col_data() -> Dict[str, Any]:
    """
    Load embedded cost of living data.

    Returns:
        Dictionary with city CoL data
    """
    try:
        with open(COL_DATA_PATH, "r") as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError) as e:
        logger.error(f"Error loading CoL data: {e}")
        return {"cities": {}}


def get_col_for_country(country_name: str) -> Optional[float]:
    """
    Get monthly cost of living for a country's capital city.

    Args:
        country_name: Country name

    Returns:
        Monthly cost in USD or None
    """
    col_data = get_col_data()
    cities = col_data.get("cities", {})

    # Find city matching country
    for city_name, city_data in cities.items():
        if city_data.get("country") == country_name:
            return city_data.get("monthly_cost_usd")

    return None


# ============================================================================
# Country Data Functions
# ============================================================================

def load_countries() -> Dict[str, Any]:
    """
    Load country configuration data.

    Returns:
        Country configuration dictionary
    """
    try:
        with open(COUNTRIES_PATH, "r") as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError) as e:
        logger.error(f"Error loading countries data: {e}")
        return {"origin": {}, "destinations": {}}


def load_baselines_v2() -> Dict[str, Any]:
    """
    Load enhanced baselines v2 data.

    Returns:
        Baselines v2 dictionary with provenance
    """
    try:
        with open(BASELINES_V2_PATH, "r") as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError) as e:
        logger.warning(f"Error loading baselines_v2 data: {e}, falling back to countries.json")
        return {}


def get_baseline_data(country_key: str) -> Dict[str, DataWithProvenance]:
    """
    Get baseline data for a country with provenance.

    Args:
        country_key: Country key from countries.json

    Returns:
        Dictionary with exchange_rate, flight_cost, col as DataWithProvenance
    """
    # Try baselines_v2 first
    baselines_v2 = load_baselines_v2()
    if baselines_v2 and country_key in baselines_v2.get("baselines", {}):
        baseline = baselines_v2["baselines"][country_key]

        # Parse last_updated for provenance
        exchange_data = baseline.get("exchange_rate", {})
        last_updated_str = exchange_data.get("last_updated", "2026-01-01")
        try:
            baseline_date = datetime.fromisoformat(last_updated_str)
        except ValueError:
            baseline_date = datetime.now()

        result = {}

        # Exchange rate
        if "exchange_rate" in baseline:
            er = baseline["exchange_rate"]
            result["exchange_rate"] = DataWithProvenance.from_baseline(
                value=er["value"],
                field_name="exchange_rate",
                baseline_date=baseline_date
            )
            result["exchange_rate"].quality_score = er.get("confidence", 0.5) * 100

        # Flight cost
        if "flight_cost_twd" in baseline:
            fc = baseline["flight_cost_twd"]
            result["flight_cost"] = DataWithProvenance.from_baseline(
                value=fc["value"],
                field_name="flight_cost",
                baseline_date=baseline_date
            )
            result["flight_cost"].quality_score = fc.get("confidence", 0.5) * 100

        # Cost of living
        if "monthly_col_usd" in baseline:
            col = baseline["monthly_col_usd"]
            result["col"] = DataWithProvenance.from_baseline(
                value=col["value"],
                field_name="col",
                baseline_date=baseline_date
            )
            result["col"].quality_score = col.get("confidence", 0.5) * 100

        return result

    # Fallback to old countries.json format
    countries = load_countries()
    destination = countries.get("destinations", {}).get(country_key)

    if destination:
        baseline = destination.get("baseline", {})
        return {
            "exchange_rate": DataWithProvenance.from_baseline(
                value=baseline.get("exchange_rate", 1.0),
                field_name="exchange_rate"
            ),
            "flight_cost": DataWithProvenance.from_baseline(
                value=baseline.get("flight_cost_twd", 10000),
                field_name="flight_cost"
            ),
            "col": DataWithProvenance.from_baseline(
                value=baseline.get("monthly_col_usd", 1500),
                field_name="col"
            ),
        }

    return {}


def get_mock_flight_cost(country_key: str) -> Optional[float]:
    """
    Get mock/baseline flight cost for a country.

    Args:
        country_key: Country key from countries.json

    Returns:
        Mock flight cost in TWD or None
    """
    baseline_data = get_baseline_data(country_key)
    if "flight_cost" in baseline_data:
        return baseline_data["flight_cost"].value
    return None


def get_mock_exchange_rate(country_key: str) -> Optional[float]:
    """
    Get mock/baseline exchange rate for a country.

    Args:
        country_key: Country key from countries.json

    Returns:
        Mock exchange rate (TWD to foreign) or None
    """
    baseline_data = get_baseline_data(country_key)
    if "exchange_rate" in baseline_data:
        return baseline_data["exchange_rate"].value
    return None
