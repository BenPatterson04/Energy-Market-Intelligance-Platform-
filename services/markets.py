import yfinance as yf


def get_market_data(symbol, decimals=2):
    """
    Fetch live market data from Yahoo Finance.
    Returns:
        {
            "price": float,
            "change": float,
            "change_percent": float,
            "direction": "up" | "down"
        }
    """

    try:

        history = yf.Ticker(symbol).history(period="2d")

        latest = history["Close"].iloc[-1]
        previous = history["Close"].iloc[-2]

        change = latest - previous
        change_percent = (change / previous) * 100

        return {
            "price": round(latest, decimals),
            "change": round(change, decimals),
            "change_percent": round(change_percent, 2),
            "direction": "up" if change >= 0 else "down",
        }

    except Exception:

        return {
            "price": "--",
            "change": "--",
            "change_percent": "--",
            "direction": "neutral",
        }


def get_markets():

    return {

        "brent": get_market_data("BZ=F"),

        "natural_gas": get_market_data("NG=F"),

        "ftse100": get_market_data("^FTSE"),

        "sp500": get_market_data("^GSPC"),

        "gold": get_market_data("GC=F"),

        "gbpusd": get_market_data("GBPUSD=X", 4),

        # No reliable free live UK wholesale electricity feed yet.
        # We'll integrate a proper source in Version 4.
        "electricity": {
            "price": "Coming Soon",
            "change": "",
            "change_percent": "",
            "direction": "neutral",
        },

    }