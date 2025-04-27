import pytest
import logging
import respx
from datetime import datetime, timedelta

from custom_components.ge_spot.api.nordpool import NordpoolAPI
from custom_components.ge_spot.const.sources import Source
from custom_components.ge_spot.const.currencies import Currency
from custom_components.ge_spot.utils.exchange_service import ExchangeRateService

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Sample response data that matches the Nordpool API format for different areas
SAMPLE_NORDPOOL_RESPONSES = {
    "SE3": {
        "deliveryDateCET": "2025-04-27",
        "version": 2,
        "updatedAt": "2025-04-26T10:55:58.9728151Z",
        "deliveryAreas": ["SE3"],
        "market": "DayAhead",
        "multiAreaEntries": [
            {"deliveryStart": "2025-04-26T22:00:00Z", "deliveryEnd": "2025-04-26T23:00:00Z", "entryPerArea": {"SE3": 34.61}},
            {"deliveryStart": "2025-04-26T23:00:00Z", "deliveryEnd": "2025-04-27T00:00:00Z", "entryPerArea": {"SE3": 32.82}},
            {"deliveryStart": "2025-04-27T00:00:00Z", "deliveryEnd": "2025-04-27T01:00:00Z", "entryPerArea": {"SE3": 31.15}},
            {"deliveryStart": "2025-04-27T01:00:00Z", "deliveryEnd": "2025-04-27T02:00:00Z", "entryPerArea": {"SE3": 31.36}},
            {"deliveryStart": "2025-04-27T02:00:00Z", "deliveryEnd": "2025-04-27T03:00:00Z", "entryPerArea": {"SE3": 30.98}},
            {"deliveryStart": "2025-04-27T03:00:00Z", "deliveryEnd": "2025-04-27T04:00:00Z", "entryPerArea": {"SE3": 31.91}},
            {"deliveryStart": "2025-04-27T04:00:00Z", "deliveryEnd": "2025-04-27T05:00:00Z", "entryPerArea": {"SE3": 35.22}},
            {"deliveryStart": "2025-04-27T05:00:00Z", "deliveryEnd": "2025-04-27T06:00:00Z", "entryPerArea": {"SE3": 32.70}},
            {"deliveryStart": "2025-04-27T06:00:00Z", "deliveryEnd": "2025-04-27T07:00:00Z", "entryPerArea": {"SE3": 20.65}},
            {"deliveryStart": "2025-04-27T07:00:00Z", "deliveryEnd": "2025-04-27T08:00:00Z", "entryPerArea": {"SE3": 1.41}},
            {"deliveryStart": "2025-04-27T08:00:00Z", "deliveryEnd": "2025-04-27T09:00:00Z", "entryPerArea": {"SE3": -1.12}},
            {"deliveryStart": "2025-04-27T09:00:00Z", "deliveryEnd": "2025-04-27T10:00:00Z", "entryPerArea": {"SE3": -3.86}},
            {"deliveryStart": "2025-04-27T10:00:00Z", "deliveryEnd": "2025-04-27T11:00:00Z", "entryPerArea": {"SE3": -9.40}},
            {"deliveryStart": "2025-04-27T11:00:00Z", "deliveryEnd": "2025-04-27T12:00:00Z", "entryPerArea": {"SE3": -14.63}},
            {"deliveryStart": "2025-04-27T12:00:00Z", "deliveryEnd": "2025-04-27T13:00:00Z", "entryPerArea": {"SE3": -16.60}},
            {"deliveryStart": "2025-04-27T13:00:00Z", "deliveryEnd": "2025-04-27T14:00:00Z", "entryPerArea": {"SE3": -8.14}},
            {"deliveryStart": "2025-04-27T14:00:00Z", "deliveryEnd": "2025-04-27T15:00:00Z", "entryPerArea": {"SE3": -0.15}},
            {"deliveryStart": "2025-04-27T15:00:00Z", "deliveryEnd": "2025-04-27T16:00:00Z", "entryPerArea": {"SE3": 5.46}},
            {"deliveryStart": "2025-04-27T16:00:00Z", "deliveryEnd": "2025-04-27T17:00:00Z", "entryPerArea": {"SE3": 33.82}},
            {"deliveryStart": "2025-04-27T17:00:00Z", "deliveryEnd": "2025-04-27T18:00:00Z", "entryPerArea": {"SE3": 42.45}},
            {"deliveryStart": "2025-04-27T18:00:00Z", "deliveryEnd": "2025-04-27T19:00:00Z", "entryPerArea": {"SE3": 53.20}},
            {"deliveryStart": "2025-04-27T19:00:00Z", "deliveryEnd": "2025-04-27T20:00:00Z", "entryPerArea": {"SE3": 56.33}},
            {"deliveryStart": "2025-04-27T20:00:00Z", "deliveryEnd": "2025-04-27T21:00:00Z", "entryPerArea": {"SE3": 33.63}},
            {"deliveryStart": "2025-04-27T21:00:00Z", "deliveryEnd": "2025-04-27T22:00:00Z", "entryPerArea": {"SE3": 32.43}}
        ],
        "currency": "EUR",
        "exchangeRate": 1,
        "areaStates": [{"state": "Final", "areas": ["SE3"]}],
        "areaAverages": [{"areaCode": "SE3", "price": 20.26}]
    },
    "FI": {
        "deliveryDateCET": "2025-04-27",
        "version": 2,
        "updatedAt": "2025-04-26T10:55:58.9728151Z",
        "deliveryAreas": ["FI"],
        "market": "DayAhead",
        "multiAreaEntries": [
            {"deliveryStart": "2025-04-26T22:00:00Z", "deliveryEnd": "2025-04-26T23:00:00Z", "entryPerArea": {"FI": 36.61}},
            {"deliveryStart": "2025-04-26T23:00:00Z", "deliveryEnd": "2025-04-27T00:00:00Z", "entryPerArea": {"FI": 34.82}},
            {"deliveryStart": "2025-04-27T00:00:00Z", "deliveryEnd": "2025-04-27T01:00:00Z", "entryPerArea": {"FI": 33.15}},
            {"deliveryStart": "2025-04-27T01:00:00Z", "deliveryEnd": "2025-04-27T02:00:00Z", "entryPerArea": {"FI": 33.36}},
            {"deliveryStart": "2025-04-27T02:00:00Z", "deliveryEnd": "2025-04-27T03:00:00Z", "entryPerArea": {"FI": 32.98}},
            {"deliveryStart": "2025-04-27T03:00:00Z", "deliveryEnd": "2025-04-27T04:00:00Z", "entryPerArea": {"FI": 33.91}},
            {"deliveryStart": "2025-04-27T04:00:00Z", "deliveryEnd": "2025-04-27T05:00:00Z", "entryPerArea": {"FI": 37.22}},
            {"deliveryStart": "2025-04-27T05:00:00Z", "deliveryEnd": "2025-04-27T06:00:00Z", "entryPerArea": {"FI": 34.70}},
            {"deliveryStart": "2025-04-27T06:00:00Z", "deliveryEnd": "2025-04-27T07:00:00Z", "entryPerArea": {"FI": 22.65}},
            {"deliveryStart": "2025-04-27T07:00:00Z", "deliveryEnd": "2025-04-27T08:00:00Z", "entryPerArea": {"FI": 3.41}},
            {"deliveryStart": "2025-04-27T08:00:00Z", "deliveryEnd": "2025-04-27T09:00:00Z", "entryPerArea": {"FI": 0.88}},
            {"deliveryStart": "2025-04-27T09:00:00Z", "deliveryEnd": "2025-04-27T10:00:00Z", "entryPerArea": {"FI": -1.86}},
            {"deliveryStart": "2025-04-27T10:00:00Z", "deliveryEnd": "2025-04-27T11:00:00Z", "entryPerArea": {"FI": -7.40}},
            {"deliveryStart": "2025-04-27T11:00:00Z", "deliveryEnd": "2025-04-27T12:00:00Z", "entryPerArea": {"FI": -12.63}},
            {"deliveryStart": "2025-04-27T12:00:00Z", "deliveryEnd": "2025-04-27T13:00:00Z", "entryPerArea": {"FI": -14.60}},
            {"deliveryStart": "2025-04-27T13:00:00Z", "deliveryEnd": "2025-04-27T14:00:00Z", "entryPerArea": {"FI": -6.14}},
            {"deliveryStart": "2025-04-27T14:00:00Z", "deliveryEnd": "2025-04-27T15:00:00Z", "entryPerArea": {"FI": 1.85}},
            {"deliveryStart": "2025-04-27T15:00:00Z", "deliveryEnd": "2025-04-27T16:00:00Z", "entryPerArea": {"FI": 7.46}},
            {"deliveryStart": "2025-04-27T16:00:00Z", "deliveryEnd": "2025-04-27T17:00:00Z", "entryPerArea": {"FI": 35.82}},
            {"deliveryStart": "2025-04-27T17:00:00Z", "deliveryEnd": "2025-04-27T18:00:00Z", "entryPerArea": {"FI": 44.45}},
            {"deliveryStart": "2025-04-27T18:00:00Z", "deliveryEnd": "2025-04-27T19:00:00Z", "entryPerArea": {"FI": 55.20}},
            {"deliveryStart": "2025-04-27T19:00:00Z", "deliveryEnd": "2025-04-27T20:00:00Z", "entryPerArea": {"FI": 58.33}},
            {"deliveryStart": "2025-04-27T20:00:00Z", "deliveryEnd": "2025-04-27T21:00:00Z", "entryPerArea": {"FI": 35.63}},
            {"deliveryStart": "2025-04-27T21:00:00Z", "deliveryEnd": "2025-04-27T22:00:00Z", "entryPerArea": {"FI": 34.43}}
        ],
        "currency": "EUR",
        "exchangeRate": 1,
        "areaStates": [{"state": "Final", "areas": ["FI"]}],
        "areaAverages": [{"areaCode": "FI", "price": 21.26}]
    },
    "NO1": {
        "deliveryDateCET": "2025-04-27",
        "version": 2,
        "updatedAt": "2025-04-26T10:55:58.9728151Z",
        "deliveryAreas": ["NO1"],
        "market": "DayAhead",
        "multiAreaEntries": [
            {"deliveryStart": "2025-04-26T22:00:00Z", "deliveryEnd": "2025-04-26T23:00:00Z", "entryPerArea": {"NO1": 30.61}},
            {"deliveryStart": "2025-04-26T23:00:00Z", "deliveryEnd": "2025-04-27T00:00:00Z", "entryPerArea": {"NO1": 28.82}},
            {"deliveryStart": "2025-04-27T00:00:00Z", "deliveryEnd": "2025-04-27T01:00:00Z", "entryPerArea": {"NO1": 27.15}},
            {"deliveryStart": "2025-04-27T01:00:00Z", "deliveryEnd": "2025-04-27T02:00:00Z", "entryPerArea": {"NO1": 27.36}},
            {"deliveryStart": "2025-04-27T02:00:00Z", "deliveryEnd": "2025-04-27T03:00:00Z", "entryPerArea": {"NO1": 26.98}},
            {"deliveryStart": "2025-04-27T03:00:00Z", "deliveryEnd": "2025-04-27T04:00:00Z", "entryPerArea": {"NO1": 27.91}},
            {"deliveryStart": "2025-04-27T04:00:00Z", "deliveryEnd": "2025-04-27T05:00:00Z", "entryPerArea": {"NO1": 31.22}},
            {"deliveryStart": "2025-04-27T05:00:00Z", "deliveryEnd": "2025-04-27T06:00:00Z", "entryPerArea": {"NO1": 28.70}},
            {"deliveryStart": "2025-04-27T06:00:00Z", "deliveryEnd": "2025-04-27T07:00:00Z", "entryPerArea": {"NO1": 16.65}},
            {"deliveryStart": "2025-04-27T07:00:00Z", "deliveryEnd": "2025-04-27T08:00:00Z", "entryPerArea": {"NO1": 0.41}},
            {"deliveryStart": "2025-04-27T08:00:00Z", "deliveryEnd": "2025-04-27T09:00:00Z", "entryPerArea": {"NO1": -1.12}},
            {"deliveryStart": "2025-04-27T09:00:00Z", "deliveryEnd": "2025-04-27T10:00:00Z", "entryPerArea": {"NO1": -3.86}},
            {"deliveryStart": "2025-04-27T10:00:00Z", "deliveryEnd": "2025-04-27T11:00:00Z", "entryPerArea": {"NO1": -8.40}},
            {"deliveryStart": "2025-04-27T11:00:00Z", "deliveryEnd": "2025-04-27T12:00:00Z", "entryPerArea": {"NO1": -11.63}},
            {"deliveryStart": "2025-04-27T12:00:00Z", "deliveryEnd": "2025-04-27T13:00:00Z", "entryPerArea": {"NO1": -12.60}},
            {"deliveryStart": "2025-04-27T13:00:00Z", "deliveryEnd": "2025-04-27T14:00:00Z", "entryPerArea": {"NO1": -7.14}},
            {"deliveryStart": "2025-04-27T14:00:00Z", "deliveryEnd": "2025-04-27T15:00:00Z", "entryPerArea": {"NO1": -0.15}},
            {"deliveryStart": "2025-04-27T15:00:00Z", "deliveryEnd": "2025-04-27T16:00:00Z", "entryPerArea": {"NO1": 4.46}},
            {"deliveryStart": "2025-04-27T16:00:00Z", "deliveryEnd": "2025-04-27T17:00:00Z", "entryPerArea": {"NO1": 28.82}},
            {"deliveryStart": "2025-04-27T17:00:00Z", "deliveryEnd": "2025-04-27T18:00:00Z", "entryPerArea": {"NO1": 37.45}},
            {"deliveryStart": "2025-04-27T18:00:00Z", "deliveryEnd": "2025-04-27T19:00:00Z", "entryPerArea": {"NO1": 48.20}},
            {"deliveryStart": "2025-04-27T19:00:00Z", "deliveryEnd": "2025-04-27T20:00:00Z", "entryPerArea": {"NO1": 50.33}},
            {"deliveryStart": "2025-04-27T20:00:00Z", "deliveryEnd": "2025-04-27T21:00:00Z", "entryPerArea": {"NO1": 28.63}},
            {"deliveryStart": "2025-04-27T21:00:00Z", "deliveryEnd": "2025-04-27T22:00:00Z", "entryPerArea": {"NO1": 27.43}}
        ],
        "currency": "EUR",
        "exchangeRate": 1,
        "areaStates": [{"state": "Final", "areas": ["NO1"]}],
        "areaAverages": [{"areaCode": "NO1", "price": 16.26}]
    },
    "DK1": {
        "deliveryDateCET": "2025-04-27",
        "version": 2,
        "updatedAt": "2025-04-26T10:55:58.9728151Z",
        "deliveryAreas": ["DK1"],
        "market": "DayAhead",
        "multiAreaEntries": [
            {"deliveryStart": "2025-04-26T22:00:00Z", "deliveryEnd": "2025-04-26T23:00:00Z", "entryPerArea": {"DK1": 32.61}},
            {"deliveryStart": "2025-04-26T23:00:00Z", "deliveryEnd": "2025-04-27T00:00:00Z", "entryPerArea": {"DK1": 30.82}},
            {"deliveryStart": "2025-04-27T00:00:00Z", "deliveryEnd": "2025-04-27T01:00:00Z", "entryPerArea": {"DK1": 29.15}},
            {"deliveryStart": "2025-04-27T01:00:00Z", "deliveryEnd": "2025-04-27T02:00:00Z", "entryPerArea": {"DK1": 29.36}},
            {"deliveryStart": "2025-04-27T02:00:00Z", "deliveryEnd": "2025-04-27T03:00:00Z", "entryPerArea": {"DK1": 28.98}},
            {"deliveryStart": "2025-04-27T03:00:00Z", "deliveryEnd": "2025-04-27T04:00:00Z", "entryPerArea": {"DK1": 29.91}},
            {"deliveryStart": "2025-04-27T04:00:00Z", "deliveryEnd": "2025-04-27T05:00:00Z", "entryPerArea": {"DK1": 33.22}},
            {"deliveryStart": "2025-04-27T05:00:00Z", "deliveryEnd": "2025-04-27T06:00:00Z", "entryPerArea": {"DK1": 30.70}},
            {"deliveryStart": "2025-04-27T06:00:00Z", "deliveryEnd": "2025-04-27T07:00:00Z", "entryPerArea": {"DK1": 18.65}},
            {"deliveryStart": "2025-04-27T07:00:00Z", "deliveryEnd": "2025-04-27T08:00:00Z", "entryPerArea": {"DK1": 0.41}},
            {"deliveryStart": "2025-04-27T08:00:00Z", "deliveryEnd": "2025-04-27T09:00:00Z", "entryPerArea": {"DK1": -2.12}},
            {"deliveryStart": "2025-04-27T09:00:00Z", "deliveryEnd": "2025-04-27T10:00:00Z", "entryPerArea": {"DK1": -4.86}},
            {"deliveryStart": "2025-04-27T10:00:00Z", "deliveryEnd": "2025-04-27T11:00:00Z", "entryPerArea": {"DK1": -10.40}},
            {"deliveryStart": "2025-04-27T11:00:00Z", "deliveryEnd": "2025-04-27T12:00:00Z", "entryPerArea": {"DK1": -15.63}},
            {"deliveryStart": "2025-04-27T12:00:00Z", "deliveryEnd": "2025-04-27T13:00:00Z", "entryPerArea": {"DK1": -17.60}},
            {"deliveryStart": "2025-04-27T13:00:00Z", "deliveryEnd": "2025-04-27T14:00:00Z", "entryPerArea": {"DK1": -9.14}},
            {"deliveryStart": "2025-04-27T14:00:00Z", "deliveryEnd": "2025-04-27T15:00:00Z", "entryPerArea": {"DK1": -1.15}},
            {"deliveryStart": "2025-04-27T15:00:00Z", "deliveryEnd": "2025-04-27T16:00:00Z", "entryPerArea": {"DK1": 3.46}},
            {"deliveryStart": "2025-04-27T16:00:00Z", "deliveryEnd": "2025-04-27T17:00:00Z", "entryPerArea": {"DK1": 31.82}},
            {"deliveryStart": "2025-04-27T17:00:00Z", "deliveryEnd": "2025-04-27T18:00:00Z", "entryPerArea": {"DK1": 40.45}},
            {"deliveryStart": "2025-04-27T18:00:00Z", "deliveryEnd": "2025-04-27T19:00:00Z", "entryPerArea": {"DK1": 51.20}},
            {"deliveryStart": "2025-04-27T19:00:00Z", "deliveryEnd": "2025-04-27T20:00:00Z", "entryPerArea": {"DK1": 54.33}},
            {"deliveryStart": "2025-04-27T20:00:00Z", "deliveryEnd": "2025-04-27T21:00:00Z", "entryPerArea": {"DK1": 31.63}},
            {"deliveryStart": "2025-04-27T21:00:00Z", "deliveryEnd": "2025-04-27T22:00:00Z", "entryPerArea": {"DK1": 30.43}}
        ],
        "currency": "EUR",
        "exchangeRate": 1,
        "areaStates": [{"state": "Final", "areas": ["DK1"]}],
        "areaAverages": [{"areaCode": "DK1", "price": 17.26}]
    }
}

# Sample response for tomorrow data
SAMPLE_NORDPOOL_TOMORROW_RESPONSES = {
    "SE3": {
        "deliveryDateCET": "2025-04-28",
        "version": 2,
        "updatedAt": "2025-04-27T10:55:58.9728151Z",
        "deliveryAreas": ["SE3"],
        "market": "DayAhead",
        "multiAreaEntries": [
            {"deliveryStart": "2025-04-27T22:00:00Z", "deliveryEnd": "2025-04-27T23:00:00Z", "entryPerArea": {"SE3": 30.21}},
            {"deliveryStart": "2025-04-27T23:00:00Z", "deliveryEnd": "2025-04-28T00:00:00Z", "entryPerArea": {"SE3": 29.82}},
            {"deliveryStart": "2025-04-28T00:00:00Z", "deliveryEnd": "2025-04-28T01:00:00Z", "entryPerArea": {"SE3": 28.65}},
            {"deliveryStart": "2025-04-28T01:00:00Z", "deliveryEnd": "2025-04-28T02:00:00Z", "entryPerArea": {"SE3": 27.36}},
            {"deliveryStart": "2025-04-28T02:00:00Z", "deliveryEnd": "2025-04-28T03:00:00Z", "entryPerArea": {"SE3": 26.98}},
            {"deliveryStart": "2025-04-28T03:00:00Z", "deliveryEnd": "2025-04-28T04:00:00Z", "entryPerArea": {"SE3": 27.91}},
            {"deliveryStart": "2025-04-28T04:00:00Z", "deliveryEnd": "2025-04-28T05:00:00Z", "entryPerArea": {"SE3": 30.22}},
            {"deliveryStart": "2025-04-28T05:00:00Z", "deliveryEnd": "2025-04-28T06:00:00Z", "entryPerArea": {"SE3": 31.70}},
            {"deliveryStart": "2025-04-28T06:00:00Z", "deliveryEnd": "2025-04-28T07:00:00Z", "entryPerArea": {"SE3": 35.65}},
            {"deliveryStart": "2025-04-28T07:00:00Z", "deliveryEnd": "2025-04-28T08:00:00Z", "entryPerArea": {"SE3": 40.41}},
            {"deliveryStart": "2025-04-28T08:00:00Z", "deliveryEnd": "2025-04-28T09:00:00Z", "entryPerArea": {"SE3": 41.12}},
            {"deliveryStart": "2025-04-28T09:00:00Z", "deliveryEnd": "2025-04-28T10:00:00Z", "entryPerArea": {"SE3": 40.86}},
            {"deliveryStart": "2025-04-28T10:00:00Z", "deliveryEnd": "2025-04-28T11:00:00Z", "entryPerArea": {"SE3": 39.40}},
            {"deliveryStart": "2025-04-28T11:00:00Z", "deliveryEnd": "2025-04-28T12:00:00Z", "entryPerArea": {"SE3": 38.63}},
            {"deliveryStart": "2025-04-28T12:00:00Z", "deliveryEnd": "2025-04-28T13:00:00Z", "entryPerArea": {"SE3": 36.60}},
            {"deliveryStart": "2025-04-28T13:00:00Z", "deliveryEnd": "2025-04-28T14:00:00Z", "entryPerArea": {"SE3": 35.14}},
            {"deliveryStart": "2025-04-28T14:00:00Z", "deliveryEnd": "2025-04-28T15:00:00Z", "entryPerArea": {"SE3": 34.15}},
            {"deliveryStart": "2025-04-28T15:00:00Z", "deliveryEnd": "2025-04-28T16:00:00Z", "entryPerArea": {"SE3": 35.46}},
            {"deliveryStart": "2025-04-28T16:00:00Z", "deliveryEnd": "2025-04-28T17:00:00Z", "entryPerArea": {"SE3": 43.82}},
            {"deliveryStart": "2025-04-28T17:00:00Z", "deliveryEnd": "2025-04-28T18:00:00Z", "entryPerArea": {"SE3": 48.45}},
            {"deliveryStart": "2025-04-28T18:00:00Z", "deliveryEnd": "2025-04-28T19:00:00Z", "entryPerArea": {"SE3": 50.20}},
            {"deliveryStart": "2025-04-28T19:00:00Z", "deliveryEnd": "2025-04-28T20:00:00Z", "entryPerArea": {"SE3": 47.33}},
            {"deliveryStart": "2025-04-28T20:00:00Z", "deliveryEnd": "2025-04-28T21:00:00Z", "entryPerArea": {"SE3": 43.63}},
            {"deliveryStart": "2025-04-28T21:00:00Z", "deliveryEnd": "2025-04-28T22:00:00Z", "entryPerArea": {"SE3": 40.43}}
        ],
        "currency": "EUR",
        "exchangeRate": 1,
        "areaStates": [{"state": "Final", "areas": ["SE3"]}],
        "areaAverages": [{"areaCode": "SE3", "price": 37.26}]
    }
}

# Mock exchange rate response
MOCK_EXCHANGE_RATES = {
    "rates": {
        "SEK": 11.0,
        "NOK": 10.5,
        "DKK": 7.45,
        "EUR": 1.0,
        "USD": 1.1
    },
    "base": "EUR"
}

@pytest.mark.asyncio
@pytest.mark.parametrize("area", ["FI", "SE3", "NO1", "DK1"])  # Test key Nordic market areas
async def test_nordpool_live_fetch_parse(area, monkeypatch):
    """Tests fetching and parsing Nordpool data for various Nordic areas.
    This test uses mocked responses injected directly into the API client.
    """
    logger.info(f"Testing Nordpool API for area: {area}...")
    
    # Create a modified version of fetch_raw_data that returns our mock data
    async def mock_fetch_raw_data(self, area, **kwargs):
        # Create a mock response structure
        response = {
            "today": SAMPLE_NORDPOOL_RESPONSES.get(area, SAMPLE_NORDPOOL_RESPONSES["SE3"]),
            "tomorrow": SAMPLE_NORDPOOL_TOMORROW_RESPONSES.get("SE3"),  # Use SE3 as default
            "timestamp": datetime.now().isoformat(),
            "api_timezone": "Europe/Oslo",  # Nordpool uses Central European Time
            "source": Source.NORDPOOL,
            "area": area,
            "delivery_area": area  # In real case this might be mapped
        }
        return response
    
    # Patch the method in the NordpoolAPI class
    monkeypatch.setattr(NordpoolAPI, "fetch_raw_data", mock_fetch_raw_data)
    
    # Patch the exchange rate service to avoid real external calls
    async def mock_get_rates(self, force_refresh=False):
        return MOCK_EXCHANGE_RATES
    
    async def mock_convert(self, amount, from_currency, to_currency):
        # Simple conversion using our mocked rates
        if from_currency == to_currency:
            return amount
        
        from_rate = MOCK_EXCHANGE_RATES["rates"].get(from_currency, 1.0)
        to_rate = MOCK_EXCHANGE_RATES["rates"].get(to_currency, 1.0)
        
        # Convert to base currency then to target
        return amount * (to_rate / from_rate)
    
    monkeypatch.setattr(ExchangeRateService, "get_rates", mock_get_rates)
    monkeypatch.setattr(ExchangeRateService, "convert", mock_convert)
    
    # Initialize the API client
    api = NordpoolAPI()

    try:
        # Act: Fetch Raw Data - using mocked responses
        raw_data = await api.fetch_raw_data(area=area)
        
        # Assert: Raw Data Structure (strict validation)
        assert raw_data is not None, f"Raw data for {area} should not be None"
        assert isinstance(raw_data, dict), f"Raw data should be a dictionary, got {type(raw_data)}"
        
        # Validate Nordpool-specific structure
        assert "today" in raw_data, "Required field 'today' missing from raw data"
        assert isinstance(raw_data.get("today"), dict), f"today should be a dictionary, got {type(raw_data.get('today'))}"
        
        # Validate source and area information
        assert raw_data.get("source") == Source.NORDPOOL, f"Source should be {Source.NORDPOOL}, got {raw_data.get('source')}"
        assert raw_data.get("area") == area, f"Area should be {area}, got {raw_data.get('area')}"
        
        # Timezone validation - Nordpool uses Oslo time
        assert raw_data.get("api_timezone") == "Europe/Oslo", f"Timezone should be Europe/Oslo, got {raw_data.get('api_timezone')}"
        
        # Validate today data structure
        today_data = raw_data.get("today", {})
        assert "multiAreaEntries" in today_data, "multiAreaEntries missing from today data"
        assert isinstance(today_data.get("multiAreaEntries"), list), f"multiAreaEntries should be a list, got {type(today_data.get('multiAreaEntries'))}"
        
        # Real-world validation: Nordpool should return price entries
        multi_area_entries = today_data.get("multiAreaEntries", [])
        assert len(multi_area_entries) > 0, f"No multiAreaEntries found for {area} - this indicates a real issue with the API"
        
        # Validate first entry structure
        if multi_area_entries:
            first_entry = multi_area_entries[0]
            assert isinstance(first_entry, dict), f"Entry should be a dictionary, got {type(first_entry)}"
            assert "deliveryStart" in first_entry, "Required field 'deliveryStart' missing from entry"
            assert "entryPerArea" in first_entry, "Required field 'entryPerArea' missing from entry"
            
            # Check if area is in entryPerArea (it should be if query is valid)
            entry_per_area = first_entry.get("entryPerArea", {})
            assert area in entry_per_area, f"Area {area} not found in entryPerArea"
        
        logger.info(f"Raw data contains {len(multi_area_entries)} price entries")

        # Act: Parse Raw Data
        parsed_data = await api.parse_raw_data(raw_data)
        
        # Assert: Parsed Data Structure (strict validation)
        assert parsed_data is not None, f"Parsed data for {area} should not be None"
        assert isinstance(parsed_data, dict), f"Parsed data should be a dictionary, got {type(parsed_data)}"
        
        # Required fields validation
        assert parsed_data.get("source") == Source.NORDPOOL, f"Source should be {Source.NORDPOOL}, got {parsed_data.get('source')}"
        assert parsed_data.get("area") == area, f"Area should be {area}, got {parsed_data.get('area')}"
        
        # Currency validation - Nordpool typically uses EUR for Nordic markets
        assert parsed_data.get("currency") == Currency.EUR, f"Currency should be {Currency.EUR}, got {parsed_data.get('currency')}"
        
        # Timezone validation
        assert parsed_data.get("api_timezone") == "Europe/Oslo", f"Timezone should be Europe/Oslo, got {parsed_data.get('api_timezone')}"
        
        # Hourly prices validation
        assert "hourly_prices" in parsed_data, "hourly_prices missing from parsed data"
        hourly_prices = parsed_data.get("hourly_prices", {})
        assert isinstance(hourly_prices, dict), f"hourly_prices should be a dictionary, got {type(hourly_prices)}"
        
        # Validate price data - should have 24 hours (or 23/25 during DST changes)
        valid_hour_counts = [23, 24, 25, 46, 47, 48]  # Account for DST changes and today+tomorrow
        assert len(hourly_prices) in valid_hour_counts, f"Expected hourly prices to be in {valid_hour_counts}, got {len(hourly_prices)}"
        
        # Validate timestamp format and price values
        for timestamp, price in hourly_prices.items():
            # Validate timestamp format
            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                
                # Check timestamp is within reasonable range (not too old/future)
                now = datetime.now().astimezone()
                yesterday = now - timedelta(days=2)  # More flexible
                tomorrow = now + timedelta(days=5)  # More flexible
                assert yesterday <= dt <= tomorrow, f"Timestamp {timestamp} is outside reasonable range for {area}"
            except ValueError:
                pytest.fail(f"Invalid timestamp format: '{timestamp}' for {area}")
            
            # Price validation
            assert isinstance(price, float), f"Price should be a float, got {type(price)} for timestamp {timestamp}"
            
            # Real-world price range validation for Nordic electricity market
            # Nordic prices typically range from negative values to several hundred EUR/MWh
            assert -500 <= price <= 3000, f"Price {price} EUR/MWh for {timestamp} is outside reasonable range for {area}"
        
        # Check for sequential hourly timestamps
        timestamps = sorted(hourly_prices.keys())
        hour_diffs = []
        for i in range(1, min(25, len(timestamps))):  # Check first 24 hours
            prev_dt = datetime.fromisoformat(timestamps[i-1].replace("Z", "+00:00"))
            curr_dt = datetime.fromisoformat(timestamps[i].replace("Z", "+00:00"))
            hour_diff = (curr_dt - prev_dt).total_seconds() / 3600
            hour_diffs.append(hour_diff)
            
            # Nordic market data should be hourly, except during DST changes
            valid_hour_diff = abs(hour_diff - 1.0) < 0.1 or abs(hour_diff - 2.0) < 0.1 or abs(hour_diff - 0.0) < 0.1
            assert valid_hour_diff, f"Unexpected time gap between {timestamps[i-1]} and {timestamps[i]} for {area}: {hour_diff} hours"
        
        logger.info(f"Nordpool Test ({area}): PASS - Found {len(hourly_prices)} prices. "
                  f"Range: {min(hourly_prices.values()):.2f} to {max(hourly_prices.values()):.2f} {parsed_data.get('currency')}/MWh")

    except AssertionError as ae:
        # Let assertion errors propagate - these are test failures that should be fixed in the code, not the test
        logger.error(f"Nordpool Test ({area}): ASSERTION FAILED - {str(ae)}")
        raise
    except Exception as e:
        # Don't catch exceptions - let the test fail to expose real issues
        logger.error(f"Nordpool Test ({area}): EXCEPTION - {str(e)}")
        raise