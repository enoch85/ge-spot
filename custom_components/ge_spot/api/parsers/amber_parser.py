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
            
        hourly_prices = {}
        
        # Parse each entry and organize by hour
        for entry in data:
            try:
                # Get the timestamp
                timestamp_str = entry.get('date')
                if not timestamp_str:
                    continue
                    
                # Parse timestamp (format: ISO format)
                dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                
                # Get the price value
                price = entry.get('perKwh')
                if price is None:
                    continue
                    
                # Convert to float if needed
                if isinstance(price, str):
                    try:
                        price = float(price)
                    except ValueError:
                        continue
                
                # Add to hourly prices - we use ISO format to preserve date information
                hourly_prices[dt.isoformat()] = price
                
            except Exception as e:
                _LOGGER.error(f"Error parsing Amber price entry: {e}")
                continue
        
        # Create standardized data structure
        result = StandardizedPriceData.create(
            source="amber",
            area=area or "unknown",
            currency=Currency.AUD,
            hourly_prices=hourly_prices,
            api_timezone="Australia/Sydney"
        ).to_dict()
        
        return result