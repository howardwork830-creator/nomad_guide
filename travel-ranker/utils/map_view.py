"""
Interactive map visualization for destination rankings.

Provides tools for:
- Rendering world map with color-coded destinations
- Displaying tooltips with key metrics
- Click-to-select functionality
"""

from typing import Dict, Any, List, Optional
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


# ISO country codes mapping (country_key to ISO Alpha-3)
COUNTRY_ISO_CODES = {
    # East Asia
    "japan": "JPN",
    "south_korea": "KOR",
    "hong_kong": "HKG",
    "china": "CHN",
    # Southeast Asia
    "thailand": "THA",
    "vietnam": "VNM",
    "malaysia": "MYS",
    "indonesia": "IDN",
    "philippines": "PHL",
    "singapore": "SGP",
    "cambodia": "KHM",
    "laos": "LAO",
    # South Asia
    "india": "IND",
    "sri_lanka": "LKA",
    "nepal": "NPL",
    # Europe
    "uk": "GBR",
    "germany": "DEU",
    "france": "FRA",
    "spain": "ESP",
    "portugal": "PRT",
    "netherlands": "NLD",
    "georgia": "GEO",
    "estonia": "EST",
    "croatia": "HRV",
    "czech_republic": "CZE",
    "poland": "POL",
    "hungary": "HUN",
    "greece": "GRC",
    "albania": "ALB",
    "romania": "ROU",
    "bulgaria": "BGR",
    "iceland": "ISL",
    "switzerland": "CHE",
    # Americas
    "usa": "USA",
    "mexico": "MEX",
    "colombia": "COL",
    "argentina": "ARG",
    "brazil": "BRA",
    "peru": "PER",
    "costa_rica": "CRI",
    "chile": "CHL",
    "panama": "PAN",
    "canada": "CAN",
    # Middle East
    "uae": "ARE",
    "turkey": "TUR",
    "israel": "ISR",
    # Africa
    "morocco": "MAR",
    "south_africa": "ZAF",
    "egypt": "EGY",
    "kenya": "KEN",
    # Oceania
    "australia": "AUS",
    "new_zealand": "NZL",
}


def get_score_color(score: float) -> str:
    """Get color based on score value."""
    if score >= 85:
        return "#2E7D32"  # Dark green
    elif score >= 70:
        return "#4CAF50"  # Green
    elif score >= 55:
        return "#8BC34A"  # Light green
    elif score >= 45:
        return "#FFC107"  # Yellow
    elif score >= 35:
        return "#FF9800"  # Orange
    else:
        return "#F44336"  # Red


def create_world_map(
    df: pd.DataFrame,
    color_by: str = "Score",
    show_all_countries: bool = True
) -> go.Figure:
    """
    Create an interactive world map showing destinations.

    Args:
        df: DataFrame with destination data (must have 'country_key' column)
        color_by: Column to use for coloring (Score, Safety, etc.)
        show_all_countries: Whether to show countries not in the dataset

    Returns:
        Plotly Figure object
    """
    if df.empty:
        return None

    # Add ISO codes to dataframe
    df_map = df.copy()
    df_map['iso_alpha'] = df_map['country_key'].map(COUNTRY_ISO_CODES)

    # Remove rows without ISO codes
    df_map = df_map[df_map['iso_alpha'].notna()]

    # Create hover text
    df_map['hover_text'] = df_map.apply(
        lambda row: (
            f"<b>{row['Country']}</b><br>"
            f"Rank: #{row['Rank']}<br>"
            f"Score: {row['Score']:.1f}<br>"
            f"Flight: {row['Flight Cost (TWD)']:,} TWD<br>"
            f"CoL: ${row['Monthly CoL (USD)']:,}/mo"
        ),
        axis=1
    )

    # Choose color scale based on metric
    if color_by in ['Score', 'Safety', 'Quality']:
        color_scale = [
            [0, '#F44336'],    # Red (low)
            [0.3, '#FF9800'],  # Orange
            [0.5, '#FFC107'],  # Yellow
            [0.7, '#8BC34A'],  # Light green
            [1, '#2E7D32']     # Dark green (high)
        ]
        color_range = [0, 100]
    else:
        # For costs, reverse the scale (lower = better = green)
        color_scale = [
            [0, '#2E7D32'],    # Green (low cost)
            [0.3, '#8BC34A'],
            [0.5, '#FFC107'],
            [0.7, '#FF9800'],
            [1, '#F44336']     # Red (high cost)
        ]
        color_range = [df_map[color_by].min(), df_map[color_by].max()]

    fig = px.choropleth(
        df_map,
        locations='iso_alpha',
        color=color_by,
        hover_name='Country',
        hover_data={
            'iso_alpha': False,
            'Score': ':.1f',
            'Rank': True,
            'Flight Cost (TWD)': ':,',
            'Monthly CoL (USD)': ':,',
        },
        color_continuous_scale=color_scale,
        range_color=color_range,
        labels={color_by: color_by},
    )

    # Update layout
    fig.update_layout(
        title=dict(
            text=f"Destinations by {color_by}",
            font=dict(size=18),
            x=0.5
        ),
        geo=dict(
            showframe=False,
            showcoastlines=True,
            coastlinecolor='#CCCCCC',
            projection_type='natural earth',
            showland=True,
            landcolor='#F5F5F5',
            showocean=True,
            oceancolor='#E3F2FD',
            showcountries=True,
            countrycolor='#CCCCCC',
            countrywidth=0.5,
        ),
        coloraxis_colorbar=dict(
            title=color_by,
            tickfont=dict(size=10),
            len=0.6,
            y=0.5,
        ),
        margin=dict(t=50, b=20, l=20, r=20),
        height=500,
    )

    return fig


def create_region_map(
    df: pd.DataFrame,
    region: str,
    color_by: str = "Score"
) -> go.Figure:
    """
    Create a zoomed map for a specific region.

    Args:
        df: DataFrame with destination data
        region: Region to focus on (e.g., 'Europe', 'Southeast Asia')
        color_by: Column to use for coloring

    Returns:
        Plotly Figure object
    """
    # Filter to region
    df_region = df[df['Region'] == region].copy()

    if df_region.empty:
        return None

    # Add ISO codes
    df_region['iso_alpha'] = df_region['country_key'].map(COUNTRY_ISO_CODES)
    df_region = df_region[df_region['iso_alpha'].notna()]

    # Region-specific map settings
    region_settings = {
        "East Asia": {"center": {"lat": 35, "lon": 120}, "zoom": 2.5},
        "Southeast Asia": {"center": {"lat": 10, "lon": 110}, "zoom": 2.5},
        "South Asia": {"center": {"lat": 22, "lon": 80}, "zoom": 2.5},
        "Europe": {"center": {"lat": 50, "lon": 10}, "zoom": 2.5},
        "Americas": {"center": {"lat": 10, "lon": -80}, "zoom": 1.5},
        "Middle East": {"center": {"lat": 30, "lon": 45}, "zoom": 2.5},
        "Africa": {"center": {"lat": 5, "lon": 20}, "zoom": 2},
        "Oceania": {"center": {"lat": -25, "lon": 145}, "zoom": 2},
    }

    settings = region_settings.get(region, {"center": {"lat": 20, "lon": 0}, "zoom": 1})

    fig = px.scatter_geo(
        df_region,
        locations='iso_alpha',
        color=color_by,
        hover_name='Country',
        size=[30] * len(df_region),  # Uniform size for visibility
        hover_data={
            'iso_alpha': False,
            'Score': ':.1f',
            'Rank': True,
        },
        color_continuous_scale='RdYlGn',
    )

    fig.update_layout(
        title=f"{region} Destinations",
        geo=dict(
            center=settings["center"],
            projection_scale=settings["zoom"],
            showframe=False,
            showcoastlines=True,
            landcolor='#F5F5F5',
            oceancolor='#E3F2FD',
        ),
        height=400,
        margin=dict(t=50, b=20, l=20, r=20),
    )

    return fig


def create_bubble_map(
    df: pd.DataFrame,
    size_by: str = "Score",
    color_by: str = "Region"
) -> go.Figure:
    """
    Create a bubble map where bubble size represents a metric.

    Args:
        df: DataFrame with destination data
        size_by: Column to use for bubble size
        color_by: Column to use for bubble color

    Returns:
        Plotly Figure object
    """
    if df.empty:
        return None

    # Add ISO codes and coordinates
    df_map = df.copy()
    df_map['iso_alpha'] = df_map['country_key'].map(COUNTRY_ISO_CODES)
    df_map = df_map[df_map['iso_alpha'].notna()]

    # Normalize size values for better visualization
    min_size = df_map[size_by].min()
    max_size = df_map[size_by].max()
    df_map['bubble_size'] = (
        (df_map[size_by] - min_size) / (max_size - min_size) * 30 + 10
    )

    fig = px.scatter_geo(
        df_map,
        locations='iso_alpha',
        color=color_by,
        size='bubble_size',
        hover_name='Country',
        hover_data={
            'iso_alpha': False,
            'bubble_size': False,
            'Score': ':.1f',
            'Rank': True,
            'Region': True,
            'Flight Cost (TWD)': ':,',
        },
        projection='natural earth',
    )

    fig.update_layout(
        title=f"Destinations (sized by {size_by})",
        geo=dict(
            showframe=False,
            showcoastlines=True,
            coastlinecolor='#CCCCCC',
            landcolor='#F5F5F5',
            oceancolor='#E3F2FD',
        ),
        height=500,
        margin=dict(t=50, b=20, l=20, r=20),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.15,
            xanchor="center",
            x=0.5
        )
    )

    return fig


def create_flight_routes_map(
    df: pd.DataFrame,
    origin_lat: float = 25.0797,  # TPE latitude
    origin_lon: float = 121.2342,  # TPE longitude
    top_n: int = 10
) -> go.Figure:
    """
    Create a map showing flight routes from Taiwan to top destinations.

    Args:
        df: DataFrame with destination data
        origin_lat: Origin airport latitude (TPE default)
        origin_lon: Origin airport longitude (TPE default)
        top_n: Number of top destinations to show routes for

    Returns:
        Plotly Figure object
    """
    if df.empty:
        return None

    # Get top N destinations
    df_top = df.head(top_n).copy()

    # Destination coordinates (approximate capital/major city coordinates)
    dest_coords = {
        "japan": (35.6762, 139.6503),      # Tokyo
        "south_korea": (37.5665, 126.9780), # Seoul
        "hong_kong": (22.3193, 114.1694),
        "china": (31.2304, 121.4737),       # Shanghai
        "thailand": (13.7563, 100.5018),    # Bangkok
        "vietnam": (10.8231, 106.6297),     # Ho Chi Minh
        "malaysia": (3.1390, 101.6869),     # KL
        "indonesia": (-6.2088, 106.8456),   # Jakarta
        "philippines": (14.5995, 120.9842), # Manila
        "singapore": (1.3521, 103.8198),
        "india": (28.6139, 77.2090),        # Delhi
        "uk": (51.5074, -0.1278),           # London
        "germany": (52.5200, 13.4050),      # Berlin
        "france": (48.8566, 2.3522),        # Paris
        "spain": (40.4168, -3.7038),        # Madrid
        "portugal": (38.7223, -9.1393),     # Lisbon
        "netherlands": (52.3676, 4.9041),   # Amsterdam
        "usa": (34.0522, -118.2437),        # LA
        "mexico": (19.4326, -99.1332),      # Mexico City
        "colombia": (4.7110, -74.0721),     # Bogota
        "argentina": (-34.6037, -58.3816),  # Buenos Aires
        "uae": (25.2048, 55.2708),          # Dubai
        "turkey": (41.0082, 28.9784),       # Istanbul
        "australia": (-33.8688, 151.2093),  # Sydney
        "new_zealand": (-36.8485, 174.7633),# Auckland
        "georgia": (41.7151, 44.8271),      # Tbilisi
        "estonia": (59.4370, 24.7536),      # Tallinn
        "croatia": (45.8150, 15.9819),      # Zagreb
        "czech_republic": (50.0755, 14.4378),# Prague
        "poland": (52.2297, 21.0122),       # Warsaw
        "hungary": (47.4979, 19.0402),      # Budapest
        "greece": (37.9838, 23.7275),       # Athens
        "albania": (41.3275, 19.8187),      # Tirana
        "romania": (44.4268, 26.1025),      # Bucharest
        "bulgaria": (42.6977, 23.3219),     # Sofia
        "brazil": (-23.5505, -46.6333),     # Sao Paulo
        "peru": (-12.0464, -77.0428),       # Lima
        "costa_rica": (9.9281, -84.0907),   # San Jose
        "chile": (-33.4489, -70.6693),      # Santiago
        "panama": (8.9824, -79.5199),       # Panama City
        "cambodia": (11.5564, 104.9282),    # Phnom Penh
        "laos": (17.9757, 102.6331),        # Vientiane
        "sri_lanka": (6.9271, 79.8612),     # Colombo
        "nepal": (27.7172, 85.3240),        # Kathmandu
        "morocco": (33.5731, -7.5898),      # Casablanca
        "south_africa": (-33.9249, 18.4241),# Cape Town
        "egypt": (30.0444, 31.2357),        # Cairo
        "kenya": (-1.2921, 36.8219),        # Nairobi
        "israel": (32.0853, 34.7818),       # Tel Aviv
        "iceland": (64.1466, -21.9426),     # Reykjavik
        "canada": (49.2827, -123.1207),     # Vancouver
        "switzerland": (47.3769, 8.5417),   # Zurich
    }

    fig = go.Figure()

    # Add destination points
    for _, row in df_top.iterrows():
        country_key = row['country_key']
        if country_key in dest_coords:
            lat, lon = dest_coords[country_key]
            score = row['Score']

            # Add route line
            fig.add_trace(go.Scattergeo(
                lon=[origin_lon, lon],
                lat=[origin_lat, lat],
                mode='lines',
                line=dict(
                    width=2,
                    color=get_score_color(score),
                ),
                opacity=0.6,
                hoverinfo='skip',
                showlegend=False,
            ))

            # Add destination marker
            fig.add_trace(go.Scattergeo(
                lon=[lon],
                lat=[lat],
                mode='markers+text',
                marker=dict(
                    size=12,
                    color=get_score_color(score),
                    line=dict(width=1, color='white'),
                ),
                text=row['Country'],
                textposition='top center',
                textfont=dict(size=9),
                hovertemplate=(
                    f"<b>{row['Country']}</b><br>"
                    f"Rank: #{row['Rank']}<br>"
                    f"Score: {score:.1f}<br>"
                    f"Flight: {row['Flight Cost (TWD)']:,} TWD"
                    "<extra></extra>"
                ),
                showlegend=False,
            ))

    # Add Taiwan (origin)
    fig.add_trace(go.Scattergeo(
        lon=[origin_lon],
        lat=[origin_lat],
        mode='markers+text',
        marker=dict(
            size=15,
            color='#1E88E5',
            symbol='star',
            line=dict(width=2, color='white'),
        ),
        text='Taiwan',
        textposition='bottom center',
        textfont=dict(size=10, color='#1E88E5'),
        hovertemplate="<b>Taiwan (TPE)</b><br>Origin<extra></extra>",
        showlegend=False,
    ))

    fig.update_layout(
        title=f"Top {top_n} Destination Routes from Taiwan",
        geo=dict(
            projection_type='natural earth',
            showframe=False,
            showcoastlines=True,
            coastlinecolor='#CCCCCC',
            landcolor='#F5F5F5',
            oceancolor='#E3F2FD',
            showcountries=True,
            countrycolor='#CCCCCC',
        ),
        height=500,
        margin=dict(t=50, b=20, l=20, r=20),
    )

    return fig


def get_region_stats(df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    """
    Calculate statistics by region for display.

    Args:
        df: DataFrame with destination data

    Returns:
        Dictionary with region-level statistics
    """
    stats = {}

    for region in df['Region'].unique():
        region_df = df[df['Region'] == region]
        stats[region] = {
            "count": len(region_df),
            "avg_score": round(region_df['Score'].mean(), 1),
            "best_destination": region_df.loc[region_df['Score'].idxmax(), 'Country'],
            "avg_flight_cost": int(region_df['Flight Cost (TWD)'].mean()),
            "avg_col": int(region_df['Monthly CoL (USD)'].mean()),
        }

    return stats
