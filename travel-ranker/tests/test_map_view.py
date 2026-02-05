"""
Unit tests for the map_view module.
Tests world map, bubble map, flight routes, region stats, and ISO codes.
"""

import pytest
import pandas as pd
import plotly.graph_objects as go
from utils.map_view import (
    create_world_map,
    create_bubble_map,
    create_flight_routes_map,
    create_region_map,
    get_region_stats,
    get_score_color,
    COUNTRY_ISO_CODES,
)


def create_sample_df(num_countries=5):
    """Create a sample DataFrame for testing."""
    data = {
        "Country": ["Japan", "Thailand", "Vietnam", "Germany", "Mexico"],
        "country_key": ["japan", "thailand", "vietnam", "germany", "mexico"],
        "Region": ["East Asia", "Southeast Asia", "Southeast Asia", "Europe", "Americas"],
        "Score": [75.0, 82.0, 78.0, 70.0, 72.0],
        "Rank": [1, 2, 3, 4, 5],
        "Flight Cost (TWD)": [8000, 6000, 5500, 25000, 22000],
        "Monthly CoL (USD)": [1800, 1200, 900, 2500, 1000],
        "Quality": [90, 85, 80, 88, 82],
    }
    if num_countries < 5:
        for key in data:
            data[key] = data[key][:num_countries]
    return pd.DataFrame(data)


class TestScoreColor:
    """Tests for score color mapping."""

    def test_excellent_score_color(self):
        """Score >= 85 returns dark green."""
        color = get_score_color(90)
        assert color == "#2E7D32"

    def test_good_score_color(self):
        """Score 70-84 returns green."""
        color = get_score_color(75)
        assert color == "#4CAF50"

    def test_moderate_score_color(self):
        """Score 55-69 returns light green."""
        color = get_score_color(60)
        assert color == "#8BC34A"

    def test_fair_score_color(self):
        """Score 45-54 returns yellow."""
        color = get_score_color(50)
        assert color == "#FFC107"

    def test_poor_score_color(self):
        """Score 35-44 returns orange."""
        color = get_score_color(40)
        assert color == "#FF9800"

    def test_low_score_color(self):
        """Score < 35 returns red."""
        color = get_score_color(30)
        assert color == "#F44336"


class TestWorldMap:
    """Tests for world map creation."""

    def test_world_map_returns_figure(self):
        """Returns plotly Figure object."""
        df = create_sample_df()
        fig = create_world_map(df, color_by="Score")
        assert fig is not None
        assert isinstance(fig, go.Figure)

    def test_world_map_empty_df(self):
        """Returns None for empty dataframe."""
        df = pd.DataFrame()
        fig = create_world_map(df)
        assert fig is None

    def test_world_map_color_by_score(self):
        """Colors by score correctly."""
        df = create_sample_df()
        fig = create_world_map(df, color_by="Score")
        assert fig is not None
        # Check that the figure has the expected layout
        assert "Destinations by Score" in fig.layout.title.text

    def test_world_map_color_by_quality(self):
        """Colors by quality correctly."""
        df = create_sample_df()
        fig = create_world_map(df, color_by="Quality")
        assert fig is not None
        assert "Quality" in fig.layout.title.text

    def test_world_map_color_by_cost(self):
        """Colors by cost (reversed scale)."""
        df = create_sample_df()
        fig = create_world_map(df, color_by="Flight Cost (TWD)")
        assert fig is not None
        assert "Flight Cost" in fig.layout.title.text


class TestBubbleMap:
    """Tests for bubble map creation."""

    def test_bubble_map_returns_figure(self):
        """Returns plotly Figure object."""
        df = create_sample_df()
        fig = create_bubble_map(df, size_by="Score", color_by="Region")
        assert fig is not None
        assert isinstance(fig, go.Figure)

    def test_bubble_map_empty_df(self):
        """Returns None for empty dataframe."""
        df = pd.DataFrame()
        fig = create_bubble_map(df)
        assert fig is None

    def test_bubble_map_size_by_score(self):
        """Bubble size varies by score."""
        df = create_sample_df()
        fig = create_bubble_map(df, size_by="Score")
        assert fig is not None
        # Title should mention sizing by Score
        assert "sized by Score" in fig.layout.title.text

    def test_bubble_map_color_by_region(self):
        """Colors by region."""
        df = create_sample_df()
        fig = create_bubble_map(df, size_by="Score", color_by="Region")
        assert fig is not None


class TestFlightRoutesMap:
    """Tests for flight routes map creation."""

    def test_flight_routes_top_10(self):
        """Shows routes for top destinations."""
        df = create_sample_df()
        fig = create_flight_routes_map(df, top_n=10)
        assert fig is not None
        assert isinstance(fig, go.Figure)
        # Should have multiple traces (routes + markers + Taiwan)
        assert len(fig.data) > 1

    def test_flight_routes_top_3(self):
        """Respects top_n parameter."""
        df = create_sample_df()
        fig = create_flight_routes_map(df, top_n=3)
        assert fig is not None
        assert "Top 3" in fig.layout.title.text

    def test_flight_routes_origin_marker(self):
        """Includes Taiwan origin marker."""
        df = create_sample_df()
        fig = create_flight_routes_map(df, top_n=5)
        assert fig is not None
        # Look for Taiwan marker in traces
        taiwan_found = False
        for trace in fig.data:
            if hasattr(trace, 'text') and trace.text == 'Taiwan':
                taiwan_found = True
                break
        assert taiwan_found

    def test_flight_routes_empty_df(self):
        """Returns None for empty dataframe."""
        df = pd.DataFrame()
        fig = create_flight_routes_map(df)
        assert fig is None


class TestRegionMap:
    """Tests for region-specific map creation."""

    def test_region_map_europe(self):
        """Creates zoomed map for Europe."""
        df = create_sample_df()
        fig = create_region_map(df, region="Europe")
        assert fig is not None
        assert "Europe" in fig.layout.title.text

    def test_region_map_empty_region(self):
        """Returns None when region has no data."""
        df = create_sample_df()
        fig = create_region_map(df, region="Oceania")
        assert fig is None


class TestRegionStats:
    """Tests for region statistics calculation."""

    def test_region_stats_all_regions(self):
        """Returns stats for all regions."""
        df = create_sample_df()
        stats = get_region_stats(df)
        assert isinstance(stats, dict)
        assert "East Asia" in stats
        assert "Southeast Asia" in stats
        assert "Europe" in stats
        assert "Americas" in stats

    def test_region_stats_correct_counts(self):
        """Counts countries per region correctly."""
        df = create_sample_df()
        stats = get_region_stats(df)
        assert stats["East Asia"]["count"] == 1  # Only Japan
        assert stats["Southeast Asia"]["count"] == 2  # Thailand, Vietnam

    def test_region_stats_avg_score(self):
        """Calculates average score correctly."""
        df = create_sample_df()
        stats = get_region_stats(df)
        # Southeast Asia: Thailand (82) + Vietnam (78) = 160 / 2 = 80
        assert stats["Southeast Asia"]["avg_score"] == 80.0

    def test_region_stats_best_destination(self):
        """Identifies best destination per region."""
        df = create_sample_df()
        stats = get_region_stats(df)
        assert stats["East Asia"]["best_destination"] == "Japan"
        assert stats["Southeast Asia"]["best_destination"] == "Thailand"


class TestISOCodes:
    """Tests for ISO country code mapping."""

    def test_iso_codes_coverage(self):
        """All 52 expected countries have ISO codes."""
        # These are the countries we expect to have
        expected_countries = [
            "japan", "south_korea", "hong_kong", "china",
            "thailand", "vietnam", "malaysia", "indonesia", "philippines",
            "singapore", "cambodia", "laos",
            "india", "sri_lanka", "nepal",
            "uk", "germany", "france", "spain", "portugal", "netherlands",
            "georgia", "estonia", "croatia", "czech_republic", "poland",
            "hungary", "greece", "albania", "romania", "bulgaria",
            "iceland", "switzerland",
            "usa", "mexico", "colombia", "argentina", "brazil", "peru",
            "costa_rica", "chile", "panama", "canada",
            "uae", "turkey", "israel",
            "morocco", "south_africa", "egypt", "kenya",
            "australia", "new_zealand",
        ]
        for country in expected_countries:
            assert country in COUNTRY_ISO_CODES, f"Missing ISO code for {country}"

    def test_iso_codes_valid_format(self):
        """All ISO codes are 3 characters."""
        for country, code in COUNTRY_ISO_CODES.items():
            assert len(code) == 3, f"Invalid ISO code length for {country}: {code}"
            assert code.isupper(), f"ISO code should be uppercase for {country}: {code}"

    def test_iso_codes_unique(self):
        """All ISO codes are unique."""
        codes = list(COUNTRY_ISO_CODES.values())
        assert len(codes) == len(set(codes)), "Duplicate ISO codes found"

    def test_iso_codes_known_countries(self):
        """Spot check known country codes."""
        assert COUNTRY_ISO_CODES["japan"] == "JPN"
        assert COUNTRY_ISO_CODES["usa"] == "USA"
        assert COUNTRY_ISO_CODES["uk"] == "GBR"
        assert COUNTRY_ISO_CODES["germany"] == "DEU"
        assert COUNTRY_ISO_CODES["australia"] == "AUS"


class TestMapIntegration:
    """Integration tests for map visualization."""

    def test_all_regions_have_coordinates(self):
        """All regions can be mapped."""
        regions = ["East Asia", "Southeast Asia", "South Asia", "Europe",
                   "Americas", "Middle East", "Africa", "Oceania"]
        df = pd.DataFrame({
            "Country": ["Test"] * len(regions),
            "country_key": ["japan", "thailand", "india", "germany",
                           "mexico", "turkey", "morocco", "australia"],
            "Region": regions,
            "Score": [70.0] * len(regions),
            "Rank": list(range(1, len(regions) + 1)),
            "Flight Cost (TWD)": [10000] * len(regions),
            "Monthly CoL (USD)": [1500] * len(regions),
        })

        for region in regions:
            fig = create_region_map(df, region=region)
            # Some regions might not have data, but if they do, should return figure
            if len(df[df['Region'] == region]) > 0:
                # At minimum, should not raise an error
                pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
