"""
GridWise Version 4 - AI Market Commentary
============================================

Turns the numbers already on the dashboard (markets, grid, i-SEM, news
headlines, domestic tariffs) into a short daily-briefing paragraph,
written specifically for the account type it's for: business/professional,
student, or domestic/household. Each gets genuinely different content, not
just a different tone on the same paragraph - business gets exact
i-SEM figures and market terminology, students get an explainer with the
"why", and domestic gets what it means for their actual bill using the
real Ofgem tariff figures. All three are generated from the same data
pull so they never contradict each other.

Requires ANTHROPIC_API_KEY in the environment. If it's missing or the
call fails, we fall back to a simple templated summary so the dashboard
still has something useful in that slot rather than an error - the
fallback is also written per-audience, not a single generic sentence.
"""

import os
import json
from datetime import datetime

try:
    import anthropic
    _client = anthropic.Anthropic() if os.getenv("ANTHROPIC_API_KEY") else None
except ImportError:
    _client = None

MODEL = "claude-sonnet-5"

VALID_AUDIENCES = ("business", "student", "domestic")


def _build_prompt(context, audience):

    audience_instructions = {
        "business": (
            "Write for energy-sector professionals (traders, analysts, grid "
            "operators). Use correct market terminology (i-SEM, SEM-O, "
            "imbalance price, SNSP, curtailment, etc.) freely. Be specific "
            "about the numbers and what's driving them - this reader wants "
            "signal, not explanation of basics."
        ),
        "student": (
            "Write for a student learning about energy markets for the "
            "first time. Explain the 'why' behind the numbers, not just "
            "what they are - e.g. why wind share matters for carbon "
            "intensity, why oil prices ripple into electricity prices. "
            "Avoid jargon, or define it in-line the first time it's used."
        ),
        "domestic": (
            "Write for a household managing their own energy bills, with "
            "no market background. Focus specifically on what today's "
            "numbers mean for their actual bill - use the real tariff "
            "rates provided if you have them, and give one practical, "
            "concrete takeaway (e.g. a good/bad day to run high-usage "
            "appliances) if the data supports it. Skip anything that isn't "
            "actionable for a household."
        ),
    }

    return f"""You are GridWise's daily energy briefing writer.

Today's data pull ({context['timestamp']}):
{json.dumps(context['data'], indent=2)}

{audience_instructions[audience]}

Write a single briefing of 90-130 words. No headers, no bullet points, no
markdown - plain prose only, like a short morning note. Do not invent any
figures that aren't in the data above; if something is unavailable, just
don't mention it."""


def _fallback_commentary(context, audience):
    data = context["data"]

    if audience == "domestic":
        bits = []
        if data.get("electricity_tariff"):
            bits.append(f"your electricity rate is {data['electricity_tariff']}")
        if data.get("gas_tariff"):
            bits.append(f"gas is {data['gas_tariff']}")
        if data.get("carbon_intensity") not in (None, "--"):
            bits.append(f"grid carbon intensity is {data['carbon_intensity']}")
        if not bits:
            return "Live briefing is temporarily unavailable - check back shortly."
        return "Today's household snapshot: " + ", ".join(bits) + "."

    bits = []
    if data.get("brent_price") not in (None, "--"):
        bits.append(f"Brent crude is trading at ${data['brent_price']}")
    if data.get("isem_demand_mw") not in (None, "--"):
        bits.append(f"all-island electricity demand is around {data['isem_demand_mw']:.0f} MW")
    if data.get("isem_wind_percent") not in (None, "--"):
        bits.append(f"wind is meeting roughly {data['isem_wind_percent']:.0f}% of that demand")
    if data.get("carbon_intensity") not in (None, "--"):
        bits.append(f"grid carbon intensity is {data['carbon_intensity']}")

    if not bits:
        return "Live briefing is temporarily unavailable - check back shortly."

    return "Today's snapshot: " + ", ".join(bits) + "."


def generate_commentary(markets, isem, grid, news, audience="domestic", domestic=None):
    """
    audience: "business", "student", or "domestic" - must match a real
    account_type so the briefing is genuinely tailored, not just relabelled.
    domestic: optional dict from services.domestic.get_domestic_prices(),
    only used (and only useful) for the "domestic" audience.
    Returns plain text commentary.
    """

    if audience not in VALID_AUDIENCES:
        audience = "domestic"

    context = {
        "timestamp": datetime.utcnow().strftime("%d %b %Y %H:%M UTC"),
        "data": {
            "brent_price": markets.get("brent", {}).get("price"),
            "natural_gas_price": markets.get("natural_gas", {}).get("price"),
            "gbp_usd": markets.get("gbpusd", {}).get("price"),
            "isem_demand_mw": isem.get("demand_mw"),
            "isem_wind_percent": isem.get("wind_percent"),
            "isem_system_price_eur": isem.get("system_price_eur"),
            "carbon_intensity": grid.get("carbon"),
            "top_generation_source": grid.get("fuel_1"),
            "headline_uk_news": [a["title"] for a in (news.get("uk") or [])[:3]],
            "headline_global_news": [a["title"] for a in (news.get("global") or [])[:3]],
        },
    }

    if audience == "domestic" and domestic:
        context["data"]["electricity_tariff"] = domestic.get("electricity_tariff")
        context["data"]["gas_tariff"] = domestic.get("gas_tariff")
        context["data"]["standing_charge"] = domestic.get("standing_charge")

    if _client is None:
        return _fallback_commentary(context, audience)

    try:
        response = _client.messages.create(
            model=MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": _build_prompt(context, audience)}],
        )

        text_blocks = [b.text for b in response.content if b.type == "text"]
        return "".join(text_blocks).strip()

    except Exception as e:
        print("AI commentary error:", e)
        return _fallback_commentary(context, audience)
