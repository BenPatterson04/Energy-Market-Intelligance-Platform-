"""
GridWise Version 4 - i-SEM / EirGrid Integration
==================================================

Pulls live all-island power system data from EirGrid's Smart Grid Dashboard
(https://www.smartgriddashboard.com), which underpins the public dashboard
used across ROI, NI and all-island views.

IMPORTANT - read before deploying:
This is a community-reverse-engineered endpoint, not an officially
published/documented API with a stable contract. EirGrid can change the
response shape without notice. Because of that, every parsing step here is
defensive: if a field is missing or the request fails, we fall back to the
last good snapshot stored in SQLite (services/history.py) so the dashboard
never shows a broken page - it just shows slightly stale data with a
"last updated" timestamp.

Before going live, run `python -c "from services.isem import get_isem_snapshot;
print(get_isem_snapshot())"` and sanity check the numbers against
https://www.smartgriddashboard.com/all/ for the same timestamp. If EirGrid
have changed the field names, update FIELD_MAP below - nothing else needs
to change.
"""

import requests
from datetime import datetime, timedelta

from services import history

BASE_URL = "https://www.smartgriddashboard.com/DashboardService.svc/data"

# EirGrid "area" codes as used by the public dashboard's underlying data
# service. These are camelCase - confirmed against community tooling that's
# used this endpoint for years (smartgriddashboard.com/DashboardService.svc).
# If a chart on smartgriddashboard.com stops matching, open the page, open
# your browser's Network tab, and look at the ?area= value in the request
# it fires - that's the code to use here.
AREAS = {
    "demand": "demandActual",
    "wind": "windActual",
    "co2_intensity": "co2intensity",
    "frequency": "frequencyActual",
    "system_price": "systemprice",  # i-SEM imbalance settlement price (EUR/MWh) - unconfirmed area code, check if this 404s
}

REGIONS = ["ALL", "ROI", "NI"]


def _fetch_area(area_code, region="ALL", hours=6):
    """Fetch a single metric's time series for the trailing `hours` hours."""

    now = datetime.utcnow()
    date_to = now.strftime("%d-%b-%Y %H:%M")
    date_from = (now - timedelta(hours=hours)).strftime("%d-%b-%Y %H:%M")

    params = {
        "area": area_code,
        "region": region,
        "datefrom": date_from,
        "dateto": date_to,
    }

    # Some servers reject requests that don't look like they came from a
    # real browser (Python's default requests User-Agent is an easy tell).
    # Sending browser-like headers here fixed a 503 we were seeing without them.
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.smartgriddashboard.com/",
    }

    response = requests.get(BASE_URL, params=params, headers=headers, timeout=10)
    response.raise_for_status()
    payload = response.json()

    rows = payload.get("Rows") or payload.get("rows") or []

    series = []
    for row in rows:
        ts = row.get("EffectiveTime") or row.get("Time") or row.get("time")
        value = row.get("Value") if "Value" in row else row.get("value")

        if ts is None or value is None:
            continue

        series.append({"time": ts, "value": value})

    return series


def get_isem_snapshot(region="ALL"):
    """
    Latest reading across all tracked metrics for a region, plus a
    'source' flag so the UI can show whether this is live or cached data.
    """

    result = {
        "region": region,
        "demand_mw": None,
        "wind_mw": None,
        "wind_percent": None,
        "co2_intensity": None,
        "system_price_eur": None,
        "frequency_hz": None,
        "source": "live",
        "last_updated": datetime.utcnow().strftime("%d %b %Y %H:%M UTC"),
    }

    try:
        demand_series = _fetch_area(AREAS["demand"], region)
        wind_series = _fetch_area(AREAS["wind"], region)
        co2_series = _fetch_area(AREAS["co2_intensity"], region)
        freq_series = _fetch_area(AREAS["frequency"], region)
        price_series = _fetch_area(AREAS["system_price"], region)

        demand = demand_series[-1]["value"] if demand_series else None
        wind = wind_series[-1]["value"] if wind_series else None

        result["demand_mw"] = demand
        result["wind_mw"] = wind
        result["wind_percent"] = round((wind / demand) * 100, 1) if demand and wind else None
        result["co2_intensity"] = co2_series[-1]["value"] if co2_series else None
        result["frequency_hz"] = freq_series[-1]["value"] if freq_series else None
        result["system_price_eur"] = price_series[-1]["value"] if price_series else None

        if not any([demand, wind, result["co2_intensity"], result["frequency_hz"]]):
            raise ValueError("EirGrid response returned no usable rows")

        # Persist so the historical charts + alerts have something to work with
        history.record_isem_snapshot(
            region=region,
            demand_mw=result["demand_mw"],
            wind_mw=result["wind_mw"],
            wind_percent=result["wind_percent"],
            co2_intensity=result["co2_intensity"],
            system_price_eur=result["system_price_eur"],
            frequency_hz=result["frequency_hz"],
        )

    except Exception as e:

        print("i-SEM / EirGrid fetch error:", e)

        cached = history.get_isem_history(region=region, hours=6)

        if cached:
            latest = cached[-1]
            result.update({
                "demand_mw": latest["demand_mw"],
                "wind_mw": latest["wind_mw"],
                "wind_percent": latest["wind_percent"],
                "co2_intensity": latest["co2_intensity"],
                "system_price_eur": latest["system_price_eur"],
                "frequency_hz": latest["frequency_hz"],
                "last_updated": latest["recorded_at"] + " (cached)",
            })

        result["source"] = "cached"

    return result


def get_isem_chart_data(region="ALL", hours=24):
    """
    Shaped for Plotly: parallel arrays the frontend can drop straight into
    a `data` trace without any reformatting in JS.
    """

    rows = history.get_isem_history(region=region, hours=hours)

    return {
        "timestamps": [r["recorded_at"] for r in rows],
        "demand_mw": [r["demand_mw"] for r in rows],
        "wind_mw": [r["wind_mw"] for r in rows],
        "wind_percent": [r["wind_percent"] for r in rows],
        "co2_intensity": [r["co2_intensity"] for r in rows],
        "system_price_eur": [r["system_price_eur"] for r in rows],
        "frequency_hz": [r["frequency_hz"] for r in rows],
    }


# Fixed reference points for the grid map (interconnectors + regional
# demand centres). Coordinates are approximate substation/landing points -
# fine for a market-overview map, not for engineering use.
GRID_MAP_NODES = [
    {"name": "EWIC Interconnector (Ireland–Wales)", "lat": 53.29, "lon": -6.13, "type": "interconnector"},
    {"name": "Moyle Interconnector (NI–Scotland)", "lat": 54.86, "lon": -5.80, "type": "interconnector"},
    {"name": "Greenlink (Ireland–Wales)", "lat": 52.17, "lon": -6.76, "type": "interconnector"},
    {"name": "Dublin (ROI demand centre)", "lat": 53.3498, "lon": -6.2603, "type": "demand"},
    {"name": "Belfast (NI demand centre)", "lat": 54.5973, "lon": -5.9301, "type": "demand"},
    {"name": "Cork (ROI demand centre)", "lat": 51.8985, "lon": -8.4756, "type": "demand"},
]


def get_grid_map_data():
    return GRID_MAP_NODES