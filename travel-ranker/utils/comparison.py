"""
Destination comparison utilities for side-by-side analysis.

Provides tools for:
- Comparing 2-3 destinations across all indicators
- Generating radar charts for visual comparison
- Highlighting differences and trade-offs
"""

from typing import Dict, Any, List, Optional, Tuple
import plotly.graph_objects as go
import plotly.express as px


def normalize_score(value: float, min_val: float, max_val: float) -> float:
    """Normalize a value to 0-100 scale."""
    if max_val == min_val:
        return 50.0
    return ((value - min_val) / (max_val - min_val)) * 100


def create_comparison_radar_chart(
    destinations: List[Dict[str, Any]],
    include_expanded: bool = True
) -> go.Figure:
    """
    Create a radar chart comparing multiple destinations.

    Args:
        destinations: List of destination dictionaries with score_data
        include_expanded: Whether to include safety/visa/access indicators

    Returns:
        Plotly Figure object
    """
    if not destinations:
        return None

    # Define categories based on whether we have expanded data
    if include_expanded and _has_expanded_data(destinations[0]):
        categories = [
            'Exchange Rate',
            'Flight Cost',
            'Cost of Living',
            'Safety',
            'Visa Ease',
            'Accessibility'
        ]
    else:
        categories = [
            'Exchange Rate',
            'Flight Cost',
            'Cost of Living'
        ]

    fig = go.Figure()

    # Color palette for up to 4 destinations
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']

    for i, dest in enumerate(destinations):
        score_data = dest.get('score_data', {})
        components = score_data.get('components', {})

        # Build values for each category
        values = [
            components.get('exchange', {}).get('score', 50),
            components.get('flight', {}).get('score', 50),
            components.get('col', {}).get('score', 50),
        ]

        if include_expanded and _has_expanded_data(dest):
            values.extend([
                components.get('safety', {}).get('score', 50),
                components.get('visa', {}).get('score', 50),
                components.get('access', {}).get('score', 50),
            ])

        # Close the radar chart
        values.append(values[0])
        categories_closed = categories + [categories[0]]

        fig.add_trace(go.Scatterpolar(
            r=values,
            theta=categories_closed,
            fill='toself',
            name=dest.get('Country', f'Destination {i+1}'),
            line=dict(color=colors[i % len(colors)]),
            fillcolor=colors[i % len(colors)],
            opacity=0.3
        ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 100],
                tickfont=dict(size=10),
            ),
            angularaxis=dict(
                tickfont=dict(size=11),
            )
        ),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.2,
            xanchor="center",
            x=0.5
        ),
        title=dict(
            text="Destination Comparison",
            font=dict(size=16)
        ),
        margin=dict(t=60, b=80, l=60, r=60),
        height=450,
    )

    return fig


def create_comparison_bar_chart(
    destinations: List[Dict[str, Any]],
    metric: str = "Score"
) -> go.Figure:
    """
    Create a grouped bar chart comparing destinations on a specific metric.

    Args:
        destinations: List of destination dictionaries
        metric: The metric to compare (Score, Flight Cost, CoL, Safety, etc.)

    Returns:
        Plotly Figure object
    """
    if not destinations:
        return None

    countries = [d.get('Country', f'Dest {i}') for i, d in enumerate(destinations)]
    values = [d.get(metric, 0) for d in destinations]

    # Color based on value (green = better)
    if metric in ['Score', 'Safety', 'Visa Ease', 'Quality']:
        # Higher is better
        colors = ['#4CAF50' if v >= 70 else '#FFC107' if v >= 50 else '#F44336' for v in values]
    else:
        # Lower is better (costs)
        max_val = max(values) if values else 1
        colors = ['#4CAF50' if v <= max_val * 0.4 else '#FFC107' if v <= max_val * 0.7 else '#F44336' for v in values]

    fig = go.Figure(data=[
        go.Bar(
            x=countries,
            y=values,
            marker_color=colors,
            text=[f'{v:.1f}' if isinstance(v, float) else str(v) for v in values],
            textposition='outside'
        )
    ])

    fig.update_layout(
        title=f'{metric} Comparison',
        xaxis_title='Destination',
        yaxis_title=metric,
        height=350,
        margin=dict(t=50, b=50, l=50, r=50),
    )

    return fig


def calculate_comparison_summary(
    destinations: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Calculate summary statistics for destination comparison.

    Args:
        destinations: List of destination dictionaries

    Returns:
        Dictionary with comparison insights
    """
    if not destinations:
        return {}

    if len(destinations) < 2:
        return {"error": "Need at least 2 destinations to compare"}

    # Extract key metrics
    scores = [d.get('Score', 0) for d in destinations]
    flight_costs = [d.get('Flight Cost (TWD)', 0) for d in destinations]
    col_costs = [d.get('Monthly CoL (USD)', 0) for d in destinations]
    countries = [d.get('Country', '') for d in destinations]

    # Find best/worst for each metric
    best_score_idx = scores.index(max(scores))
    best_flight_idx = flight_costs.index(min(flight_costs))
    best_col_idx = col_costs.index(min(col_costs))

    # Calculate differences
    score_diff = max(scores) - min(scores)
    flight_diff = max(flight_costs) - min(flight_costs)
    col_diff = max(col_costs) - min(col_costs)

    summary = {
        "best_overall": {
            "country": countries[best_score_idx],
            "score": scores[best_score_idx]
        },
        "cheapest_flight": {
            "country": countries[best_flight_idx],
            "cost": flight_costs[best_flight_idx]
        },
        "lowest_col": {
            "country": countries[best_col_idx],
            "cost": col_costs[best_col_idx]
        },
        "score_spread": round(score_diff, 1),
        "flight_cost_spread": int(flight_diff),
        "col_spread": int(col_diff),
        "insights": []
    }

    # Generate insights
    if score_diff < 5:
        summary["insights"].append("These destinations have very similar overall scores.")
    elif score_diff > 20:
        summary["insights"].append(f"{countries[best_score_idx]} significantly outperforms the others.")

    if flight_diff > 10000:
        summary["insights"].append(
            f"Flight costs vary significantly. {countries[best_flight_idx]} is most accessible."
        )

    if col_diff > 500:
        summary["insights"].append(
            f"{countries[best_col_idx]} offers the lowest cost of living, "
            f"saving ~${col_diff}/month compared to the most expensive option."
        )

    # Check for safety data
    safety_scores = []
    for d in destinations:
        score_data = d.get('score_data', {})
        safety = score_data.get('components', {}).get('safety', {}).get('value')
        if safety:
            safety_scores.append((d.get('Country', ''), safety))

    if safety_scores:
        safest = max(safety_scores, key=lambda x: x[1])
        if safest[1] >= 85:
            summary["insights"].append(f"{safest[0]} is exceptionally safe (score: {safest[1]}).")

    return summary


def get_comparison_table_data(
    destinations: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Generate structured data for a comparison table.

    Args:
        destinations: List of destination dictionaries

    Returns:
        List of dictionaries suitable for table display
    """
    if not destinations:
        return []

    rows = []
    metrics = [
        ("Overall Score", "Score", "higher", None),
        ("Flight Cost", "Flight Cost (TWD)", "lower", "TWD"),
        ("Monthly CoL", "Monthly CoL (USD)", "lower", "USD"),
        ("Data Quality", "Quality", "higher", "%"),
    ]

    # Add expanded metrics if available
    if _has_expanded_data(destinations[0]):
        # Get values from score_data components
        for metric_name, key, better, unit in metrics:
            row = {"Metric": metric_name, "Better": better, "Unit": unit}
            values = []

            for i, dest in enumerate(destinations):
                value = dest.get(key, 0)
                row[dest.get('Country', f'Dest {i}')] = value
                values.append(value)

            # Mark best value
            if better == "higher":
                best_idx = values.index(max(values))
            else:
                best_idx = values.index(min(values))

            row["best_country"] = destinations[best_idx].get('Country', '')
            rows.append(row)

        # Add safety, visa, access from score_data
        expanded_metrics = [
            ("Safety Index", "safety", "higher"),
            ("Visa Ease", "visa", "higher"),
            ("Travel Access", "access", "higher"),
        ]

        for metric_name, comp_key, better in expanded_metrics:
            row = {"Metric": metric_name, "Better": better, "Unit": "pts"}
            values = []

            for i, dest in enumerate(destinations):
                score_data = dest.get('score_data', {})
                comp = score_data.get('components', {}).get(comp_key, {})
                value = comp.get('value', 0) or 0
                row[dest.get('Country', f'Dest {i}')] = value
                values.append(value)

            if values and any(v > 0 for v in values):
                best_idx = values.index(max(values))
                row["best_country"] = destinations[best_idx].get('Country', '')
                rows.append(row)
    else:
        for metric_name, key, better, unit in metrics:
            row = {"Metric": metric_name, "Better": better, "Unit": unit}
            values = []

            for i, dest in enumerate(destinations):
                value = dest.get(key, 0)
                row[dest.get('Country', f'Dest {i}')] = value
                values.append(value)

            if better == "higher":
                best_idx = values.index(max(values))
            else:
                best_idx = values.index(min(values))

            row["best_country"] = destinations[best_idx].get('Country', '')
            rows.append(row)

    return rows


def _has_expanded_data(destination: Dict[str, Any]) -> bool:
    """Check if destination has expanded indicator data."""
    score_data = destination.get('score_data', {})
    components = score_data.get('components', {})
    return 'safety' in components or 'visa' in components or 'access' in components


def render_comparison_badges_html(destinations: List[Dict[str, Any]]) -> str:
    """
    Render HTML showing unique badges for each destination.

    Args:
        destinations: List of destination dictionaries

    Returns:
        HTML string showing badges comparison
    """
    if not destinations:
        return ""

    html_parts = ['<div style="display: flex; flex-wrap: wrap; gap: 1rem;">']

    for dest in destinations:
        country = dest.get('Country', 'Unknown')
        badges = dest.get('badges_list', [])

        html_parts.append(f'''
        <div style="flex: 1; min-width: 200px; padding: 1rem; background: #f8f9fa; border-radius: 8px;">
            <h4 style="margin: 0 0 0.5rem 0; color: #333;">{country}</h4>
            <div style="display: flex; flex-wrap: wrap; gap: 0.25rem;">
        ''')

        if badges:
            for badge in badges:
                badge_color = _get_badge_color(badge)
                html_parts.append(f'''
                    <span style="
                        background: {badge_color['bg']};
                        color: {badge_color['text']};
                        padding: 2px 8px;
                        border-radius: 4px;
                        font-size: 0.75rem;
                        font-weight: 500;
                    ">{badge}</span>
                ''')
        else:
            html_parts.append('<span style="color: #666; font-size: 0.85rem;">No badges</span>')

        html_parts.append('</div></div>')

    html_parts.append('</div>')

    return ''.join(html_parts)


def _get_badge_color(badge: str) -> Dict[str, str]:
    """Get color scheme for a badge."""
    badge_colors = {
        "EXCELLENT": {"bg": "#E8F5E9", "text": "#2E7D32"},
        "HOT DEAL": {"bg": "#FFEBEE", "text": "#C62828"},
        "CURRENCY WIN": {"bg": "#E3F2FD", "text": "#1565C0"},
        "FLIGHT DEAL": {"bg": "#FFF3E0", "text": "#E65100"},
        "DEFLATION": {"bg": "#F3E5F5", "text": "#7B1FA2"},
        "SAFE HAVEN": {"bg": "#E0F7FA", "text": "#00695C"},
        "EASY ENTRY": {"bg": "#FFF8E1", "text": "#FF6F00"},
        "NOMAD VISA": {"bg": "#FCE4EC", "text": "#AD1457"},
        "WELL CONNECTED": {"bg": "#E8EAF6", "text": "#283593"},
    }
    return badge_colors.get(badge, {"bg": "#ECEFF1", "text": "#455A64"})
