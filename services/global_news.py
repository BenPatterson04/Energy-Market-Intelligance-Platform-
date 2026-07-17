import requests

from config import NEWS_API_KEY

URL = "https://newsapi.org/v2/everything"

# Same approach as uk_news.py - different query per account type so the
# global feed is actually relevant to each audience, not identical for all.
QUERIES = {
    "business": (
        '(Brent OR "crude oil" OR LNG OR OPEC OR "energy markets" OR '
        '"day-ahead price" OR IEA OR "gas storage")'
    ),
    "student": (
        '("energy transition" OR "renewable energy" OR "solar power" OR '
        '"wind power" OR "climate change" OR "carbon emissions" explainer)'
    ),
    "domestic": (
        '("energy prices" OR "household bills" OR "cost of living" energy OR '
        '"heating costs" OR "energy efficiency" home)'
    ),
}

DEFAULT_QUERY = (
    '(Brent OR crude oil OR LNG OR natural gas OR OPEC OR electricity '
    'market OR renewable energy OR IEA)'
)


def get_global_news(account_type=None):

    params = {
        "q": QUERIES.get(account_type, DEFAULT_QUERY),
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 6,
        "apiKey": NEWS_API_KEY
    }

    try:

        response = requests.get(URL, params=params, timeout=10)
        response.raise_for_status()

        data = response.json()

        articles = []

        for article in data.get("articles", []):

            articles.append({
                "title": article["title"],
                "source": article["source"]["name"]
            })

        return articles

    except Exception as e:

        print(e)

        return []
