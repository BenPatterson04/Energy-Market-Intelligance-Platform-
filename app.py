from flask import Flask, render_template
import requests
import plotly.graph_objects as go
import plotly
import json
from datetime import datetime

app = Flask(__name__)

API_KEY = "33e78ee7ef8c1cc110237f9095609230"


@app.route("/")
def home():

    city = "Belfast"

    weather_url = (
        f"https://api.openweathermap.org/data/2.5/weather"
        f"?q={city}&appid={API_KEY}&units=metric"
    )

    response = requests.get(weather_url)
    weather = response.json()

    if "main" in weather:

        temperature = round(weather["main"]["temp"], 1)
        wind_speed = round(weather["wind"]["speed"] * 3.6, 1)   # km/h
        condition = weather["weather"][0]["description"].title()
        icon = weather["weather"][0]["icon"]

    else:

        temperature = "N/A"
        wind_speed = "N/A"
        condition = "Unavailable"
        icon = "01d"

    # Temporary market values
    brent = 71.42
    gas = 84.60
    electricity = 96.35

    updated = datetime.now().strftime("%d %b %Y %H:%M")

    # Brent chart
    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=[
                "Mon",
                "Tue",
                "Wed",
                "Thu",
                "Fri",
                "Sat",
                "Sun"
            ],
            y=[
                68.4,
                69.2,
                70.1,
                69.8,
                70.7,
                71.1,
                brent
            ],
            mode="lines+markers",
            line=dict(width=4)
        )
    )

    fig.update_layout(
        template="plotly_dark",
        title="Brent Crude Price Trend",
        height=420,
        margin=dict(l=30, r=30, t=50, b=30)
    )

    graphJSON = json.dumps(
        fig,
        cls=plotly.utils.PlotlyJSONEncoder
    )

    return render_template(
        "index.html",
        city=city,
        temperature=temperature,
        wind_speed=wind_speed,
        condition=condition,
        icon=icon,
        brent=brent,
        gas=gas,
        electricity=electricity,
        updated=updated,
        graphJSON=graphJSON
    )


if __name__ == "__main__":
    app.run(debug=True)