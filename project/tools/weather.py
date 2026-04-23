import os

import requests


WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"


def get_weather(city: str, unit: str = "celsius") -> dict:
    api_key = os.getenv("WEATHER_API_KEY")
    units = "imperial" if unit == "fahrenheit" else "metric"

    params = {
        "q": city,
        "appid": api_key,
        "units": units,
    }

    try:
        response = requests.get(WEATHER_URL, params=params, timeout=5)

        if response.status_code == 404:
            return {"error": "City not found"}

        response.raise_for_status()
        data = response.json()

        return {
            "city": data["name"],
            "temperature": data["main"]["temp"],
            "feels_like": data["main"]["feels_like"],
            "condition": data["weather"][0]["description"],
            "humidity": data["main"]["humidity"],
            "unit": unit,
        }
    except requests.exceptions.Timeout:
        return {"error": "Weather service timed out"}
    except Exception:
        return {"error": "Weather service unavailable"}
