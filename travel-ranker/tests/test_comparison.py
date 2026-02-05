"""
Unit tests for the comparison module.
Tests radar charts, comparison summaries, and table data generation.
"""

import pytest
import plotly.graph_objects as go
from utils.comparison import (
    create_comparison_radar_chart,
    create_comparison_bar_chart,
    calculate_comparison_summary,
    get_comparison_table_data,
    normalize_score,
    _has_expanded_data,
    render_comparison_badges_html,
)


# Sample destination data for testing
def create_sample_destination(
    country: str,
    score: float,
    flight_cost: int,
    col: int,
    safety: float = None,
    visa: float = None,
    access: float = None,
    badges: list = None
):
    """Helper to create sample destination data."""
    dest = {
        "Country": country,
        "Score": score,
        "Flight Cost (TWD)": flight_cost,
        "Monthly CoL (USD)": col,
        "Quality": 85,
        "badges_list": badges or [],
        "score_data": {
            "final_score": score,
            "overall_change": 5,
            "components": {
                "exchange": {"score": 55, "change": 5},
                "flight": {"score": 60, "change": 10},
                "col": {"score": 70, "change": 5},
            }
        }
    }
    if safety is not None:
        dest["score_data"]["components"]["safety"] = {"score": safety, "value": safety}
    if visa is not None:
        dest["score_data"]["components"]["visa"] = {"score": visa, "value": visa}
    if access is not None:
        dest["score_data"]["components"]["access"] = {"score": access, "value": access}
    return dest


class TestNormalizeScore:
    """Tests for score normalization utility."""

    def test_normalize_mid_value(self):
        """Mid value normalizes to 50."""
        result = normalize_score(50, 0, 100)
        assert result == 50.0

    def test_normalize_min_value(self):
        """Min value normalizes to 0."""
        result = normalize_score(0, 0, 100)
        assert result == 0.0

    def test_normalize_max_value(self):
        """Max value normalizes to 100."""
        result = normalize_score(100, 0, 100)
        assert result == 100.0

    def test_normalize_same_min_max(self):
        """Same min/max returns 50."""
        result = normalize_score(50, 50, 50)
        assert result == 50.0


class TestRadarChart:
    """Tests for radar chart creation."""

    def test_radar_chart_two_destinations(self):
        """Creates valid figure for 2 destinations."""
        destinations = [
            create_sample_destination("Japan", 75.0, 8000, 1800),
            create_sample_destination("Thailand", 82.0, 6000, 1200),
        ]
        fig = create_comparison_radar_chart(destinations, include_expanded=False)
        assert fig is not None
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 2  # Two traces for two destinations

    def test_radar_chart_three_destinations(self):
        """Creates valid figure for 3 destinations."""
        destinations = [
            create_sample_destination("Japan", 75.0, 8000, 1800),
            create_sample_destination("Thailand", 82.0, 6000, 1200),
            create_sample_destination("Vietnam", 78.0, 5500, 900),
        ]
        fig = create_comparison_radar_chart(destinations, include_expanded=False)
        assert fig is not None
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 3

    def test_radar_chart_empty_list(self):
        """Returns None for empty list."""
        fig = create_comparison_radar_chart([])
        assert fig is None

    def test_radar_chart_with_expanded_data(self):
        """Includes all 6 indicators when expanded data present."""
        destinations = [
            create_sample_destination("Japan", 75.0, 8000, 1800, safety=85, visa=100, access=90),
            create_sample_destination("Thailand", 82.0, 6000, 1200, safety=70, visa=100, access=85),
        ]
        fig = create_comparison_radar_chart(destinations, include_expanded=True)
        assert fig is not None
        # Check that the first trace has 7 points (6 categories + closing point)
        assert len(fig.data[0].r) == 7

    def test_radar_chart_without_expanded_data(self):
        """Shows only 3 indicators when no expanded data."""
        destinations = [
            create_sample_destination("Japan", 75.0, 8000, 1800),
            create_sample_destination("Thailand", 82.0, 6000, 1200),
        ]
        fig = create_comparison_radar_chart(destinations, include_expanded=False)
        assert fig is not None
        # Check that the first trace has 4 points (3 categories + closing point)
        assert len(fig.data[0].r) == 4


class TestBarChart:
    """Tests for bar chart creation."""

    def test_bar_chart_returns_figure(self):
        """Creates valid figure for destinations."""
        destinations = [
            create_sample_destination("Japan", 75.0, 8000, 1800),
            create_sample_destination("Thailand", 82.0, 6000, 1200),
        ]
        fig = create_comparison_bar_chart(destinations, metric="Score")
        assert fig is not None
        assert isinstance(fig, go.Figure)

    def test_bar_chart_empty_list(self):
        """Returns None for empty list."""
        fig = create_comparison_bar_chart([])
        assert fig is None


class TestComparisonSummary:
    """Tests for comparison summary generation."""

    def test_summary_best_overall(self):
        """Correctly identifies best destination."""
        destinations = [
            create_sample_destination("Japan", 75.0, 8000, 1800),
            create_sample_destination("Thailand", 82.0, 6000, 1200),
            create_sample_destination("Vietnam", 78.0, 5500, 900),
        ]
        summary = calculate_comparison_summary(destinations)
        assert summary["best_overall"]["country"] == "Thailand"
        assert summary["best_overall"]["score"] == 82.0

    def test_summary_cheapest_flight(self):
        """Correctly identifies cheapest flight."""
        destinations = [
            create_sample_destination("Japan", 75.0, 8000, 1800),
            create_sample_destination("Thailand", 82.0, 6000, 1200),
            create_sample_destination("Vietnam", 78.0, 5500, 900),
        ]
        summary = calculate_comparison_summary(destinations)
        assert summary["cheapest_flight"]["country"] == "Vietnam"
        assert summary["cheapest_flight"]["cost"] == 5500

    def test_summary_lowest_col(self):
        """Correctly identifies lowest CoL."""
        destinations = [
            create_sample_destination("Japan", 75.0, 8000, 1800),
            create_sample_destination("Thailand", 82.0, 6000, 1200),
            create_sample_destination("Vietnam", 78.0, 5500, 900),
        ]
        summary = calculate_comparison_summary(destinations)
        assert summary["lowest_col"]["country"] == "Vietnam"
        assert summary["lowest_col"]["cost"] == 900

    def test_summary_insights_generated(self):
        """Generates at least 1 insight when meaningful differences exist."""
        destinations = [
            create_sample_destination("Japan", 75.0, 25000, 2500),
            create_sample_destination("Vietnam", 78.0, 5500, 900),
        ]
        summary = calculate_comparison_summary(destinations)
        # With such different costs, should generate insights
        assert len(summary["insights"]) >= 1

    def test_summary_insufficient_data(self):
        """Handles single destination gracefully."""
        destinations = [
            create_sample_destination("Japan", 75.0, 8000, 1800),
        ]
        summary = calculate_comparison_summary(destinations)
        assert "error" in summary

    def test_summary_empty_list(self):
        """Returns empty dict for empty list."""
        summary = calculate_comparison_summary([])
        assert summary == {}

    def test_summary_score_spread(self):
        """Calculates correct score spread."""
        destinations = [
            create_sample_destination("Japan", 60.0, 8000, 1800),
            create_sample_destination("Thailand", 80.0, 6000, 1200),
        ]
        summary = calculate_comparison_summary(destinations)
        assert summary["score_spread"] == 20.0


class TestComparisonTable:
    """Tests for comparison table data generation."""

    def test_table_data_structure(self):
        """Returns list of dicts with correct keys."""
        destinations = [
            create_sample_destination("Japan", 75.0, 8000, 1800),
            create_sample_destination("Thailand", 82.0, 6000, 1200),
        ]
        rows = get_comparison_table_data(destinations)
        assert isinstance(rows, list)
        assert len(rows) > 0
        first_row = rows[0]
        assert "Metric" in first_row
        assert "Better" in first_row
        assert "best_country" in first_row

    def test_table_data_best_country_marked(self):
        """Marks best country for each metric."""
        destinations = [
            create_sample_destination("Japan", 75.0, 8000, 1800),
            create_sample_destination("Thailand", 82.0, 6000, 1200),
        ]
        rows = get_comparison_table_data(destinations)

        # Find the Overall Score row
        score_row = next((r for r in rows if r["Metric"] == "Overall Score"), None)
        assert score_row is not None
        assert score_row["best_country"] == "Thailand"  # Higher score

        # Find the Flight Cost row
        flight_row = next((r for r in rows if r["Metric"] == "Flight Cost"), None)
        assert flight_row is not None
        assert flight_row["best_country"] == "Thailand"  # Lower cost

    def test_table_data_empty_list(self):
        """Returns empty list for empty input."""
        rows = get_comparison_table_data([])
        assert rows == []

    def test_table_data_with_expanded(self):
        """Includes expanded metrics when data available."""
        destinations = [
            create_sample_destination("Japan", 75.0, 8000, 1800, safety=85, visa=100, access=90),
            create_sample_destination("Thailand", 82.0, 6000, 1200, safety=70, visa=100, access=85),
        ]
        rows = get_comparison_table_data(destinations)
        metric_names = [r["Metric"] for r in rows]
        assert "Safety Index" in metric_names
        assert "Visa Ease" in metric_names
        assert "Travel Access" in metric_names


class TestHasExpandedData:
    """Tests for expanded data detection."""

    def test_has_expanded_data_true(self):
        """Returns True when safety/visa/access present."""
        dest = create_sample_destination("Japan", 75.0, 8000, 1800, safety=85, visa=100, access=90)
        assert _has_expanded_data(dest) is True

    def test_has_expanded_data_false(self):
        """Returns False when no expanded data."""
        dest = create_sample_destination("Japan", 75.0, 8000, 1800)
        assert _has_expanded_data(dest) is False

    def test_has_expanded_data_partial(self):
        """Returns True when any expanded indicator present."""
        dest = create_sample_destination("Japan", 75.0, 8000, 1800, safety=85)
        assert _has_expanded_data(dest) is True


class TestBadgesHTML:
    """Tests for badges HTML rendering."""

    def test_render_badges_html_returns_string(self):
        """Returns HTML string."""
        destinations = [
            create_sample_destination("Japan", 75.0, 8000, 1800, badges=["EXCELLENT"]),
        ]
        html = render_comparison_badges_html(destinations)
        assert isinstance(html, str)
        assert "Japan" in html
        assert "EXCELLENT" in html

    def test_render_badges_html_empty_list(self):
        """Returns empty string for empty list."""
        html = render_comparison_badges_html([])
        assert html == ""

    def test_render_badges_html_no_badges(self):
        """Handles destinations with no badges."""
        destinations = [
            create_sample_destination("Japan", 60.0, 8000, 1800, badges=[]),
        ]
        html = render_comparison_badges_html(destinations)
        assert "No badges" in html


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
