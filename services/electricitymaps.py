"""
GridWise Version 4 - Electricity Maps Integration
=====================================================

Replaces the ENTSO-E integration as the primary live data source, since
ENTSO-E's API access requires manual approval (email + ~3 working day
wait) that didn't come through. Electricity Maps' free tier is instant,
self-serve signup - no approval step.

Setup required:
1. Sign up at https://www.electricitymaps.com/free-tier-api (the FREE
   TIER signup specifically, not the "request a trial" option - those are
   different things with different approval processes).
2. During signup you choose ONE zone - this matters a lot, see below.
3. Get your API key from the Electricity Maps dashboard/API portal.
4. Add it to your .env file:
       ELECTRICITYMAPS_API_KEY=your-token-here
       ELECTRICITYMAPS_ZONE=IE
   Never put the token directly in this file - .env only.

IMPORTANT LIMITATION - read this before assuming both ROI and NI will work:
The free tier is locked to a SINGLE zone, chosen at signup. Ireland (IE)
and Northern Ireland (GB-NIR) are separate zones in Electricity Maps'
system, even though they trade as one i-SEM market. Your key only returns
data for whichever zone you picked - requests for the other zone will
fail (403/no data), and this code falls back to cached history when that
happens, same as any other failure. Set ELECTRICITYMAPS_ZONE in .env to
whichever zone your account is actually scoped to.

What this covers vs ENTSO-E:
- Demand (MW): YES - via powerConsumptionTotal on the power-breakdown
  endpoint. This is a genuine improvement over what I said earlier.
- Wind generation (MW): YES - via the power breakdown by source.
- Carbon intensity (gCO2/kWh): YES - this is Electricity Maps' core
  product, more reliable here than anywhere else we've tried.
- Day-ahead / imbalance price: NO - not part of this free tier.
- System frequency: NO - not published by this API.
"""

import os
import requests
from datetime import datetime

from services import history

API_KEY = os.getenv("ELECTRICITYMAPS_API_KEY")
DEFAULT_ZONE = os.getenv("ELECTRICITYMAPS_ZONE", "IE")

BASE_URL = "https://api-access.electricitymaps.com/free-tier"

# Region -> Electricity Maps zone. "ALL" and "ROI" both map to IE since
# there's no combined all-island zone in their system - this is an
# approximation of i-SEM, not a true combined figure. Only the zone your
# key is actually scoped to (see DEFAULT_ZONE above) will return real data.
ZONES = {
    "ALL": DEFAULT_ZONE,
    "ROI": "IE",
    "NI": "GB-NIR",
}


def _headers():
    if not API_KEY:
        raise RuntimeError("ELECTRICITYMAPS_API_KEY is not set in the environment")
    return {"auth-token": API_KEY}


def get_carbon_intensity(zone):
    response = requests.get(
        f"{BASE_URL}/carbon-intensity/latest",
        params={"zone": zone},
        headers=_headers(),
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def get_power_breakdown(zone):
    response = requests.get(
        f"{BASE_URL}/power-breakdown/latest",
        params={"zone": zone},
        headers=_headers(),
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def get_isem_snapshot(region="ALL"):
    """
    Latest reading across tracked metrics for a region, plus a 'source'
    flag so the UI can show whether this is live or cached data.

    system_price_eur and frequency_hz are intentionally always None -
    neither is published by this API. Kept as keys so templates/JS that
    reference them don't break; they'll just render as unavailable.
    """

    zone = ZONES.get(region, DEFAULT_ZONE)

    result = {
        "region": region,
        "demand_mw": None,
        "wind_mw": None,
        "wind_percent": None,
        "co2_intensity": None,
        "system_price_eur": None,   # not available via this API
        "frequency_hz": None,       # not available via this API
        "source": "live",
        "last_updated": datetime.utcnow().strftime("%d %b %Y %H:%M UTC"),
    }

    try:
        carbon_data = get_carbon_intensity(zone)
        breakdown_data = get_power_breakdown(zone)

        result["co2_intensity"] = carbon_data.get("carbonIntensity")

        total_demand = breakdown_data.get("powerConsumptionTotal")
        wind_mw = (breakdown_data.get("powerConsumptionBreakdown") or {}).get("wind")

        result["demand_mw"] = total_demand
        result["wind_mw"] = wind_mw
        result["wind_percent"] = (
            round((wind_mw / total_demand) * 100, 1)
            if total_demand and wind_mw else None
        )

        if result["demand_mw"] is None and result["co2_intensity"] is None:
            raise ValueError("Electricity Maps returned no usable data for this zone")

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

        print("Electricity Maps fetch error:", e)

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
    """Shaped for Plotly - reads from our own SQLite history (populated
    over time by get_isem_snapshot), not live on every chart load."""

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
