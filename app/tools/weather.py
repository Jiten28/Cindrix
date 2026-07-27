"""Weather lookup tool. Ported directly from gemini_retrieval.py."""

from typing import Optional

import requests

from app.ai.gemini_client import call_gemini, call_gemini_json
from app.config import settings


def get_weather_openweather(city: str) -> Optional[str]:
    """Current weather via OpenWeather (requires OPENWEATHER_API_KEY).
    Returns a natural sentence or None on failure."""
    if not settings.OPENWEATHER_API_KEY:
        return None
    try:
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {"q": city, "appid": settings.OPENWEATHER_API_KEY, "units": "metric"}
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        js = r.json()
        if js.get("cod") != 200:
            return None
        temp = js["main"]["temp"]
        desc = js["weather"][0]["description"]
        hum = js["main"].get("humidity")
        wind = js.get("wind", {}).get("speed")
        extra = []
        if hum is not None:
            extra.append(f"humidity {hum}%")
        if wind is not None:
            extra.append(f"wind {wind} m/s")
        tail = f" ({', '.join(extra)})" if extra else ""
        return f"The weather in {city} is {temp:.1f}°C with {desc}{tail}."
    except Exception:
        return None


def get_weather_gemini(city: str) -> str:
    """Gemini fallback phrasing (not guaranteed real-time)."""
    prompt = f"""
You are a concise weather assistant. If you don't have live data, give a best-effort estimate and speak naturally.
Return ONLY a JSON object:
{{
  "temperature_C": number,
  "description": "string",
  "note": "string (e.g., 'approximate')"
}}
City: {city}
"""
    data = call_gemini_json(prompt)
    if data and "temperature_C" in data and "description" in data:
        note = f" ({data.get('note')})" if data.get("note") else ""
        return f"The weather in {city} is about {data['temperature_C']}°C with {data['description']}.{note}"
    txt = call_gemini(f"Briefly describe the current weather in {city}. Keep it to one sentence.")
    return txt or f"Sorry, I couldn't determine the weather for {city}."


def get_weather(city: str) -> str:
    """Public entry point used by the router: real data first, Gemini fallback second."""
    return get_weather_openweather(city) or get_weather_gemini(city)
