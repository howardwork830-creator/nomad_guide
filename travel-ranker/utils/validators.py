"""
Data validation framework for the Digital Nomad Destination Ranker.

Provides Pydantic models for API responses and validation functions
for exchange rates, flight costs, and cost of living data.
"""

from dataclasses import dataclass
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple, Any, Literal
import statistics

from pydantic import BaseModel, Field, field_validator, model_validator


# ============================================================================
# Validation Constants
# ============================================================================

VALIDATION_RULES = {
    "exchange_rate": {"min": 0.0001, "max": 100000, "type": float, "null_ok": False},
    "flight_cost_twd": {"min": 1000, "max": 500000, "type": float, "null_ok": False},
    "col_monthly_usd": {"min": 100, "max": 20000, "type": float, "null_ok": False},
    "score": {"min": 0, "max": 100, "type": float, "null_ok": False},
}

# Known exchange rate ranges (1 TWD = X foreign currency)
# Example: USD 0.0315 means 1 TWD buys 0.0315 USD
EXCHANGE_RATE_RANGES = {
    # East Asia
    "JPY": (3.5, 6.0),        # Japan Yen
    "KRW": (35.0, 50.0),      # Korean Won
    "HKD": (0.20, 0.30),      # Hong Kong Dollar
    "CNY": (0.18, 0.28),      # Chinese Yuan
    # Southeast Asia
    "THB": (0.85, 1.25),      # Thai Baht
    "VND": (700.0, 900.0),    # Vietnamese Dong
    "MYR": (0.11, 0.17),      # Malaysian Ringgit
    "IDR": (400.0, 600.0),    # Indonesian Rupiah
    "PHP": (1.5, 2.2),        # Philippine Peso
    "SGD": (0.035, 0.050),    # Singapore Dollar
    "KHR": (100.0, 160.0),    # Cambodian Riel
    "LAK": (550.0, 800.0),    # Lao Kip (high volatility)
    # South Asia
    "INR": (2.2, 3.2),        # Indian Rupee
    "LKR": (8.0, 12.0),       # Sri Lankan Rupee
    "NPR": (3.5, 5.0),        # Nepalese Rupee (pegged to INR)
    # Europe - Major
    "GBP": (0.020, 0.030),    # British Pound
    "EUR": (0.024, 0.035),    # Euro (used by Germany, France, Spain, Portugal, Netherlands, Estonia, Croatia, Greece)
    "CHF": (0.024, 0.032),    # Swiss Franc
    # Europe - Central/Eastern
    "CZK": (0.60, 0.85),      # Czech Koruna
    "PLN": (0.10, 0.15),      # Polish Zloty
    "HUF": (9.0, 14.0),       # Hungarian Forint
    "RON": (0.13, 0.17),      # Romanian Leu
    "BGN": (0.050, 0.065),    # Bulgarian Lev (pegged to EUR)
    "ALL": (2.5, 3.5),        # Albanian Lek
    "GEL": (0.070, 0.100),    # Georgian Lari
    # Americas
    "USD": (0.028, 0.038),    # US Dollar (also used by Panama)
    "CAD": (0.038, 0.052),    # Canadian Dollar
    "MXN": (0.45, 0.65),      # Mexican Peso
    "COP": (100.0, 150.0),    # Colombian Peso
    "ARS": (15.0, 60.0),      # Argentine Peso (high volatility)
    "BRL": (0.13, 0.19),      # Brazilian Real
    "PEN": (0.10, 0.14),      # Peruvian Sol
    "CRC": (13.0, 20.0),      # Costa Rican Colon
    "CLP": (24.0, 36.0),      # Chilean Peso
    # Middle East
    "AED": (0.10, 0.14),      # UAE Dirham (pegged to USD)
    "TRY": (0.8, 1.8),        # Turkish Lira (high volatility)
    "ILS": (0.10, 0.14),      # Israeli Shekel
    "EGP": (1.2, 2.0),        # Egyptian Pound (volatile)
    # Africa
    "MAD": (0.28, 0.38),      # Moroccan Dirham
    "ZAR": (0.45, 0.70),      # South African Rand
    "KES": (3.5, 4.8),        # Kenyan Shilling
    # Oceania
    "AUD": (0.040, 0.060),    # Australian Dollar
    "NZD": (0.045, 0.065),    # New Zealand Dollar
    # Nordic
    "ISK": (3.8, 5.0),        # Icelandic Krona
}


# ============================================================================
# Pydantic Models for API Responses
# ============================================================================

class FlightPriceResponse(BaseModel):
    """Validated flight price response from SerpApi."""

    price: float = Field(ge=0, le=500000, description="Flight price in TWD")
    currency: str = Field(default="TWD", max_length=3)
    departure_date: Optional[date] = None
    return_date: Optional[date] = None
    origin: str = Field(max_length=5, description="Origin airport code")
    destination: str = Field(max_length=5, description="Destination airport code")
    airline: Optional[str] = None
    stops: Optional[int] = Field(default=None, ge=0, le=5)

    @field_validator("price")
    @classmethod
    def validate_price_range(cls, v: float) -> float:
        """Validate price is within reasonable range."""
        if v < 1000:
            raise ValueError(f"Flight price {v} TWD is unreasonably low")
        if v > 500000:
            raise ValueError(f"Flight price {v} TWD is unreasonably high")
        return v

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        """Validate currency code format."""
        return v.upper()


class ExchangeRateResponse(BaseModel):
    """Validated exchange rate response."""

    base_code: str = Field(default="TWD", max_length=3)
    rates: Dict[str, float] = Field(default_factory=dict)
    last_update: Optional[datetime] = None

    @field_validator("rates")
    @classmethod
    def validate_rates(cls, v: Dict[str, float]) -> Dict[str, float]:
        """Validate all rates are positive."""
        for currency, rate in v.items():
            if rate <= 0:
                raise ValueError(f"Invalid rate for {currency}: {rate}")
            if rate > 100000:
                raise ValueError(f"Rate for {currency} is unreasonably high: {rate}")
        return v


class CostOfLivingData(BaseModel):
    """Validated cost of living data."""

    city: str
    country: str
    monthly_cost_usd: float = Field(ge=100, le=20000)
    accommodation_usd: Optional[float] = Field(default=None, ge=0, le=15000)
    food_usd: Optional[float] = Field(default=None, ge=0, le=3000)
    transport_usd: Optional[float] = Field(default=None, ge=0, le=1000)
    misc_usd: Optional[float] = Field(default=None, ge=0, le=2000)
    last_updated: Optional[date] = None
    source: Optional[str] = None
    confidence: float = Field(default=0.5, ge=0, le=1.0)


class BaselineData(BaseModel):
    """Validated baseline data for a destination."""

    exchange_rate: float = Field(ge=0.0001, le=100000)
    flight_cost_twd: float = Field(ge=1000, le=500000)
    monthly_col_usd: float = Field(ge=100, le=20000)
    source: str = Field(default="manual")
    confidence: float = Field(default=0.5, ge=0, le=1.0)
    last_updated: Optional[date] = None


# ============================================================================
# Validation Result Types
# ============================================================================

@dataclass
class ValidationResult:
    """Result of a validation operation."""

    is_valid: bool
    sanitized_value: Optional[float]
    errors: List[str]
    warnings: List[str]
    confidence: float  # 0-1 confidence in the value

    @classmethod
    def success(
        cls,
        value: float,
        confidence: float = 1.0,
        warnings: Optional[List[str]] = None
    ) -> "ValidationResult":
        """Create a successful validation result."""
        return cls(
            is_valid=True,
            sanitized_value=value,
            errors=[],
            warnings=warnings or [],
            confidence=confidence
        )

    @classmethod
    def failure(cls, errors: List[str]) -> "ValidationResult":
        """Create a failed validation result."""
        return cls(
            is_valid=False,
            sanitized_value=None,
            errors=errors,
            warnings=[],
            confidence=0.0
        )


# ============================================================================
# Validation Functions
# ============================================================================

def validate_exchange_rate(
    rate: Any,
    currency: str,
    strict: bool = False
) -> ValidationResult:
    """
    Validate an exchange rate value.

    Args:
        rate: Exchange rate value to validate (TWD to foreign currency)
        currency: Target currency code
        strict: If True, fail on warnings; if False, return with warnings

    Returns:
        ValidationResult with is_valid, sanitized_value, errors, and warnings
    """
    errors = []
    warnings = []
    confidence = 1.0

    # Type check
    if rate is None:
        return ValidationResult.failure(["Exchange rate is None"])

    try:
        rate = float(rate)
    except (TypeError, ValueError):
        return ValidationResult.failure([f"Cannot convert rate to float: {rate}"])

    # Basic range check
    rules = VALIDATION_RULES["exchange_rate"]
    if rate < rules["min"]:
        errors.append(f"Rate {rate} is below minimum {rules['min']}")
    if rate > rules["max"]:
        errors.append(f"Rate {rate} is above maximum {rules['max']}")

    if errors:
        return ValidationResult.failure(errors)

    # Currency-specific range check
    currency = currency.upper()
    if currency in EXCHANGE_RATE_RANGES:
        min_rate, max_rate = EXCHANGE_RATE_RANGES[currency]
        if rate < min_rate:
            msg = f"Rate {rate} for {currency} is below expected range ({min_rate}-{max_rate})"
            if strict:
                errors.append(msg)
            else:
                warnings.append(msg)
                confidence *= 0.7
        elif rate > max_rate:
            msg = f"Rate {rate} for {currency} is above expected range ({min_rate}-{max_rate})"
            if strict:
                errors.append(msg)
            else:
                warnings.append(msg)
                confidence *= 0.7
    else:
        warnings.append(f"Unknown currency {currency}, cannot validate expected range")
        confidence *= 0.9

    if errors:
        return ValidationResult.failure(errors)

    return ValidationResult.success(rate, confidence, warnings)


def validate_flight_cost(
    cost: Any,
    origin: str = "TPE",
    destination: str = "",
    strict: bool = False
) -> ValidationResult:
    """
    Validate a flight cost value.

    Args:
        cost: Flight cost in TWD
        origin: Origin airport code
        destination: Destination airport code
        strict: If True, fail on warnings

    Returns:
        ValidationResult with validation status and details
    """
    errors = []
    warnings = []
    confidence = 1.0

    # Type check
    if cost is None:
        return ValidationResult.failure(["Flight cost is None"])

    try:
        cost = float(cost)
    except (TypeError, ValueError):
        return ValidationResult.failure([f"Cannot convert cost to float: {cost}"])

    # Basic range check
    rules = VALIDATION_RULES["flight_cost_twd"]
    if cost < rules["min"]:
        errors.append(f"Cost {cost} TWD is below minimum {rules['min']}")
    if cost > rules["max"]:
        errors.append(f"Cost {cost} TWD is above maximum {rules['max']}")

    if errors:
        return ValidationResult.failure(errors)

    # Route-specific reasonableness checks
    # Flights from TPE to nearby destinations should be cheaper
    nearby_destinations = {"HKG", "MNL", "SGN", "BKK", "KUL", "SIN"}
    far_destinations = {"LHR", "CDG", "FRA", "LAX", "EZE", "BOG"}

    if destination in nearby_destinations:
        if cost > 25000:
            msg = f"Cost {cost} TWD for nearby destination {destination} seems high"
            warnings.append(msg)
            confidence *= 0.8
        elif cost < 2000:
            msg = f"Cost {cost} TWD for {destination} seems unusually low"
            warnings.append(msg)
            confidence *= 0.7

    if destination in far_destinations:
        if cost < 15000:
            msg = f"Cost {cost} TWD for distant destination {destination} seems low"
            warnings.append(msg)
            confidence *= 0.7
        elif cost > 100000:
            msg = f"Cost {cost} TWD for {destination} seems unusually high"
            warnings.append(msg)
            confidence *= 0.8

    return ValidationResult.success(cost, confidence, warnings)


def validate_col_data(
    col: Any,
    country: str = "",
    city: str = "",
    strict: bool = False
) -> ValidationResult:
    """
    Validate cost of living data.

    Args:
        col: Monthly cost of living in USD
        country: Country name
        city: City name
        strict: If True, fail on warnings

    Returns:
        ValidationResult with validation status and details
    """
    errors = []
    warnings = []
    confidence = 1.0

    # Type check
    if col is None:
        return ValidationResult.failure(["Cost of living is None"])

    try:
        col = float(col)
    except (TypeError, ValueError):
        return ValidationResult.failure([f"Cannot convert CoL to float: {col}"])

    # Basic range check
    rules = VALIDATION_RULES["col_monthly_usd"]
    if col < rules["min"]:
        errors.append(f"CoL ${col}/month is below minimum ${rules['min']}")
    if col > rules["max"]:
        errors.append(f"CoL ${col}/month is above maximum ${rules['max']}")

    if errors:
        return ValidationResult.failure(errors)

    # Country-specific reasonableness checks
    high_col_countries = {
        "Singapore", "United Kingdom", "United States", "Australia",
        "Hong Kong", "Netherlands", "France", "Germany", "Switzerland",
        "Iceland", "Israel", "Canada", "New Zealand"
    }
    low_col_countries = {
        "Vietnam", "Indonesia", "India", "Philippines",
        "Thailand", "Colombia", "Argentina", "Mexico",
        "Georgia", "Albania", "Bulgaria", "Romania",
        "Cambodia", "Laos", "Nepal", "Sri Lanka",
        "Egypt", "Morocco", "Kenya", "Peru"
    }

    if country in high_col_countries:
        if col < 1500:
            msg = f"CoL ${col}/month for {country} seems low for this region"
            warnings.append(msg)
            confidence *= 0.8

    if country in low_col_countries:
        if col > 2000:
            msg = f"CoL ${col}/month for {country} seems high for this region"
            warnings.append(msg)
            confidence *= 0.8
        elif col < 400:
            msg = f"CoL ${col}/month for {country} seems unusually low"
            warnings.append(msg)
            confidence *= 0.7

    return ValidationResult.success(col, confidence, warnings)


def validate_score(score: Any) -> ValidationResult:
    """
    Validate a score value.

    Args:
        score: Score value (0-100)

    Returns:
        ValidationResult with validation status
    """
    if score is None:
        return ValidationResult.failure(["Score is None"])

    try:
        score = float(score)
    except (TypeError, ValueError):
        return ValidationResult.failure([f"Cannot convert score to float: {score}"])

    rules = VALIDATION_RULES["score"]
    if score < rules["min"] or score > rules["max"]:
        return ValidationResult.failure(
            [f"Score {score} is outside valid range [{rules['min']}, {rules['max']}]"]
        )

    return ValidationResult.success(score)


# ============================================================================
# Outlier Detection
# ============================================================================

def detect_outliers(
    values: List[float],
    method: Literal["zscore", "iqr"] = "zscore",
    threshold: float = 3.0
) -> List[int]:
    """
    Detect outliers in a list of values.

    Args:
        values: List of numeric values
        method: Detection method ("zscore" or "iqr")
        threshold: Threshold for outlier detection
            - For zscore: number of standard deviations (default 3.0)
            - For IQR: multiplier for IQR range (default 1.5)

    Returns:
        List of indices of outlier values
    """
    if len(values) < 3:
        return []  # Not enough data for outlier detection

    outlier_indices = []

    if method == "zscore":
        mean = statistics.mean(values)
        stdev = statistics.stdev(values)

        if stdev == 0:
            return []  # All values are the same

        for i, value in enumerate(values):
            z_score = abs((value - mean) / stdev)
            if z_score > threshold:
                outlier_indices.append(i)

    elif method == "iqr":
        sorted_values = sorted(values)
        n = len(sorted_values)
        q1_idx = n // 4
        q3_idx = (3 * n) // 4

        q1 = sorted_values[q1_idx]
        q3 = sorted_values[q3_idx]
        iqr = q3 - q1

        lower_bound = q1 - (threshold * iqr)
        upper_bound = q3 + (threshold * iqr)

        for i, value in enumerate(values):
            if value < lower_bound or value > upper_bound:
                outlier_indices.append(i)

    return outlier_indices


def calculate_data_quality_score(
    data: Dict[str, Any],
    required_fields: Optional[List[str]] = None
) -> float:
    """
    Calculate an overall data quality score (0-100).

    Factors considered:
    - Completeness: presence of required fields
    - Validity: fields pass validation
    - Freshness: data age (if available)
    - Consistency: no outliers in related data

    Args:
        data: Dictionary of data fields
        required_fields: List of required field names

    Returns:
        Quality score from 0-100
    """
    if not data:
        return 0.0

    scores = []

    # Default required fields
    if required_fields is None:
        required_fields = ["exchange_rate", "flight_cost", "col"]

    # Completeness score
    present_fields = sum(1 for f in required_fields if f in data and data[f] is not None)
    completeness = (present_fields / len(required_fields)) * 100 if required_fields else 100
    scores.append(completeness)

    # Validity score based on field validation
    validity_scores = []

    if "exchange_rate" in data and data["exchange_rate"] is not None:
        currency = data.get("currency_code", "USD")
        result = validate_exchange_rate(data["exchange_rate"], currency)
        validity_scores.append(result.confidence * 100 if result.is_valid else 0)

    if "flight_cost" in data and data["flight_cost"] is not None:
        result = validate_flight_cost(data["flight_cost"])
        validity_scores.append(result.confidence * 100 if result.is_valid else 0)

    if "col" in data and data["col"] is not None:
        country = data.get("country", "")
        result = validate_col_data(data["col"], country)
        validity_scores.append(result.confidence * 100 if result.is_valid else 0)

    if validity_scores:
        scores.append(statistics.mean(validity_scores))

    # Freshness score
    if "fetched_at" in data:
        fetched_at = data["fetched_at"]
        if isinstance(fetched_at, datetime):
            age_hours = (datetime.now() - fetched_at).total_seconds() / 3600
            # Full score if < 1 hour, decreases to 50% at 48 hours, 0% at 168 hours (1 week)
            if age_hours < 1:
                freshness = 100
            elif age_hours < 48:
                freshness = 100 - (age_hours / 48) * 50
            elif age_hours < 168:
                freshness = 50 - ((age_hours - 48) / 120) * 50
            else:
                freshness = 0
            scores.append(freshness)

    # Source score
    source_scores = {
        "live_api": 100,
        "api": 100,
        "cache": 90,
        "stale_cache": 60,
        "baseline": 40,
        "mock": 20,
    }
    if "source" in data:
        source = data.get("source", "mock")
        scores.append(source_scores.get(source, 20))

    # Calculate weighted average
    if scores:
        return round(statistics.mean(scores), 1)
    return 50.0  # Default middle score


def validate_all_fields(data: Dict[str, Any]) -> Tuple[bool, Dict[str, ValidationResult]]:
    """
    Validate all data fields and return comprehensive results.

    Args:
        data: Dictionary with exchange_rate, flight_cost, col, etc.

    Returns:
        Tuple of (all_valid, field_results_dict)
    """
    results = {}
    all_valid = True

    if "exchange_rate" in data:
        currency = data.get("currency_code", "USD")
        results["exchange_rate"] = validate_exchange_rate(data["exchange_rate"], currency)
        if not results["exchange_rate"].is_valid:
            all_valid = False

    if "flight_cost" in data:
        origin = data.get("origin", "TPE")
        destination = data.get("destination", "")
        results["flight_cost"] = validate_flight_cost(data["flight_cost"], origin, destination)
        if not results["flight_cost"].is_valid:
            all_valid = False

    if "col" in data:
        country = data.get("country", "")
        city = data.get("city", "")
        results["col"] = validate_col_data(data["col"], country, city)
        if not results["col"].is_valid:
            all_valid = False

    if "score" in data:
        results["score"] = validate_score(data["score"])
        if not results["score"].is_valid:
            all_valid = False

    return all_valid, results
