"""
Hybrid momentum scoring algorithm for destination ranking.

Enhanced with:
- Input validation using validators module
- Confidence-weighted scoring
- Deterministic results (no random variation)
- Data quality multiplier
- New indicators: Safety, Visa, Travel Accessibility

Scoring weights (v2 - expanded indicators):
- Exchange rate: 20%
- Flight cost: 15%
- Cost of living: 35%
- Safety index: 15%
- Visa ease: 10%
- Travel accessibility: 5%
"""

from typing import Dict, Any, List, Tuple, Optional

from utils.validators import (
    validate_exchange_rate,
    validate_flight_cost,
    validate_col_data,
    validate_score,
)
from utils.data_quality import (
    calculate_confidence_multiplier,
    DestinationDataQuality,
)
from utils.logging_config import get_logger

# Logger
logger = get_logger("scoring")

# Scoring weights (v2 - expanded indicators)
EXCHANGE_WEIGHT = 0.20
FLIGHT_WEIGHT = 0.15
COL_WEIGHT = 0.35
SAFETY_WEIGHT = 0.15
VISA_WEIGHT = 0.10
ACCESS_WEIGHT = 0.05

# Legacy weights (for backwards compatibility)
LEGACY_FLIGHT_WEIGHT = 0.20
LEGACY_EXCHANGE_WEIGHT = 0.30
LEGACY_COL_WEIGHT = 0.50

# Badge thresholds
BADGE_EXCELLENT_THRESHOLD = 85
BADGE_HOT_DEAL_THRESHOLD = 15  # overall change %
BADGE_CURRENCY_WIN_THRESHOLD = 20  # rate change %
BADGE_FLIGHT_DEAL_THRESHOLD = 25  # flight change %
BADGE_DEFLATION_THRESHOLD = 15  # col change %
BADGE_SAFE_HAVEN_THRESHOLD = 85  # safety score
BADGE_EASY_ENTRY_THRESHOLD = 100  # visa score (visa-free)
BADGE_NOMAD_VISA_THRESHOLD = True  # has digital nomad visa
BADGE_WELL_CONNECTED_THRESHOLD = 80  # access score

# Badge styles for HTML rendering (clean, no emoji)
BADGE_STYLES = {
    "EXCELLENT": {"bg": "#E8F5E9", "text": "#2E7D32", "label": "EXCELLENT"},
    "HOT DEAL": {"bg": "#FFEBEE", "text": "#C62828", "label": "HOT DEAL"},
    "CURRENCY WIN": {"bg": "#E3F2FD", "text": "#1565C0", "label": "CURRENCY WIN"},
    "FLIGHT DEAL": {"bg": "#FFF3E0", "text": "#E65100", "label": "FLIGHT DEAL"},
    "DEFLATION": {"bg": "#F3E5F5", "text": "#7B1FA2", "label": "DEFLATION"},
    "SAFE HAVEN": {"bg": "#E0F7FA", "text": "#00695C", "label": "SAFE HAVEN"},
    "EASY ENTRY": {"bg": "#FFF8E1", "text": "#FF6F00", "label": "EASY ENTRY"},
    "NOMAD VISA": {"bg": "#FCE4EC", "text": "#AD1457", "label": "NOMAD VISA"},
    "WELL CONNECTED": {"bg": "#E8EAF6", "text": "#283593", "label": "WELL CONNECTED"},
}


def clip(value: float, min_val: float, max_val: float) -> float:
    """Clip value to range [min_val, max_val]."""
    return max(min_val, min(max_val, value))


def calculate_exchange_score(
    current_rate: float,
    baseline_rate: float,
    currency: str = "USD"
) -> Tuple[float, float, float]:
    """
    Calculate exchange rate score (pure momentum - 100%).

    Higher score = TWD has strengthened (you get more foreign currency per TWD).

    Args:
        current_rate: Current TWD to foreign currency rate
        baseline_rate: Baseline TWD to foreign currency rate
        currency: Currency code for validation

    Returns:
        Tuple of (score, change_percentage, confidence)
    """
    confidence = 1.0

    # Validate inputs
    current_validation = validate_exchange_rate(current_rate, currency)
    if not current_validation.is_valid:
        logger.warning(
            f"Invalid current exchange rate: {current_validation.errors}",
            extra={"rate": current_rate, "currency": currency}
        )
        return 50.0, 0.0, 0.5

    confidence *= current_validation.confidence

    if baseline_rate <= 0:
        logger.warning(f"Invalid baseline rate: {baseline_rate}")
        return 50.0, 0.0, 0.5

    # Rate change percentage (positive = TWD strengthened)
    rate_change_pct = ((current_rate - baseline_rate) / baseline_rate) * 100

    # Map to 0-100 score: -50% change -> 0, 0% -> 50, +50% -> 100
    score = clip((rate_change_pct + 50) * 1, 0, 100)

    return score, rate_change_pct, confidence


def calculate_flight_score(
    current_cost: float,
    baseline_cost: float,
    absolute_min: float = 3000,
    absolute_max: float = 50000,
    origin: str = "TPE",
    destination: str = ""
) -> Tuple[float, float, float]:
    """
    Calculate flight cost score (70% momentum, 30% absolute).

    Lower cost = higher score.

    Args:
        current_cost: Current flight cost in TWD
        baseline_cost: Baseline flight cost in TWD
        absolute_min: Minimum cost for absolute scoring
        absolute_max: Maximum cost for absolute scoring
        origin: Origin airport code
        destination: Destination airport code

    Returns:
        Tuple of (score, change_percentage, confidence)
    """
    confidence = 1.0

    # Validate inputs
    current_validation = validate_flight_cost(current_cost, origin, destination)
    if not current_validation.is_valid:
        logger.warning(
            f"Invalid flight cost: {current_validation.errors}",
            extra={"cost": current_cost}
        )
        return 50.0, 0.0, 0.5

    confidence *= current_validation.confidence

    if baseline_cost <= 0:
        logger.warning(f"Invalid baseline flight cost: {baseline_cost}")
        return 50.0, 0.0, 0.5

    # Momentum component (negative change = positive score)
    cost_change_pct = ((current_cost - baseline_cost) / baseline_cost) * 100
    momentum_score = clip(50 - cost_change_pct, 0, 100)

    # Absolute component (lower cost = higher score)
    cost_range = absolute_max - absolute_min
    if cost_range > 0:
        absolute_score = clip(((absolute_max - current_cost) / cost_range) * 100, 0, 100)
    else:
        absolute_score = 50.0

    # Combined: 70% momentum, 30% absolute
    score = momentum_score * 0.70 + absolute_score * 0.30

    return score, -cost_change_pct, confidence  # Negative because lower cost is better


def calculate_col_score(
    current_col: float,
    baseline_col: float,
    absolute_min: float = 500,
    absolute_max: float = 4000,
    country: str = ""
) -> Tuple[float, float, float]:
    """
    Calculate cost of living score (80% absolute, 20% momentum).

    Lower CoL = higher score.

    Args:
        current_col: Current monthly CoL in USD
        baseline_col: Baseline monthly CoL in USD
        absolute_min: Minimum CoL for absolute scoring
        absolute_max: Maximum CoL for absolute scoring
        country: Country name for validation

    Returns:
        Tuple of (score, change_percentage, confidence)
    """
    confidence = 1.0

    # Validate inputs
    current_validation = validate_col_data(current_col, country)
    if not current_validation.is_valid:
        logger.warning(
            f"Invalid CoL data: {current_validation.errors}",
            extra={"col": current_col, "country": country}
        )
        return 50.0, 0.0, 0.5

    confidence *= current_validation.confidence

    if baseline_col <= 0:
        logger.warning(f"Invalid baseline CoL: {baseline_col}")
        return 50.0, 0.0, 0.5

    # Absolute component (lower CoL = higher score)
    col_range = absolute_max - absolute_min
    if col_range > 0:
        absolute_score = clip(((absolute_max - current_col) / col_range) * 100, 0, 100)
    else:
        absolute_score = 50.0

    # Momentum component (negative change = positive score)
    col_change_pct = ((current_col - baseline_col) / baseline_col) * 100
    momentum_score = clip(50 - col_change_pct, 0, 100)

    # Combined: 80% absolute, 20% momentum
    score = absolute_score * 0.80 + momentum_score * 0.20

    return score, -col_change_pct, confidence  # Negative because lower CoL is better


def calculate_safety_score(safety_index: float) -> Tuple[float, float]:
    """
    Calculate safety score from composite safety index.

    The safety_index is already normalized to 0-100.
    Higher index = safer destination = higher score.

    Args:
        safety_index: Composite safety score (0-100)

    Returns:
        Tuple of (score, confidence)
    """
    if safety_index is None or safety_index < 0:
        logger.warning(f"Invalid safety index: {safety_index}")
        return 50.0, 0.5

    # Safety index is already 0-100, use directly
    score = clip(safety_index, 0, 100)

    # Confidence based on how extreme the score is
    # Very high or very low scores are more certain
    confidence = 0.85 if 30 <= safety_index <= 70 else 0.92

    return score, confidence


def calculate_visa_score(visa_score: float) -> Tuple[float, float]:
    """
    Calculate visa ease score.

    Visa scoring:
    - visa_free: 100
    - visa_on_arrival: 80
    - evisa: 60
    - visa_required: 20

    Args:
        visa_score: Pre-calculated visa score (0-100)

    Returns:
        Tuple of (score, confidence)
    """
    if visa_score is None or visa_score < 0:
        logger.warning(f"Invalid visa score: {visa_score}")
        return 50.0, 0.5

    score = clip(visa_score, 0, 100)

    # High confidence for visa data (relatively static)
    confidence = 0.95

    return score, confidence


def calculate_access_score(access_score: float) -> Tuple[float, float]:
    """
    Calculate travel accessibility score.

    Access scoring considers:
    - Direct flight availability
    - Flight duration
    - Flight frequency

    Args:
        access_score: Pre-calculated access score (0-100)

    Returns:
        Tuple of (score, confidence)
    """
    if access_score is None or access_score < 0:
        logger.warning(f"Invalid access score: {access_score}")
        return 50.0, 0.5

    score = clip(access_score, 0, 100)

    # Moderate confidence (flight schedules can change)
    confidence = 0.85

    return score, confidence


def calculate_destination_score(
    current_exchange_rate: float,
    baseline_exchange_rate: float,
    current_flight_cost: float,
    baseline_flight_cost: float,
    current_col: float,
    baseline_col: float,
    currency: str = "USD",
    country: str = "",
    data_quality: Optional[DestinationDataQuality] = None,
    safety_index: Optional[float] = None,
    visa_score: Optional[float] = None,
    access_score: Optional[float] = None,
    use_expanded_scoring: bool = True
) -> Dict[str, Any]:
    """
    Calculate the overall destination score with component breakdowns.

    Args:
        current_exchange_rate: Current TWD to foreign currency rate
        baseline_exchange_rate: Baseline TWD to foreign currency rate
        current_flight_cost: Current flight cost in TWD
        baseline_flight_cost: Baseline flight cost in TWD
        current_col: Current monthly cost of living in USD
        baseline_col: Baseline monthly cost of living in USD
        currency: Currency code for exchange rate validation
        country: Country name for validation
        data_quality: Optional data quality metadata
        safety_index: Optional safety index score (0-100)
        visa_score: Optional visa ease score (0-100)
        access_score: Optional travel accessibility score (0-100)
        use_expanded_scoring: If True, use 6-indicator scoring; if False, use legacy 3-indicator

    Returns:
        Dictionary with scores and changes for all components
    """
    # Calculate core component scores with validation
    exchange_score, exchange_change, exchange_conf = calculate_exchange_score(
        current_exchange_rate, baseline_exchange_rate, currency
    )
    flight_score, flight_change, flight_conf = calculate_flight_score(
        current_flight_cost, baseline_flight_cost
    )
    col_score, col_change, col_conf = calculate_col_score(
        current_col, baseline_col, country=country
    )

    # Calculate new indicator scores if available and expanded scoring is enabled
    has_expanded_data = (
        use_expanded_scoring and
        safety_index is not None and
        visa_score is not None and
        access_score is not None
    )

    if has_expanded_data:
        # Calculate new indicator scores
        safety_score_val, safety_conf = calculate_safety_score(safety_index)
        visa_score_val, visa_conf = calculate_visa_score(visa_score)
        access_score_val, access_conf = calculate_access_score(access_score)

        # Calculate final weighted score with all 6 indicators
        raw_score = (
            exchange_score * EXCHANGE_WEIGHT +
            flight_score * FLIGHT_WEIGHT +
            col_score * COL_WEIGHT +
            safety_score_val * SAFETY_WEIGHT +
            visa_score_val * VISA_WEIGHT +
            access_score_val * ACCESS_WEIGHT
        )

        # Calculate confidence from all component confidences
        overall_confidence = (
            exchange_conf * EXCHANGE_WEIGHT +
            flight_conf * FLIGHT_WEIGHT +
            col_conf * COL_WEIGHT +
            safety_conf * SAFETY_WEIGHT +
            visa_conf * VISA_WEIGHT +
            access_conf * ACCESS_WEIGHT
        )
    else:
        # Use legacy 3-indicator scoring
        raw_score = (
            exchange_score * LEGACY_EXCHANGE_WEIGHT +
            flight_score * LEGACY_FLIGHT_WEIGHT +
            col_score * LEGACY_COL_WEIGHT
        )

        overall_confidence = (
            exchange_conf * LEGACY_EXCHANGE_WEIGHT +
            flight_conf * LEGACY_FLIGHT_WEIGHT +
            col_conf * LEGACY_COL_WEIGHT
        )

        safety_score_val = None
        safety_conf = None
        visa_score_val = None
        visa_conf = None
        access_score_val = None
        access_conf = None

    # Apply data quality multiplier if available
    if data_quality:
        quality_multiplier = calculate_confidence_multiplier(
            data_quality.overall_quality_score
        )
        final_score = raw_score * quality_multiplier
        overall_confidence = data_quality.overall_quality_score / 100
    else:
        quality_multiplier = calculate_confidence_multiplier(overall_confidence * 100)
        final_score = raw_score * quality_multiplier

    # Calculate overall change (average of momentum-based component changes)
    overall_change = (exchange_change + flight_change + col_change) / 3

    # Build result dictionary
    result = {
        "final_score": round(final_score, 1),
        "raw_score": round(raw_score, 1),
        "overall_change": round(overall_change, 1),
        "quality_multiplier": round(quality_multiplier, 3),
        "confidence": round(overall_confidence, 2),
        "scoring_version": "expanded" if has_expanded_data else "legacy",
        "components": {
            "exchange": {
                "score": round(exchange_score, 1),
                "change": round(exchange_change, 1),
                "current": current_exchange_rate,
                "baseline": baseline_exchange_rate,
                "weight": EXCHANGE_WEIGHT if has_expanded_data else LEGACY_EXCHANGE_WEIGHT,
                "confidence": round(exchange_conf, 2)
            },
            "flight": {
                "score": round(flight_score, 1),
                "change": round(flight_change, 1),
                "current": current_flight_cost,
                "baseline": baseline_flight_cost,
                "weight": FLIGHT_WEIGHT if has_expanded_data else LEGACY_FLIGHT_WEIGHT,
                "confidence": round(flight_conf, 2)
            },
            "col": {
                "score": round(col_score, 1),
                "change": round(col_change, 1),
                "current": current_col,
                "baseline": baseline_col,
                "weight": COL_WEIGHT if has_expanded_data else LEGACY_COL_WEIGHT,
                "confidence": round(col_conf, 2)
            }
        }
    }

    # Add expanded indicator components if available
    if has_expanded_data:
        result["components"]["safety"] = {
            "score": round(safety_score_val, 1),
            "value": safety_index,
            "weight": SAFETY_WEIGHT,
            "confidence": round(safety_conf, 2)
        }
        result["components"]["visa"] = {
            "score": round(visa_score_val, 1),
            "value": visa_score,
            "weight": VISA_WEIGHT,
            "confidence": round(visa_conf, 2)
        }
        result["components"]["access"] = {
            "score": round(access_score_val, 1),
            "value": access_score,
            "weight": ACCESS_WEIGHT,
            "confidence": round(access_conf, 2)
        }

    return result


def assign_badges(
    score_data: Dict[str, Any],
    has_nomad_visa: bool = False
) -> List[str]:
    """
    Assign badges based on score thresholds.

    Badge criteria:
    - EXCELLENT: score >= 85
    - HOT DEAL: overall_change > 15%
    - CURRENCY WIN: rate_change > 20%
    - FLIGHT DEAL: flight_change > 25%
    - DEFLATION: col_change > 15%
    - SAFE HAVEN: safety_score >= 85
    - EASY ENTRY: visa_score == 100 (visa-free)
    - NOMAD VISA: country has digital nomad visa program
    - WELL CONNECTED: access_score >= 80

    Args:
        score_data: Dictionary with score components
        has_nomad_visa: Whether country has digital nomad visa program

    Returns:
        List of badge strings (clean text, no emoji)
    """
    badges = []

    final_score = score_data.get("final_score", 0)
    overall_change = score_data.get("overall_change", 0)
    components = score_data.get("components", {})

    exchange_change = components.get("exchange", {}).get("change", 0)
    flight_change = components.get("flight", {}).get("change", 0)
    col_change = components.get("col", {}).get("change", 0)

    # Core badges
    if final_score >= BADGE_EXCELLENT_THRESHOLD:
        badges.append("EXCELLENT")

    if overall_change > BADGE_HOT_DEAL_THRESHOLD:
        badges.append("HOT DEAL")

    if exchange_change > BADGE_CURRENCY_WIN_THRESHOLD:
        badges.append("CURRENCY WIN")

    if flight_change > BADGE_FLIGHT_DEAL_THRESHOLD:
        badges.append("FLIGHT DEAL")

    if col_change > BADGE_DEFLATION_THRESHOLD:
        badges.append("DEFLATION")

    # New indicator badges (only if expanded scoring data is present)
    safety_data = components.get("safety", {})
    visa_data = components.get("visa", {})
    access_data = components.get("access", {})

    if safety_data:
        safety_score = safety_data.get("value", 0)
        if safety_score and safety_score >= BADGE_SAFE_HAVEN_THRESHOLD:
            badges.append("SAFE HAVEN")

    if visa_data:
        visa_score = visa_data.get("value", 0)
        if visa_score and visa_score >= BADGE_EASY_ENTRY_THRESHOLD:
            badges.append("EASY ENTRY")

    if has_nomad_visa:
        badges.append("NOMAD VISA")

    if access_data:
        access_score = access_data.get("value", 0)
        if access_score and access_score >= BADGE_WELL_CONNECTED_THRESHOLD:
            badges.append("WELL CONNECTED")

    return badges


def get_trend_arrow(change: float) -> str:
    """
    Get trend arrow based on change percentage.

    Args:
        change: Change percentage (positive = improvement)

    Returns:
        Trend arrow character (Unicode, not emoji)
    """
    if change > 10:
        return "▲▲"  # Strong up
    elif change > 3:
        return "▲"   # Up
    elif change > -3:
        return "●"   # Stable
    elif change > -10:
        return "▼"   # Down
    else:
        return "▼▼"  # Strong down


def classify_trend(change: float) -> str:
    """
    Classify trend based on change percentage.

    Returns:
        Trend classification string
    """
    if change > 10:
        return "strong_up"
    elif change > 3:
        return "up"
    elif change > -3:
        return "stable"
    elif change > -10:
        return "down"
    else:
        return "strong_down"


def validate_score_data(score_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate a complete score data dictionary.

    Args:
        score_data: Score data dictionary from calculate_destination_score

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors = []

    # Validate final score
    final_score = score_data.get("final_score")
    result = validate_score(final_score)
    if not result.is_valid:
        errors.extend(result.errors)

    # Validate components
    components = score_data.get("components", {})

    for comp_name in ["exchange", "flight", "col"]:
        comp = components.get(comp_name, {})
        comp_score = comp.get("score")
        result = validate_score(comp_score)
        if not result.is_valid:
            errors.append(f"Invalid {comp_name} score: {result.errors}")

    return len(errors) == 0, errors


def calculate_score_delta(
    current_score_data: Dict[str, Any],
    previous_score_data: Dict[str, Any]
) -> Dict[str, float]:
    """
    Calculate score changes between two score data sets.

    Args:
        current_score_data: Current score data
        previous_score_data: Previous score data

    Returns:
        Dictionary of score deltas
    """
    deltas = {
        "final_score": (
            current_score_data.get("final_score", 0) -
            previous_score_data.get("final_score", 0)
        )
    }

    current_comps = current_score_data.get("components", {})
    previous_comps = previous_score_data.get("components", {})

    for comp_name in ["exchange", "flight", "col"]:
        current = current_comps.get(comp_name, {}).get("score", 0)
        previous = previous_comps.get(comp_name, {}).get("score", 0)
        deltas[f"{comp_name}_score"] = current - previous

    return deltas
