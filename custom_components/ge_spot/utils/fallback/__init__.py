"""Fallback utilities for GE Spot integration."""
from .source_health import SourceHealth, SourceHealthStatus
from .data_quality import DataQualityScore
from .manager import FallbackManager

__all__ = [
    "SourceHealth",
    "SourceHealthStatus",
    "DataQualityScore",
    "FallbackManager"
]
