"""Regression test: the user step must not swallow Home Assistant's AbortFlow.

``async_step_user`` wrapped its body in a broad ``except Exception`` that also
caught ``AbortFlow`` — the control-flow exception raised by
``async_set_unique_id(raise_on_progress=True)`` ("already_in_progress") and
``_abort_if_unique_id_configured()`` ("already_configured"). That turned both
into a generic ``base: "unknown"`` form error, so a user re-adding a configured
region saw "unknown error" instead of the correct abort message.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.data_entry_flow import AbortFlow

from custom_components.ge_spot.config_flow.implementation import GSpotConfigFlow
from custom_components.ge_spot.const.config import Config


async def test_async_step_user_propagates_already_in_progress():
    """AbortFlow from async_set_unique_id must propagate, not become 'unknown'."""
    flow = GSpotConfigFlow()
    with patch.object(
        flow,
        "async_set_unique_id",
        AsyncMock(side_effect=AbortFlow("already_in_progress")),
    ):
        with pytest.raises(AbortFlow) as exc:
            await flow.async_step_user({Config.AREA: "SE4"})
    assert exc.value.reason == "already_in_progress"


async def test_async_step_user_propagates_already_configured():
    """AbortFlow from _abort_if_unique_id_configured must propagate."""
    flow = GSpotConfigFlow()
    with patch.object(flow, "async_set_unique_id", AsyncMock()), patch.object(
        flow,
        "_abort_if_unique_id_configured",
        MagicMock(side_effect=AbortFlow("already_configured")),
    ):
        with pytest.raises(AbortFlow) as exc:
            await flow.async_step_user({Config.AREA: "SE4"})
    assert exc.value.reason == "already_configured"
