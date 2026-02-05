"""
Digital Nomad Destination Ranker - Streamlit Application

A tool for ranking travel destinations based on:
- Exchange rate momentum
- Flight costs
- Cost of living
- Safety index (NEW)
- Visa requirements (NEW)
- Travel accessibility (NEW)

Origin: Taiwan (TPE)
Display Currency: TWD

Enhanced with:
- Data quality indicators
- Freshness tracking
- Health monitoring
- Graceful degradation
- Comparison mode
- Interactive map view
"""

import os
import json
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Any, List, Optional

import streamlit as st
import pandas as pd
from dotenv import load_dotenv

try:
    from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode
    AGGRID_AVAILABLE = True
except ImportError:
    AGGRID_AVAILABLE = False

try:
    from streamlit_extras.metric_cards import style_metric_cards
    EXTRAS_AVAILABLE = True
except ImportError:
    EXTRAS_AVAILABLE = False

try:
    import plotly.graph_objects as go
    import plotly.express as px
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

from utils.scoring import (
    calculate_destination_score,
    assign_badges,
    get_trend_arrow,
    classify_trend,
    BADGE_STYLES
)
from utils.cache import (
    fetch_cached_data,
    save_cache,
    get_cache_age,
    check_cache_health
)
from utils.database import (
    init_database,
    store_daily_snapshot,
    get_history,
    get_data_quality_stats,
    get_country_trend_data
)
from utils.api_clients import (
    SerpApiClient,
    ExchangeRateClient,
    get_col_for_country,
    load_countries,
    get_baseline_data,
    load_baselines_v2
)
from utils.ui_helpers import (
    load_css,
    get_score_color,
    get_trend_indicator_html,
    render_badges_html,
    render_status_indicator,
    render_top_destination_card,
    render_metric_card,
    render_score_breakdown_card,
    get_simple_trend_arrow,
    format_ag_grid_badges,
    render_trend_charts
)
from utils.data_quality import (
    DataSource,
    DataWithProvenance,
    DestinationDataQuality,
    ProvenanceMetadata,
    get_quality_badge_html,
    get_freshness_indicator_html,
    get_source_label
)
from utils.health import (
    get_system_health,
    get_health_summary,
    set_last_successful_update,
    HealthStatus
)
from utils.logging_config import get_logger, metrics
from utils.comparison import (
    create_comparison_radar_chart,
    create_comparison_bar_chart,
    calculate_comparison_summary,
    get_comparison_table_data,
    render_comparison_badges_html
)
from utils.map_view import (
    create_world_map,
    create_bubble_map,
    create_flight_routes_map,
    get_region_stats
)

# Load environment variables
load_dotenv()

# Logger
logger = get_logger("app")

# Page config
st.set_page_config(
    page_title="Digital Nomad Destination Ranker",
    page_icon=None,
    layout="wide"
)

# Load custom CSS
load_css()

# Constants
USE_MOCK_DATA = os.getenv("USE_MOCK_DATA", "false").lower() == "true"
ORIGIN_AIRPORT = "TPE"
DISPLAY_CURRENCY = "TWD"

# Data paths
DATA_DIR = Path(__file__).parent / "data"


@st.cache_data(ttl=3600)
def load_safety_data() -> Dict[str, Any]:
    """Load safety index data from JSON file."""
    safety_file = DATA_DIR / "safety_index.json"
    if safety_file.exists():
        with open(safety_file, "r") as f:
            data = json.load(f)
            return data.get("safety_scores", {})
    return {}


@st.cache_data(ttl=3600)
def load_visa_data() -> Dict[str, Any]:
    """Load visa requirements data from JSON file."""
    visa_file = DATA_DIR / "visa_requirements.json"
    if visa_file.exists():
        with open(visa_file, "r") as f:
            data = json.load(f)
            return data.get("visa_requirements", {})
    return {}


@st.cache_data(ttl=3600)
def load_access_data() -> Dict[str, Any]:
    """Load travel accessibility data from JSON file."""
    access_file = DATA_DIR / "travel_access.json"
    if access_file.exists():
        with open(access_file, "r") as f:
            data = json.load(f)
            return data.get("travel_access", {})
    return {}


def get_data_status() -> str:
    """Determine current data status."""
    if USE_MOCK_DATA:
        return "mock"
    serpapi = SerpApiClient()
    exchange_client = ExchangeRateClient()
    if serpapi.is_configured and exchange_client.is_configured:
        cache_age = get_cache_age("exchange")
        if cache_age:
            return "cached"
        return "live"
    return "mock"


def get_current_data(countries: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Fetch current data for all destinations with provenance tracking.

    Uses live APIs if configured, falls back to cached data,
    then to baseline data if needed. No random variation.

    Includes new indicators: safety, visa, travel accessibility.

    Returns:
        Dictionary mapping country_key to current data with quality info
    """
    serpapi = SerpApiClient()
    exchange_client = ExchangeRateClient()

    use_live_apis = not USE_MOCK_DATA and serpapi.is_configured and exchange_client.is_configured

    # Load new indicator data
    safety_data = load_safety_data()
    visa_data = load_visa_data()
    access_data = load_access_data()

    # Try to get exchange rates (single API call for all currencies)
    exchange_rates = None
    exchange_source = DataSource.BASELINE

    if use_live_apis:
        # Try cache first with stale fallback
        cached_exchange, cache_source = fetch_cached_data("exchange", allow_stale=True)
        if cached_exchange:
            exchange_rates = cached_exchange
            exchange_source = cache_source
            metrics.record_cache_hit()
        else:
            # Try live API
            api_rates = exchange_client.get_rates(DISPLAY_CURRENCY)
            if api_rates:
                # Extract raw values for caching
                raw_rates = {k: v.value for k, v in api_rates.items()}
                save_cache("exchange", {"rates": raw_rates})
                exchange_rates = {"rates": raw_rates}
                exchange_source = DataSource.LIVE_API
                metrics.record_cache_miss()

    current_data = {}
    destinations = countries.get("destinations", {})

    for country_key, country_info in destinations.items():
        currency_code = country_info.get("currency_code", "USD")
        airport_code = country_info.get("airport_code", "")
        country_name = country_info.get("name", country_key)

        # Get baseline data with provenance
        baseline_data = get_baseline_data(country_key)
        baseline = country_info.get("baseline", {})

        # Initialize quality tracking
        quality = DestinationDataQuality(
            country_key=country_key,
            country_name=country_name
        )

        # Get exchange rate
        current_rate = None
        rate_source = DataSource.BASELINE

        if exchange_rates and "rates" in exchange_rates:
            rate_value = exchange_rates["rates"].get(currency_code)
            if rate_value:
                current_rate = rate_value
                rate_source = exchange_source

        if current_rate is None:
            # Use baseline - NO random variation for deterministic results
            if "exchange_rate" in baseline_data:
                current_rate = baseline_data["exchange_rate"].value
                rate_source = DataSource.BASELINE
            else:
                current_rate = baseline.get("exchange_rate", 1.0)
                rate_source = DataSource.BASELINE

        # Create provenance for exchange rate
        # Quality score based on source: LIVE_API=95, CACHE=85, STALE_CACHE=60, BASELINE=40
        exchange_quality = {
            DataSource.LIVE_API: 95,
            DataSource.CACHE: 85,
            DataSource.STALE_CACHE: 60,
            DataSource.BASELINE: 40,
            DataSource.MOCK: 30,
        }.get(rate_source, 40)

        quality.exchange_data = DataWithProvenance(
            value=current_rate,
            source=rate_source,
            fetched_at=datetime.now(),
            field_name="exchange_rate",
            quality_score=exchange_quality
        )

        # Get flight cost
        current_flight = None
        flight_source = DataSource.BASELINE

        if use_live_apis and not USE_MOCK_DATA:
            # Try cache first with stale fallback
            cached_flight, cache_src = fetch_cached_data("flights", country_key, allow_stale=True)
            if cached_flight:
                current_flight = cached_flight.get("price")
                flight_source = cache_src
            else:
                # Try live API
                flight_result = serpapi.get_flight_price(ORIGIN_AIRPORT, airport_code)
                if flight_result:
                    current_flight = flight_result.value
                    flight_source = DataSource.LIVE_API
                    save_cache("flights", {"price": current_flight}, country_key)

        if current_flight is None:
            # Use baseline - NO random variation
            if "flight_cost" in baseline_data:
                current_flight = baseline_data["flight_cost"].value
                flight_source = DataSource.BASELINE
            else:
                current_flight = baseline.get("flight_cost_twd", 10000)
                flight_source = DataSource.BASELINE

        # Create provenance for flight
        # Quality score based on source: LIVE_API=95, CACHE=85, STALE_CACHE=60, BASELINE=40
        flight_quality = {
            DataSource.LIVE_API: 95,
            DataSource.CACHE: 85,
            DataSource.STALE_CACHE: 60,
            DataSource.BASELINE: 40,
            DataSource.MOCK: 30,
        }.get(flight_source, 40)

        quality.flight_data = DataWithProvenance(
            value=current_flight,
            source=flight_source,
            fetched_at=datetime.now(),
            field_name="flight_cost",
            quality_score=flight_quality
        )

        # Get cost of living (from embedded data or baseline)
        current_col = get_col_for_country(country_name)
        col_source = DataSource.CACHE if current_col else DataSource.BASELINE
        col_quality = 75  # Default for embedded data

        if current_col is None:
            if "col" in baseline_data:
                current_col = baseline_data["col"].value
                # Use confidence from baselines_v2 if available (varies per country)
                col_quality = baseline_data["col"].quality_score if hasattr(baseline_data["col"], 'quality_score') else 45
            else:
                current_col = baseline.get("monthly_col_usd", 1500)
                col_quality = 40
            col_source = DataSource.BASELINE

        # Create provenance for CoL
        quality.col_data = DataWithProvenance(
            value=current_col,
            source=col_source,
            fetched_at=datetime.now(),
            field_name="col",
            quality_score=col_quality
        )

        # Get new indicator data
        country_safety = safety_data.get(country_key, {})
        country_visa = visa_data.get(country_key, {})
        country_access = access_data.get(country_key, {})

        # Extract values
        safety_score = country_safety.get("safety_score")
        visa_score_val = country_visa.get("visa_score")
        access_score = country_access.get("access_score")
        has_nomad_visa = country_visa.get("digital_nomad_visa", False)

        # Create provenance for new indicators (all from static JSON files)
        if safety_score is not None:
            quality.safety_data = DataWithProvenance(
                value=safety_score,
                source=DataSource.BASELINE,
                fetched_at=datetime.now(),
                field_name="safety",
                quality_score=85  # Static data from reputable sources
            )

        if visa_score_val is not None:
            quality.visa_data = DataWithProvenance(
                value=visa_score_val,
                source=DataSource.BASELINE,
                fetched_at=datetime.now(),
                field_name="visa",
                quality_score=90  # Official government sources
            )

        if access_score is not None:
            quality.access_data = DataWithProvenance(
                value=access_score,
                source=DataSource.BASELINE,
                fetched_at=datetime.now(),
                field_name="access",
                quality_score=80  # Airline schedule data
            )

        # Recalculate overall quality
        quality._calculate_overall_quality()

        current_data[country_key] = {
            "exchange_rate": current_rate,
            "flight_cost": current_flight,
            "col": current_col,
            "exchange_source": rate_source,
            "flight_source": flight_source,
            "col_source": col_source,
            "country_info": country_info,
            "quality": quality,
            # New indicators
            "safety_score": safety_score,
            "visa_score": visa_score_val,
            "access_score": access_score,
            "has_nomad_visa": has_nomad_visa,
            "safety_data": country_safety,
            "visa_data": country_visa,
            "access_data": country_access,
        }

    return current_data


def calculate_rankings(countries: Dict[str, Any], current_data: Dict[str, Dict[str, Any]]) -> pd.DataFrame:
    """
    Calculate scores and rankings for all destinations.

    Uses expanded 6-indicator scoring when data is available.

    Returns:
        DataFrame with ranking data
    """
    rankings = []
    destinations = countries.get("destinations", {})

    for country_key, country_info in destinations.items():
        baseline = country_info.get("baseline", {})
        current = current_data.get(country_key, {})
        quality = current.get("quality")

        # Get new indicator values
        safety_index = current.get("safety_score")
        visa_score = current.get("visa_score")
        access_score = current.get("access_score")
        has_nomad_visa = current.get("has_nomad_visa", False)

        # Calculate score with quality tracking and new indicators
        score_data = calculate_destination_score(
            current_exchange_rate=current.get("exchange_rate", baseline.get("exchange_rate", 1.0)),
            baseline_exchange_rate=baseline.get("exchange_rate", 1.0),
            current_flight_cost=current.get("flight_cost", baseline.get("flight_cost_twd", 10000)),
            baseline_flight_cost=baseline.get("flight_cost_twd", 10000),
            current_col=current.get("col", baseline.get("monthly_col_usd", 1500)),
            baseline_col=baseline.get("monthly_col_usd", 1500),
            currency=country_info.get("currency_code", "USD"),
            country=country_info.get("name", ""),
            data_quality=quality,
            safety_index=safety_index,
            visa_score=visa_score,
            access_score=access_score,
            use_expanded_scoring=True
        )

        badges = assign_badges(score_data, has_nomad_visa=has_nomad_visa)
        components = score_data.get("components", {})

        # Create provenance for database
        provenance = None
        if quality:
            provenance = ProvenanceMetadata.from_destination_quality(quality)

        # Store snapshot with provenance
        store_daily_snapshot(
            country_key,
            country_info.get("name", ""),
            score_data,
            badges,
            provenance=provenance
        )

        # Calculate quality score for display
        quality_score = quality.overall_quality_score if quality else 50

        rankings.append({
            "country_key": country_key,
            "Country": country_info.get("name", country_key),
            "Region": country_info.get("region", "Unknown"),
            "Score": score_data.get("final_score", 0),
            "Change": score_data.get("overall_change", 0),
            "Trend": get_trend_arrow(score_data.get("overall_change", 0)),
            "Exchange": components.get("exchange", {}).get("change", 0),
            "Flight": components.get("flight", {}).get("change", 0),
            "CoL": components.get("col", {}).get("change", 0),
            "Badges": format_ag_grid_badges(badges) if badges else "",
            "Flight Cost (TWD)": int(current.get("flight_cost", 0)),
            "Monthly CoL (USD)": int(current.get("col", 0)),
            "Quality": round(quality_score, 0),
            "score_data": score_data,
            "badges_list": badges,
            "quality_info": quality,
            # New indicators
            "Safety": safety_index or 0,
            "Visa": visa_score or 0,
            "Access": access_score or 0,
            "Has Nomad Visa": has_nomad_visa,
            "safety_data": current.get("safety_data", {}),
            "visa_data": current.get("visa_data", {}),
            "access_data": current.get("access_data", {}),
        })

    # Sort by score descending
    rankings.sort(key=lambda x: x["Score"], reverse=True)

    # Add rank
    for i, r in enumerate(rankings, 1):
        r["Rank"] = i

    # Record successful update
    set_last_successful_update()

    return pd.DataFrame(rankings)


def render_header(data_status: str):
    """Render clean dashboard header with health info."""
    col1, col2, col3 = st.columns([3, 1, 1])

    with col1:
        st.markdown(
            '<h1 class="dashboard-title">Digital Nomad Destination Ranker</h1>',
            unsafe_allow_html=True
        )
        st.markdown(
            f'<p class="dashboard-subtitle">Last updated: {datetime.now().strftime("%Y-%m-%d %H:%M")} | Origin: Taiwan (TPE) | Currency: TWD</p>',
            unsafe_allow_html=True
        )

    with col2:
        st.markdown(
            f'<div style="text-align: right; padding-top: 1rem;">{render_status_indicator(data_status)}</div>',
            unsafe_allow_html=True
        )

    with col3:
        # Quick health indicator
        health = get_health_summary()
        status_color = {
            "healthy": "#4CAF50",
            "degraded": "#FFC107",
            "unhealthy": "#F44336"
        }.get(health["status"], "#9E9E9E")

        st.markdown(
            f'''<div style="text-align: right; padding-top: 1rem;">
                <span style="color: {status_color};">●</span>
                <span style="font-size: 0.8rem; color: #666;">System {health["status"].title()}</span>
            </div>''',
            unsafe_allow_html=True
        )


def render_top_3_cards(df: pd.DataFrame):
    """Render hero section with top 3 destination cards."""
    st.markdown('<h2 class="section-header">Top Destinations</h2>', unsafe_allow_html=True)

    cols = st.columns(3)

    for i, (_, row) in enumerate(df.head(3).iterrows()):
        with cols[i]:
            card_html = render_top_destination_card(
                rank=i + 1,
                country=row["Country"],
                score=row["Score"],
                flight_cost=row["Flight Cost (TWD)"],
                badges=row["badges_list"],
                change=row["Change"]
            )
            st.markdown(card_html, unsafe_allow_html=True)

            # Add quality indicator below card
            quality = row.get("quality_info")
            if quality:
                st.markdown(
                    f'<div style="text-align: center; margin-top: 0.5rem;">{get_quality_badge_html(quality.overall_quality_score)}</div>',
                    unsafe_allow_html=True
                )


def render_stats_row(df: pd.DataFrame):
    """Render statistics row with metric cards."""
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric("Destinations", len(df))
    with col2:
        avg_score = df["Score"].mean()
        st.metric("Avg Score", f"{avg_score:.1f}")
    with col3:
        hot_deals = len(df[df["Change"] > 15])
        st.metric("Hot Deals", hot_deals)
    with col4:
        top_dest = df.iloc[0]["Country"] if len(df) > 0 else "N/A"
        st.metric("Top Pick", top_dest)
    with col5:
        avg_quality = df["Quality"].mean()
        st.metric("Data Quality", f"{avg_quality:.0f}%")

    # Style metric cards if available
    if EXTRAS_AVAILABLE:
        style_metric_cards()


def render_sidebar(df: pd.DataFrame) -> Dict[str, Any]:
    """Render sidebar filters and return filter state."""
    st.sidebar.markdown(
        '<div class="sidebar-section-title">Filters</div>',
        unsafe_allow_html=True
    )

    # Region filter
    regions = sorted(df["Region"].unique().tolist())
    selected_regions = st.sidebar.multiselect(
        "Regions",
        options=regions,
        default=regions,
        help="Filter by geographic region"
    )

    # Budget slider
    max_flight = int(df["Flight Cost (TWD)"].max())
    min_flight = int(df["Flight Cost (TWD)"].min())
    budget_range = st.sidebar.slider(
        "Flight Budget (TWD)",
        min_value=min_flight,
        max_value=max_flight,
        value=(min_flight, max_flight),
        step=1000,
        help="Filter by flight cost range"
    )

    # Hot deals toggle
    hot_deals_only = st.sidebar.toggle(
        "Hot Deals Only",
        value=False,
        help="Show only destinations with >15% improvement"
    )

    # Score minimum
    min_score = st.sidebar.slider(
        "Minimum Score",
        min_value=0,
        max_value=100,
        value=0,
        step=5,
        help="Filter by minimum destination score"
    )

    # Quality filter
    min_quality = st.sidebar.slider(
        "Minimum Data Quality",
        min_value=0,
        max_value=100,
        value=0,
        step=10,
        help="Filter by minimum data quality score"
    )

    st.sidebar.divider()

    # New indicator filters
    st.sidebar.markdown(
        '<div class="sidebar-section-title">New Indicators</div>',
        unsafe_allow_html=True
    )

    # Safety filter
    min_safety = st.sidebar.slider(
        "Minimum Safety Score",
        min_value=0,
        max_value=100,
        value=0,
        step=5,
        help="Filter by minimum safety index"
    )

    # Visa filter
    visa_options = ["All", "Visa Free", "VOA/eVisa", "Visa Required"]
    selected_visa = st.sidebar.selectbox(
        "Visa Requirement",
        options=visa_options,
        help="Filter by visa requirements for Taiwan passport"
    )

    # Digital nomad visa filter
    nomad_visa_only = st.sidebar.toggle(
        "Has Digital Nomad Visa",
        value=False,
        help="Show only countries with digital nomad visa programs"
    )

    st.sidebar.divider()

    # Data status
    st.sidebar.markdown(
        '<div class="sidebar-section-title">Data Status</div>',
        unsafe_allow_html=True
    )

    exchange_age = get_cache_age("exchange")
    if exchange_age:
        st.sidebar.text(f"Exchange rates: {exchange_age}")
    else:
        st.sidebar.text("Exchange rates: Using baseline data")

    # Cache health
    cache_health = check_cache_health()
    st.sidebar.text(f"Cache files: {cache_health['valid_count']} valid, {cache_health['stale_count']} stale")

    if USE_MOCK_DATA:
        st.sidebar.info("Running in demo mode with baseline data")

    # Health check expander
    with st.sidebar.expander("System Health"):
        health = get_health_summary()
        st.json(health)

    return {
        "regions": selected_regions,
        "budget_range": budget_range,
        "hot_deals_only": hot_deals_only,
        "min_score": min_score,
        "min_quality": min_quality,
        "min_safety": min_safety,
        "selected_visa": selected_visa,
        "nomad_visa_only": nomad_visa_only,
    }


def apply_filters(df: pd.DataFrame, filters: Dict[str, Any]) -> pd.DataFrame:
    """Apply sidebar filters to dataframe."""
    filtered = df.copy()

    # Region filter
    if filters["regions"]:
        filtered = filtered[filtered["Region"].isin(filters["regions"])]

    # Budget filter
    min_budget, max_budget = filters["budget_range"]
    filtered = filtered[
        (filtered["Flight Cost (TWD)"] >= min_budget) &
        (filtered["Flight Cost (TWD)"] <= max_budget)
    ]

    # Hot deals filter
    if filters["hot_deals_only"]:
        filtered = filtered[filtered["Change"] > 15]

    # Score filter
    filtered = filtered[filtered["Score"] >= filters["min_score"]]

    # Quality filter
    filtered = filtered[filtered["Quality"] >= filters["min_quality"]]

    # Safety filter
    if "min_safety" in filters and filters["min_safety"] > 0:
        filtered = filtered[filtered["Safety"] >= filters["min_safety"]]

    # Visa filter
    if "selected_visa" in filters and filters["selected_visa"] != "All":
        if filters["selected_visa"] == "Visa Free":
            filtered = filtered[filtered["Visa"] == 100]
        elif filters["selected_visa"] == "VOA/eVisa":
            filtered = filtered[(filtered["Visa"] >= 60) & (filtered["Visa"] < 100)]
        elif filters["selected_visa"] == "Visa Required":
            filtered = filtered[filtered["Visa"] < 60]

    # Digital nomad visa filter
    if "nomad_visa_only" in filters and filters["nomad_visa_only"]:
        filtered = filtered[filtered["Has Nomad Visa"] == True]

    # Re-rank after filtering
    filtered = filtered.reset_index(drop=True)
    filtered["Rank"] = range(1, len(filtered) + 1)

    return filtered


def render_ranking_table_aggrid(df: pd.DataFrame):
    """Render ranking table using AG Grid."""
    # Select key columns (including quality)
    display_columns = [
        "Rank", "Country", "Score", "Quality", "Trend", "Change",
        "Flight Cost (TWD)", "Badges"
    ]

    display_df = df[display_columns].copy()
    display_df["Change"] = display_df["Change"].apply(lambda x: f"{x:+.1f}%")
    display_df["Quality"] = display_df["Quality"].apply(lambda x: f"{x:.0f}%")

    # Build grid options
    gb = GridOptionsBuilder.from_dataframe(display_df)

    # Configure columns
    gb.configure_column("Rank", width=70, pinned="left")
    gb.configure_column("Country", width=150)
    gb.configure_column("Score", width=90, type=["numericColumn"])
    gb.configure_column("Quality", width=90)
    gb.configure_column("Trend", width=70)
    gb.configure_column("Change", width=90)
    gb.configure_column("Flight Cost (TWD)", width=130, type=["numericColumn"])
    gb.configure_column("Badges", width=200, wrapText=True)

    # Add conditional formatting for scores using JsCode
    score_cell_style = JsCode("""
    function(params) {
        if (params.value >= 85) {
            return {'backgroundColor': 'rgba(76, 175, 80, 0.15)', 'color': '#2E7D32', 'fontWeight': '600'};
        } else if (params.value >= 70) {
            return {'backgroundColor': 'rgba(255, 193, 7, 0.15)', 'color': '#F57F17', 'fontWeight': '600'};
        } else if (params.value >= 50) {
            return {'backgroundColor': 'rgba(255, 152, 0, 0.15)', 'color': '#E65100', 'fontWeight': '600'};
        } else {
            return {'backgroundColor': 'rgba(244, 67, 54, 0.15)', 'color': '#C62828', 'fontWeight': '600'};
        }
    }
    """)

    # Trend cell styling
    trend_cell_style = JsCode("""
    function(params) {
        if (params.value && params.value.includes('\u25B2')) {
            return {'color': '#4CAF50', 'fontWeight': '600'};
        } else if (params.value && params.value.includes('\u25BC')) {
            return {'color': '#F44336', 'fontWeight': '600'};
        }
        return {'color': '#9E9E9E'};
    }
    """)

    # Row highlighting for top 3
    row_style = JsCode("""
    function(params) {
        if (params.data.Rank <= 3) {
            return {'backgroundColor': '#FFFDE7'};
        }
        return null;
    }
    """)

    gb.configure_column("Score", cellStyle=score_cell_style)
    gb.configure_column("Trend", cellStyle=trend_cell_style)

    # Grid options
    gb.configure_selection(selection_mode="single", use_checkbox=False)
    gb.configure_grid_options(
        domLayout='normal',
        getRowStyle=row_style,
        suppressRowHoverHighlight=False,
        rowHeight=40
    )

    grid_options = gb.build()

    # Render grid
    AgGrid(
        display_df,
        gridOptions=grid_options,
        height=400,
        theme="streamlit",
        update_mode=GridUpdateMode.SELECTION_CHANGED,
        allow_unsafe_jscode=True,
        fit_columns_on_grid_load=True
    )


def render_ranking_table_standard(df: pd.DataFrame):
    """Render ranking table using standard Streamlit (fallback)."""
    display_columns = [
        "Rank", "Country", "Score", "Quality", "Trend", "Change",
        "Flight Cost (TWD)", "Badges"
    ]

    display_df = df[display_columns].copy()
    display_df["Change"] = display_df["Change"].apply(lambda x: f"{x:+.1f}%")
    display_df["Quality"] = display_df["Quality"].apply(lambda x: f"{x:.0f}%")

    # Style the dataframe
    def highlight_score(val):
        if isinstance(val, (int, float)):
            if val >= 85:
                return "background-color: rgba(76, 175, 80, 0.15); color: #2E7D32; font-weight: 600"
            elif val >= 70:
                return "background-color: rgba(255, 193, 7, 0.15); color: #F57F17; font-weight: 600"
            elif val >= 50:
                return "background-color: rgba(255, 152, 0, 0.15); color: #E65100; font-weight: 600"
            elif val < 50:
                return "background-color: rgba(244, 67, 54, 0.15); color: #C62828; font-weight: 600"
        return ""

    def highlight_trend(val):
        if isinstance(val, str):
            if "▲" in val:
                return "color: #4CAF50; font-weight: 600"
            elif "▼" in val:
                return "color: #F44336; font-weight: 600"
        return "color: #9E9E9E"

    styled_df = display_df.style.map(
        highlight_score,
        subset=["Score"]
    ).map(
        highlight_trend,
        subset=["Trend"]
    )

    st.dataframe(
        styled_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Rank": st.column_config.NumberColumn("Rank", width="small"),
            "Country": st.column_config.TextColumn("Country", width="medium"),
            "Score": st.column_config.NumberColumn("Score", format="%.1f", width="small"),
            "Quality": st.column_config.TextColumn("Quality", width="small"),
            "Trend": st.column_config.TextColumn("Trend", width="small"),
            "Change": st.column_config.TextColumn("Change", width="small"),
            "Flight Cost (TWD)": st.column_config.NumberColumn("Flight", format="%d TWD"),
            "Badges": st.column_config.TextColumn("Badges", width="medium"),
        }
    )


def render_ranking_table(df: pd.DataFrame):
    """Render the main ranking table."""
    st.markdown('<h2 class="section-header">Destination Rankings</h2>', unsafe_allow_html=True)

    if AGGRID_AVAILABLE:
        render_ranking_table_aggrid(df)
    else:
        render_ranking_table_standard(df)


def render_score_breakdown(df: pd.DataFrame):
    """Render expandable score breakdown for each country."""
    st.markdown('<h2 class="section-header">Score Breakdown</h2>', unsafe_allow_html=True)

    for _, row in df.iterrows():
        score_data = row["score_data"]
        components = score_data.get("components", {})
        quality_info = row.get("quality_info")
        scoring_version = score_data.get("scoring_version", "legacy")

        # Build header with quality indicator and scoring version
        quality_badge = ""
        if quality_info:
            quality_badge = f" | Quality: {quality_info.overall_quality_score:.0f}%"

        version_badge = " [6 indicators]" if scoring_version == "expanded" else ""

        with st.expander(f"{row['Country']} - Score: {row['Score']:.1f}{quality_badge}{version_badge}"):
            col1, col2, col3 = st.columns(3)

            with col1:
                exchange = components.get("exchange", {})
                card_html = render_score_breakdown_card(
                    title="Exchange Rate",
                    score=exchange.get("score", 0),
                    change=exchange.get("change", 0),
                    current=f"{exchange.get('current', 0):.4f}",
                    baseline=f"{exchange.get('baseline', 0):.4f}",
                    card_type="exchange"
                )
                st.markdown(card_html, unsafe_allow_html=True)

                # Source indicator
                if quality_info and quality_info.exchange_data:
                    st.markdown(
                        f'<div style="text-align: center; font-size: 0.75rem; color: #666;">Source: {get_source_label(quality_info.exchange_data.source)}</div>',
                        unsafe_allow_html=True
                    )

            with col2:
                flight = components.get("flight", {})
                card_html = render_score_breakdown_card(
                    title="Flight Cost",
                    score=flight.get("score", 0),
                    change=flight.get("change", 0),
                    current=f"{flight.get('current', 0):,.0f} TWD",
                    baseline=f"{flight.get('baseline', 0):,.0f} TWD",
                    card_type="flight"
                )
                st.markdown(card_html, unsafe_allow_html=True)

                # Source indicator
                if quality_info and quality_info.flight_data:
                    st.markdown(
                        f'<div style="text-align: center; font-size: 0.75rem; color: #666;">Source: {get_source_label(quality_info.flight_data.source)}</div>',
                        unsafe_allow_html=True
                    )

            with col3:
                col_comp = components.get("col", {})
                card_html = render_score_breakdown_card(
                    title="Cost of Living",
                    score=col_comp.get("score", 0),
                    change=col_comp.get("change", 0),
                    current=f"${col_comp.get('current', 0):,.0f}/mo",
                    baseline=f"${col_comp.get('baseline', 0):,.0f}/mo",
                    card_type="col"
                )
                st.markdown(card_html, unsafe_allow_html=True)

                # Source indicator
                if quality_info and quality_info.col_data:
                    st.markdown(
                        f'<div style="text-align: center; font-size: 0.75rem; color: #666;">Source: {get_source_label(quality_info.col_data.source)}</div>',
                        unsafe_allow_html=True
                    )

            # New indicators row (if expanded scoring)
            if scoring_version == "expanded":
                st.markdown("---")
                st.markdown("**Additional Indicators**")
                col4, col5, col6 = st.columns(3)

                with col4:
                    safety_comp = components.get("safety", {})
                    safety_val = safety_comp.get("value", 0) or 0
                    safety_data = row.get("safety_data", {})

                    st.markdown(f'''
                        <div style="background: #E0F7FA; padding: 1rem; border-radius: 8px; text-align: center;">
                            <div style="font-size: 0.85rem; color: #00695C; font-weight: 500;">Safety Index</div>
                            <div style="font-size: 1.5rem; font-weight: 600; color: #00695C;">{safety_val:.0f}</div>
                            <div style="font-size: 0.75rem; color: #666;">GPI Rank: {safety_data.get('gpi_rank', 'N/A')}</div>
                        </div>
                    ''', unsafe_allow_html=True)

                with col5:
                    visa_comp = components.get("visa", {})
                    visa_val = visa_comp.get("value", 0) or 0
                    visa_info = row.get("visa_data", {})
                    visa_type = visa_info.get("visa_type", "unknown").replace("_", " ").title()
                    max_stay = visa_info.get("max_stay_days", "N/A")
                    has_nomad = visa_info.get("digital_nomad_visa", False)

                    nomad_badge = ' <span style="background:#FCE4EC;color:#AD1457;padding:2px 6px;border-radius:4px;font-size:0.7rem;">NOMAD VISA</span>' if has_nomad else ''

                    st.markdown(f'''
                        <div style="background: #FFF8E1; padding: 1rem; border-radius: 8px; text-align: center;">
                            <div style="font-size: 0.85rem; color: #FF6F00; font-weight: 500;">Visa Ease{nomad_badge}</div>
                            <div style="font-size: 1.5rem; font-weight: 600; color: #FF6F00;">{visa_val:.0f}</div>
                            <div style="font-size: 0.75rem; color: #666;">{visa_type} | {max_stay} days</div>
                        </div>
                    ''', unsafe_allow_html=True)

                with col6:
                    access_comp = components.get("access", {})
                    access_val = access_comp.get("value", 0) or 0
                    access_info = row.get("access_data", {})
                    has_direct = access_info.get("has_direct_flight", False)
                    duration = access_info.get("flight_duration_hours", "N/A")

                    direct_badge = "Direct" if has_direct else "Connection"

                    st.markdown(f'''
                        <div style="background: #E8EAF6; padding: 1rem; border-radius: 8px; text-align: center;">
                            <div style="font-size: 0.85rem; color: #283593; font-weight: 500;">Travel Access</div>
                            <div style="font-size: 1.5rem; font-weight: 600; color: #283593;">{access_val:.0f}</div>
                            <div style="font-size: 0.75rem; color: #666;">{direct_badge} | ~{duration}h</div>
                        </div>
                    ''', unsafe_allow_html=True)

            # Historical Trend Charts
            st.markdown("---")
            st.markdown("**Historical Trends**")
            trend_data = get_country_trend_data(row["country_key"], days=30)
            if len(trend_data) >= 2:
                fig = render_trend_charts(trend_data, row['Country'])
                if fig:
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.caption("Insufficient historical data for trend charts")

            if row["badges_list"]:
                st.markdown(
                    f'<div style="margin-top: 1rem;">{render_badges_html(row["badges_list"])}</div>',
                    unsafe_allow_html=True
                )

            # Show confidence info
            confidence = score_data.get("confidence", 0)
            multiplier = score_data.get("quality_multiplier", 1.0)
            st.markdown(
                f'''<div style="margin-top: 1rem; padding: 0.5rem; background: #f5f5f5; border-radius: 4px; font-size: 0.8rem;">
                    <strong>Score Details:</strong> Raw: {score_data.get("raw_score", 0):.1f} | Confidence: {confidence:.0%} | Quality Multiplier: {multiplier:.3f}
                </div>''',
                unsafe_allow_html=True
            )


def export_csv(df: pd.DataFrame) -> str:
    """Generate CSV export data."""
    export_columns = [
        "Rank", "Country", "Region", "Score", "Quality", "Change",
        "Flight Cost (TWD)", "Monthly CoL (USD)", "Safety", "Visa", "Access", "Badges"
    ]
    # Filter to only existing columns
    export_columns = [c for c in export_columns if c in df.columns]
    return df[export_columns].to_csv(index=False)


def render_comparison_mode(df: pd.DataFrame):
    """Render the comparison mode interface."""
    st.markdown('<h2 class="section-header">Compare Destinations</h2>', unsafe_allow_html=True)

    # Country selection
    all_countries = df['Country'].tolist()

    col1, col2, col3 = st.columns(3)

    with col1:
        dest1 = st.selectbox(
            "First Destination",
            options=all_countries,
            index=0 if all_countries else None,
            key="compare_dest1"
        )
    with col2:
        dest2 = st.selectbox(
            "Second Destination",
            options=all_countries,
            index=1 if len(all_countries) > 1 else 0,
            key="compare_dest2"
        )
    with col3:
        dest3 = st.selectbox(
            "Third Destination (optional)",
            options=["None"] + all_countries,
            index=0,
            key="compare_dest3"
        )

    # Get selected destinations data
    selected = [dest1, dest2]
    if dest3 != "None":
        selected.append(dest3)

    # Filter to selected destinations
    comparison_df = df[df['Country'].isin(selected)]
    comparison_data = comparison_df.to_dict('records')

    if len(comparison_data) >= 2:
        # Radar chart
        st.subheader("Visual Comparison")
        if PLOTLY_AVAILABLE:
            radar_fig = create_comparison_radar_chart(comparison_data)
            if radar_fig:
                st.plotly_chart(radar_fig, use_container_width=True)
        else:
            st.info("Install plotly for radar chart visualization")

        # Comparison summary
        summary = calculate_comparison_summary(comparison_data)
        if summary and "insights" in summary:
            st.subheader("Key Insights")
            for insight in summary["insights"]:
                st.markdown(f"- {insight}")

        # Side-by-side metrics
        st.subheader("Detailed Comparison")
        metric_cols = st.columns(len(comparison_data))

        for i, dest in enumerate(comparison_data):
            with metric_cols[i]:
                st.markdown(f"**{dest['Country']}**")
                st.metric("Overall Score", f"{dest['Score']:.1f}")
                st.metric("Flight Cost", f"{dest['Flight Cost (TWD)']:,} TWD")
                st.metric("Monthly CoL", f"${dest['Monthly CoL (USD)']:,}")

                # New indicators
                if dest.get('Safety'):
                    st.metric("Safety Index", f"{dest['Safety']:.0f}")
                if dest.get('Visa'):
                    visa_type = dest.get('visa_data', {}).get('visa_type', 'Unknown')
                    st.metric("Visa", visa_type.replace('_', ' ').title())
                if dest.get('Access'):
                    st.metric("Accessibility", f"{dest['Access']:.0f}")

        # Badges comparison
        st.subheader("Badges")
        st.markdown(
            render_comparison_badges_html(comparison_data),
            unsafe_allow_html=True
        )
    else:
        st.warning("Select at least 2 different destinations to compare.")


def render_map_view(df: pd.DataFrame):
    """Render the interactive map view."""
    st.markdown('<h2 class="section-header">World Map View</h2>', unsafe_allow_html=True)

    if not PLOTLY_AVAILABLE:
        st.warning("Install plotly for map visualization: pip install plotly")
        return

    # Map type selector
    map_type = st.radio(
        "Map Type",
        options=["World Map", "Bubble Map", "Flight Routes"],
        horizontal=True
    )

    # Color by selector (only for world/bubble map)
    if map_type in ["World Map", "Bubble Map"]:
        color_options = ["Score", "Safety", "Monthly CoL (USD)", "Flight Cost (TWD)"]
        color_by = st.selectbox("Color by", options=color_options, index=0)
    else:
        color_by = "Score"

    # Render map
    if map_type == "World Map":
        fig = create_world_map(df, color_by=color_by)
        if fig:
            st.plotly_chart(fig, use_container_width=True)

    elif map_type == "Bubble Map":
        fig = create_bubble_map(df, size_by="Score", color_by="Region")
        if fig:
            st.plotly_chart(fig, use_container_width=True)

    elif map_type == "Flight Routes":
        top_n = st.slider("Number of destinations to show", 5, 20, 10)
        fig = create_flight_routes_map(df, top_n=top_n)
        if fig:
            st.plotly_chart(fig, use_container_width=True)

    # Region statistics
    st.subheader("Regional Statistics")
    region_stats = get_region_stats(df)

    # Display as a clean table
    stats_data = []
    for region, stats in region_stats.items():
        stats_data.append({
            "Region": region,
            "Countries": stats["count"],
            "Avg Score": stats["avg_score"],
            "Best": stats["best_destination"],
            "Avg Flight (TWD)": f"{stats['avg_flight_cost']:,}",
            "Avg CoL (USD)": f"${stats['avg_col']:,}"
        })

    stats_df = pd.DataFrame(stats_data)
    st.dataframe(stats_df, use_container_width=True, hide_index=True)


def main():
    """Main application entry point."""
    # Initialize database
    init_database()

    # Determine data status
    data_status = get_data_status()

    # Render header
    render_header(data_status)

    # Load data
    with st.spinner("Loading destination data..."):
        countries = load_countries()
        current_data = get_current_data(countries)
        df = calculate_rankings(countries, current_data)

    # Sidebar filters
    filters = render_sidebar(df)

    # Apply filters
    filtered_df = apply_filters(df, filters)

    # Main content
    if filtered_df.empty:
        st.warning("No destinations match your filters. Try adjusting the criteria.")
    else:
        # Top 3 cards
        render_top_3_cards(filtered_df)

        st.divider()

        # Stats row
        render_stats_row(filtered_df)

        st.divider()

        # Create tabs for different views
        tab_rankings, tab_compare, tab_map, tab_details = st.tabs([
            "Rankings",
            "Compare",
            "Map View",
            "Score Details"
        ])

        with tab_rankings:
            # Ranking table
            render_ranking_table(filtered_df)

            # Export button
            csv_data = export_csv(filtered_df)
            st.download_button(
                label="Export to CSV",
                data=csv_data,
                file_name=f"destination_rankings_{date.today().isoformat()}.csv",
                mime="text/csv"
            )

        with tab_compare:
            render_comparison_mode(filtered_df)

        with tab_map:
            render_map_view(filtered_df)

        with tab_details:
            # Score breakdowns
            render_score_breakdown(filtered_df)

    # Footer
    st.divider()

    # Data quality summary
    quality_stats = get_data_quality_stats()
    if quality_stats:
        st.caption(
            f"Data Quality: Avg {quality_stats.get('avg_quality', 0):.0f}% | "
            f"Live: {quality_stats.get('source_distribution', {}).get('live_api', 0)} | "
            f"Cached: {quality_stats.get('source_distribution', {}).get('cache', 0)} | "
            f"Baseline: {quality_stats.get('source_distribution', {}).get('baseline', 0)}"
        )

    st.caption(
        "Data sources: SerpApi Google Flights (flights), ExchangeRate-API (currency), "
        "Embedded CoL data, Global Peace Index (safety), MOFA Taiwan (visas), "
        "Airline schedules (accessibility). Scores update based on API availability and cache TTL."
    )


if __name__ == "__main__":
    main()
