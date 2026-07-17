import requests

from config import OPENWEATHER_API_KEY
from config import DEFAULT_CITY


def get_weather():

    url = (
        f"https://api.openweathermap.org/data/2.5/weather"
        f"?q={DEFAULT_CITY}"
        f"&appid={OPENWEATHER_API_KEY}"
        f"&units=metric"
    )

    try:

        response = requests.get(url, timeout=10)

        response.raise_for_status()

        data = response.json()

        return {

            "location": data["name"],

            "temperature": round(data["main"]["temp"], 1),

            "feels_like": round(data["main"]["feels_like"], 1),

            "humidity": data["main"]["humidity"],

            "pressure": data["main"]["pressure"],

            "wind_speed": round(data["wind"]["speed"] * 3.6, 1),

            "condition": data["weather"][0]["description"].title(),

            "icon": data["weather"][0]["icon"]

        }

    except Exception as e:

        print(f"Weather API Error: {e}")

        return {

            "location": "Unavailable",

            "temperature": "--",

            "feels_like": "--",

            "humidity": "--",

            "pressure": "--",

            "wind_speed": "--",

            "condition": "--",

            "icon": "01d"

        }