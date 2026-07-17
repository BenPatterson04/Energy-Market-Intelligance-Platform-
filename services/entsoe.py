"""
GridWise Version 4 - ENTSO-E Transparency Platform Integration
=================================================================

Replaces the earlier EirGrid "Smart Grid Dashboard" integration, which used
an undocumented, unofficial endpoint (DashboardService.svc) that turned out
to be unreliable / possibly retired (persistent 503s even with correct
headers). ENTSO-E's Transparency Platform is the EU's official, documented,
versioned electricity market data API - this is a much more durable
foundation to build on.

Setup required:
1. Register for a free account at https://transparency.entsoe.eu
2. Get a "Web API Security Token" from My Account Settings (may require
   emailing transparency@entsoe.eu to request API access first - this has
   historically not been fully self-service).
3. Add it to your .env file:
       ENTSOE_API_KEY=your-token-here
   Never put the token directly in this file or any other source file -
   it must only ever live in .env, which should be in your .gitignore.

What this does and doesn't cover:
- System demand (load) and wind generation: solidly available, this is
  ENTSO-E's core data.
- Day-ahead price: available, but this is NOT the same thing as the i-SEM
  imbalance settlement price (that's a SEM-O product, not published via
  ENTSO-E the same way) - labelled accordingly rather than mislabelled.
- System frequency: not published by ENTSO-E at all. Grid-operator-only
  real-time metric. Shown as unavailable.
- Carbon intensity: ENTSO-E gives generation-by-fuel-type, not a computed
  gCO2/kWh figure directly. Shown as unavailable for now rather than
  guessed at - a fuel-mix-based estimate is a reasonable future addition
  if wanted, but it's a separate, more involved piece of work.

i-SEM trades Ireland and Northern Ireland as a single unified bidding zone
(since 2018), so "ALL" is the accurate, reliable region. ROI/NI splits are
attempted via separate control-area codes but may return less complete
data since the market itself doesn't split at that level.
"""

import os
import re
import requests
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET

from services import history

API_KEY = os.getenv("ENTSOE_API_KEY")
BASE_URL = "https://web-api.tp.entsoe.eu/api"

# EIC codes for the i-SEM market. IE_SEM is the all-island bidding zone -
# use this as the default/primary region. IE and NIE are the separate
# EirGrid / SONI control areas, kept for the ROI / NI tab attempts.
DOMAINS = {
    "ALL": "10Y1001A1001A59C",  # Ireland (SEM) BZ / MBA - all-island
    "ROI": "10YIE-1001A00010",  # Ireland, EirGrid CA
    "NI": "10Y1001A1001A016",   # Northern Ireland, SONI CA
}

# Wind generation PSR (Production/Sourcing Resource) type codes.
PSR_WIND_ONSHORE = "B19"
PSR_WIND_OFFSHORE = "B18"


def _strip_ns(tag):
    """ElementTree keeps XML namespaces glued to tag names - strip them
    so we can navigate the tree by plain local names regardless of which
    document schema (load / generation / price) we're parsing."""
    return tag.split("}")[-1] if "}" in tag else tag


def _local_findall(element, path):
    """Namespace-agnostic version of element.findall() for simple paths
    like 'TimeSeries/Period/Point'."""
    current = [element]
    for part in path.split("/"):
        next_level = []
        for el in current:
            for child in el:
                if _strip_ns(child.tag) == part:
                    next_level.append(child)
        current = next_level
    return current


def _local_find(element, tag):
    for child in element:
        if _strip_ns(child.tag) == tag:
            return child
    return None


def _parse_resolution_minutes(resolution_text):
    """'PT30M' -> 30, 'PT60M' -> 60, 'PT15M' -> 15, 'PT1H' -> 60"""
    match = re.match(r"PT(\d+)([MH])", resolution_text)
    if not match:
        return 60
    value, unit = int(match.group(1)), match.group(2)
    return value * 60 if unit == "H" else value


def _fetch_entsoe(params, timeout=15):
    """Low-level GET against the ENTSO-E API. Returns parsed XML root,
    or raises - caller is expected to handle failure and fall back."""

    if not API_KEY:
        raise RuntimeError("ENTSOE_API_KEY is not set in the environment")

    full_params = dict(params)
    full_params["securityToken"] = API_KEY

    response = requests.get(BASE_URL, params=full_params, timeout=timeout)
    response.raise_for_status()

    root = ET.fromstring(response.text)

    # ENTSO-E returns HTTP 200 even for "no data" / error responses -
    # the actual error is inside an Acknowledgement_MarketDocument.
    if _strip_ns(root.tag) == "Acknowledgement_MarketDocument":
        reason = _local_find(root, "Reason")
        text = _local_find(reason, "text").text if reason is not None else "unknown reason"
        raise ValueError(f"ENTSO-E returned no data: {text}")

    return root


def _extract_series(root, value_tag="quantity"):
    """
    Walk a GL_MarketDocument-style response (used by load, generation, and
    price documents alike) and return a flat list of {"time": datetime,
    "value": float} points, newest last.
    """

    points = []

    for timeseries in _local_findall(root, "TimeSeries"):
        for period in _local_findall(timeseries, "Period"):

            time_interval = _local_find(period, "timeInterval")
            start_text = _local_find(time_interval, "start").text
            start_time = datetime.strptime(start_text, "%Y-%m-%dT%H:%MZ")

            resolution_text = _local_find(period, "resolution").text
            resolution_minutes = _parse_resolution_minutes(resolution_text)

            for point in _local_findall(period, "Point"):
                position = int(_local_find(point, "position").text)
                value_el = _local_find(point, value_tag)

                if value_el is None:
                    continue

                timestamp = start_time + timedelta(minutes=(position - 1) * resolution_minutes)
                points.append({"time": timestamp, "value": float(value_el.text)})

    points.sort(key=lambda p: p["time"])
    return points


def get_load_series(region="ALL", hours=24):
    """System demand (MW) for the trailing `hours` hours."""

    now = datetime.utcnow()
    period_start = (now - timedelta(hours=hours)).strftime("%Y%m%d%H%M")
    period_end = now.strftime("%Y%m%d%H%M")

    root = _fetch_entsoe({
        "documentType": "A65",
        "processType": "A16",  # Realised
        "outBiddingZone_Domain": DOMAINS[region],
        "periodStart": period_start,
        "periodEnd": period_end,
    })

    return _extract_series(root)


def get_wind_series(region="ALL", hours=24):
    """Combined onshore + offshore wind generation (MW) for the trailing
    `hours` hours. Returns a merged, time-summed series."""

    now = datetime.utcnow()
    period_start = (now - timedelta(hours=hours)).strftime("%Y%m%d%H%M")
    period_end = now.strftime("%Y%m%d%H%M")

    combined = {}

    for psr_type in (PSR_WIND_ONSHORE, PSR_WIND_OFFSHORE):
        try:
            root = _fetch_entsoe({
                "documentType": "A75",
                "processType": "A16",
                "in_Domain": DOMAINS[region],
                "periodStart": period_start,
                "periodEnd": period_end,
                "psrType": psr_type,
            })
        except Exception:
            continue  # offshore wind especially may not exist for this zone

        for point in _extract_series(root):
            combined[point["time"]] = combined.get(point["time"], 0) + point["value"]

    return [{"time": t, "value": v} for t, v in sorted(combined.items())]


def get_day_ahead_price_series(region="ALL", hours=24):
    """Day-ahead price (EUR/MWh) - NOT the i-SEM imbalance settlement
    price. May return empty for IE_SEM since SEM-O runs its own auction
    outside the standard ENTSO-E day-ahead coupling in some periods."""

    now = datetime.utcnow()
    period_start = (now - timedelta(hours=hours)).strftime("%Y%m%d%H%M")
    period_end = now.strftime("%Y%m%d%H%M")

    root = _fetch_entsoe({
        "documentType": "A44",
        "in_Domain": DOMAINS[region],
        "out_Domain": DOMAINS[region],
        "periodStart": period_start,
        "periodEnd": period_end,
    })

    return _extract_series(root, value_tag="price.amount")


def get_isem_snapshot(region="ALL"):
    """
    Latest reading across tracked metrics for a region, plus a 'source'
    flag so the UI can show whether this is live or cached data.

    frequency_hz and co2_intensity are intentionally always None - ENTSO-E
    doesn't publish either. Kept as keys so templates/JS that reference
    them don't break; they'll just render as unavailable.
    """

    result = {
        "region": region,
        "demand_mw": None,
        "wind_mw": None,
        "wind_percent": None,
        "co2_intensity": None,      # not available via ENTSO-E
        "system_price_eur": None,   # day-ahead price, not imbalance price
        "frequency_hz": None,       # not available via ENTSO-E
        "source": "live",
        "last_updated": datetime.utcnow().strftime("%d %b %Y %H:%M UTC"),
    }

    try:
        demand_series = get_load_series(region, hours=6)
        wind_series = get_wind_series(region, hours=6)

        demand = demand_series[-1]["value"] if demand_series else None
        wind = wind_series[-1]["value"] if wind_series else None

        result["demand_mw"] = demand
        result["wind_mw"] = wind
        result["wind_percent"] = round((wind / demand) * 100, 1) if demand and wind else None

        try:
            price_series = get_day_ahead_price_series(region, hours=6)
            result["system_price_eur"] = price_series[-1]["value"] if price_series else None
        except Exception as e:
            print("ENTSO-E day-ahead price unavailable:", e)

        if demand is None and wind is None:
            raise ValueError("ENTSO-E returned no usable demand/wind data")

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

        print("ENTSO-E fetch error:", e)

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
    """Shaped for Plotly: parallel arrays the frontend drops straight into
    a `data` trace without reformatting in JS. Reads from our own SQLite
    history (populated over time by get_isem_snapshot), not live from
    ENTSO-E on every chart load - keeps this fast and rate-limit-friendly."""

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