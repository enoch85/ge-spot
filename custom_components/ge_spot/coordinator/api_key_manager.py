"""API key manager for electricity spot prices."""

import logging
from typing import Any, Dict, Optional, List

from homeassistant.core import HomeAssistant

from ..const.config import Config
from ..const.sources import Source

_LOGGER = logging.getLogger(__name__)


class ApiKeyManager:
    """Manager for API key validation and status tracking."""

    def __init__(self, hass: HomeAssistant, config: Dict[str, Any], session: Optional[Any] = None):
        """Initialize the API key manager.

        Args:
            hass: Home Assistant instance
            config: Configuration dictionary
            session: Optional session for API requests
        """
        self.hass = hass
        self.config = config
        self.session = session
        self._api_key_status = {}

    async def check_api_key_status(self) -> Dict[str, Any]:
        """Check status of configured API keys and report in attributes.

        Returns:
            Dictionary with API key status
        """
        api_key_status = {}

        # Check for ENTSOE API key
        if Source.ENTSOE in self.config.get(Config.SOURCE_PRIORITY, []):
            api_key = self.config.get(Config.API_KEY)
            if api_key:
                try:
                    from ..api import entsoe

                    area = self.config.get("area")
                    is_valid = await entsoe.validate_api_key(api_key, area, self.session)
                    api_key_status[Source.ENTSOE] = {
                        "configured": True,
                        "valid": is_valid,
                        "status": "valid" if is_valid else "invalid",
                        "region": area,
                    }
                    _LOGGER.debug(
                        f"ENTSO-E API key status for region {area}: {'valid' if is_valid else 'invalid'}"
                    )

                    # If key is invalid, adjust source priority to avoid using ENTSOE
                    if not is_valid and self.config.get(Config.SOURCE_PRIORITY):
                        # Create a new list without ENTSOE
                        original_priority = self.config.get(Config.SOURCE_PRIORITY, [])
                        adjusted_priority = [s for s in original_priority if s != Source.ENTSOE]
                        # Add ENTSOE at the end for completeness
                        adjusted_priority.append(Source.ENTSOE)
                        self.config[Config.SOURCE_PRIORITY] = adjusted_priority
                        _LOGGER.warning(
                            f"Detected invalid ENTSOE API key, adjusted source priority: {adjusted_priority}"
                        )
                except Exception as e:
                    area = self.config.get("area")
                    _LOGGER.error(f"Error validating ENTSO-E API key for region {area}: {e}")
                    api_key_status[Source.ENTSOE] = {
                        "configured": True,
                        "valid": False,
                        "status": "error",
                        "region": area,
                    }
            else:
                area = self.config.get("area")
                api_key_status[Source.ENTSOE] = {
                    "configured": False,
                    "valid": None,
                    "status": "not_configured",
                    "region": area,
                }
                _LOGGER.debug(f"ENTSO-E API key not configured for region {area}")

        self._api_key_status = api_key_status
        return api_key_status

    def get_status(self) -> Dict[str, Any]:
        """Get current API key status.

        Returns:
            Dictionary with API key status
        """
        return self._api_key_status
