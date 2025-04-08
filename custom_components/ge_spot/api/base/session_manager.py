"""Session management for API connections."""
import logging
import aiohttp
import asyncio
import weakref
from typing import Any, Optional, Dict

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

async def ensure_session(api_obj):
    """Ensure that an API object has an aiohttp session."""
    try:
        if api_obj.session is None or api_obj.session.closed:
            _LOGGER.debug(f"Creating new aiohttp session for {api_obj.__class__.__name__}")
            api_obj.session = aiohttp.ClientSession()
            api_obj._owns_session = True
            # Register the session for potential cleanup
            _SESSION_REGISTRY.add(api_obj.session)
    except Exception as e:
        _LOGGER.error(f"Error creating session in {api_obj.__class__.__name__}: {str(e)}")

async def close_session(api_obj):
    """Close an API object's session if it owns it."""
    if api_obj.session and api_obj._owns_session and not api_obj.session.closed:
        try:
            await api_obj.session.close()
            _LOGGER.debug(f"Closed session for {api_obj.__class__.__name__}")
        except Exception as e:
            _LOGGER.error(f"Error closing session: {str(e)}")
        finally:
            api_obj.session = None
            api_obj._owns_session = False

async def fetch_with_retry(api_obj, url, params=None, headers=None, timeout=30, max_retries=3):
    """Fetch data from URL with retry mechanism."""
    await ensure_session(api_obj)

    if not api_obj.session or api_obj.session.closed:
        _LOGGER.error("No session available for API request")
        return None

    # Default headers if none provided
    if headers is None:
        headers = {
            "User-Agent": "HomeAssistantGESpot/1.0",
            "Accept": "application/json, text/plain, */*"
        }

    for attempt in range(max_retries):
        try:
            _LOGGER.debug(f"API request attempt {attempt+1}/{max_retries}: {url}")

            async with api_obj.session.get(url, params=params, headers=headers, timeout=timeout) as response:
                if response.status != 200:
                    _LOGGER.error(f"Error fetching from URL (attempt {attempt+1}/{max_retries}): HTTP {response.status}")

                    # Log response body for debugging if not successful
                    if response.status != 404:  # Don't log 404 body as it's usually large error pages
                        try:
                            error_text = await response.text()
                            _LOGGER.debug(f"Error response (first 500 chars): {error_text[:500]}")
                        except:
                            _LOGGER.debug("Could not read error response body")

                    if attempt < max_retries - 1:
                        retry_delay = 2 ** attempt  # Exponential backoff
                        _LOGGER.debug(f"Retrying in {retry_delay} seconds...")
                        await asyncio.sleep(retry_delay)
                        continue
                    return None

                # Check content type to handle response appropriately
                content_type = response.headers.get('Content-Type', '')
                _LOGGER.debug(f"Response content type: {content_type}")

                response_text = await response.text()

                # Only log a snippet to avoid overwhelming logs
                if len(response_text) > 1000:
                    _LOGGER.debug(f"Raw API response (first 1000 chars): {response_text[:1000]}...")
                else:
                    _LOGGER.debug(f"Raw API response: {response_text}")

                if 'application/json' in content_type:
                    try:
                        json_data = await response.json()
                        _LOGGER.debug(f"Parsed JSON data successfully")
                        return json_data
                    except Exception as e:
                        _LOGGER.error(f"Failed to parse response as JSON: {e}")
                        return response_text
                else:
                    _LOGGER.debug(f"Returning non-JSON response")
                    return response_text

        except asyncio.TimeoutError:
            _LOGGER.error(f"Timeout fetching from URL (attempt {attempt+1}/{max_retries})")
            if attempt < max_retries - 1:
                retry_delay = 2 ** attempt  # Exponential backoff
                await asyncio.sleep(retry_delay)
                continue
            raise
        except aiohttp.ClientConnectorError as e:
            _LOGGER.error(f"Connection error fetching from URL (attempt {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                retry_delay = 2 ** attempt  # Exponential backoff
                await asyncio.sleep(retry_delay)
                continue
            raise
        except Exception as e:
            _LOGGER.error(f"Error in fetch_with_retry: {str(e)}")
            if attempt < max_retries - 1:
                retry_delay = 2 ** attempt  # Exponential backoff
                await asyncio.sleep(retry_delay)
                continue
            raise

    return None

def register_shutdown_task(hass):
    """Register session cleanup as a shutdown task."""
    if hass:
        async def _async_shutdown(_):
            await close_all_sessions()

        hass.bus.async_listen_once("homeassistant_stop", _async_shutdown)
