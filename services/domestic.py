from datetime import datetime

from services import octopus


def get_domestic_prices(postcode=None):
    """
    UK domestic tariffs - now genuinely live via Octopus Energy's public
    API (see services/octopus.py), replacing the old hardcoded Ofgem
    price cap figures. Octopus's default tariff tracks the Ofgem cap
    closely (required to, by regulation) but is exposed through a real,
    stable, documented, no-auth-needed API - so this now updates
    automatically rather than needing a manual edit every quarter.

    Heating oil has been removed entirely rather than faked - there is no
    free, authoritative, live source for it. If you want it back, it
    would need a paid data provider; better to not show a number than
    show a stale/approximate one presented as current.

    postcode: optional - if provided, looks up the correct regional
    tariff rate. Defaults to the London (C) region if not given.
    """

    region_letter = octopus.get_region_letter_for_postcode(postcode) if postcode else "C"
    live = octopus.get_live_tariff_rates(region_letter=region_letter)

    return {
        "electricity_tariff": live["electricity_unit_rate"] or "unavailable",
        "gas_tariff": live["gas_unit_rate"] or "unavailable",
        "standing_charge": _combine_standing_charges(live),
        "product_name": live["product_name"] or "Octopus Energy (live)",
        "source": live["source"],
        "source_note": (
            f"Live rates from {live['product_name'] or 'Octopus Energy'}'s public API "
            "(api.octopus.energy), which tracks the Ofgem price cap. Region: "
            f"{region_letter}. This updates automatically - no manual edits needed."
        ) if live["source"] == "live" else (
            "Live tariff data is temporarily unavailable - Octopus Energy's API "
            "did not respond. Try refreshing shortly."
        ),
        "last_updated": live["last_updated"],
    }


def _combine_standing_charges(live):
    elec = live.get("electricity_standing_charge")
    gas = live.get("gas_standing_charge")

    try:
        elec_val = float(elec.split(" ")[0]) if elec else 0
        gas_val = float(gas.split(" ")[0]) if gas else 0
        if elec_val or gas_val:
            return f"{elec_val + gas_val:.2f} p/day"
    except (ValueError, AttributeError):
        pass

    return "unavailable"
