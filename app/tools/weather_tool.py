"""Simple OpenWeatherMap helper for the weather tool."""

import httpx

from app.config import settings


async def get_weather(city: str) -> dict:
    """Fetch weather data for one city.

    This is our first tool usage example. We call the weather API directly
    instead of asking LangChain because the API gives more reliable weather data.
    """
    if not settings.openweather_api_key:
        raise ValueError("OPENWEATHER_API_KEY is missing")

    params = {
        "q": city,
        "appid": settings.openweather_api_key,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params=params,
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        raise ValueError(f"Could not fetch weather for '{city}'") from exc
    except httpx.HTTPError as exc:
        raise ValueError("Weather service is unavailable right now") from exc

    temperature_kelvin = data["main"]["temp"]
    temperature_celsius = round(temperature_kelvin - 273.15, 1)

    return {
        "temperature": temperature_celsius,
        "summary": data["weather"][0]["description"].title(),
        "location": data["name"],
    }
