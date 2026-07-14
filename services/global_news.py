import requests

from config import NEWS_API_KEY

URL = "https://newsapi.org/v2/everything"


def get_global_news():

    params = {
        "q": '(Brent OR crude oil OR LNG OR natural gas OR OPEC OR electricity market OR renewable energy OR IEA)',
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