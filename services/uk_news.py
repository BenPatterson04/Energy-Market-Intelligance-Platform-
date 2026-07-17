import requests

from config import NEWS_API_KEY

URL = "https://newsapi.org/v2/everything"

# Different search queries per account type - this is what makes the news
# actually "relevant" per user rather than the same generic feed for
# everyone. Real NewsAPI queries, not a fallback - if NEWS_API_KEY is set,
# this genuinely returns different, tailored headlines per audience.
QUERIES = {
    "business": (
        '(EirGrid OR SONI OR SEMO OR "SEM-O" OR "i-SEM" OR Ofgem OR '
        '"wholesale electricity" OR "energy trading" OR "capacity market")'
    ),
    "student": (
        '("renewable energy" OR "energy transition" OR "net zero" OR '
        '"climate policy" OR "clean energy" OR "how the grid works")'
    ),
    "domestic": (
        '("energy bills" OR "price cap" OR "household energy" OR '
        '"switch energy supplier" OR "energy saving tips" OR heating)'
    ),
}

DEFAULT_QUERY = (
    '(National Grid OR NESO OR EirGrid OR SONI OR SEMO OR Ofgem OR '
    '"UK electricity" OR "Irish electricity" OR "power market")'
)


def get_uk_news(account_type=None):

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
