from flask import Flask, render_template
import requests
import yfinance as yf
from datetime import datetime

app = Flask(__name__)

# -----------------------------
# API KEY
# -----------------------------
API_KEY = "33e78ee7ef8c1cc110237f9095609230"


@app.route("/")
def home():

    # -----------------------------
    # WEATHER
    # -----------------------------
    city = "Belfast"

    weather_url = (
        f"https://api.openweathermap.org/data/2.5/weather"
        f"?q={city}&appid={API_KEY}&units=metric"
    )

    try:
        weather = requests.get(weather_url, timeout=10).json()

        location = weather["name"]
        temperature = round(weather["main"]["temp"], 1)
        wind_speed = round(weather["wind"]["speed"] * 3.6, 1)
        condition = weather["weather"][0]["description"].title()

    except Exception:
        location = "Unavailable"
        temperature = "--"
        wind_speed = "--"
        condition = "--"

    # -----------------------------
    # LIVE MARKETS
    # -----------------------------
    try:
        brent = round(
            yf.Ticker("BZ=F").history(period="1d")["Close"].iloc[-1], 2
        )
    except Exception:
        brent = "--"

    try:
        gas = round(
            yf.Ticker("NG=F").history(period="1d")["Close"].iloc[-1], 2
        )
    except Exception:
        gas = "--"

    electricity = 96.35

    # -----------------------------
    # RETAIL PRICES
    # -----------------------------
    electricity_tariff = "27.5p/kWh"
    gas_tariff = "6.8p/kWh"
    heating_oil = "54.3p/L"
    standing_charge = "61p/day"

    updated = datetime.now().strftime("%d %B %Y %H:%M")

    return render_template(
        "index.html",

        brent=brent,
        gas=gas,
        electricity=electricity,

        electricity_tariff=electricity_tariff,
        gas_tariff=gas_tariff,
        heating_oil=heating_oil,
        standing_charge=standing_charge,

        location=location,
        temperature=temperature,
        wind_speed=wind_speed,
        condition=condition,

        updated=updated,
    )


if __name__ == "__main__":
    app.run(debug=True)
