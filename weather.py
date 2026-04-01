import requests

def get_weather(city: str = "Chennai") -> str:
    """Fetch current weather from wttr.in — no API key needed."""
    try:
        city_enc = city.strip().replace(" ", "+")
        url = f"https://wttr.in/{city_enc}?format=4"
        resp = requests.get(url, headers={"User-Agent": "Maxy-Bot/1.0"}, timeout=6)
        resp.raise_for_status()
        return resp.text.strip()
    except Exception as e:
        return f"Could not fetch weather for {city}: {e}"
