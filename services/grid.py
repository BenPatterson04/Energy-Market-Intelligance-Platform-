import requests

INTENSITY_URL = "https://api.carbonintensity.org.uk/intensity"
GENERATION_URL = "https://api.carbonintensity.org.uk/generation"


def get_grid_status():

    try:

        intensity_response = requests.get(INTENSITY_URL, timeout=10)
        generation_response = requests.get(GENERATION_URL, timeout=10)

        intensity_response.raise_for_status()
        generation_response.raise_for_status()

        intensity_data = intensity_response.json()["data"][0]
        generation_data = generation_response.json()["data"]["generationmix"]

        generation_data = sorted(
            generation_data,
            key=lambda x: x["perc"],
            reverse=True
        )

        return {

            "status": "LIVE",

            "carbon": f'{intensity_data["intensity"]["actual"]} gCO₂/kWh',

            "index": intensity_data["intensity"]["index"].title(),

            "fuel_1": generation_data[0]["fuel"].replace("-", " ").title(),
            "fuel_1_percent": f'{generation_data[0]["perc"]:.1f}%',

            "fuel_2": generation_data[1]["fuel"].replace("-", " ").title(),
            "fuel_2_percent": f'{generation_data[1]["perc"]:.1f}%',

            "fuel_3": generation_data[2]["fuel"].replace("-", " ").title(),
            "fuel_3_percent": f'{generation_data[2]["perc"]:.1f}%',

        }

    except Exception as e:

        print("Grid API Error:", e)

        return {

            "status": "Unavailable",

            "carbon": "--",

            "index": "--",

            "fuel_1": "--",
            "fuel_1_percent": "--",

            "fuel_2": "--",
            "fuel_2_percent": "--",

            "fuel_3": "--",
            "fuel_3_percent": "--",

        }