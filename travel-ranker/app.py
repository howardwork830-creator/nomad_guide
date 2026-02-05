"""
Digital Nomad Destination Ranker - Streamlit Application

A tool for ranking travel destinations based on:
- Exchange rate momentum
- Flight costs
- Cost of living

Origin: Taiwan (TPE)
Display Currency: TWD

Enhanced with:
- Data quality indicators
- Freshness tracking
- Health monitoring
- Graceful degradation
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

    Returns:
        Dictionary mapping country_key to current data with quality info
    """
    serpapi = SerpApiClient()
    exchange_client = ExchangeRateClient()

    use_live_apis = not USE_MOCK_DATA and serpapi.is_configured and exchange_client.is_configured

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
        }

    return current_data


def calculate_rankings(countries: Dict[str, Any], current_data: Dict[str, Dict[str, Any]]) -> pd.DataFrame:
    """
    Calculate scores and rankings for all destinations.

    Returns:
        DataFrame with ranking data
    """
    rankings = []
    destinations = countries.get("destinations", {})

    for country_key, country_info in destinations.items():
        baseline = country_info.get("baseline", {})
        current = current_data.get(country_key, {})
        quality = current.get("quality")

        # Calculate score with quality tracking
        score_data = calculate_destination_score(
            current_exchange_rate=current.get("exchange_rate", baseline.get("exchange_rate", 1.0)),
            baseline_exchange_rate=baseline.get("exchange_rate", 1.0),
            current_flight_cost=current.get("flight_cost", baseline.get("flight_cost_twd", 10000)),
            baseline_flight_cost=baseline.get("flight_cost_twd", 10000),
            current_col=current.get("col", baseline.get("monthly_col_usd", 1500)),
            baseline_col=baseline.get("monthly_col_usd", 1500),
            currency=country_info.get("currency_code", "USD"),
            country=country_info.get("name", ""),
            data_quality=quality
        )

        badges = assign_badges(score_data)
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
        "min_quality": min_quality
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

        # Build header with quality indicator
        quality_badge = ""
        if quality_info:
            quality_badge = f" | Quality: {quality_info.overall_quality_score:.0f}%"

        with st.expander(f"{row['Country']} - Score: {row['Score']:.1f}{quality_badge}"):
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
        "Flight Cost (TWD)", "Monthly CoL (USD)", "Badges"
    ]
    return df[export_columns].to_csv(index=False)


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

        st.divider()

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
        "Embedded CoL data. Scores update based on API availability and cache TTL."
    )


if __name__ == "__main__":
    main()
