import yfinance as yf
import plotly.graph_objects as go


MARKETS = {
    "brent": ("BZ=F", "Brent Crude"),
    "gas": ("NG=F", "Natural Gas"),
    "gold": ("GC=F", "Gold"),
    "ftse": ("^FTSE", "FTSE 100"),
    "gbpusd": ("GBPUSD=X", "GBP/USD"),
}


def get_chart(market="brent"):

    ticker_symbol, title = MARKETS.get(
        market,
        MARKETS["brent"]
    )

    ticker = yf.Ticker(ticker_symbol)

    data = ticker.history(period="6mo")

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=data.index,
            y=data["Close"],
            mode="lines",
            name=title,
            line=dict(width=3)
        )
    )

    fig.update_layout(

        template="plotly_dark",

        paper_bgcolor="#111827",
        plot_bgcolor="#111827",

        font=dict(color="white"),

        title=title,

        margin=dict(
            l=20,
            r=20,
            t=45,
            b=20
        ),

        height=430

    )

    return fig.to_html(
        full_html=False,
        include_plotlyjs="cdn"
    )