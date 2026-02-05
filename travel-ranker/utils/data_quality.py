"""
Data quality scoring and provenance tracking.

Provides tools for:
- Tracking data source and freshness
- Calculating confidence scores
- Managing data provenance metadata
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Literal, Optional


# ============================================================================
# Data Source Types
# ============================================================================

class DataSource(Enum):
    """Source types for data provenance."""
    LIVE_API = "live_api"       # Fresh data from API
    CACHE = "cache"             # Cached data within TTL
    STALE_CACHE = "stale_cache" # Cached data beyond TTL but usable
    BASELINE = "baseline"       # Baseline/historical data
    MOCK = "mock"               # Mock/demo data


# Source quality scores (higher = better)
SOURCE_QUALITY_SCORES = {
    DataSource.LIVE_API: 100,
    DataSource.CACHE: 90,
    DataSource.STALE_CACHE: 60,
    DataSource.BASELINE: 40,
    DataSource.MOCK: 20,
}


# ============================================================================
# Data Provenance Types
# ============================================================================

@dataclass
class DataWithProvenance:
    """
    Container for data with provenance tracking.

    Tracks the source, freshness, and quality of a data value.
    """

    value: Any
    source: DataSource
    fetched_at: datetime
    cache_age_seconds: Optional[int] = None
    quality_score: float = 50.0  # 0-100 confidence
    field_name: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None
    validation_warnings: List[str] = field(default_factory=list)

    @property
    def is_fresh(self) -> bool:
        """Check if data is considered fresh (< 1 hour old)."""
        if self.source in (DataSource.LIVE_API, DataSource.CACHE):
            age = (datetime.now() - self.fetched_at).total_seconds()
            return age < 3600  # 1 hour
        return False

    @property
    def is_stale(self) -> bool:
        """Check if data is stale (> 24 hours old)."""
        if self.source == DataSource.STALE_CACHE:
            return True
        age = (datetime.now() - self.fetched_at).total_seconds()
        return age > 86400  # 24 hours

    @property
    def freshness_level(self) -> Literal["fresh", "recent", "stale", "very_stale"]:
        """Get freshness level category."""
        age_hours = (datetime.now() - self.fetched_at).total_seconds() / 3600

        if age_hours < 1:
            return "fresh"
        elif age_hours < 24:
            return "recent"
        elif age_hours < 168:  # 1 week
            return "stale"
        else:
            return "very_stale"

    @property
    def freshness_color(self) -> str:
        """Get color indicator for UI display."""
        level = self.freshness_level
        colors = {
            "fresh": "#4CAF50",      # Green
            "recent": "#8BC34A",     # Light green
            "stale": "#FFC107",      # Yellow
            "very_stale": "#F44336", # Red
        }
        return colors.get(level, "#9E9E9E")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "value": self.value,
            "source": self.source.value,
            "fetched_at": self.fetched_at.isoformat(),
            "cache_age_seconds": self.cache_age_seconds,
            "quality_score": self.quality_score,
            "field_name": self.field_name,
            "freshness_level": self.freshness_level,
            "validation_warnings": self.validation_warnings,
        }

    @classmethod
    def from_api(
        cls,
        value: Any,
        field_name: str = "",
        quality_score: float = 100.0
    ) -> "DataWithProvenance":
        """Create from fresh API data."""
        return cls(
            value=value,
            source=DataSource.LIVE_API,
            fetched_at=datetime.now(),
            quality_score=quality_score,
            field_name=field_name,
        )

    @classmethod
    def from_cache(
        cls,
        value: Any,
        cached_at: datetime,
        field_name: str = "",
        is_stale: bool = False
    ) -> "DataWithProvenance":
        """Create from cached data."""
        age_seconds = int((datetime.now() - cached_at).total_seconds())
        source = DataSource.STALE_CACHE if is_stale else DataSource.CACHE

        # Reduce quality based on age
        base_score = SOURCE_QUALITY_SCORES[source]
        age_penalty = min(age_seconds / 3600, 20)  # Up to 20 point penalty
        quality_score = max(base_score - age_penalty, 20)

        return cls(
            value=value,
            source=source,
            fetched_at=cached_at,
            cache_age_seconds=age_seconds,
            quality_score=quality_score,
            field_name=field_name,
        )

    @classmethod
    def from_baseline(
        cls,
        value: Any,
        field_name: str = "",
        baseline_date: Optional[datetime] = None
    ) -> "DataWithProvenance":
        """Create from baseline data."""
        return cls(
            value=value,
            source=DataSource.BASELINE,
            fetched_at=baseline_date or datetime.now(),
            quality_score=SOURCE_QUALITY_SCORES[DataSource.BASELINE],
            field_name=field_name,
        )

    @classmethod
    def from_mock(cls, value: Any, field_name: str = "") -> "DataWithProvenance":
        """Create from mock data."""
        return cls(
            value=value,
            source=DataSource.MOCK,
            fetched_at=datetime.now(),
            quality_score=SOURCE_QUALITY_SCORES[DataSource.MOCK],
            field_name=field_name,
        )


# ============================================================================
# Data Quality Tracking
# ============================================================================

@dataclass
class DestinationDataQuality:
    """
    Quality tracking for all data components of a destination.

    Combines quality scores from exchange rate, flight cost, CoL data,
    and the new indicators: safety, visa, and travel accessibility.
    """

    country_key: str
    country_name: str
    exchange_data: Optional[DataWithProvenance] = None
    flight_data: Optional[DataWithProvenance] = None
    col_data: Optional[DataWithProvenance] = None
    safety_data: Optional[DataWithProvenance] = None
    visa_data: Optional[DataWithProvenance] = None
    access_data: Optional[DataWithProvenance] = None
    overall_quality_score: float = 0.0
    calculated_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """Calculate overall quality score."""
        self._calculate_overall_quality()

    def _calculate_overall_quality(self) -> None:
        """Calculate weighted overall quality score.

        Weights match the scoring weights when all indicators are present:
        - Exchange: 20%
        - Flight: 15%
        - CoL: 35%
        - Safety: 15%
        - Visa: 10%
        - Access: 5%

        Falls back to legacy weights (30/20/50) if new indicators not present.
        """
        scores = []
        weights = []

        # Check if we have expanded indicator data
        has_expanded = (
            self.safety_data is not None or
            self.visa_data is not None or
            self.access_data is not None
        )

        if has_expanded:
            # Use new weights
            if self.exchange_data:
                scores.append(self.exchange_data.quality_score)
                weights.append(0.20)
            if self.flight_data:
                scores.append(self.flight_data.quality_score)
                weights.append(0.15)
            if self.col_data:
                scores.append(self.col_data.quality_score)
                weights.append(0.35)
            if self.safety_data:
                scores.append(self.safety_data.quality_score)
                weights.append(0.15)
            if self.visa_data:
                scores.append(self.visa_data.quality_score)
                weights.append(0.10)
            if self.access_data:
                scores.append(self.access_data.quality_score)
                weights.append(0.05)
        else:
            # Legacy weights
            if self.exchange_data:
                scores.append(self.exchange_data.quality_score)
                weights.append(0.30)
            if self.flight_data:
                scores.append(self.flight_data.quality_score)
                weights.append(0.20)
            if self.col_data:
                scores.append(self.col_data.quality_score)
                weights.append(0.50)

        if scores and weights:
            # Normalize weights
            total_weight = sum(weights)
            normalized_weights = [w / total_weight for w in weights]
            self.overall_quality_score = sum(
                s * w for s, w in zip(scores, normalized_weights)
            )
        else:
            self.overall_quality_score = 0.0

    @property
    def quality_level(self) -> Literal["excellent", "good", "fair", "poor"]:
        """Get quality level category."""
        if self.overall_quality_score >= 80:
            return "excellent"
        elif self.overall_quality_score >= 60:
            return "good"
        elif self.overall_quality_score >= 40:
            return "fair"
        else:
            return "poor"

    @property
    def primary_source(self) -> DataSource:
        """Get the primary data source (lowest quality source)."""
        sources = []
        if self.exchange_data:
            sources.append(self.exchange_data.source)
        if self.flight_data:
            sources.append(self.flight_data.source)
        if self.col_data:
            sources.append(self.col_data.source)
        if self.safety_data:
            sources.append(self.safety_data.source)
        if self.visa_data:
            sources.append(self.visa_data.source)
        if self.access_data:
            sources.append(self.access_data.source)

        if not sources:
            return DataSource.MOCK

        # Return the "worst" source (lowest in enum order represents lower quality)
        source_order = [
            DataSource.MOCK,
            DataSource.BASELINE,
            DataSource.STALE_CACHE,
            DataSource.CACHE,
            DataSource.LIVE_API,
        ]
        for source in source_order:
            if source in sources:
                return source

        return DataSource.MOCK

    @property
    def has_expanded_data(self) -> bool:
        """Check if expanded indicator data is available."""
        return (
            self.safety_data is not None or
            self.visa_data is not None or
            self.access_data is not None
        )

    def get_freshness_summary(self) -> Dict[str, str]:
        """Get freshness levels for all components."""
        summary = {}
        if self.exchange_data:
            summary["exchange"] = self.exchange_data.freshness_level
        if self.flight_data:
            summary["flight"] = self.flight_data.freshness_level
        if self.col_data:
            summary["col"] = self.col_data.freshness_level
        if self.safety_data:
            summary["safety"] = self.safety_data.freshness_level
        if self.visa_data:
            summary["visa"] = self.visa_data.freshness_level
        if self.access_data:
            summary["access"] = self.access_data.freshness_level
        return summary

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        components = {
            "exchange": self.exchange_data.to_dict() if self.exchange_data else None,
            "flight": self.flight_data.to_dict() if self.flight_data else None,
            "col": self.col_data.to_dict() if self.col_data else None,
        }

        # Add expanded components if present
        if self.safety_data:
            components["safety"] = self.safety_data.to_dict()
        if self.visa_data:
            components["visa"] = self.visa_data.to_dict()
        if self.access_data:
            components["access"] = self.access_data.to_dict()

        return {
            "country_key": self.country_key,
            "country_name": self.country_name,
            "overall_quality_score": round(self.overall_quality_score, 1),
            "quality_level": self.quality_level,
            "primary_source": self.primary_source.value,
            "calculated_at": self.calculated_at.isoformat(),
            "has_expanded_data": self.has_expanded_data,
            "components": components,
            "freshness": self.get_freshness_summary(),
        }


# ============================================================================
# Quality Score Calculations
# ============================================================================

def calculate_confidence_multiplier(quality_score: float) -> float:
    """
    Calculate confidence multiplier for score adjustment.

    Higher quality data = multiplier closer to 1.0
    Lower quality data = multiplier closer to 0.8

    Args:
        quality_score: Data quality score (0-100)

    Returns:
        Multiplier between 0.8 and 1.0
    """
    # Map 0-100 quality to 0.8-1.0 multiplier
    # Quality 100 -> 1.0, Quality 0 -> 0.8
    return 0.8 + (quality_score / 100) * 0.2


def calculate_source_quality(
    source: DataSource,
    age_hours: float = 0
) -> float:
    """
    Calculate quality score based on source and age.

    Args:
        source: Data source type
        age_hours: Age of data in hours

    Returns:
        Quality score (0-100)
    """
    base_score = SOURCE_QUALITY_SCORES.get(source, 20)

    # Age penalty (applies mainly to cached data)
    if source in (DataSource.CACHE, DataSource.STALE_CACHE):
        # Penalty increases with age
        # 0 hours -> 0 penalty, 24 hours -> 10 penalty, 168 hours -> 30 penalty
        age_penalty = min(age_hours / 24 * 10, 30)
        return max(base_score - age_penalty, 10)

    return base_score


def aggregate_quality_scores(
    qualities: List[DestinationDataQuality]
) -> Dict[str, Any]:
    """
    Aggregate quality statistics across multiple destinations.

    Args:
        qualities: List of destination quality objects

    Returns:
        Aggregated statistics
    """
    if not qualities:
        return {
            "average_quality": 0,
            "min_quality": 0,
            "max_quality": 0,
            "source_distribution": {},
            "freshness_distribution": {},
        }

    scores = [q.overall_quality_score for q in qualities]

    # Count sources
    source_counts: Dict[str, int] = {}
    for q in qualities:
        source = q.primary_source.value
        source_counts[source] = source_counts.get(source, 0) + 1

    # Count freshness levels
    freshness_counts: Dict[str, int] = {}
    for q in qualities:
        for level in q.get_freshness_summary().values():
            freshness_counts[level] = freshness_counts.get(level, 0) + 1

    return {
        "average_quality": round(sum(scores) / len(scores), 1),
        "min_quality": round(min(scores), 1),
        "max_quality": round(max(scores), 1),
        "source_distribution": source_counts,
        "freshness_distribution": freshness_counts,
        "total_destinations": len(qualities),
    }


# ============================================================================
# Provenance Metadata
# ============================================================================

@dataclass
class ProvenanceMetadata:
    """
    Metadata for tracking data provenance in database records.

    Stores source, quality, and timestamp information.
    """

    data_source: DataSource
    data_quality_score: float
    exchange_source: Optional[str] = None
    flight_source: Optional[str] = None
    col_source: Optional[str] = None
    safety_source: Optional[str] = None
    visa_source: Optional[str] = None
    access_source: Optional[str] = None
    fetched_at: datetime = field(default_factory=datetime.now)

    def to_db_columns(self) -> Dict[str, Any]:
        """Convert to dictionary for database insertion."""
        result = {
            "data_source": self.data_source.value,
            "data_quality_score": round(self.data_quality_score, 1),
            "exchange_source": self.exchange_source or self.data_source.value,
            "flight_source": self.flight_source or self.data_source.value,
            "col_source": self.col_source or self.data_source.value,
        }

        # Add expanded sources if present
        if self.safety_source:
            result["safety_source"] = self.safety_source
        if self.visa_source:
            result["visa_source"] = self.visa_source
        if self.access_source:
            result["access_source"] = self.access_source

        return result

    @classmethod
    def from_destination_quality(
        cls,
        quality: DestinationDataQuality
    ) -> "ProvenanceMetadata":
        """Create from DestinationDataQuality object."""
        return cls(
            data_source=quality.primary_source,
            data_quality_score=quality.overall_quality_score,
            exchange_source=(
                quality.exchange_data.source.value
                if quality.exchange_data else None
            ),
            flight_source=(
                quality.flight_data.source.value
                if quality.flight_data else None
            ),
            col_source=(
                quality.col_data.source.value
                if quality.col_data else None
            ),
            safety_source=(
                quality.safety_data.source.value
                if quality.safety_data else None
            ),
            visa_source=(
                quality.visa_data.source.value
                if quality.visa_data else None
            ),
            access_source=(
                quality.access_data.source.value
                if quality.access_data else None
            ),
        )


# ============================================================================
# UI Display Helpers
# ============================================================================

def get_quality_badge_html(quality_score: float) -> str:
    """
    Generate HTML badge for quality score display.

    Args:
        quality_score: Quality score (0-100)

    Returns:
        HTML string for quality badge
    """
    if quality_score >= 80:
        bg_color = "#E8F5E9"
        text_color = "#2E7D32"
        label = "High Quality"
    elif quality_score >= 60:
        bg_color = "#E3F2FD"
        text_color = "#1565C0"
        label = "Good Quality"
    elif quality_score >= 40:
        bg_color = "#FFF3E0"
        text_color = "#E65100"
        label = "Fair Quality"
    else:
        bg_color = "#FFEBEE"
        text_color = "#C62828"
        label = "Low Quality"

    return f'''
        <span style="
            background-color: {bg_color};
            color: {text_color};
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 500;
        ">{label} ({quality_score:.0f}%)</span>
    '''


def get_freshness_indicator_html(freshness_level: str) -> str:
    """
    Generate HTML indicator for data freshness.

    Args:
        freshness_level: One of 'fresh', 'recent', 'stale', 'very_stale'

    Returns:
        HTML string for freshness indicator
    """
    indicators = {
        "fresh": ("●", "#4CAF50", "Fresh"),
        "recent": ("●", "#8BC34A", "Recent"),
        "stale": ("●", "#FFC107", "Stale"),
        "very_stale": ("●", "#F44336", "Very Stale"),
    }

    dot, color, label = indicators.get(freshness_level, ("●", "#9E9E9E", "Unknown"))

    return f'''
        <span style="color: {color}; font-weight: 600;" title="{label}">
            {dot}
        </span>
        <span style="font-size: 0.75rem; color: #666;">{label}</span>
    '''


def get_source_label(source: DataSource) -> str:
    """
    Get human-readable label for data source.

    Args:
        source: DataSource enum value

    Returns:
        Human-readable label
    """
    labels = {
        DataSource.LIVE_API: "Live API",
        DataSource.CACHE: "Cached",
        DataSource.STALE_CACHE: "Stale Cache",
        DataSource.BASELINE: "Baseline",
        DataSource.MOCK: "Demo Data",
    }
    return labels.get(source, "Unknown")
