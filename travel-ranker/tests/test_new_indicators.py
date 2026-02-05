"""
Unit tests for new indicators: Safety, Visa, and Travel Accessibility.
Also includes tests for new badges and expanded scoring.
"""

import pytest
from utils.scoring import (
    calculate_safety_score,
    calculate_visa_score,
    calculate_access_score,
    calculate_destination_score,
    assign_badges,
    SAFETY_WEIGHT,
    VISA_WEIGHT,
    ACCESS_WEIGHT,
    EXCHANGE_WEIGHT,
    FLIGHT_WEIGHT,
    COL_WEIGHT,
)


class TestSafetyScore:
    """Tests for safety index scoring."""

    def test_safety_score_valid_input(self):
        """Valid safety index returns correct score."""
        score, confidence = calculate_safety_score(75.0)
        assert score == 75.0
        assert 0.8 <= confidence <= 1.0

    def test_safety_score_none_input(self):
        """None returns default 50.0 with low confidence."""
        score, confidence = calculate_safety_score(None)
        assert score == 50.0
        assert confidence == 0.5

    def test_safety_score_negative_input(self):
        """Negative returns default 50.0 with low confidence."""
        score, confidence = calculate_safety_score(-10)
        assert score == 50.0
        assert confidence == 0.5

    def test_safety_score_high_value(self):
        """Score >= 85 gives high confidence."""
        score, confidence = calculate_safety_score(90.0)
        assert score == 90.0
        assert confidence == 0.92  # High confidence for extreme values

    def test_safety_score_mid_value(self):
        """Score 30-70 gives moderate confidence."""
        score, confidence = calculate_safety_score(50.0)
        assert score == 50.0
        assert confidence == 0.85  # Moderate confidence

    def test_safety_score_clipped_high(self):
        """Score > 100 is clipped to 100."""
        score, confidence = calculate_safety_score(120.0)
        assert score == 100.0

    def test_safety_score_zero(self):
        """Zero is a valid safety score."""
        score, confidence = calculate_safety_score(0.0)
        assert score == 0.0
        assert confidence == 0.92  # Extreme value


class TestVisaScore:
    """Tests for visa ease scoring."""

    def test_visa_score_visa_free(self):
        """100 points for visa-free."""
        score, confidence = calculate_visa_score(100)
        assert score == 100.0
        assert confidence == 0.95

    def test_visa_score_voa(self):
        """80 points for visa-on-arrival."""
        score, confidence = calculate_visa_score(80)
        assert score == 80.0
        assert confidence == 0.95

    def test_visa_score_evisa(self):
        """60 points for e-visa."""
        score, confidence = calculate_visa_score(60)
        assert score == 60.0
        assert confidence == 0.95

    def test_visa_score_required(self):
        """20 points for visa required."""
        score, confidence = calculate_visa_score(20)
        assert score == 20.0
        assert confidence == 0.95

    def test_visa_score_high_confidence(self):
        """Visa scores always return 0.95 confidence."""
        for visa_val in [20, 60, 80, 100]:
            _, confidence = calculate_visa_score(visa_val)
            assert confidence == 0.95

    def test_visa_score_none_input(self):
        """None returns default 50.0 with low confidence."""
        score, confidence = calculate_visa_score(None)
        assert score == 50.0
        assert confidence == 0.5

    def test_visa_score_negative_input(self):
        """Negative returns default 50.0."""
        score, confidence = calculate_visa_score(-10)
        assert score == 50.0
        assert confidence == 0.5


class TestAccessScore:
    """Tests for travel accessibility scoring."""

    def test_access_score_valid_input(self):
        """Valid score returns correctly."""
        score, confidence = calculate_access_score(85.0)
        assert score == 85.0
        assert confidence == 0.85

    def test_access_score_direct_flight_bonus(self):
        """Higher access scores represent better connectivity."""
        high_score, _ = calculate_access_score(95.0)
        low_score, _ = calculate_access_score(50.0)
        assert high_score > low_score

    def test_access_score_none_input(self):
        """None returns default 50.0."""
        score, confidence = calculate_access_score(None)
        assert score == 50.0
        assert confidence == 0.5

    def test_access_score_confidence(self):
        """Returns 0.85 confidence for valid inputs."""
        _, confidence = calculate_access_score(75.0)
        assert confidence == 0.85

    def test_access_score_clipped(self):
        """Score > 100 is clipped to 100."""
        score, _ = calculate_access_score(150.0)
        assert score == 100.0

    def test_access_score_negative_input(self):
        """Negative returns default 50.0."""
        score, confidence = calculate_access_score(-5)
        assert score == 50.0
        assert confidence == 0.5


class TestNewBadges:
    """Tests for new badge assignments."""

    def test_badge_safe_haven(self):
        """Safety >= 85 triggers SAFE HAVEN badge."""
        score_data = {
            "final_score": 70,
            "overall_change": 5,
            "components": {
                "exchange": {"change": 5},
                "flight": {"change": 5},
                "col": {"change": 5},
                "safety": {"score": 90, "value": 90},
                "visa": {"score": 60, "value": 60},
                "access": {"score": 70, "value": 70},
            }
        }
        badges = assign_badges(score_data)
        assert "SAFE HAVEN" in badges

    def test_badge_safe_haven_threshold(self):
        """Safety = 84 does NOT trigger SAFE HAVEN badge."""
        score_data = {
            "final_score": 70,
            "overall_change": 5,
            "components": {
                "exchange": {"change": 5},
                "flight": {"change": 5},
                "col": {"change": 5},
                "safety": {"score": 84, "value": 84},
            }
        }
        badges = assign_badges(score_data)
        assert "SAFE HAVEN" not in badges

    def test_badge_easy_entry(self):
        """Visa == 100 triggers EASY ENTRY badge."""
        score_data = {
            "final_score": 70,
            "overall_change": 5,
            "components": {
                "exchange": {"change": 5},
                "flight": {"change": 5},
                "col": {"change": 5},
                "visa": {"score": 100, "value": 100},
            }
        }
        badges = assign_badges(score_data)
        assert "EASY ENTRY" in badges

    def test_badge_easy_entry_threshold(self):
        """Visa = 80 (VOA) does NOT trigger EASY ENTRY badge."""
        score_data = {
            "final_score": 70,
            "overall_change": 5,
            "components": {
                "exchange": {"change": 5},
                "flight": {"change": 5},
                "col": {"change": 5},
                "visa": {"score": 80, "value": 80},
            }
        }
        badges = assign_badges(score_data)
        assert "EASY ENTRY" not in badges

    def test_badge_nomad_visa(self):
        """has_nomad_visa=True triggers NOMAD VISA badge."""
        score_data = {
            "final_score": 70,
            "overall_change": 5,
            "components": {
                "exchange": {"change": 5},
                "flight": {"change": 5},
                "col": {"change": 5},
            }
        }
        badges = assign_badges(score_data, has_nomad_visa=True)
        assert "NOMAD VISA" in badges

    def test_badge_nomad_visa_false(self):
        """has_nomad_visa=False does NOT trigger NOMAD VISA badge."""
        score_data = {
            "final_score": 70,
            "overall_change": 5,
            "components": {
                "exchange": {"change": 5},
                "flight": {"change": 5},
                "col": {"change": 5},
            }
        }
        badges = assign_badges(score_data, has_nomad_visa=False)
        assert "NOMAD VISA" not in badges

    def test_badge_well_connected(self):
        """Access >= 80 triggers WELL CONNECTED badge."""
        score_data = {
            "final_score": 70,
            "overall_change": 5,
            "components": {
                "exchange": {"change": 5},
                "flight": {"change": 5},
                "col": {"change": 5},
                "access": {"score": 85, "value": 85},
            }
        }
        badges = assign_badges(score_data)
        assert "WELL CONNECTED" in badges

    def test_badge_well_connected_threshold(self):
        """Access = 79 does NOT trigger WELL CONNECTED badge."""
        score_data = {
            "final_score": 70,
            "overall_change": 5,
            "components": {
                "exchange": {"change": 5},
                "flight": {"change": 5},
                "col": {"change": 5},
                "access": {"score": 79, "value": 79},
            }
        }
        badges = assign_badges(score_data)
        assert "WELL CONNECTED" not in badges

    def test_multiple_new_badges(self):
        """Multiple badges can be assigned together."""
        score_data = {
            "final_score": 90,
            "overall_change": 20,
            "components": {
                "exchange": {"change": 25},
                "flight": {"change": 30},
                "col": {"change": 20},
                "safety": {"score": 90, "value": 90},
                "visa": {"score": 100, "value": 100},
                "access": {"score": 85, "value": 85},
            }
        }
        badges = assign_badges(score_data, has_nomad_visa=True)
        # Should have: EXCELLENT, HOT DEAL, CURRENCY WIN, FLIGHT DEAL, DEFLATION
        # Plus new: SAFE HAVEN, EASY ENTRY, NOMAD VISA, WELL CONNECTED
        assert "SAFE HAVEN" in badges
        assert "EASY ENTRY" in badges
        assert "NOMAD VISA" in badges
        assert "WELL CONNECTED" in badges
        assert "EXCELLENT" in badges
        assert len(badges) >= 8


class TestExpandedDestinationScore:
    """Tests for destination scoring with expanded indicators."""

    def test_destination_score_expanded_weights(self):
        """Verifies 6-indicator weights sum to 1.0."""
        total = EXCHANGE_WEIGHT + FLIGHT_WEIGHT + COL_WEIGHT + SAFETY_WEIGHT + VISA_WEIGHT + ACCESS_WEIGHT
        assert total == 1.0

    def test_destination_score_with_expanded_data(self):
        """Score calculation includes all 6 indicators when data available."""
        result = calculate_destination_score(
            current_exchange_rate=1.0,
            baseline_exchange_rate=1.0,
            current_flight_cost=10000,
            baseline_flight_cost=10000,
            current_col=1500,
            baseline_col=1500,
            safety_index=80.0,
            visa_score=100.0,
            access_score=75.0,
            use_expanded_scoring=True
        )
        assert "final_score" in result
        assert "components" in result
        assert "safety" in result["components"]
        assert "visa" in result["components"]
        assert "access" in result["components"]
        assert result["scoring_version"] == "expanded"

    def test_destination_score_legacy_fallback(self):
        """Falls back to 3 indicators when missing expanded data."""
        result = calculate_destination_score(
            current_exchange_rate=1.0,
            baseline_exchange_rate=1.0,
            current_flight_cost=10000,
            baseline_flight_cost=10000,
            current_col=1500,
            baseline_col=1500,
            safety_index=None,
            visa_score=None,
            access_score=None,
            use_expanded_scoring=True
        )
        assert result["scoring_version"] == "legacy"
        assert "safety" not in result["components"]
        assert "visa" not in result["components"]
        assert "access" not in result["components"]

    def test_destination_score_expanded_vs_legacy(self):
        """Expanded scoring produces different results than legacy."""
        expanded = calculate_destination_score(
            current_exchange_rate=1.0,
            baseline_exchange_rate=1.0,
            current_flight_cost=10000,
            baseline_flight_cost=10000,
            current_col=1500,
            baseline_col=1500,
            safety_index=90.0,
            visa_score=100.0,
            access_score=85.0,
            use_expanded_scoring=True
        )

        legacy = calculate_destination_score(
            current_exchange_rate=1.0,
            baseline_exchange_rate=1.0,
            current_flight_cost=10000,
            baseline_flight_cost=10000,
            current_col=1500,
            baseline_col=1500,
            use_expanded_scoring=False
        )

        # With high safety/visa/access scores, expanded should differ from legacy
        assert expanded["final_score"] != legacy["final_score"]
        assert expanded["scoring_version"] == "expanded"
        assert legacy["scoring_version"] == "legacy"

    def test_destination_score_expanded_components(self):
        """Expanded components have correct structure."""
        result = calculate_destination_score(
            current_exchange_rate=1.0,
            baseline_exchange_rate=1.0,
            current_flight_cost=10000,
            baseline_flight_cost=10000,
            current_col=1500,
            baseline_col=1500,
            safety_index=80.0,
            visa_score=100.0,
            access_score=75.0,
            use_expanded_scoring=True
        )

        # Check safety component
        safety = result["components"]["safety"]
        assert "score" in safety
        assert "value" in safety
        assert "weight" in safety
        assert "confidence" in safety
        assert safety["weight"] == SAFETY_WEIGHT

        # Check visa component
        visa = result["components"]["visa"]
        assert visa["weight"] == VISA_WEIGHT

        # Check access component
        access = result["components"]["access"]
        assert access["weight"] == ACCESS_WEIGHT


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
