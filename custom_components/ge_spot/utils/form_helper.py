"""Form helper utilities for GE-Spot integration."""

from homeassistant.helpers import selector


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
