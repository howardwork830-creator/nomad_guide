"""
UI Helper functions for the Digital Nomad Destination Ranker.

Provides styled HTML components and CSS loading utilities.
"""

from pathlib import Path
from typing import List, Dict, Any, Optional
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def load_css() -> None:
    """Load custom CSS theme into Streamlit app."""
    css_path = Path(__file__).parent.parent / "styles" / "theme.css"
    if css_path.exists():
        with open(css_path) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


def get_score_color(score: float) -> str:
    """
    Return color class based on score value.

    Args:
        score: Score value (0-100)

    Returns:
        CSS color string
    """
    if score >= 85:
        return "#4CAF50"  # Green - Excellent
    elif score >= 70:
        return "#FFC107"  # Amber - Good
    elif score >= 50:
        return "#FF9800"  # Orange - Average
    else:
        return "#F44336"  # Red - Poor


def get_score_class(score: float) -> str:
    """
    Return CSS class based on score value.

    Args:
        score: Score value (0-100)

    Returns:
        CSS class name
    """
    if score >= 85:
        return "cell-score-excellent"
    elif score >= 70:
        return "cell-score-good"
    elif score >= 50:
        return "cell-score-average"
    else:
        return "cell-score-poor"


def get_trend_indicator_html(change: float) -> str:
    """
    Generate styled HTML for trend indicator.

    Args:
        change: Change percentage (positive = improvement)

    Returns:
        HTML string for styled trend indicator
    """
    # Cap extreme values to prevent overflow display
    display_change = max(min(change, 999.9), -999.9)

    if display_change > 10:
        arrow = "&#8593;&#8593;"  # Double up arrow
        trend_class = "trend-up"
        label = f"+{display_change:.1f}%"
    elif display_change > 3:
        arrow = "&#8593;"  # Up arrow
        trend_class = "trend-up"
        label = f"+{display_change:.1f}%"
    elif display_change > -3:
        arrow = "&#8596;"  # Horizontal arrow
        trend_class = "trend-stable"
        label = f"{display_change:+.1f}%"
    elif display_change > -10:
        arrow = "&#8595;"  # Down arrow
        trend_class = "trend-down"
        label = f"{display_change:.1f}%"
    else:
        arrow = "&#8595;&#8595;"  # Double down arrow
        trend_class = "trend-down"
        label = f"{display_change:.1f}%"

    return f'<span class="trend-indicator {trend_class}">{arrow} {label}</span>'


def get_simple_trend_arrow(change: float) -> str:
    """
    Return simple text arrow for trend.

    Args:
        change: Change percentage

    Returns:
        Arrow character string
    """
    if change > 10:
        return "▲▲"
    elif change > 3:
        return "▲"
    elif change > -3:
        return "●"
    elif change > -10:
        return "▼"
    else:
        return "▼▼"


def render_badges_html(badges: List[str]) -> str:
    """
    Generate styled HTML for badge pills.

    Args:
        badges: List of badge strings (e.g., ["EXCELLENT", "HOT DEAL"])

    Returns:
        HTML string with styled badge pills
    """
    badge_styles = {
        "EXCELLENT": "badge-excellent",
        "HOT DEAL": "badge-hot-deal",
        "CURRENCY WIN": "badge-currency-win",
        "FLIGHT DEAL": "badge-flight-deal",
        "DEFLATION": "badge-deflation",
    }

    html_parts = []
    for badge in badges:
        css_class = badge_styles.get(badge, "badge-excellent")
        html_parts.append(f'<span class="badge {css_class}">{badge}</span>')

    return " ".join(html_parts)


def render_status_indicator(status: str) -> str:
    """
    Render data status indicator.

    Args:
        status: One of "live", "cached", "mock"

    Returns:
        HTML string for status indicator
    """
    status_map = {
        "live": ("status-live", "Live Data"),
        "cached": ("status-cached", "Cached"),
        "mock": ("status-mock", "Demo Mode"),
    }

    css_class, label = status_map.get(status, ("status-mock", "Unknown"))

    return f'''
        <span class="status-indicator {css_class}">
            <span class="status-dot"></span>
            {label}
        </span>
    '''


def render_top_destination_card(
    rank: int,
    country: str,
    score: float,
    flight_cost: int,
    badges: List[str],
    change: float
) -> str:
    """
    Render a top destination card (for top 3).

    Args:
        rank: Destination rank (1, 2, or 3)
        country: Country name
        score: Overall score
        flight_cost: Flight cost in TWD
        badges: List of badge strings
        change: Overall change percentage

    Returns:
        HTML string for the card
    """
    rank_classes = {
        1: ("top-card-gold", "rank-badge-gold"),
        2: ("top-card-silver", "rank-badge-silver"),
        3: ("top-card-bronze", "rank-badge-bronze"),
    }

    card_class, badge_class = rank_classes.get(rank, ("top-card-gold", "rank-badge-gold"))
    score_color = get_score_color(score)
    badges_html = render_badges_html(badges) if badges else ""
    trend_html = get_trend_indicator_html(change)

    return f'''
        <div class="top-card {card_class}">
            <div class="rank-badge {badge_class}">{rank}</div>
            <div class="card-country-name">{country}</div>
            <div class="card-score" style="color: {score_color}">{score:.1f}</div>
            <div class="card-score-label">Overall Score</div>
            <div class="card-detail">
                <span class="card-detail-label">Trend</span>
                {trend_html}
            </div>
            <div class="card-detail">
                <span class="card-detail-label">Flight</span>
                <span class="card-detail-value">{flight_cost:,} TWD</span>
            </div>
            <div style="margin-top: 0.75rem;">
                {badges_html}
            </div>
        </div>
    '''


def render_metric_card(label: str, value: str, delta: Optional[str] = None, delta_positive: bool = True) -> str:
    """
    Render a styled metric card.

    Args:
        label: Metric label
        value: Metric value (formatted)
        delta: Optional delta value string
        delta_positive: Whether delta is positive (for color)

    Returns:
        HTML string for metric card
    """
    delta_html = ""
    if delta:
        delta_class = "metric-delta-positive" if delta_positive else "metric-delta-negative"
        delta_html = f'<div class="metric-delta {delta_class}">{delta}</div>'

    return f'''
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
            {delta_html}
        </div>
    '''


def render_score_breakdown_card(
    title: str,
    score: float,
    change: float,
    current: str,
    baseline: str,
    card_type: str = "exchange"
) -> str:
    """
    Render a score breakdown card.

    Args:
        title: Component title (e.g., "Exchange Rate")
        score: Component score
        change: Change percentage
        current: Current value string
        baseline: Baseline value string
        card_type: Card type for styling ("exchange", "flight", "col")

    Returns:
        HTML string for breakdown card
    """
    score_color = get_score_color(score)
    trend_html = get_trend_indicator_html(change)

    return f'''
        <div class="breakdown-card breakdown-card-{card_type}">
            <div class="breakdown-title">{title}</div>
            <div class="breakdown-score" style="color: {score_color}">{score:.1f}</div>
            <div style="margin: 0.5rem 0">{trend_html}</div>
            <div class="breakdown-detail">Current: {current}</div>
            <div class="breakdown-detail">Baseline: {baseline}</div>
        </div>
    '''


def format_ag_grid_badges(badges_list: List[str]) -> str:
    """
    Format badges for AG Grid display (plain text version).

    Args:
        badges_list: List of badge strings

    Returns:
        Formatted string for display
    """
    if not badges_list:
        return ""
    return " | ".join(badges_list)


def get_rank_medal(rank: int) -> str:
    """
    Get rank display string.

    Args:
        rank: Numeric rank

    Returns:
        Formatted rank string
    """
    if rank == 1:
        return "1st"
    elif rank == 2:
        return "2nd"
    elif rank == 3:
        return "3rd"
    else:
        return str(rank)


def render_trend_charts(data: List[Dict], country_name: str):
    """Create 3 line charts for country trends."""
    if len(data) < 2:
        return None

    dates = [d['snapshot_date'] for d in data]
    exchange_rates = [d['exchange_rate'] for d in data]
    flight_costs = [d['flight_cost'] for d in data]
    col_amounts = [d['col_amount'] for d in data]

    fig = make_subplots(rows=1, cols=3, subplot_titles=(
        'Exchange Rate', 'Flight Cost (TWD)', 'Cost of Living (USD)'
    ))

    # Chart colors matching existing theme
    fig.add_trace(go.Scatter(x=dates, y=exchange_rates, mode='lines+markers',
                             line=dict(color='#1565C0')), row=1, col=1)
    fig.add_trace(go.Scatter(x=dates, y=flight_costs, mode='lines+markers',
                             line=dict(color='#E65100')), row=1, col=2)
    fig.add_trace(go.Scatter(x=dates, y=col_amounts, mode='lines+markers',
                             line=dict(color='#7B1FA2')), row=1, col=3)

    fig.update_layout(height=250, showlegend=False, margin=dict(l=40, r=40, t=40, b=40))
    return fig
