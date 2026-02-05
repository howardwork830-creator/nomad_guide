"""
Unit tests for the scoring algorithm.
"""

import pytest
from utils.scoring import (
    calculate_destination_score,
    calculate_exchange_score,
    calculate_flight_score,
    calculate_col_score,
    assign_badges,
    get_trend_arrow,
    classify_trend,
    clip,
    FLIGHT_WEIGHT,
    EXCHANGE_WEIGHT,
    COL_WEIGHT
)


class TestClip:
    """Tests for clip utility function."""

    def test_clip_within_range(self):
        assert clip(50, 0, 100) == 50

    def test_clip_below_min(self):
        assert clip(-10, 0, 100) == 0

    def test_clip_above_max(self):
        assert clip(150, 0, 100) == 100

    def test_clip_at_boundaries(self):
        assert clip(0, 0, 100) == 0
        assert clip(100, 0, 100) == 100


class TestExchangeScore:
    """Tests for exchange rate scoring."""

    def test_no_change(self):
        """No change should give score around 50."""
        score, change, confidence = calculate_exchange_score(1.0, 1.0)
        assert change == 0.0
        assert score == 50.0

    def test_positive_change(self):
        """Currency strengthening should give higher score."""
        # 10% increase in rate (TWD strengthened)
        score, change, confidence = calculate_exchange_score(1.1, 1.0)
        assert abs(change - 10.0) < 0.01  # Allow floating point tolerance
        assert score > 50.0

    def test_negative_change(self):
        """Currency weakening should give lower score."""
        # 10% decrease in rate (TWD weakened)
        score, change, confidence = calculate_exchange_score(0.9, 1.0)
        assert abs(change - (-10.0)) < 0.01  # Allow floating point tolerance
        assert score < 50.0

    def test_zero_baseline(self):
        """Zero baseline should return defaults."""
        score, change, confidence = calculate_exchange_score(1.0, 0)
        assert score == 50.0
        assert change == 0.0


class TestFlightScore:
    """Tests for flight cost scoring."""

    def test_no_change(self):
        """No change should give moderate score."""
        score, change, confidence = calculate_flight_score(10000, 10000)
        # Change is inverted (lower cost = positive change)
        assert change == 0.0

    def test_lower_cost(self):
        """Lower cost should give higher score."""
        score, change, confidence = calculate_flight_score(8000, 10000)
        # 20% decrease in cost = positive 20% change
        assert change == 20.0
        assert score > 50.0

    def test_higher_cost(self):
        """Higher cost should give lower score."""
        score, change, confidence = calculate_flight_score(12000, 10000)
        # 20% increase in cost = negative 20% change
        assert change == -20.0
        assert score < 50.0

    def test_absolute_component(self):
        """Verify absolute component affects score."""
        # Same percentage change but different absolute values
        score_cheap, _, _ = calculate_flight_score(5000, 5000)
        score_expensive, _, _ = calculate_flight_score(40000, 40000)
        # Cheaper absolute should score higher
        assert score_cheap > score_expensive


class TestColScore:
    """Tests for cost of living scoring."""

    def test_no_change(self):
        """No change should give moderate score."""
        score, change, confidence = calculate_col_score(1500, 1500)
        assert change == 0.0

    def test_lower_col(self):
        """Lower CoL should give higher score."""
        score, change, confidence = calculate_col_score(1200, 1500)
        assert change == 20.0  # 20% decrease = positive change
        assert score > 50.0

    def test_higher_col(self):
        """Higher CoL should give lower score than baseline at same CoL."""
        score_higher, change, _ = calculate_col_score(1800, 1500)
        score_baseline, _, _ = calculate_col_score(1500, 1500)
        assert abs(change - (-20.0)) < 0.01  # 20% increase = negative change
        # Score for higher CoL should be lower than score at baseline
        assert score_higher < score_baseline

    def test_absolute_dominates(self):
        """80% absolute weight should dominate scoring."""
        # Very low CoL city
        score_cheap, _, _ = calculate_col_score(600, 600)
        # Very high CoL city
        score_expensive, _, _ = calculate_col_score(3500, 3500)
        # Cheap city should score much higher due to 80% absolute weight
        assert score_cheap > score_expensive + 30


class TestDestinationScore:
    """Tests for full destination score calculation."""

    def test_weights_sum_to_one(self):
        """Verify weights sum to 1.0."""
        assert FLIGHT_WEIGHT + EXCHANGE_WEIGHT + COL_WEIGHT == 1.0

    def test_baseline_scenario(self):
        """All values at baseline should give moderate score."""
        result = calculate_destination_score(
            current_exchange_rate=1.0,
            baseline_exchange_rate=1.0,
            current_flight_cost=10000,
            baseline_flight_cost=10000,
            current_col=1500,
            baseline_col=1500
        )
        # Score should be moderate (around 50-60 due to absolute components)
        assert 40 <= result["final_score"] <= 70
        assert result["overall_change"] == 0.0

    def test_all_improvements(self):
        """All metrics improving should give high score."""
        result = calculate_destination_score(
            current_exchange_rate=1.2,  # 20% stronger
            baseline_exchange_rate=1.0,
            current_flight_cost=7000,   # 30% cheaper
            baseline_flight_cost=10000,
            current_col=1200,           # 20% lower
            baseline_col=1500
        )
        assert result["final_score"] > 70
        assert result["overall_change"] > 15

    def test_all_deteriorations(self):
        """All metrics worsening should give low score."""
        result = calculate_destination_score(
            current_exchange_rate=0.8,  # 20% weaker
            baseline_exchange_rate=1.0,
            current_flight_cost=13000,  # 30% more expensive
            baseline_flight_cost=10000,
            current_col=1800,           # 20% higher
            baseline_col=1500
        )
        assert result["final_score"] < 50
        assert result["overall_change"] < -15

    def test_japan_example(self):
        """Test Japan example from project.md (approximate)."""
        # Based on project.md example:
        # - Exchange: slight weakening
        # - Flight: moderate decrease
        # - CoL: relatively high but stable
        result = calculate_destination_score(
            current_exchange_rate=0.21,   # Slight decrease
            baseline_exchange_rate=0.22,
            current_flight_cost=7500,     # Lower than baseline
            baseline_flight_cost=8500,
            current_col=1850,             # About same
            baseline_col=1800
        )
        # Should be in reasonable range (60-75)
        assert 55 <= result["final_score"] <= 80

    def test_returns_all_components(self):
        """Verify all expected fields are returned."""
        result = calculate_destination_score(1.0, 1.0, 10000, 10000, 1500, 1500)

        assert "final_score" in result
        assert "overall_change" in result
        assert "components" in result

        for component in ["exchange", "flight", "col"]:
            assert component in result["components"]
            assert "score" in result["components"][component]
            assert "change" in result["components"][component]
            assert "current" in result["components"][component]
            assert "baseline" in result["components"][component]
            assert "weight" in result["components"][component]


class TestBadges:
    """Tests for badge assignment."""

    def test_excellent_badge(self):
        """Score >= 85 should get EXCELLENT badge."""
        score_data = {"final_score": 90, "overall_change": 5, "components": {
            "exchange": {"change": 5},
            "flight": {"change": 5},
            "col": {"change": 5}
        }}
        badges = assign_badges(score_data)
        assert "EXCELLENT" in badges

    def test_hot_deal_badge(self):
        """Overall change > 15% should get HOT DEAL badge."""
        score_data = {"final_score": 70, "overall_change": 20, "components": {
            "exchange": {"change": 20},
            "flight": {"change": 20},
            "col": {"change": 20}
        }}
        badges = assign_badges(score_data)
        assert "HOT DEAL" in badges

    def test_currency_win_badge(self):
        """Exchange change > 20% should get CURRENCY WIN badge."""
        score_data = {"final_score": 60, "overall_change": 10, "components": {
            "exchange": {"change": 25},
            "flight": {"change": 5},
            "col": {"change": 0}
        }}
        badges = assign_badges(score_data)
        assert "CURRENCY WIN" in badges

    def test_flight_deal_badge(self):
        """Flight change > 25% should get FLIGHT DEAL badge."""
        score_data = {"final_score": 60, "overall_change": 10, "components": {
            "exchange": {"change": 5},
            "flight": {"change": 30},
            "col": {"change": 0}
        }}
        badges = assign_badges(score_data)
        assert "FLIGHT DEAL" in badges

    def test_deflation_badge(self):
        """CoL change > 15% should get DEFLATION badge."""
        score_data = {"final_score": 60, "overall_change": 10, "components": {
            "exchange": {"change": 5},
            "flight": {"change": 5},
            "col": {"change": 20}
        }}
        badges = assign_badges(score_data)
        assert "DEFLATION" in badges

    def test_no_badges(self):
        """Moderate values should not earn badges."""
        score_data = {"final_score": 60, "overall_change": 5, "components": {
            "exchange": {"change": 5},
            "flight": {"change": 5},
            "col": {"change": 5}
        }}
        badges = assign_badges(score_data)
        assert len(badges) == 0

    def test_multiple_badges(self):
        """Multiple conditions can earn multiple badges."""
        score_data = {"final_score": 90, "overall_change": 25, "components": {
            "exchange": {"change": 25},
            "flight": {"change": 30},
            "col": {"change": 20}
        }}
        badges = assign_badges(score_data)
        assert len(badges) >= 4  # EXCELLENT, HOT DEAL, CURRENCY WIN, FLIGHT DEAL, DEFLATION


class TestTrendArrow:
    """Tests for trend arrow function."""

    def test_strong_up(self):
        assert get_trend_arrow(15) == "▲▲"

    def test_up(self):
        assert get_trend_arrow(5) == "▲"

    def test_stable(self):
        assert get_trend_arrow(0) == "●"
        assert get_trend_arrow(2) == "●"
        assert get_trend_arrow(-2) == "●"

    def test_down(self):
        assert get_trend_arrow(-5) == "▼"

    def test_strong_down(self):
        assert get_trend_arrow(-15) == "▼▼"


class TestClassifyTrend:
    """Tests for trend classification."""

    def test_strong_up(self):
        assert classify_trend(15) == "strong_up"

    def test_up(self):
        assert classify_trend(5) == "up"

    def test_stable(self):
        assert classify_trend(0) == "stable"

    def test_down(self):
        assert classify_trend(-5) == "down"

    def test_strong_down(self):
        assert classify_trend(-15) == "strong_down"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
