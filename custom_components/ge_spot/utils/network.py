import asyncio
import logging
from typing import Any, Dict, Optional

import aiohttp

from custom_components.ge_spot.const.network import NETWORK_TIMEOUT

_LOGGER = logging.getLogger(__name__)

async def async_get_json_or_raise(
    session: aiohttp.ClientSession,
    url: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = NETWORK_TIMEOUT,
    headers: Optional[Dict[str, str]] = None,
) -> Any:
    """
    Perform an asynchronous GET request, return JSON response, or raise HTTP error.

    Args:
        session: The aiohttp client session.
        url: The URL to fetch.
        params: Optional dictionary of query parameters.
        timeout: Request timeout in seconds.
        headers: Optional dictionary of request headers.

    Returns:
        The JSON response from the server.

    Raises:
        aiohttp.ClientResponseError: If the HTTP request returns a 4xx or 5xx status.
        asyncio.TimeoutError: If the request times out.
        aiohttp.ClientError: For other client-side errors.
    """
    try:
        async with session.get(url, params=params, timeout=timeout, headers=headers) as response:
            response.raise_for_status()  # Raises ClientResponseError for 4xx/5xx
            return await response.json()
    except asyncio.TimeoutError:
        _LOGGER.error("Timeout error requesting data from %s", url)
        raise
    except aiohttp.ClientResponseError as e:
        _LOGGER.error("HTTP error %s requesting data from %s: %s", e.status, url, e.message)
        raise
    except aiohttp.ClientError as e:
        _LOGGER.error("Client error requesting data from %s: %s", url, e)
        raise
    except Exception as e: # Catch any other unexpected errors during request or JSON decoding
        _LOGGER.error("Unexpected error requesting data from %s: %s", url, e)
        raise

async def async_post_graphql_or_raise(
    session: aiohttp.ClientSession,
    url: str,
    payload: Dict[str, Any], # GraphQL query typically in a 'query' field
    auth_header: str, # Authorization header, e.g., Bearer token
    timeout: int = NETWORK_TIMEOUT,
) -> Any:
    """
    Perform an asynchronous POST request for GraphQL, return JSON response, or raise HTTP error.

    Args:
        session: The aiohttp client session.
        url: The GraphQL endpoint URL.
        payload: The GraphQL query payload (dictionary).
        auth_header: The Authorization header string.
        timeout: Request timeout in seconds.

    Returns:
        The JSON response from the server.

    Raises:
        aiohttp.ClientResponseError: If the HTTP request returns a 4xx or 5xx status.
        asyncio.TimeoutError: If the request times out.
        aiohttp.ClientError: For other client-side errors.
    """
    headers = {
        "Authorization": auth_header,
        "Content-Type": "application/json",
    }
    try:
        async with session.post(url, json=payload, headers=headers, timeout=timeout) as response:
            response.raise_for_status() # Raises ClientResponseError for 4xx/5xx
            json_response = await response.json()
            if "errors" in json_response and json_response["errors"]:
                _LOGGER.error(
                    "GraphQL API at %s returned errors: %s", url, json_response["errors"]
                )
                # Depending on desired behavior, you might raise a custom error here
                # For now, returning the response as some data might still be present
            return json_response
    except asyncio.TimeoutError:
        _LOGGER.error("Timeout error posting to GraphQL API at %s", url)
        raise
    except aiohttp.ClientResponseError as e:
        _LOGGER.error(
            "HTTP error %s posting to GraphQL API at %s: %s", e.status, url, e.message
        )
        raise
    except aiohttp.ClientError as e:
        _LOGGER.error("Client error posting to GraphQL API at %s: %s", url, e)
        raise
    except Exception as e: # Catch any other unexpected errors
        _LOGGER.error("Unexpected error posting to GraphQL API at %s: %s", url, e)
        raise