"""Weather lookup: Open-Meteo, with a Gemini fallback."""

from typing import Optional, Tuple

import requests

from app.ai.gemini_client import call_gemini_json
from app.ai.retry import call_generation

_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_TIMEOUT = 10

# Open-Meteo gives a numeric WMO code with no text field, so map it here.
_WMO_CODE_TEXT = {
    0: "clear sky",
    1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "depositing rime fog",
    51: "light drizzle", 53: "moderate drizzle", 55: "dense drizzle",
    56: "light freezing drizzle", 57: "dense freezing drizzle",
    61: "slight rain", 63: "moderate rain", 65: "heavy rain",
    66: "light freezing rain", 67: "heavy freezing rain",
    71: "slight snowfall", 73: "moderate snowfall", 75: "heavy snowfall",
    77: "snow grains",
    80: "slight rain showers", 81: "moderate rain showers", 82: "violent rain showers",
    85: "slight snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with slight hail", 99: "thunderstorm with heavy hail",
}


def _wmo_description(code: Optional[int]) -> str:
    if code is None:
        return "unknown conditions"
    return _WMO_CODE_TEXT.get(int(code), f"conditions (WMO code {code})")


def _geocode(city: str) -> Optional[Tuple[float, float, str]]:
    """City name -> (lat, lon, display_name), or None on failure."""
    try:
        r = requests.get(
            _GEOCODE_URL,
            params={"name": city, "count": 1, "language": "en", "format": "json"},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        results = (r.json() or {}).get("results") or []
        if not results:
            return None
        top = results[0]
        lat, lon = top.get("latitude"), top.get("longitude")
        if lat is None or lon is None:
            return None
        name = top.get("name") or city
        country = top.get("country")
        display = f"{name}, {country}" if country else name
        return float(lat), float(lon), display
    except Exception:
        return None


def get_weather_open_meteo(city: str) -> Optional[str]:
    """Current weather via Open-Meteo, or None on failure."""
    geo = _geocode(city)
    if not geo:
        return None
    lat, lon, display = geo
    try:
        r = requests.get(
            _FORECAST_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
            },
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        current = (r.json() or {}).get("current") or {}
        temp = current.get("temperature_2m")
        if temp is None:
            return None
        desc = _wmo_description(current.get("weather_code"))
        hum = current.get("relative_humidity_2m")
        wind = current.get("wind_speed_10m")
        extra = []
        if hum is not None:
            extra.append(f"humidity {hum}%")
        if wind is not None:
            extra.append(f"wind {wind} km/h")
        tail = f" ({', '.join(extra)})" if extra else ""
        return f"The weather in {display} is {float(temp):.1f}°C with {desc}{tail}."
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
    txt = call_generation(f"Briefly describe the current weather in {city}. Keep it to one sentence.")
    return txt or f"Sorry, I couldn't determine the weather for {city}."


def get_weather(city: str) -> str:
    """Open-Meteo first, Gemini estimate as fallback."""
    return get_weather_open_meteo(city) or get_weather_gemini(city)
