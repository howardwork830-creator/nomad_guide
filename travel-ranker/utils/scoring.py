"""
Hybrid momentum scoring algorithm for destination ranking.

Scoring weights:
- Flight cost: 20%
- Exchange rate: 30%
- Cost of living: 50%
"""

from typing import Dict, Any, List, Tuple


# Scoring weights
FLIGHT_WEIGHT = 0.20
EXCHANGE_WEIGHT = 0.30
COL_WEIGHT = 0.50

# Badge thresholds
BADGE_EXCELLENT_THRESHOLD = 85
BADGE_HOT_DEAL_THRESHOLD = 15  # overall change %
BADGE_CURRENCY_WIN_THRESHOLD = 20  # rate change %
BADGE_FLIGHT_DEAL_THRESHOLD = 25  # flight change %
BADGE_DEFLATION_THRESHOLD = 15  # col change %

# Badge styles for HTML rendering (clean, no emoji)
BADGE_STYLES = {
    "EXCELLENT": {"bg": "#E8F5E9", "text": "#2E7D32", "label": "EXCELLENT"},
    "HOT DEAL": {"bg": "#FFEBEE", "text": "#C62828", "label": "HOT DEAL"},
    "CURRENCY WIN": {"bg": "#E3F2FD", "text": "#1565C0", "label": "CURRENCY WIN"},
    "FLIGHT DEAL": {"bg": "#FFF3E0", "text": "#E65100", "label": "FLIGHT DEAL"},
    "DEFLATION": {"bg": "#F3E5F5", "text": "#7B1FA2", "label": "DEFLATION"},
}


def clip(value: float, min_val: float, max_val: float) -> float:
    """Clip value to range [min_val, max_val]."""
    return max(min_val, min(max_val, value))


def calculate_exchange_score(current_rate: float, baseline_rate: float) -> Tuple[float, float]:
    """
    Calculate exchange rate score (pure momentum - 100%).

    Higher score = TWD has strengthened (you get more foreign currency per TWD).

    Returns:
        Tuple of (score, change_percentage)
    """
    if baseline_rate <= 0:
        return 50.0, 0.0

    # Rate change percentage (positive = TWD strengthened)
    rate_change_pct = ((current_rate - baseline_rate) / baseline_rate) * 100

    # Map to 0-100 score: -50% change -> 0, 0% -> 50, +50% -> 100
    score = clip((rate_change_pct + 50) * 1, 0, 100)

    return score, rate_change_pct


def calculate_flight_score(
    current_cost: float,
    baseline_cost: float,
    absolute_min: float = 3000,
    absolute_max: float = 50000
) -> Tuple[float, float]:
    """
    Calculate flight cost score (70% momentum, 30% absolute).

    Lower cost = higher score.

    Returns:
        Tuple of (score, change_percentage)
    """
    if baseline_cost <= 0:
        return 50.0, 0.0

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

    return score, -cost_change_pct  # Negative because lower cost is better


def calculate_col_score(
    current_col: float,
    baseline_col: float,
    absolute_min: float = 500,
    absolute_max: float = 4000
) -> Tuple[float, float]:
    """
    Calculate cost of living score (80% absolute, 20% momentum).

    Lower CoL = higher score.

    Returns:
        Tuple of (score, change_percentage)
    """
    if baseline_col <= 0:
        return 50.0, 0.0

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

    return score, -col_change_pct  # Negative because lower CoL is better


def calculate_destination_score(
    current_exchange_rate: float,
    baseline_exchange_rate: float,
    current_flight_cost: float,
    baseline_flight_cost: float,
    current_col: float,
    baseline_col: float
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

    Returns:
        Dictionary with scores and changes for all components
    """
    # Calculate component scores
    exchange_score, exchange_change = calculate_exchange_score(
        current_exchange_rate, baseline_exchange_rate
    )
    flight_score, flight_change = calculate_flight_score(
        current_flight_cost, baseline_flight_cost
    )
    col_score, col_change = calculate_col_score(
        current_col, baseline_col
    )

    # Calculate final weighted score
    final_score = (
        exchange_score * EXCHANGE_WEIGHT +
        flight_score * FLIGHT_WEIGHT +
        col_score * COL_WEIGHT
    )

    # Calculate overall change (average of component changes)
    overall_change = (exchange_change + flight_change + col_change) / 3

    return {
        "final_score": round(final_score, 1),
        "overall_change": round(overall_change, 1),
        "components": {
            "exchange": {
                "score": round(exchange_score, 1),
                "change": round(exchange_change, 1),
                "current": current_exchange_rate,
                "baseline": baseline_exchange_rate,
                "weight": EXCHANGE_WEIGHT
            },
            "flight": {
                "score": round(flight_score, 1),
                "change": round(flight_change, 1),
                "current": current_flight_cost,
                "baseline": baseline_flight_cost,
                "weight": FLIGHT_WEIGHT
            },
            "col": {
                "score": round(col_score, 1),
                "change": round(col_change, 1),
                "current": current_col,
                "baseline": baseline_col,
                "weight": COL_WEIGHT
            }
        }
    }


def assign_badges(score_data: Dict[str, Any]) -> List[str]:
    """
    Assign badges based on score thresholds.

    Badge criteria:
    - EXCELLENT: score >= 85
    - HOT DEAL: overall_change > 15%
    - CURRENCY WIN: rate_change > 20%
    - FLIGHT DEAL: flight_change > 25%
    - DEFLATION: col_change > 15%

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
