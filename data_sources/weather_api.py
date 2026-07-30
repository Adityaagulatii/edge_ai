import requests

_MOCK_WEATHER = {
    "temp_f": 72.0,
    "humidity_pct": 65,
    "precip_mm": 0.0,
    "wind_mph": 8.0,
    "timestamp": "mock",
}


def get_weather(lat, lon):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
    }
    try:
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        c = resp.json()["current"]
        return {
            "temp_f":       c["temperature_2m"],
            "humidity_pct": c["relative_humidity_2m"],
            "precip_mm":    c["precipitation"],
            "wind_mph":     c["wind_speed_10m"],
            "timestamp":    c["time"],
        }
    except Exception:
        return _MOCK_WEATHER
