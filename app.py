from dotenv import load_dotenv

load_dotenv()
from flask import Flask, render_template

from services.weather import get_weather
from services.markets import get_markets
from services.domestic import get_domestic_prices
from services.uk_news import get_uk_news
from services.global_news import get_global_news
from services.grid import get_grid_status

app = Flask(__name__)


@app.route("/")
def home():

    weather = get_weather()

    markets = get_markets()

    domestic = get_domestic_prices()

    uk_news = get_uk_news()

    global_news = get_global_news()

    grid = get_grid_status()

    return render_template(
        "dashboard.html",
        weather=weather,
        markets=markets,
        domestic=domestic,
        grid=grid,
        news={
            "uk": uk_news,
            "global": global_news,
        },
    )


if __name__ == "__main__":
    app.run(debug=True)
    