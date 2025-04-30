"""Parser for Amber Energy API data."""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from ..base.price_parser import BasePriceParser
from ..base.data_structure import StandardizedPriceData
from ...const.currencies import Currency

_LOGGER = logging.getLogger(__name__)

class AmberParser(BasePriceParser):
    """Parser for Amber Energy API data."""

    def parse(self, data: List[Dict[str, Any]], area: Optional[str] = None) -> Dict[str, Any]:
        """Parse Amber Energy API data.
        
        Args:
            data: Raw API data (list of price entries)
            area: Optional area code
            
        Returns:
            Standardized price data
        """
        if not data:
            _LOGGER.warning("No data to parse")
            return {}
            
        hourly_prices = self.parse_hourly_prices(data)
        
        # Create standardized data structure
        result = StandardizedPriceData.create(
            source="amber",
            area=area or "unknown",
            currency=Currency.AUD,
            hourly_prices=hourly_prices,
            api_timezone="Australia/Sydney"
        ).to_dict()
        
        return result
    
    def parse_hourly_prices(self, data: Any, area: str) -> Dict[str, Any]:
        hourly_prices = {}
        if isinstance(data, list):
            for entry in data:
                try:
                    timestamp_str = entry.get('date')
                    if not timestamp_str:
                        continue
                    dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    price = entry.get('perKwh')
                    if price is None:
                        continue
                    if isinstance(price, str):
                        try:
                            price = float(price)
                        except ValueError:
                            continue
                    hourly_prices[dt.isoformat()] = price
                except Exception:
                    continue
        return hourly_prices