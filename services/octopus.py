"""
GridWise Version 4 - Octopus Energy Integration
====================================================

Replaces the static Ofgem price cap figures with genuinely live data from
Octopus Energy's public REST API (api.octopus.energy/v1/) - this is a
real, stable, well-documented API, not a reverse-engineered endpoint like
the EirGrid one that broke on us earlier. Product/tariff-rate endpoints
require NO authentication or API key at all.

Why this instead of Ofgem directly: Ofgem only publishes the price cap as
quarterly PDF/spreadsheet reports, with no API - there's no way to make
that genuinely live without scraping fragile documents. Octopus republish
their own tariffs in near-lockstep with the Ofgem cap (their default
tariffs are required to track it), but expose it through a real API - so
this gets you live-updating numbers that closely track the real cap,
sourced from a stable, documented, no-key-needed endpoint.

Bonus feature this unlocks that a static number never could: Octopus's
Agile tariff publishes real half-hourly electricity prices tied to actual
wholesale prices, released daily around 4pm for the following day. This
lets GridWise show genuinely live "cheapest/most expensive time to use
electricity today" data - useful demand-shifting information, and
something no static quarterly figure could ever provide.

IMPORTANT - product codes are versioned and change periodically (e.g.
"AGILE-24-10-01" gets superseded by a new dated code every so often).
This code does NOT hardcode a product code - it always asks the /products/
endpoint for what's currently live and picks the newest matching one, so
it keeps working after Octopus rolls out a new version, without needing
a code update each time.
"""

import requests
from datetime import datetime, timedelta

BASE_URL = "https://api.octopus.energy/v1"


def _get_current_product(product_family_keyword):
    """
    Finds the currently-active product whose display name contains
    product_family_keyword (e.g. "Agile", "Flexible") - picks the most
    recently made-available one, since Octopus runs several versions at
    once during rollover periods.
    """

    response = requests.get(f"{BASE_URL}/products/", params={"is_variable": "true"}, timeout=10)
    response.raise_for_status()
    products = response.json().get("results", [])

    matches = [
        p for p in products
        if product_family_keyword.lower() in p.get("display_name", "").lower()
    ]

    if not matches:
        return None

    matches.sort(key=lambda p: p.get("available_from") or "", reverse=True)
    return matches[0]


def _get_tariff_code(product_code, fuel="electricity", region_letter="C"):
    """
    region_letter: one of the 14 GB regional letters (A-P, skipping some) -
    defaults to "C" (London) as a reasonable general reference point.
    Use get_region_letter_for_postcode() for a real user's actual region.
    """

    if fuel == "electricity":
        return f"E-1R-{product_code}-{region_letter}"
    return f"G-1R-{product_code}-{region_letter}"


def get_region_letter_for_postcode(postcode):
    """Looks up the correct regional tariff letter for a real postcode -
    use this instead of the default 'C' when you know the user's area."""

    try:
        response = requests.get(
            f"{BASE_URL}/industry/grid-supply-points/",
            params={"postcode": postcode},
            timeout=10,
        )
        response.raise_for_status()
        results = response.json().get("results", [])
        return results[0]["group_id"].replace("_", "") if results else "C"
    except Exception as e:
        print("Octopus GSP lookup error:", e)
        return "C"


def get_live_tariff_rates(region_letter="C"):
    """
    Live standing charge + unit rate for Octopus's current standard
    variable-style tariff (their default, price-cap-tracking product) -
    this is the direct live replacement for the old hardcoded Ofgem figures.

    Returns {"electricity_unit_rate": "26.1p/kWh", "electricity_standing_charge": "...",
             "gas_unit_rate": "...", "gas_standing_charge": "...",
             "product_name": "...", "source": "live"} or a dict with
    source="unavailable" if the API call fails - never fabricates a number.
    """

    result = {
        "electricity_unit_rate": None,
        "electricity_standing_charge": None,
        "gas_unit_rate": None,
        "gas_standing_charge": None,
        "product_name": None,
        "source": "live",
        "last_updated": datetime.utcnow().strftime("%d %b %Y %H:%M UTC"),
    }

    try:
        elec_product = _get_current_product("Flexible")

        if elec_product:
            code = elec_product["code"]
            tariff_code = _get_tariff_code(code, "electricity", region_letter)

            unit_resp = requests.get(
                f"{BASE_URL}/products/{code}/electricity-tariffs/{tariff_code}/standard-unit-rates/",
                timeout=10,
            )
            unit_resp.raise_for_status()
            unit_data = unit_resp.json().get("results", [])

            standing_resp = requests.get(
                f"{BASE_URL}/products/{code}/electricity-tariffs/{tariff_code}/standing-charges/",
                timeout=10,
            )
            standing_resp.raise_for_status()
            standing_data = standing_resp.json().get("results", [])

            if unit_data:
                result["electricity_unit_rate"] = f"{unit_data[0]['value_inc_vat']:.2f} p/kWh"
            if standing_data:
                result["electricity_standing_charge"] = f"{standing_data[0]['value_inc_vat']:.2f} p/day"

            result["product_name"] = elec_product.get("display_name")

        gas_product = _get_current_product("Flexible")

        if gas_product:
            code = gas_product["code"]
            tariff_code = _get_tariff_code(code, "gas", region_letter)

            unit_resp = requests.get(
                f"{BASE_URL}/products/{code}/gas-tariffs/{tariff_code}/standard-unit-rates/",
                timeout=10,
            )
            unit_resp.raise_for_status()
            unit_data = unit_resp.json().get("results", [])

            standing_resp = requests.get(
                f"{BASE_URL}/products/{code}/gas-tariffs/{tariff_code}/standing-charges/",
                timeout=10,
            )
            standing_resp.raise_for_status()
            standing_data = standing_resp.json().get("results", [])

            if unit_data:
                result["gas_unit_rate"] = f"{unit_data[0]['value_inc_vat']:.2f} p/kWh"
            if standing_data:
                result["gas_standing_charge"] = f"{standing_data[0]['value_inc_vat']:.2f} p/day"

        if not any([result["electricity_unit_rate"], result["gas_unit_rate"]]):
            raise ValueError("Octopus API returned no usable tariff data")

    except Exception as e:
        print("Octopus tariff fetch error:", e)
        result["source"] = "unavailable"

    return result


def get_agile_rates_today(region_letter="C"):
    """
    Half-hourly Agile Octopus electricity prices for today - genuinely
    live, dynamic data a static tariff figure could never provide. Returns
    a list of {"time": "HH:MM", "price_pence": float}, cheapest-aware so
    the frontend can highlight the best/worst times to use electricity.
    """

    try:
        product = _get_current_product("Agile")

        if not product:
            return []

        code = product["code"]
        tariff_code = _get_tariff_code(code, "electricity", region_letter)

        now = datetime.utcnow()
        period_from = now.replace(hour=0, minute=0, second=0, microsecond=0)
        period_to = period_from + timedelta(days=1)

        response = requests.get(
            f"{BASE_URL}/products/{code}/electricity-tariffs/{tariff_code}/standard-unit-rates/",
            params={
                "period_from": period_from.strftime("%Y-%m-%dT%H:%MZ"),
                "period_to": period_to.strftime("%Y-%m-%dT%H:%MZ"),
            },
            timeout=10,
        )
        response.raise_for_status()
        results = response.json().get("results", [])

        rates = [
            {
                "time": datetime.fromisoformat(r["valid_from"].replace("Z", "+00:00")).strftime("%H:%M"),
                "price_pence": r["value_inc_vat"],
            }
            for r in results
        ]

        rates.sort(key=lambda r: r["time"])
        return rates

    except Exception as e:
        print("Octopus Agile rates error:", e)
        return []
