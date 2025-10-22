import aiohttp
import asyncio
from datetime import datetime


async def fetch_nordpool():
    url = "https://dataportal-api.nordpoolgroup.com/api/DayAheadPrices"
    params = {
        "currency": "EUR",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "market": "DayAhead",
        "deliveryArea": "SE4",
    }
    headers = {"User-Agent": "GE-Spot/1.0", "Accept": "application/json"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, headers=headers) as resp:
            print("Status:", resp.status)
            print("Headers:", resp.headers)
            try:
                data = await resp.json()
                print("Data:", data)
            except Exception as e:
                print("Failed to parse JSON:", e)
                print("Raw text:", await resp.text())


if __name__ == "__main__":
    asyncio.run(fetch_nordpool())
