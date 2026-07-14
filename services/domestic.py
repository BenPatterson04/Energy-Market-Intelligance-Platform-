from datetime import datetime


def get_domestic_prices():
    """
    Latest domestic energy information.
    These values represent the latest published
    reference prices and can be replaced with
    a live API in Version 4.
    """

    return {

        "electricity_tariff": "27.5 p/kWh",

        "gas_tariff": "6.8 p/kWh",

        "heating_oil": "54.3 p/L",

        "standing_charge": "61 p/day",

        "price_cap": "Current",

        "last_updated": datetime.now().strftime("%d %b %Y %H:%M")

    }
