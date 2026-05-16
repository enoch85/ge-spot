"""Session management for API connections.

This module is the integration's HA shutdown hook. The coordinator passes the
shared `async_get_clientsession(hass)` session into every API client, so the
registry is currently empty in production; `close_all_sessions()` is a safety
net for any session that opts in via `_SESSION_REGISTRY.add()`.
"""

import logging
import weakref

_LOGGER = logging.getLogger(__name__)

# Global session registry to prevent leaks
_SESSION_REGISTRY = weakref.WeakSet()


async def close_all_sessions():
    """Close all registered sessions."""
    for session in list(_SESSION_REGISTRY):
        if not session.closed:
            try:
                await session.close()
            except Exception as e:
                _LOGGER.error(f"Error closing session: {e}")


def register_shutdown_task(hass):
    """Register session cleanup as a shutdown task."""
    if hass:

        async def _async_shutdown(_):
            await close_all_sessions()

        hass.bus.async_listen_once("homeassistant_stop", _async_shutdown)
