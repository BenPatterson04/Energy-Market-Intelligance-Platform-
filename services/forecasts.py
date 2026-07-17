"""
GridWise Version 4 - Forecasts (simple trend projection)
============================================================

This is intentionally NOT a certified load/price forecast - building a
real one requires proper time-series modelling (weather-adjusted demand
models, historical seasonal patterns, etc.), which is a substantial
separate project on its own.

What this does instead, honestly: takes the last few hours of recorded
i-SEM demand/wind from our own SQLite history and extrapolates a simple
linear trend forward a few hours. Useful as a "which way is this
heading" indicator, not as a number anyone should trade or plan around -
the template labels it that way explicitly, and this docstring is the
reminder to keep it labelled that way if this file gets extended later.
"""

from datetime import timedelta
from services import history


def _linear_trend_projection(points, hours_ahead=6, step_minutes=30):
    """
    points: list of {"recorded_at": iso string, "value": number}
    Returns projected points using simple linear regression on the
    available history. Needs at least 2 points to project anything.
    """

    if len(points) < 2:
        return []

    # x = minutes elapsed since first point, y = value
    xs = []
    ys = []
    base_time = points[0]["time"]

    for p in points:
        if p["value"] is None:
            continue
        xs.append((p["time"] - base_time).total_seconds() / 60)
        ys.append(p["value"])

    if len(xs) < 2:
        return []

    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n

    numerator = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
    denominator = sum((xs[i] - mean_x) ** 2 for i in range(n))

    slope = numerator / denominator if denominator else 0
    intercept = mean_y - slope * mean_x

    last_time = points[-1]["time"]
    last_x = xs[-1]

    projected = []
    steps = int((hours_ahead * 60) / step_minutes)

    for i in range(1, steps + 1):
        future_x = last_x + (i * step_minutes)
        future_time = last_time + timedelta(minutes=i * step_minutes)
        projected.append({
            "time": future_time,
            "value": round(intercept + slope * future_x, 1),
        })

    return projected


def get_demand_wind_projection(region="ALL", history_hours=6, forecast_hours=6):
    """
    Returns actual recent history plus a simple forward projection for
    both demand and wind, shaped for a single combined Plotly chart.
    """

    rows = history.get_isem_history(region=region, hours=history_hours)

    from datetime import datetime

    demand_points = []
    wind_points = []

    for r in rows:
        t = datetime.fromisoformat(r["recorded_at"])
        if r["demand_mw"] is not None:
            demand_points.append({"time": t, "value": r["demand_mw"]})
        if r["wind_mw"] is not None:
            wind_points.append({"time": t, "value": r["wind_mw"]})

    demand_projection = _linear_trend_projection(demand_points, hours_ahead=forecast_hours)
    wind_projection = _linear_trend_projection(wind_points, hours_ahead=forecast_hours)

    def fmt(points):
        return {
            "timestamps": [p["time"].strftime("%Y-%m-%dT%H:%M") for p in points],
            "values": [p["value"] for p in points],
        }

    return {
        "demand_actual": fmt(demand_points),
        "demand_projected": fmt(demand_projection),
        "wind_actual": fmt(wind_points),
        "wind_projected": fmt(wind_projection),
        "has_enough_data": len(demand_points) >= 2,
    }
