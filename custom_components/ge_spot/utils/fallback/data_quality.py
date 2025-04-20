"""Data quality scoring for API sources."""
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

_LOGGER = logging.getLogger(__name__)

class DataQualityScore:
    """Score data quality from different sources."""

    def __init__(self):
        """Initialize data quality scorer."""
        self.scores = {}

    def score_data(self, data: Dict[str, Any], source: str) -> float:
        """Score data quality.

        Args:
            data: Data to score
            source: Source identifier

        Returns:
            Quality score (0.0 to 1.0)
        """
        if not data:
            return 0.0

        # Initialize score components
        completeness = self._score_completeness(data)
        consistency = self._score_consistency(data)
        timeliness = self._score_timeliness(data)

        # Calculate overall score
        score = (completeness + consistency + timeliness) / 3

        # Store score
        self.scores[source] = {
            "overall": score,
            "completeness": completeness,
            "consistency": consistency,
            "timeliness": timeliness,
            "timestamp": datetime.now().isoformat()
        }

        return score

    def _score_completeness(self, data: Dict[str, Any]) -> float:
        """Score data completeness.

        Args:
            data: Data to score

        Returns:
            Completeness score (0.0 to 1.0)
        """
        # Check for required fields
        required_fields = [
            "hourly_prices",
            "current_price",
            "next_hour_price",
            "day_average_price"
        ]

        # Optional but valuable fields
        valuable_fields = [
            "tomorrow_hourly_prices"
        ]

        # Count present fields
        present = sum(1 for field in required_fields if field in data and data[field] is not None)
        valuable_present = sum(1 for field in valuable_fields if field in data and data[field] is not None)

        # Check hourly prices
        hourly_completeness = 0.0
        if "hourly_prices" in data and isinstance(data["hourly_prices"], dict):
            # Expect 24 hours
            hourly_completeness = len(data["hourly_prices"]) / 24

        # Check tomorrow hourly prices
        tomorrow_completeness = 0.0
        if "tomorrow_hourly_prices" in data and isinstance(data["tomorrow_hourly_prices"], dict):
            # Expect 24 hours
            tomorrow_completeness = len(data["tomorrow_hourly_prices"]) / 24

        # Combine scores - weight required fields, hourly completeness, and tomorrow data
        # 50% for required fields, 25% for today hours, 25% for tomorrow hours
        required_score = 0.5 * (present / max(1, len(required_fields)))
        today_score = 0.25 * hourly_completeness
        tomorrow_score = 0.25 * tomorrow_completeness

        # Add bonus for having valuable fields
        valuable_bonus = 0.1 * (valuable_present / max(1, len(valuable_fields)))

        # Cap total score at 1.0
        return min(1.0, required_score + today_score + tomorrow_score + valuable_bonus)

    def _score_consistency(self, data: Dict[str, Any]) -> float:
        """Score data consistency.

        Args:
            data: Data to score

        Returns:
            Consistency score (0.0 to 1.0)
        """
        # Check if statistics are consistent with hourly prices
        if "hourly_prices" not in data or not isinstance(data["hourly_prices"], dict) or not data["hourly_prices"]:
            return 0.5  # Neutral score if no hourly prices

        hourly_prices = [price for price in data["hourly_prices"].values() if isinstance(price, (int, float))]
        if not hourly_prices:
            return 0.5

        # Calculate expected statistics
        expected_avg = sum(hourly_prices) / len(hourly_prices)
        expected_peak = max(hourly_prices)
        expected_off_peak = min(hourly_prices)

        # Check if actual statistics match expected
        consistency_scores = []

        if "day_average_price" in data and data["day_average_price"] is not None:
            avg_diff = abs(data["day_average_price"] - expected_avg) / max(1, expected_avg)
            consistency_scores.append(max(0, 1 - avg_diff))

        if "peak_price" in data and data["peak_price"] is not None:
            peak_diff = abs(data["peak_price"] - expected_peak) / max(1, expected_peak)
            consistency_scores.append(max(0, 1 - peak_diff))

        if "off_peak_price" in data and data["off_peak_price"] is not None:
            off_peak_diff = abs(data["off_peak_price"] - expected_off_peak) / max(1, expected_off_peak)
            consistency_scores.append(max(0, 1 - off_peak_diff))

        # Return average consistency score
        return sum(consistency_scores) / max(1, len(consistency_scores))

    def _score_timeliness(self, data: Dict[str, Any]) -> float:
        """Score data timeliness.

        Args:
            data: Data to score

        Returns:
            Timeliness score (0.0 to 1.0)
        """
        # Check if data has a timestamp
        if "last_updated" not in data:
            return 0.5  # Neutral score if no timestamp

        try:
            # Parse timestamp
            if isinstance(data["last_updated"], str):
                last_updated = datetime.fromisoformat(data["last_updated"].replace('Z', '+00:00'))
            elif isinstance(data["last_updated"], datetime):
                last_updated = data["last_updated"]
            else:
                return 0.5

            # Calculate age in hours
            age_hours = (datetime.now(last_updated.tzinfo) - last_updated).total_seconds() / 3600

            # Score based on age
            if age_hours <= 1:
                return 1.0  # Fresh data
            elif age_hours <= 3:
                return 0.8  # Recent data
            elif age_hours <= 6:
                return 0.6  # Somewhat recent
            elif age_hours <= 12:
                return 0.4  # Older data
            elif age_hours <= 24:
                return 0.2  # Old data
            else:
                return 0.0  # Very old data

        except (ValueError, TypeError):
            return 0.5  # Neutral score if timestamp parsing fails

    def get_best_source(self, sources: List[str]) -> Optional[str]:
        """Get the best source based on quality scores.

        Args:
            sources: List of sources to consider

        Returns:
            Best source, or None if no scores available
        """
        # Filter to sources with scores
        scored_sources = [s for s in sources if s in self.scores]
        if not scored_sources:
            return None

        # Return source with highest score
        return max(scored_sources, key=lambda s: self.scores[s]["overall"])

    def get_scores(self) -> Dict[str, Any]:
        """Get all quality scores."""
        return self.scores
