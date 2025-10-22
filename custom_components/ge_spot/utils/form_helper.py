"""Form helper utilities for GE-Spot integration."""

import logging
from typing import Dict, List

from homeassistant.helpers import selector

from ..const.display import DisplayUnit

_LOGGER = logging.getLogger(__name__)


class FormHelper:
    """Helper class for creating consistent form selectors."""

    @staticmethod
    def create_api_key_selector(required: bool = False) -> selector.TextSelector:
        """Create a properly structured API key selector.

        Args:
            required: Whether the field is required

        Returns:
            A TextSelector for API keys
        """
        return selector.TextSelector(
            selector.TextSelectorConfig(
                type=selector.TextSelectorType.TEXT, autocomplete="off"
            )
        )

    @staticmethod
    def create_source_priority_selector(sources: List[str]) -> selector.SelectSelector:
        """Create a source priority selector.

        Args:
            sources: List of available source values

        Returns:
            A SelectSelector for priority ordering
        """
        return selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    {"value": source, "label": source.replace("_", " ").title()}
                    for source in sources
                ],
                mode=selector.SelectSelectorMode.LIST,
                multiple=True,
            )
        )

    @staticmethod
    def create_display_unit_selector() -> selector.SelectSelector:
        """Create display unit selector.

        Returns:
            A SelectSelector for display unit
        """
        return selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    {"value": key, "label": value}
                    for key, value in DisplayUnit.OPTIONS.items()
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )

    @staticmethod
    def create_area_selector(areas: Dict[str, str]) -> selector.SelectSelector:
        """Create area selector.

        Args:
            areas: Dictionary mapping area codes to display names

        Returns:
            A SelectSelector for areas
        """
        return selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    {"value": area, "label": name}
                    for area, name in sorted(areas.items(), key=lambda x: x[1])
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )

    @staticmethod
    def create_info_text(text: str) -> selector.TextSelector:
        """Create an informational text field.

        Args:
            text: The informational text to display

        Returns:
            A TextSelector configured as read-only info text
        """
        return selector.TextSelector(
            selector.TextSelectorConfig(
                type=selector.TextSelectorType.TEXT,
                multiline=True,
            )
        )
