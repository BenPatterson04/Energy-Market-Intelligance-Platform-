import os

# -----------------------------
# API KEYS
# -----------------------------
NEWS_API_KEY = os.getenv(
    "NEWS_API_KEY",
    "881eab18137148a7a30288a4687e1fe0"
)
OPENWEATHER_API_KEY = os.getenv(
    "OPENWEATHER_API_KEY",
    "33e78ee7ef8c1cc110237f9095609230"
)

# -----------------------------
# DEFAULT SETTINGS
# -----------------------------

DEFAULT_CITY = "Belfast"