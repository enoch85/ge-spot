# filepath: /workspaces/ge-spot/custom_components/ge_spot/api/base_adapter.py
from abc import ABC, abstractmethod
from typing import Dict, Any, List, TypedDict
from dataclasses import dataclass, field
from datetime import datetime

# Define PriceEntry and PriceData structures
class PriceEntry(TypedDict):
    start_time: datetime
    price: float

@dataclass
class PriceData:
    hourly_raw: List[PriceEntry] = field(default_factory=list)
    timezone: str | None = None
    currency: str | None = None
    source: str | None = None
    meta: Dict[str, Any] = field(default_factory=dict)

class BaseAPI(ABC):
    api_name: str # Changed from adapter_name to api_name
    supported_regions: list[str]
    default_priority: int

    def __init__(self, config: Dict[str, Any] | None = None, session: Any | None = None):
        self.config = config or {}
        self.session = session

    @abstractmethod
    async def fetch_data(self, area: str) -> PriceData: # Changed return type to PriceData
        """
        Must return raw API data in a standard dict format:
        {
          "hourly_raw":    [ { "start_time": "2025-04-27T00:00:00+02:00", "price": 10.5 }, ... ],
          "timezone":      "Europe/Stockholm",
          "currency":      "EUR",
          "source_name":   "nordpool",
          # Potentially other metadata like raw API response for debugging
          "raw_response": Any
        }
        """
        pass

    def get_config_value(self, key: str, default: Any = None) -> Any:
        """Helper to get a value from the adapter's configuration."""
        return self.config.get(key, default)

    # You can add other common utility methods here if needed
